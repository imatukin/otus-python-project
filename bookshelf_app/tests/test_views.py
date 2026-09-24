"""Тесты представлений каталога книг."""

import datetime

import pytest
from django.urls import reverse

from bookshelf_app.models import Author, Book, ReadingEntry, ReadingStatus
from bookshelf_app.views import SEARCH_LIMIT


def messages_of(response):
    """Тексты сообщений на странице (ответ получен с follow=True)."""
    return [str(message) for message in response.context["messages"]]


class TestIndexView:
    """Главная страница."""

    @pytest.mark.django_db
    def test_status_and_template(self, client):
        response = client.get(reverse("index"))
        assert response.status_code == 200
        assert "bookshelf_app/index.html" in [t.name for t in response.templates]

    @pytest.mark.django_db
    def test_guest_has_no_diary(self, client):
        response = client.get(reverse("index"))
        assert "columns" not in response.context
        assert "diary_total" not in response.context

    @pytest.mark.django_db
    def test_reader_columns(self, auth_client, entries):
        response = auth_client.get(reverse("index"))
        columns = response.context["columns"]
        assert [column.status for column in columns] == [
            ReadingStatus.READING,
            ReadingStatus.PLANNED,
            ReadingStatus.READ,
            ReadingStatus.ABANDONED,
        ]
        assert response.context["diary_total"] == len(entries)

    @pytest.mark.django_db
    def test_only_own_entries(self, auth_client_2, entries):  # pylint: disable=unused-argument
        response = auth_client_2.get(reverse("index"))
        assert response.context["diary_total"] == 0


class TestAboutView:
    """Страница «О сайте»."""

    def test_status_and_template(self, client):
        response = client.get(reverse("about"))
        assert response.status_code == 200
        assert "bookshelf_app/about.html" in [t.name for t in response.templates]

    def test_breadcrumbs(self, client):
        response = client.get(reverse("about"))
        titles = [crumb["title"] for crumb in response.context["breadcrumbs"]]
        assert titles == ["Главная", "О сайте"]


class TestBookListView:
    """Список всех книг."""

    @pytest.mark.django_db
    def test_status_and_template(self, client):
        response = client.get(reverse("books"))
        assert response.status_code == 200
        assert "bookshelf_app/books.html" in [t.name for t in response.templates]

    @pytest.mark.django_db
    def test_empty_list(self, client):
        response = client.get(reverse("books"))
        assert not list(response.context["books"])

    @pytest.mark.django_db
    # book_of_user_2 нужен как данные в базе, обращаться к нему в тесте не требуется.
    def test_shows_all_books(self, client, books, book_of_user_2):  # pylint: disable=unused-argument
        response = client.get(reverse("books"))
        assert response.context["books"].count() == len(books) + 1

    @pytest.mark.django_db
    def test_book_title_in_content(self, client, book):
        response = client.get(reverse("books"))
        assert book.title in response.content.decode()

    @pytest.mark.django_db
    def test_no_status_actions_for_guest(self, client, book):  # pylint: disable=unused-argument
        [item] = client.get(reverse("books")).context["books"]
        assert not hasattr(item, "status_actions")

    @pytest.mark.django_db
    def test_status_actions_by_diary(self, auth_client, entries, book, book_of_user_2, books):  # pylint: disable=unused-argument
        response = auth_client.get(reverse("books"))
        items = {item.pk: item for item in response.context["books"]}
        assert items[book.pk].diary_status == ReadingStatus.READ
        assert [action.label for action in items[book.pk].status_actions] == ["Хочу прочитать", "Перечитать"]
        assert [action.status for action in items[book_of_user_2.pk].status_actions] == [
            ReadingStatus.READING, ReadingStatus.READ,
        ]
        assert items[books[0].pk].diary_status is None

    @pytest.mark.django_db
    def test_query_count_does_not_grow(self, auth_client, books, django_assert_max_num_queries):
        """Статус в дневнике берётся подзапросом, а не отдельным запросом на каждую книгу."""
        for item in books:
            ReadingEntry.objects.create(reader=item.added_by, book=item)
        # Сессия, пользователь, книги с подзапросом статуса, жанры.
        with django_assert_max_num_queries(4):
            auth_client.get(reverse("books"))


