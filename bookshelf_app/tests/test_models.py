"""Тесты моделей каталога книг и дневника чтения."""

import datetime

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models
from django.urls import reverse
from django.utils import timezone

from bookshelf_app.models import Book, Genre, ReadingEntry, ReadingStatus, Review


class TestAuthor:
    """Модель автора."""

    @pytest.mark.django_db
    def test_str(self, author):
        assert str(author) == "Михаил Булгаков"

    @pytest.mark.django_db
    def test_repr(self, author):
        assert repr(author) == "Михаил Булгаков"

    @pytest.mark.django_db
    def test_books_related_name(self, author, books):
        assert author.books.count() == len(books)


class TestGenre:
    """Модель жанра."""

    @pytest.mark.django_db
    def test_str(self, genre):
        assert str(genre) == "Роман"

    @pytest.mark.django_db
    def test_name_is_unique(self, genre):
        with pytest.raises(IntegrityError):
            Genre.objects.create(name=genre.name)

    @pytest.mark.django_db
    def test_books_related_name(self, genre, book):
        assert list(genre.books.all()) == [book]


class TestBook:
    """Модель книги."""

    @pytest.mark.django_db
    def test_str(self, book):
        assert str(book) == "Мастер и Маргарита"

    @pytest.mark.django_db
    def test_repr(self, book, author):
        assert repr(book) == f"Мастер и Маргарита ({author})"

    @pytest.mark.django_db
    def test_get_absolute_url(self, book):
        assert book.get_absolute_url() == reverse("book_detail", args=[book.pk])

    @pytest.mark.django_db
    def test_added_by(self, book, user_1):
        assert book.added_by == user_1
        assert list(user_1.added_books.all()) == [book]

    @pytest.mark.django_db
    def test_genres(self, book, genre):
        assert list(book.genres.all()) == [genre]

    @pytest.mark.django_db
    def test_optional_fields_may_be_empty(self, author, user_1):
        book = Book.objects.create(title="Без года", author=author, added_by=user_1)
        assert book.description == ""
        assert book.published_year is None
        assert book.genres.count() == 0

    @pytest.mark.django_db
    def test_is_pending_is_false_by_default(self, book):
        assert book.is_pending is False

    @pytest.mark.django_db
    def test_is_pending_book_keeps_only_title_and_author(self, author, user_1):
        """Книга из быстрой формы: заполнены только название и автор."""
        book = Book.objects.create(
            title="Быстрая книга",
            author=author,
            added_by=user_1,
            is_pending=True,
        )
        book.full_clean()
        assert book.is_pending is True

    @pytest.mark.django_db
    def test_kept_when_user_deleted(self, book, user_1):
        """Удалённый пользователь не уносит свои книги."""
        user_1.delete()
        book.refresh_from_db()
        assert Book.objects.filter(pk=book.pk).exists()
        assert book.added_by == user_1

    def test_added_by_set_null(self):
        """Если пользователя всё же сотрут из базы, книга останется без автора добавления."""
        field = Book._meta.get_field("added_by")
        assert field.null is True
        assert field.remote_field.on_delete is models.SET_NULL


class TestReview:
    """Модель отзыва."""

    @pytest.mark.django_db
    def test_str(self, review, user_2, book):
        assert str(review) == f"Отзыв {user_2} на «{book}»"

    @pytest.mark.django_db
    def test_repr(self, review):
        assert repr(review).startswith(f"Review by {review.reader} on {review.book}: ")

    @pytest.mark.django_db
    def test_created_at_filled_automatically(self, review):
        assert review.created_at is not None

    @pytest.mark.django_db
    def test_related_names(self, review, book, user_2):
        assert list(book.reviews.all()) == [review]
        assert list(user_2.reviews.all()) == [review]

    @pytest.mark.parametrize("rating", [1, 3, 5])
    @pytest.mark.django_db
    def test_valid_rating(self, book, user_1, rating):
        review = Review(book=book, reader=user_1, text="Текст", rating=rating)
        review.full_clean()

    @pytest.mark.parametrize("rating", [0, 6])
    @pytest.mark.django_db
    def test_invalid_rating(self, book, user_1, rating):
        review = Review(book=book, reader=user_1, text="Текст", rating=rating)
        with pytest.raises(ValidationError):
            review.full_clean()

    @pytest.mark.django_db
    def test_deleted_with_book(self, review, book):
        book.delete()
        assert not Review.objects.filter(pk=review.pk).exists()
        assert Review.all_objects.get(pk=review.pk).is_deleted is True



