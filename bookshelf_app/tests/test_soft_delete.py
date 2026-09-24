"""Тесты мягкого удаления: модель, менеджеры, каскад, защита связей и админка."""

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import AnonymousUser
from django.db.models import ProtectedError
from django.urls import reverse
from django.utils.text import capfirst

from bookshelf_app.admin import BookAdmin
from bookshelf_app.models import Author, Book, ReadingEntry, Review

pytestmark = pytest.mark.django_db


class TestSoftDeleteModel:
    """Пометка вместо физического удаления."""

    def test_delete_marks_object(self, review, user_1):
        review.delete(user=user_1)
        review.refresh_from_db()
        assert review.is_deleted is True
        assert review.deleted_at is not None
        assert review.deleted_by == user_1

    def test_delete_without_user(self, review):
        review.delete()
        review.refresh_from_db()
        assert review.is_deleted is True
        assert review.deleted_by is None

    def test_row_stays_in_database(self, review):
        review.delete()
        assert Review.all_objects.filter(pk=review.pk).exists()

    def test_managers(self, reviews):
        reviews[0].delete()
        assert list(Review.objects.all()) == [reviews[1]]
        assert set(Review.all_objects.all()) == set(reviews)

    def test_reverse_relation_sees_alive_only(self, book, reviews):
        reviews[0].delete()
        assert list(book.reviews.all()) == [reviews[1]]

    def test_forward_relation_sees_deleted(self, book, review):
        """Отзыв продолжает ссылаться на удалённую книгу — например, в админке."""
        book.delete()
        review = Review.all_objects.get(pk=review.pk)
        assert review.book == book

    def test_delete_returns_count(self, book, review, entry):  # pylint: disable=unused-argument
        assert book.delete() == (3, {"bookshelf_app.Book": 1})

    def test_restore(self, review):
        review.delete()
        review.restore()
        review.refresh_from_db()
        assert review.is_deleted is False
        assert review.deleted_at is None
        assert review.deleted_by is None

    def test_restore_alive_is_noop(self, review, django_assert_num_queries):
        with django_assert_num_queries(0):
            review.restore()
        assert review.is_deleted is False


class TestBookCascade:
    """Удалённая книга уносит свои отзывы и записи дневника всех читателей."""

    def test_cascade(self, book, reviews, entry, user_2, user_1):
        other_entry = ReadingEntry.objects.create(reader=user_2, book=book)
        book.delete(user=user_1)
        book.refresh_from_db()
        for obj in (*reviews, entry, other_entry):
            obj.refresh_from_db()
            assert obj.is_deleted is True
            assert obj.deleted_by == user_1
            assert obj.deleted_at == book.deleted_at

    def test_other_books_untouched(self, book, book_of_user_2, user_1):
        other = ReadingEntry.objects.create(reader=user_1, book=book_of_user_2)
        book.delete()
        other.refresh_from_db()
        assert other.is_deleted is False

    def test_already_deleted_child_keeps_its_mark(self, book, reviews):
        reviews[0].delete()
        first_deleted_at = Review.all_objects.get(pk=reviews[0].pk).deleted_at
        book.delete()
        assert Review.all_objects.get(pk=reviews[0].pk).deleted_at == first_deleted_at

    def test_restore_brings_back_cascaded_only(self, book, reviews, entry):
        """Отзыв, удалённый раньше книги и отдельно, при восстановлении книги не возвращается."""
        reviews[0].delete()
        book.delete()
        book.restore()

        assert Book.objects.filter(pk=book.pk).exists()
        assert list(book.reviews.all()) == [reviews[1]]
        assert list(book.entries.all()) == [entry]

    def test_deleted_related(self, book, reviews, entry):
        related = {name: list(queryset) for name, queryset in book.deleted_related().items()}
        assert related == {
            Review._meta.verbose_name_plural: sorted(reviews, key=lambda review: review.pk),
            ReadingEntry._meta.verbose_name_plural: [entry],
        }


class TestAuthorProtect:
    """Автора с живыми книгами удалить нельзя — как PROTECT у внешнего ключа."""

    def test_protected(self, author, book):
        with pytest.raises(ProtectedError) as error:
            author.delete()
        assert error.value.protected_objects == {book}
        author.refresh_from_db()
        assert author.is_deleted is False

    def test_allowed_when_books_deleted(self, author, book):
        book.delete()
        author.delete()
        assert not Author.objects.filter(pk=author.pk).exists()

    def test_book_of_deleted_author_still_shows_author(self, author, book):
        book.delete()
        author.delete()
        book = Book.all_objects.get(pk=book.pk)
        assert book.author == author


class TestSoftDeleteQuerySet:
    """Массовое удаление и восстановление."""

    def test_delete(self, books, user_1):
        count, by_model = Book.objects.filter(pk__in=[books[0].pk, books[1].pk]).delete(user=user_1)
        assert count == 2
        assert by_model == {"bookshelf_app.Book": 2}
        assert list(Book.objects.all()) == [books[2]]
        assert all(book.deleted_by == user_1 for book in Book.all_objects.filter(is_deleted=True))

    def test_delete_cascades(self, book, review):
        Book.objects.filter(pk=book.pk).delete()
        review.refresh_from_db()
        assert review.is_deleted is True

    def test_restore(self, books):
        Book.objects.all().delete()
        assert Book.all_objects.all().restore() == len(books)
        assert Book.objects.count() == len(books)