class TestBookDetailView:
    """Страница одной книги."""

    @pytest.mark.django_db
    def test_status_and_object(self, client, book):
        response = client.get(book.get_absolute_url())
        assert response.status_code == 200
        assert response.context["book"] == book
        assert response.context["page_title"] == book.title

    @pytest.mark.django_db
    def test_missing_book_returns_404(self, client):
        response = client.get(reverse("book_detail", args=[404]))
        assert response.status_code == 404

    @pytest.mark.django_db
    def test_reviews_in_context(self, client, book, reviews):
        response = client.get(book.get_absolute_url())
        assert list(response.context["reviews"]) == sorted(
            reviews, key=lambda review: review.created_at, reverse=True
        )

    @pytest.mark.django_db
    def test_breadcrumbs(self, client, book):
        response = client.get(book.get_absolute_url())
        titles = [crumb["title"] for crumb in response.context["breadcrumbs"]]
        assert titles == ["Главная", "Все книги", book.title]

    @pytest.mark.django_db
    def test_deleted_book_returns_404(self, client, book):
        book.delete()
        assert client.get(book.get_absolute_url()).status_code == 404

    @pytest.mark.django_db
    def test_deleted_reviews_hidden(self, client, book, reviews):
        reviews[0].delete()
        response = client.get(book.get_absolute_url())
        assert list(response.context["reviews"]) == [reviews[1]]

    @pytest.mark.parametrize(
        ("client_fixture", "expected"),
        [("client", False), ("auth_client", True), ("auth_client_2", False), ("admin_auth_client", True)],
    )
    @pytest.mark.django_db
    def test_can_delete(self, request, book, client_fixture, expected):
        client = request.getfixturevalue(client_fixture)
        assert client.get(book.get_absolute_url()).context["can_delete"] is expected

    @pytest.mark.django_db
    def test_guest_has_no_diary_block(self, client, book):
        context = client.get(book.get_absolute_url()).context
        assert "entry" not in context
        assert "status_actions" not in context

    @pytest.mark.django_db
    def test_book_not_in_diary(self, auth_client, book):
        context = auth_client.get(book.get_absolute_url()).context
        assert context["entry"] is None
        assert [action.status for action in context["status_actions"]] == [
            ReadingStatus.PLANNED, ReadingStatus.READING, ReadingStatus.READ,
        ]

    @pytest.mark.django_db
    def test_own_entry(self, auth_client, book, entry):
        context = auth_client.get(book.get_absolute_url()).context
        assert context["entry"] == entry
        assert [action.status for action in context["status_actions"]] == [
            ReadingStatus.READ, ReadingStatus.ABANDONED,
        ]

    @pytest.mark.django_db
    def test_other_readers_entry_not_shown(self, auth_client_2, book, entry):  # pylint: disable=unused-argument
        assert auth_client_2.get(book.get_absolute_url()).context["entry"] is None


class TestBookCreateView:
    """Добавление книги."""

    @pytest.mark.django_db
    def test_anonymous_redirected_to_login(self, client):
        url = reverse("book_add")
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == f"{reverse('login')}?next={url}"

    @pytest.mark.django_db
    def test_form_available_for_authorized(self, auth_client):
        response = auth_client.get(reverse("book_add"))
        assert response.status_code == 200
        assert response.context["submit_label"] == "Добавить книгу"

    @pytest.mark.django_db
    def test_book_created(self, auth_client, user_1, book_form_data):
        response = auth_client.post(reverse("book_add"), data=book_form_data)
        book = Book.objects.get(title=book_form_data["title"])
        assert response.status_code == 302
        assert response.url == book.get_absolute_url()
        assert book.added_by == user_1
        assert book.genres.count() == len(book_form_data["genres"])

    @pytest.mark.django_db
    def test_success_message(self, auth_client, book_form_data):
        response = auth_client.post(
            reverse("book_add"), data=book_form_data, follow=True
        )
        messages = [str(message) for message in response.context["messages"]]
        assert f"Книга «{book_form_data['title']}» добавлена в каталог." in messages

    @pytest.mark.django_db
    def test_invalid_form_does_not_create_book(self, auth_client, book_form_data):
        book_form_data["title"] = ""
        response = auth_client.post(reverse("book_add"), data=book_form_data)
        assert response.status_code == 200
        assert not Book.objects.exists()
        assert "Название книги не заполнено." in response.context["form"].errors["title"]

    @pytest.mark.django_db
    def test_duplicate_is_rejected(self, auth_client, book, book_form_data):
        book_form_data["title"] = book.title
        book_form_data["author"] = book.author.pk
        response = auth_client.post(reverse("book_add"), data=book_form_data)
        assert response.status_code == 200
        assert Book.objects.count() == 1


