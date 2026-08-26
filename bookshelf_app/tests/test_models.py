"""Тесты моделей каталога книг."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse

from bookshelf_app.models import Book, Genre, Review


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
    def test_deleted_with_user(self, book, user_1):
        """Книги удаляются вместе с пользователем (CASCADE)."""
        user_1.delete()
        assert not Book.objects.filter(pk=book.pk).exists()


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
