"""Тесты журнала событий: снимки и сравнение полей, запись с сайта и из админки, просмотр."""

import datetime

import pytest
from django.urls import reverse

from bookshelf_app.events import diff, log_created, log_updated, snapshot, stored_snapshot
from bookshelf_app.models import Book, EventLog


@pytest.fixture
def on_commit(django_capture_on_commit_callbacks):
    """Контекст, в котором отложенные до коммита задачи выполняются сразу.

    Тест целиком идёт в транзакции, которая откатывается, — без этого
    `transaction.on_commit()` никогда не сработает и журнал останется пустым.
    """
    return lambda: django_capture_on_commit_callbacks(execute=True)


def events_of(obj):
    """События журнала об объекте — от старых к новым."""
    object_type = "book" if isinstance(obj, Book) else "author"
    return list(EventLog.objects.filter(object_type=object_type, object_id=obj.pk).order_by("created_at", "pk"))


class TestSnapshot:
    """Снимок полей и сравнение снимков."""

    @pytest.mark.django_db
    def test_book_snapshot(self, book, user_1):
        assert snapshot(book) == {
            "title": "Мастер и Маргарита",
            "description": "Роман о добре и зле.",
            "author": "Михаил Булгаков",
            "genres": ["Роман"],
            "published_year": 1967,
            "is_pending": False,
            "added_by": str(user_1),
        }

    @pytest.mark.django_db
    def test_author_snapshot_dates_in_iso(self, author):
        assert snapshot(author) == {
            "name": "Михаил Булгаков",
            "bio": "Русский писатель и драматург.",
            "birth_date": "1891-05-15",
        }

    @pytest.mark.django_db
    def test_empty_relation(self, book):
        book.added_by = None
        assert snapshot(book)["added_by"] is None

    @pytest.mark.django_db
    def test_stored_snapshot_ignores_unsaved_changes(self, book):
        book.title = "Черновик"
        assert stored_snapshot(book)["title"] == "Мастер и Маргарита"

    @pytest.mark.django_db
    def test_stored_snapshot_of_deleted(self, book):
        book.delete()
        assert stored_snapshot(book)["title"] == "Мастер и Маргарита"

    def test_diff(self):
        old = {"title": "А", "genres": ["Роман"], "published_year": None}
        new = {"title": "Б", "genres": ["Роман"], "published_year": 1900}
        assert diff(old, new) == {
            "title": {"old": "А", "new": "Б"},
            "published_year": {"old": None, "new": 1900},
        }


@pytest.mark.django_db
class TestLogHelpers:
    """Функции, которые ставят события в очередь."""

    def test_created_skips_empty_fields(self, author_2, user_1, on_commit):
        with on_commit():
            log_created(author_2, user_1)
        [event] = events_of(author_2)
        assert event.action == EventLog.Action.CREATED
        assert event.user == user_1
        assert event.changes == {"name": {"old": None, "new": "Фёдор Достоевский"}}

    def test_updated_without_changes_is_not_logged(self, book, user_1, on_commit):
        with on_commit():
            assert log_updated(book, user_1, snapshot(book)) == {}
        assert not events_of(book)

    def test_not_logged_on_rollback(self, author_2, user_1, django_capture_on_commit_callbacks):
        """Событие ставится только после коммита: откатили транзакцию — задачи не было."""
        with django_capture_on_commit_callbacks() as callbacks:
            log_created(author_2, user_1)
        assert len(callbacks) == 1
        assert not events_of(author_2)


