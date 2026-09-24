"""Тесты представлений каталога книг."""

import pytest
from django.urls import reverse

from bookshelf_app.models import Book, ReadingStatus


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