class TestCanBeDeletedBy:
    """Кто вправе удалить книгу."""

    def test_owner(self, book, user_1):
        assert book.can_be_deleted_by(user_1) is True

    def test_other_reader(self, book, user_2):
        assert book.can_be_deleted_by(user_2) is False

    def test_admin(self, book, superuser):
        assert book.can_be_deleted_by(superuser) is True

    def test_anonymous(self, book):
        assert book.can_be_deleted_by(AnonymousUser()) is False

    def test_without_owner_only_admin(self, book, user_1, superuser):
        book.added_by = None
        assert book.can_be_deleted_by(user_1) is False
        assert book.can_be_deleted_by(superuser) is True


class TestSoftDeleteAdmin:
    """Админка видит удалённое и умеет его восстанавливать."""

    def changelist(self, client, model="book", **params):
        """Список объектов модели каталога в админке."""
        return client.get(reverse(f"admin:bookshelf_app_{model}_changelist"), params)

    def test_changelist_shows_deleted(self, admin_auth_client, books):
        books[0].delete()
        response = self.changelist(admin_auth_client)
        assert set(response.context["cl"].queryset) == set(books)

    def test_filter_deleted(self, admin_auth_client, books):
        books[0].delete()
        response = self.changelist(admin_auth_client, is_deleted__exact="1")
        assert list(response.context["cl"].queryset) == [books[0]]

    def test_list_display_and_filter(self, rf, superuser):
        request = rf.get("/")
        request.user = superuser
        model_admin = BookAdmin(Book, AdminSite())
        assert model_admin.get_list_display(request)[-1] == "is_deleted"
        assert model_admin.get_list_filter(request)[-1] == "is_deleted"

    def test_change_page_of_deleted(self, admin_auth_client, book):
        book.delete()
        response = admin_auth_client.get(reverse("admin:bookshelf_app_book_change", args=[book.pk]))
        assert response.status_code == 200
        assert "is_deleted" not in response.context["adminform"].form.fields

    def test_add_page_has_no_soft_delete_fields(self, admin_auth_client):
        response = admin_auth_client.get(reverse("admin:bookshelf_app_book_add"))
        fields = response.context["adminform"].form.fields
        assert not {"is_deleted", "deleted_at", "deleted_by"} & set(fields)

    def test_deleted_review_can_be_saved(self, admin_auth_client, review, book):
        """Форма удалённого отзыва сохраняется, хотя книга тоже удалена."""
        book.delete()
        url = reverse("admin:bookshelf_app_review_change", args=[review.pk])
        response = admin_auth_client.post(url, {"book": book.pk, "reader": review.reader.pk})
        assert response.status_code == 302

    def test_review_fieldsets_have_deletion_block(self, admin_auth_client, review):
        response = admin_auth_client.get(reverse("admin:bookshelf_app_review_change", args=[review.pk]))
        names = [fieldset.name for fieldset in response.context["adminform"]]
        assert names[-1] == "Удаление"

    def test_delete_view_is_soft(self, admin_auth_client, book, review, superuser):
        url = reverse("admin:bookshelf_app_book_delete", args=[book.pk])
        admin_auth_client.post(url, {"post": "yes"})
        book = Book.all_objects.get(pk=book.pk)
        assert book.is_deleted is True
        assert book.deleted_by == superuser
        assert Review.all_objects.get(pk=review.pk).is_deleted is True

    # review и entry нужны как данные в базе: они и попадают в список удаляемого.
    def test_delete_confirmation_lists_cascade(
        self, admin_auth_client, book, review, entry,  # pylint: disable=unused-argument
    ):
        response = admin_auth_client.get(reverse("admin:bookshelf_app_book_delete", args=[book.pk]))
        model_count = dict(response.context["model_count"])
        assert model_count == {
            str(Book._meta.verbose_name_plural): 1,
            str(Review._meta.verbose_name_plural): 1,
            str(ReadingEntry._meta.verbose_name_plural): 1,
        }
        deleted = response.context["deleted_objects"]
        assert len(deleted) == 2  # сама книга и вложенный список связанных
        assert len(deleted[1]) == 2

    def test_delete_protected_author(self, admin_auth_client, author, book):
        response = admin_auth_client.get(reverse("admin:bookshelf_app_author_delete", args=[author.pk]))
        assert response.context["protected"] == [f"{capfirst(Book._meta.verbose_name)}: {book}"]

    def test_bulk_delete_action(self, admin_auth_client, books, superuser):
        admin_auth_client.post(
            reverse("admin:bookshelf_app_book_changelist"),
            {"action": "delete_selected", "_selected_action": [books[0].pk], "post": "yes"},
        )
        deleted = Book.all_objects.get(pk=books[0].pk)
        assert deleted.is_deleted is True
        assert deleted.deleted_by == superuser

    def test_restore_action(self, admin_auth_client, book, review):
        book.delete()
        response = admin_auth_client.post(
            reverse("admin:bookshelf_app_book_changelist"),
            {"action": "restore_selected", "_selected_action": [book.pk]},
            follow=True,
        )
        assert Book.objects.filter(pk=book.pk).exists()
        assert Review.objects.filter(pk=review.pk).exists()
        messages = [str(message) for message in response.context["messages"]]
        assert "Восстановлено записей: 1." in messages

    def test_restore_action_hidden_in_popup(self, rf, superuser):
        request = rf.get("/", {"_popup": "1"})
        request.user = superuser
        assert "restore_selected" not in BookAdmin(Book, AdminSite()).get_actions(request)

    def test_restore_action_kept_with_own_actions(self, rf, superuser):
        """У BookAdmin свои `actions`, но «восстановить» всё равно есть."""
        request = rf.get("/")
        request.user = superuser
        actions = BookAdmin(Book, AdminSite()).get_actions(request)
        assert {"restore_selected", "confirm_pending", "delete_selected"} <= set(actions)