@pytest.mark.django_db
class TestSiteEvents:
    """Действия на сайте попадают в журнал."""

    def test_book_create(self, auth_client, book_form_data, user_1, on_commit):
        with on_commit():
            auth_client.post(reverse("book_add"), data=book_form_data)
        book = Book.objects.get(title=book_form_data["title"])
        [event] = events_of(book)
        assert event.action == EventLog.Action.CREATED
        assert event.user == user_1
        assert event.object_repr == "Собачье сердце"
        assert event.changes["genres"] == {"old": None, "new": ["Роман"]}
        assert event.changes["added_by"] == {"old": None, "new": str(user_1)}
        assert "is_pending" not in event.changes

    def test_invalid_form_is_not_logged(self, auth_client, book_form_data, on_commit):
        with on_commit():
            auth_client.post(reverse("book_add"), data={**book_form_data, "title": ""})
        assert not EventLog.objects.exists()

    def test_book_update_logs_only_changes(self, auth_client, book, genre_2, user_1, on_commit):
        data = {
            "title": "Мастер и Маргарита",
            "author": book.author.pk,
            "genres": [genre_2.pk],
            "published_year": 1973,
            "description": book.description,
        }
        with on_commit():
            auth_client.post(reverse("book_edit", args=[book.pk]), data=data)
        [event] = events_of(book)
        assert event.action == EventLog.Action.UPDATED
        assert event.user == user_1
        assert event.changes == {
            "genres": {"old": ["Роман"], "new": ["Фантастика"]},
            "published_year": {"old": 1967, "new": 1973},
        }

    def test_book_update_without_changes(self, auth_client, book, genre, on_commit):
        data = {
            "title": book.title,
            "author": book.author.pk,
            "genres": [genre.pk],
            "published_year": book.published_year,
            "description": book.description,
        }
        with on_commit():
            auth_client.post(reverse("book_edit", args=[book.pk]), data=data)
        assert not events_of(book)

    def test_pending_book_confirmed_by_form(self, auth_client, book, genre, on_commit):
        """Снятый полной формой флаг черновика — тоже изменение."""
        Book.objects.filter(pk=book.pk).update(is_pending=True)
        data = {
            "title": book.title,
            "author": book.author.pk,
            "genres": [genre.pk],
            "published_year": book.published_year,
            "description": book.description,
        }
        with on_commit():
            auth_client.post(reverse("book_edit", args=[book.pk]), data=data)
        assert events_of(book)[0].changes == {"is_pending": {"old": True, "new": False}}

    def test_book_delete(self, auth_client, book, user_1, on_commit):
        with on_commit():
            auth_client.post(reverse("book_delete", args=[book.pk]))
        [event] = events_of(book)
        assert event.action == EventLog.Action.DELETED
        assert event.user == user_1
        assert event.changes == {}

    def test_quick_add_with_new_author(self, auth_client, user_1, on_commit):
        with on_commit():
            auth_client.post(reverse("diary_add"), {"title": "Бег", "author": "Михаил Булгаков", "status": "read"})
        book = Book.objects.get(title="Бег")
        [author_event] = events_of(book.author)
        [book_event] = events_of(book)
        assert author_event.action == book_event.action == EventLog.Action.CREATED
        assert author_event.user == book_event.user == user_1
        assert book_event.changes["is_pending"] == {"old": None, "new": True}

    def test_quick_add_with_existing_author(self, auth_client, author, on_commit):
        with on_commit():
            auth_client.post(reverse("diary_add"), {"title": "Бег", "author": author.name, "status": "planned"})
        assert len(events_of(Book.objects.get(title="Бег"))) == 1
        assert not events_of(author)

    def test_reviews_and_diary_are_not_logged(self, auth_client, book, on_commit):
        with on_commit():
            auth_client.post(reverse("book_status", args=[book.pk]), {"status": "reading"})
            auth_client.post(reverse("review_add", args=[book.pk]), {"rating": 5, "text": "Хорошо."})
        assert not EventLog.objects.exists()