class TestReadingEntry:
    """Модель записи дневника."""

    @pytest.mark.django_db
    def test_str(self, entry):
        assert str(entry) == "«Мастер и Маргарита» — читаю"

    @pytest.mark.django_db
    def test_repr(self, entry, user_1, book):
        assert repr(entry) == f"ReadingEntry({user_1}, {book}, reading)"

    @pytest.mark.django_db
    def test_default_status_is_planned(self, book, user_1):
        entry = ReadingEntry.objects.create(reader=user_1, book=book)
        assert entry.status == ReadingStatus.PLANNED

    @pytest.mark.django_db
    def test_related_names(self, entry, book, user_1):
        assert list(book.entries.all()) == [entry]
        assert list(user_1.entries.all()) == [entry]

    @pytest.mark.django_db
    def test_timestamps_filled_automatically(self, entry):
        assert entry.created_at is not None
        assert entry.updated_at is not None

    @pytest.mark.django_db
    def test_book_may_be_read_several_times(self, book, user_1):
        """Ограничения уникальности нет — ведём историю прочтений."""
        first = ReadingEntry.objects.create(
            reader=user_1, book=book, status=ReadingStatus.READ
        )
        second = ReadingEntry.objects.create(
            reader=user_1, book=book, status=ReadingStatus.READING
        )
        assert book.entries.count() == 2
        # Свежая запись идёт первой: сортировка по убыванию даты добавления.
        assert list(book.entries.all()) == [second, first]

    @pytest.mark.django_db
    def test_deleted_with_book(self, entry, book):
        book.delete()
        assert not ReadingEntry.objects.filter(pk=entry.pk).exists()
        assert ReadingEntry.all_objects.get(pk=entry.pk).is_deleted is True

    @pytest.mark.django_db
    def test_finished_before_started_is_invalid(self, book, user_1):
        entry = ReadingEntry(
            reader=user_1,
            book=book,
            status=ReadingStatus.READ,
            started_at=datetime.date(2026, 5, 1),
            finished_at=datetime.date(2026, 4, 1),
        )
        with pytest.raises(ValidationError):
            entry.full_clean()

    @pytest.mark.django_db
    def test_same_dates_are_valid(self, book, user_1):
        """Книгу можно прочитать за один день."""
        entry = ReadingEntry(
            reader=user_1,
            book=book,
            status=ReadingStatus.READ,
            started_at=datetime.date(2026, 5, 1),
            finished_at=datetime.date(2026, 5, 1),
        )
        entry.full_clean()


class TestApplyStatus:
    """Автоматическая простановка дат при смене статуса."""

    today = datetime.date(2026, 5, 20)

    def test_planned_leaves_dates_empty(self):
        entry = ReadingEntry().apply_status(ReadingStatus.PLANNED, today=self.today)
        assert (entry.started_at, entry.finished_at) == (None, None)

    def test_reading_sets_started_at(self):
        entry = ReadingEntry().apply_status(ReadingStatus.READING, today=self.today)
        assert entry.started_at == self.today
        assert entry.finished_at is None

    @pytest.mark.parametrize("status", [ReadingStatus.READ, ReadingStatus.ABANDONED])
    def test_read_and_abandoned_set_both_dates(self, status):
        entry = ReadingEntry().apply_status(status, today=self.today)
        assert entry.started_at == self.today
        assert entry.finished_at == self.today

    def test_existing_dates_are_kept(self):
        """Проставленную руками дату автоматика не затирает."""
        started = datetime.date(2025, 1, 1)
        entry = ReadingEntry(started_at=started)
        entry.apply_status(ReadingStatus.READ, today=self.today)
        assert entry.started_at == started
        assert entry.finished_at == self.today

    @pytest.mark.django_db
    def test_today_by_default(self, book, user_1):
        entry = ReadingEntry(reader=user_1, book=book)
        entry.apply_status(ReadingStatus.READING)
        assert entry.started_at == timezone.localdate()