class TestBookUpdateView:
    """Редактирование книги."""

    @pytest.mark.django_db
    def test_anonymous_redirected_to_login(self, client, book):
        url = reverse("book_edit", args=[book.pk])
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == f"{reverse('login')}?next={url}"

    @pytest.mark.django_db
    def test_form_prefilled(self, auth_client, book):
        response = auth_client.get(reverse("book_edit", args=[book.pk]))
        assert response.status_code == 200
        assert response.context["form"].instance == book
        assert response.context["page_title"] == f"Редактирование: {book.title}"

    @pytest.mark.django_db
    def test_book_updated(self, auth_client, book, book_form_data):
        book_form_data["title"] = "Новое название"
        book_form_data["author"] = book.author.pk
        response = auth_client.post(
            reverse("book_edit", args=[book.pk]), data=book_form_data
        )
        book.refresh_from_db()
        assert response.status_code == 302
        assert book.title == "Новое название"

    @pytest.mark.django_db
    def test_own_title_is_not_a_duplicate(self, auth_client, book, book_form_data):
        """Сохранение книги без смены названия не считается повтором."""
        book_form_data["title"] = book.title
        book_form_data["author"] = book.author.pk
        response = auth_client.post(
            reverse("book_edit", args=[book.pk]), data=book_form_data
        )
        assert response.status_code == 302

    @pytest.mark.django_db
    def test_saving_clears_pending(self, auth_client, book, book_form_data):
        """Книгу-черновик дозаполнили полной формой — она больше не черновик."""
        book.is_pending = True
        book.save()
        book_form_data["author"] = book.author.pk
        auth_client.post(reverse("book_edit", args=[book.pk]), data=book_form_data)
        book.refresh_from_db()
        assert book.is_pending is False

    @pytest.mark.django_db
    def test_can_edit_book_of_another_user(self, auth_client, book_of_user_2):
        """Каталог общий: ограничений по владельцу во view нет."""
        response = auth_client.get(reverse("book_edit", args=[book_of_user_2.pk]))
        assert response.status_code == 200


class TestBookDeleteView:
    """Удаление книги."""

    @pytest.mark.django_db
    def test_anonymous_redirected_to_login(self, client, book):
        url = reverse("book_delete", args=[book.pk])
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == f"{reverse('login')}?next={url}"

    @pytest.mark.django_db
    def test_confirmation_page(self, auth_client, book):
        response = auth_client.get(reverse("book_delete", args=[book.pk]))
        assert response.status_code == 200
        assert response.context["book"] == book
        assert response.context["page_title"] == f"Удаление: {book.title}"

    @pytest.mark.django_db
    def test_confirmation_counts(self, auth_client, book, review, entry):  # pylint: disable=unused-argument
        response = auth_client.get(reverse("book_delete", args=[book.pk]))
        assert response.context["reviews_count"] == 1
        assert response.context["entries_count"] == 1

    @pytest.mark.django_db
    def test_book_soft_deleted(self, auth_client, book, user_1):
        response = auth_client.post(reverse("book_delete", args=[book.pk]))
        assert response.status_code == 302
        assert response.url == reverse("books")
        assert not Book.objects.filter(pk=book.pk).exists()

        book = Book.all_objects.get(pk=book.pk)
        assert book.is_deleted is True
        assert book.deleted_by == user_1
        assert book.deleted_at is not None

    @pytest.mark.django_db
    def test_cascade_to_reviews_and_entries(self, auth_client, book, review, entry):
        auth_client.post(reverse("book_delete", args=[book.pk]))
        for obj in (review, entry):
            obj.refresh_from_db()
            assert obj.is_deleted is True

    @pytest.mark.parametrize("method", ["get", "post"])
    @pytest.mark.django_db
    def test_other_reader_forbidden(self, auth_client_2, book, method):
        response = getattr(auth_client_2, method)(reverse("book_delete", args=[book.pk]))
        assert response.status_code == 403
        assert Book.objects.filter(pk=book.pk).exists()

    @pytest.mark.django_db
    def test_admin_can_delete(self, admin_auth_client, book, superuser):
        response = admin_auth_client.post(reverse("book_delete", args=[book.pk]))
        assert response.status_code == 302
        assert Book.all_objects.get(pk=book.pk).deleted_by == superuser

    @pytest.mark.django_db
    def test_deleted_book_not_found(self, auth_client, book):
        book.delete()
        assert auth_client.get(reverse("book_delete", args=[book.pk])).status_code == 404

    @pytest.mark.django_db
    def test_success_message(self, auth_client, book):
        title = book.title
        response = auth_client.post(
            reverse("book_delete", args=[book.pk]), follow=True
        )
        messages = [str(message) for message in response.context["messages"]]
        assert f"Книга «{title}» удалена из каталога." in messages