@pytest.mark.django_db
class TestAdminEvents:
    """Действия в админке попадают в журнал."""

    def changelist_action(self, client, model, action, objects, **extra):
        """Применяет действие к выбранным объектам в списке админки."""
        return client.post(
            reverse(f"admin:bookshelf_app_{model}_changelist"),
            {"action": action, "_selected_action": [obj.pk for obj in objects], **extra},
        )

    def test_add_book(self, admin_auth_client, author, genre, superuser, on_commit):
        with on_commit():
            admin_auth_client.post(
                reverse("admin:bookshelf_app_book_add"),
                {"title": "Бег", "author": author.pk, "genres": [genre.pk]},
            )
        [event] = events_of(Book.objects.get(title="Бег"))
        assert event.action == EventLog.Action.CREATED
        assert event.user == superuser
        assert event.changes["genres"] == {"old": None, "new": ["Роман"]}

    def test_change_author(self, admin_auth_client, author, superuser, on_commit):
        with on_commit():
            admin_auth_client.post(
                reverse("admin:bookshelf_app_author_change", args=[author.pk]),
                {"name": "М. А. Булгаков", "bio": author.bio, "birth_date": "1891-05-15"},
            )
        [event] = events_of(author)
        assert event.action == EventLog.Action.UPDATED
        assert event.user == superuser
        assert event.changes == {"name": {"old": "Михаил Булгаков", "new": "М. А. Булгаков"}}

    def test_change_book_genres(self, admin_auth_client, book, genre_2, on_commit):
        """Жанры сохраняются после самой книги — сравнение должно их увидеть."""
        with on_commit():
            admin_auth_client.post(
                reverse("admin:bookshelf_app_book_change", args=[book.pk]),
                {
                    "title": book.title,
                    "author": book.author.pk,
                    "genres": [genre_2.pk],
                    "published_year": book.published_year,
                    "description": book.description,
                    "added_by": book.added_by.pk,
                },
            )
        assert events_of(book)[0].changes == {"genres": {"old": ["Роман"], "new": ["Фантастика"]}}

    def test_delete_view(self, admin_auth_client, book, superuser, on_commit):
        with on_commit():
            admin_auth_client.post(reverse("admin:bookshelf_app_book_delete", args=[book.pk]), {"post": "yes"})
        [event] = events_of(book)
        assert event.action == EventLog.Action.DELETED
        assert event.user == superuser

    def test_delete_selected(self, admin_auth_client, books, on_commit):
        with on_commit():
            self.changelist_action(admin_auth_client, "book", "delete_selected", books[:2], post="yes")
        assert Book.objects.count() == 1
        assert [len(events_of(item)) for item in books] == [1, 1, 0]

    def test_restore(self, admin_auth_client, book, superuser, on_commit):
        book.delete()
        with on_commit():
            self.changelist_action(admin_auth_client, "book", "restore_selected", [book])
        assert Book.objects.filter(pk=book.pk).exists()
        [event] = events_of(book)
        assert event.action == EventLog.Action.RESTORED
        assert event.user == superuser

    def test_confirm_pending(self, admin_auth_client, books, on_commit):
        Book.objects.filter(pk__in=[books[0].pk, books[1].pk]).update(is_pending=True)
        with on_commit():
            self.changelist_action(admin_auth_client, "book", "confirm_pending", books)
        assert not Book.objects.filter(is_pending=True).exists()
        assert events_of(books[0])[0].changes == {"is_pending": {"old": True, "new": False}}
        assert not events_of(books[2])

    def test_reviews_are_not_logged(self, admin_auth_client, review, on_commit):
        with on_commit():
            admin_auth_client.post(reverse("admin:bookshelf_app_review_delete", args=[review.pk]), {"post": "yes"})
        assert not EventLog.objects.exists()


@pytest.fixture
def event(book, user_1):
    """Событие «книга изменена»: название, жанры и флаг черновика."""
    return EventLog.objects.create(
        user=user_1,
        action=EventLog.Action.UPDATED,
        object_type=EventLog.ObjectType.BOOK,
        object_id=book.pk,
        object_repr=book.title,
        changes={
            "title": {"old": "Мастер", "new": "Мастер и Маргарита"},
            "genres": {"old": [], "new": ["Роман", "Фантастика"]},
            "is_pending": {"old": True, "new": False},
            "removed_field": {"old": 1, "new": 2},
        },
    )