class TestReadingStatusView:
    """Смена статуса книги кнопкой."""

    def url(self, book):
        """Адрес смены статуса книги."""
        return reverse("book_status", args=[book.pk])

    @pytest.mark.django_db
    def test_anonymous_redirected_to_login(self, client, book):
        response = client.post(self.url(book), {"status": "planned"})
        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))
        assert not ReadingEntry.objects.exists()

    @pytest.mark.django_db
    def test_get_not_allowed(self, auth_client, book):
        assert auth_client.get(self.url(book)).status_code == 405

    @pytest.mark.django_db
    def test_adds_book_to_diary(self, auth_client, book, user_1):
        response = auth_client.post(self.url(book), {"status": "planned"})
        assert response.status_code == 302
        assert response.url == book.get_absolute_url()
        entry = ReadingEntry.objects.get()
        assert (entry.reader, entry.book, entry.status) == (user_1, book, ReadingStatus.PLANNED)

    @pytest.mark.django_db
    def test_changes_status_and_dates(self, auth_client, book, entry):
        auth_client.post(self.url(book), {"status": "read"})
        entry.refresh_from_db()
        assert entry.status == ReadingStatus.READ
        assert entry.finished_at is not None

    @pytest.mark.django_db
    def test_success_message(self, auth_client, book):
        response = auth_client.post(self.url(book), {"status": "reading"}, follow=True)
        assert f"Дневник обновлён: «{book.title}» — читаю." in messages_of(response)

    @pytest.mark.django_db
    def test_forbidden_transition(self, auth_client, book, entry):
        response = auth_client.post(self.url(book), {"status": "planned"}, follow=True)
        entry.refresh_from_db()
        assert entry.status == ReadingStatus.READING
        assert f"Статус книги «{book.title}» так поменять нельзя." in messages_of(response)

    @pytest.mark.django_db
    def test_missing_status(self, auth_client, book):
        auth_client.post(self.url(book))
        assert not ReadingEntry.objects.exists()

    @pytest.mark.django_db
    def test_redirects_to_next(self, auth_client, book):
        response = auth_client.post(self.url(book), {"status": "planned", "next": "/books/?page=2"})
        assert response.url == "/books/?page=2"

    @pytest.mark.django_db
    def test_external_next_ignored(self, auth_client, book):
        response = auth_client.post(self.url(book), {"status": "planned", "next": "https://evil.example/"})
        assert response.url == book.get_absolute_url()

    @pytest.mark.django_db
    def test_deleted_book_not_found(self, auth_client, book):
        book.delete()
        assert auth_client.post(self.url(book), {"status": "planned"}).status_code == 404
        assert not ReadingEntry.all_objects.exists()