@pytest.mark.django_db
class TestEventLogAdmin:
    """Просмотр журнала в админке — только чтение, с фильтрами."""

    def changelist(self, client, **params):
        """Список событий журнала."""
        return client.get(reverse("admin:bookshelf_app_eventlog_changelist"), params)

    def test_changelist(self, admin_auth_client, event):
        response = self.changelist(admin_auth_client)
        assert response.status_code == 200
        assert list(response.context["cl"].queryset) == [event]
        content = response.content.decode()
        assert reverse("admin:bookshelf_app_book_change", args=[event.object_id]) in content
        assert "Название, Жанры, Требует дозаполнения, removed_field" in content

    def test_detail_is_readonly(self, admin_auth_client, event):
        response = admin_auth_client.get(reverse("admin:bookshelf_app_eventlog_change", args=[event.pk]))
        assert response.status_code == 200
        assert not response.context["has_change_permission"]
        content = response.content.decode()
        assert "<td>Название</td><td>Мастер</td><td>Мастер и Маргарита</td>" in content
        assert "<td>Жанры</td><td>—</td><td>Роман, Фантастика</td>" in content
        assert "<td>Требует дозаполнения</td><td>да</td><td>нет</td>" in content
        assert "<td>removed_field</td><td>1</td><td>2</td>" in content

    def test_detail_without_changes(self, admin_auth_client, event):
        EventLog.objects.filter(pk=event.pk).update(changes={}, action=EventLog.Action.DELETED)
        response = admin_auth_client.get(reverse("admin:bookshelf_app_eventlog_change", args=[event.pk]))
        assert "<th>Было</th>" not in response.content.decode()

    def test_cannot_add_or_delete(self, admin_auth_client, event):
        assert admin_auth_client.get(reverse("admin:bookshelf_app_eventlog_add")).status_code == 403
        url = reverse("admin:bookshelf_app_eventlog_delete", args=[event.pk])
        assert admin_auth_client.post(url, {"post": "yes"}).status_code == 403
        assert EventLog.objects.filter(pk=event.pk).exists()

    def test_filter_by_user_includes_deleted(self, admin_auth_client, event, user_1, user_2, author):
        other = EventLog.objects.create(
            user=user_2, action=EventLog.Action.CREATED, object_type=EventLog.ObjectType.AUTHOR,
            object_id=author.pk, object_repr=author.name,
        )
        user_2.delete()
        response = self.changelist(admin_auth_client)
        user_filter = response.context["cl"].filter_specs[0]
        assert {str(user_1.pk), str(user_2.pk)} <= {str(pk) for pk, _ in user_filter.lookup_choices}

        assert list(self.changelist(admin_auth_client, user=user_2.pk).context["cl"].queryset) == [other]
        assert list(self.changelist(admin_auth_client, user=user_1.pk).context["cl"].queryset) == [event]

    def test_filter_by_type_and_date(self, admin_auth_client, event, author):
        old = EventLog.objects.create(
            action=EventLog.Action.CREATED, object_type=EventLog.ObjectType.AUTHOR,
            object_id=author.pk, object_repr=author.name,
            created_at=datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc),
        )
        by_type = self.changelist(admin_auth_client, object_type__exact="author")
        assert list(by_type.context["cl"].queryset) == [old]
        by_year = self.changelist(admin_auth_client, created_at__year="2020")
        assert list(by_year.context["cl"].queryset) == [old]
        assert event not in by_year.context["cl"].queryset

    def test_author_link(self, admin_auth_client, author):
        EventLog.objects.create(
            action=EventLog.Action.CREATED, object_type=EventLog.ObjectType.AUTHOR,
            object_id=author.pk, object_repr=author.name,
        )
        response = self.changelist(admin_auth_client)
        assert reverse("admin:bookshelf_app_author_change", args=[author.pk]) in response.content.decode()

    def test_repr(self, event, user_1):
        assert repr(event) == f"EventLog(updated, book#{event.object_id}, user={user_1.pk})"
        assert str(event) == f"Изменение: книга «Мастер и Маргарита» ({user_1})"