class TestReadingEntryUpdateView:
    """Правка записи дневника."""

    def url(self, entry):
        """Адрес правки записи."""
        return reverse("entry_edit", args=[entry.pk])

    @pytest.mark.django_db
    def test_anonymous_redirected_to_login(self, client, entry):
        url = self.url(entry)
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == f"{reverse('login')}?next={url}"

    @pytest.mark.django_db
    def test_form_prefilled(self, auth_client, entry, book):
        response = auth_client.get(self.url(entry))
        assert response.status_code == 200
        assert "bookshelf_app/book_form.html" in [t.name for t in response.templates]
        context = response.context
        assert context["form"].instance == entry
        assert context["page_title"] == f"Запись дневника: {book.title}"
        assert context["submit_label"] == "Сохранить"
        assert context["cancel_url"] == reverse("index")
        assert context["delete_url"] == reverse("entry_delete", args=[entry.pk])

    @pytest.mark.django_db
    def test_breadcrumbs(self, auth_client, entry, book):
        response = auth_client.get(self.url(entry))
        crumbs = response.context["breadcrumbs"]
        assert [crumb["title"] for crumb in crumbs] == ["Главная", book.title, "Запись дневника"]
        assert crumbs[1]["url"] == book.get_absolute_url()

    @pytest.mark.django_db
    def test_entry_updated(self, auth_client, entry, book):
        data = {"status": "abandoned", "started_at": "2025-12-01", "finished_at": "2026-01-15"}
        response = auth_client.post(self.url(entry), data, follow=True)
        assert response.redirect_chain[-1][0] == reverse("index")
        entry.refresh_from_db()
        assert entry.status == ReadingStatus.ABANDONED
        assert entry.started_at == datetime.date(2025, 12, 1)
        assert entry.finished_at == datetime.date(2026, 1, 15)
        assert f"Запись сохранена: «{book.title}» — брошено." in messages_of(response)

    @pytest.mark.django_db
    def test_invalid_dates(self, auth_client, entry):
        data = {"status": "read", "started_at": "2026-02-01", "finished_at": "2026-01-01"}
        response = auth_client.post(self.url(entry), data)
        assert response.status_code == 200
        entry.refresh_from_db()
        assert entry.status == ReadingStatus.READING

    @pytest.mark.parametrize("method", ["get", "post"])
    @pytest.mark.django_db
    def test_other_reader_not_found(self, auth_client_2, entry, method):
        response = getattr(auth_client_2, method)(self.url(entry), {"status": "read"})
        assert response.status_code == 404
        entry.refresh_from_db()
        assert entry.status == ReadingStatus.READING

    @pytest.mark.django_db
    def test_deleted_entry_not_found(self, auth_client, entry):
        entry.delete()
        assert auth_client.get(self.url(entry)).status_code == 404

    @pytest.mark.django_db
    def test_entry_of_deleted_book_not_found(self, auth_client, entry, book):
        book.delete()
        ReadingEntry.all_objects.filter(pk=entry.pk).update(is_deleted=False, deleted_at=None)
        assert auth_client.get(self.url(entry)).status_code == 404


class TestReadingEntryDeleteView:
    """Удаление записи дневника."""

    def url(self, entry):
        """Адрес удаления записи."""
        return reverse("entry_delete", args=[entry.pk])

    @pytest.mark.django_db
    def test_anonymous_redirected_to_login(self, client, entry):
        response = client.post(self.url(entry))
        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))
        entry.refresh_from_db()
        assert entry.is_deleted is False

    @pytest.mark.django_db
    def test_confirmation_page(self, auth_client, entry, book):
        response = auth_client.get(self.url(entry))
        assert response.status_code == 200
        assert response.context["entry"] == entry
        assert response.context["page_title"] == f"Удаление записи: {book.title}"
        assert response.context["breadcrumbs"][-1]["title"] == "Удаление записи"

    @pytest.mark.django_db
    def test_entry_soft_deleted(self, auth_client, entry, book, user_1):
        response = auth_client.post(self.url(entry), follow=True)
        assert response.redirect_chain[-1][0] == reverse("index")
        entry = ReadingEntry.all_objects.get(pk=entry.pk)
        assert entry.is_deleted is True
        assert entry.deleted_by == user_1
        assert Book.objects.filter(pk=book.pk).exists()
        assert f"Запись о книге «{book.title}» удалена из дневника." in messages_of(response)

    @pytest.mark.django_db
    def test_other_reader_not_found(self, auth_client_2, entry):
        assert auth_client_2.post(self.url(entry)).status_code == 404
        entry.refresh_from_db()
        assert entry.is_deleted is False


class TestDiaryAddView:
    """Быстрое добавление книги в дневник."""

    @staticmethod
    def search(client, query):
        """Страница поиска со строкой `query`."""
        return client.get(reverse("diary_add"), {"q": query})

    @pytest.mark.django_db
    def test_anonymous_redirected_to_login(self, client):
        url = reverse("diary_add")
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == f"{reverse('login')}?next={url}"

    @pytest.mark.django_db
    def test_empty_query(self, auth_client):
        response = auth_client.get(reverse("diary_add"))
        assert response.status_code == 200
        assert "bookshelf_app/diary_add.html" in [t.name for t in response.templates]
        assert response.context["query"] == ""
        assert response.context["results"] == []
        assert response.context["page_title"] == "Добавить книгу в дневник"

    @pytest.mark.django_db
    def test_breadcrumbs(self, auth_client):
        response = auth_client.get(reverse("diary_add"))
        assert [crumb["title"] for crumb in response.context["breadcrumbs"]] == ["Главная", "Добавить в дневник"]

    @pytest.mark.django_db
    def test_search_by_title_part(self, auth_client, book, book_of_user_2):  # pylint: disable=unused-argument
        response = self.search(auth_client, "  маргарита ")
        assert response.context["query"] == "маргарита"
        assert list(response.context["results"]) == [book]

    @pytest.mark.django_db
    def test_results_have_status_actions(self, auth_client, book, entry):  # pylint: disable=unused-argument
        [item] = self.search(auth_client, book.title).context["results"]
        assert [action.status for action in item.status_actions] == [ReadingStatus.READ, ReadingStatus.ABANDONED]

    @pytest.mark.django_db
    def test_results_limited(self, auth_client, author):
        for number in range(SEARCH_LIMIT + 1):
            Book.objects.create(title=f"Том {number}", author=author)
        assert len(self.search(auth_client, "Том").context["results"]) == SEARCH_LIMIT

    @pytest.mark.django_db
    def test_deleted_books_not_found(self, auth_client, book):
        book.delete()
        assert not self.search(auth_client, book.title).context["results"]

    @pytest.mark.django_db
    def test_form_prefilled_with_query(self, auth_client):
        form = self.search(auth_client, "Белая гвардия").context["form"]
        assert form.initial["title"] == "Белая гвардия"

    @pytest.mark.django_db
    def test_quick_add(self, auth_client, user_1):
        data = {"title": "Белая гвардия", "author": "Михаил Булгаков", "status": "planned"}
        response = auth_client.post(f"{reverse('diary_add')}?q=Белая", data, follow=True)
        assert response.redirect_chain[-1][0] == reverse("index")

        book = Book.objects.get(title="Белая гвардия")
        assert book.is_pending is True
        assert book.added_by == user_1
        assert ReadingEntry.objects.get(book=book).reader == user_1
        assert "Книга «Белая гвардия» добавлена в каталог черновиком и в ваш дневник." in messages_of(response)

    @pytest.mark.django_db
    def test_quick_add_logs_new_book(self, auth_client, mocker):
        delay = mocker.patch("bookshelf_app.views.log_new_book_task.delay")
        auth_client.post(reverse("diary_add"), {"title": "Бег", "author": "Михаил Булгаков", "status": "read"})
        book = Book.objects.get(title="Бег")
        delay.assert_called_once_with(
            book_id=book.pk, title="Бег", author="Михаил Булгаков", added_by=str(book.added_by),
        )

    @pytest.mark.django_db
    def test_invalid_form_keeps_query(self, auth_client, book):
        response = auth_client.post(
            f"{reverse('diary_add')}?q=Мастер",
            {"title": book.title, "author": book.author.name, "status": "planned"},
        )
        assert response.status_code == 200
        assert response.context["query"] == "Мастер"
        assert list(response.context["results"]) == [book]
        assert "title" in response.context["form"].errors
        assert Book.objects.count() == 1
        assert Author.objects.count() == 1
