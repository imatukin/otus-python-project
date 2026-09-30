"""Тесты раздела «Что почитать»: сигналы, вкус читателя, подборка и её страница."""

import pytest
from django.urls import reverse

from bookshelf_app.models import Author, Book, ReadingEntry, ReadingStatus, Review
from bookshelf_app.recommendations import (
    ABANDONED_SIGNAL,
    READ_SIGNAL,
    Taste,
    book_signals,
    recommend,
)
from bookshelf_app.tests.test_templates import get_soup, status_buttons, text_of
from bookshelf_app.views import CATALOG_PAGE_SIZE, with_book_stats

pytestmark = pytest.mark.django_db


def make_book(title, author, *genres, **fields):
    """Книга с жанрами."""
    book = Book.objects.create(title=title, author=author, **fields)
    book.genres.add(*genres)
    return book


def rate(reader, book, *ratings):
    """Отзывы читателя на книгу с указанными оценками."""
    for rating in ratings:
        Review.objects.create(book=book, reader=reader, text="Отзыв.", rating=rating)


def mark(reader, book, *statuses):
    """Записи дневника читателя о книге — по одной на статус, в указанном порядке."""
    for status in statuses:
        ReadingEntry.objects.create(reader=reader, book=book, status=status)


def recommended(reader=None):
    """Названия книг подборки по порядку."""
    books, _ = recommend(with_book_stats(Book.objects.all()), reader)
    return [book.title for book in books]


class TestBookSignals:
    """Сигналы книг: отзывы, а без них — дневник."""

    def test_rating_minus_neutral(self, user_1, book):
        rate(user_1, book, 5)
        assert book_signals(user_1) == {book.pk: 2}

    def test_reviews_are_averaged(self, user_1, book):
        rate(user_1, book, 4, 5)
        assert book_signals(user_1) == {book.pk: 1.5}

    def test_low_rating_is_negative(self, user_1, book):
        rate(user_1, book, 1)
        assert book_signals(user_1) == {book.pk: -2}

    def test_read_without_review(self, user_1, book):
        mark(user_1, book, ReadingStatus.READ)
        assert book_signals(user_1) == {book.pk: READ_SIGNAL}

    def test_abandoned(self, user_1, book):
        mark(user_1, book, ReadingStatus.ABANDONED)
        assert book_signals(user_1) == {book.pk: ABANDONED_SIGNAL}

    def test_abandoned_then_read(self, user_1, book):
        mark(user_1, book, ReadingStatus.ABANDONED, ReadingStatus.READ)
        assert book_signals(user_1) == {book.pk: READ_SIGNAL}

    def test_review_beats_diary(self, user_1, book):
        mark(user_1, book, ReadingStatus.ABANDONED)
        rate(user_1, book, 4)
        assert book_signals(user_1) == {book.pk: 1}

    @pytest.mark.parametrize("status", [ReadingStatus.PLANNED, ReadingStatus.READING])
    def test_unfinished_gives_no_signal(self, user_1, book, status):
        mark(user_1, book, status)
        assert not book_signals(user_1)

    def test_only_own_activity(self, user_1, user_2, book):
        rate(user_2, book, 5)
        mark(user_2, book, ReadingStatus.READ)
        assert not book_signals(user_1)

    def test_deleted_review_and_entry_ignored(self, user_1, book):
        rate(user_1, book, 5)
        mark(user_1, book, ReadingStatus.READ)
        Review.objects.all().delete()
        ReadingEntry.objects.all().delete()
        assert not book_signals(user_1)

    def test_deleted_book_ignored(self, user_1, book):
        rate(user_1, book, 5)
        book.delete()
        # Отзыв удаляется вместе с книгой — проверяем и случай, когда его восстановили отдельно.
        Review.all_objects.update(is_deleted=False)
        assert not book_signals(user_1)


class TestTaste:
    """Вкус читателя и балл книги."""

    def test_empty(self, book):
        taste = Taste({})
        assert not taste
        assert taste.score(book) == (0, None)

    def test_author_weight(self, author, genre, genre_2):
        liked = make_book("Любимая", author, genre)
        taste = Taste({liked.pk: 2})
        candidate = make_book("Кандидат", author, genre_2)
        assert taste.score(candidate) == (4, f"Вам понравились книги автора: {author.name}")

    def test_author_taste_is_mean(self, author):
        good = make_book("Хорошая", author)
        bad = make_book("Плохая", author)
        taste = Taste({good.pk: 2, bad.pk: -1})
        assert taste.score(make_book("Кандидат", author))[0] == 1

    def test_genre_mean_over_known_genres(self, author, author_2, genre, genre_2):
        """Жанры без сигналов в среднее не идут; вклад жанра — с весом 1."""
        roman = make_book("Роман", author, genre)
        taste = Taste({roman.pk: 2})
        candidate = make_book("Кандидат", author_2, genre, genre_2)
        assert taste.score(candidate) == (2, f"Вы любите жанр «{genre.name}»")

    def test_genre_mean_over_book_genres(self, author, author_2, genre, genre_2):
        liked = make_book("Нравится", author, genre)
        disliked = make_book("Не нравится", author, genre_2)
        taste = Taste({liked.pk: 2, disliked.pk: -1})
        candidate = make_book("Кандидат", author_2, genre, genre_2)
        assert taste.score(candidate) == (0.5, f"Вы любите жанр «{genre.name}»")

    def test_negative_genre_has_no_reason(self, author, author_2, genre):
        disliked = make_book("Не нравится", author, genre)
        taste = Taste({disliked.pk: -2})
        assert taste.score(make_book("Кандидат", author_2, genre)) == (-2, None)

    def test_disliked_author_reason_from_genre(self, author, genre, genre_2):
        """Автор не понравился, а жанр — да: объясняем жанром."""
        bad = make_book("Плохая", author, genre)
        good = make_book("Хорошая", Author.objects.create(name="Другой"), genre_2)
        taste = Taste({bad.pk: -1, good.pk: 2})
        score, reason = taste.score(make_book("Кандидат", author, genre_2))
        assert score == 0
        assert reason == f"Вы любите жанр «{genre_2.name}»"


class TestRecommend:
    """Какие книги попадают в подборку и в каком порядке."""

    def test_guest_gets_popular_books(self, user_1, user_2, author):
        top = make_book("Лучшая", author)
        read_often = make_book("Читают", author)
        make_book("Без оценок", author)
        rate(user_1, top, 5)
        rate(user_2, read_often, 3)
        mark(user_1, read_often, ReadingStatus.READ)
        mark(user_2, read_often, ReadingStatus.READ)
        books, taste = recommend(with_book_stats(Book.objects.all()))
        assert [book.title for book in books] == ["Лучшая", "Читают", "Без оценок"]
        assert not taste
        assert all(book.recommendation_reason is None for book in books)

    def test_ties_by_readings_then_title(self, user_1, author):
        make_book("Б", author)
        make_book("А", author)
        read = make_book("В", author)
        mark(user_1, read, ReadingStatus.READ)
        assert recommended() == ["В", "А", "Б"]

    def test_excludes_pending(self, author):
        make_book("Черновик", author, is_pending=True)
        make_book("Готовая", author)
        assert recommended() == ["Готовая"]

    def test_excludes_deleted(self, author):
        make_book("Удалённая", author).delete()
        assert recommended() == []

    @pytest.mark.parametrize("status", list(ReadingStatus))
    def test_excludes_diary_books(self, user_1, author, author_2, status):
        mark(user_1, make_book("В дневнике", author), status)
        # Другой автор: брошенная книга иначе утянула бы «Новую» в минус.
        make_book("Новая", author_2)
        assert recommended(user_1) == ["Новая"]

    def test_excludes_reviewed_books(self, user_1, author):
        rate(user_1, make_book("С отзывом", author), 3)
        make_book("Новая", author)
        assert recommended(user_1) == ["Новая"]

    def test_deleted_diary_entry_returns_book(self, user_1, author):
        mark(user_1, make_book("Была в дневнике", author), ReadingStatus.PLANNED)
        ReadingEntry.objects.all().delete()
        assert recommended(user_1) == ["Была в дневнике"]

    def test_other_reader_diary_does_not_exclude(self, user_1, user_2, author):
        mark(user_2, make_book("Чужая", author), ReadingStatus.READ)
        assert recommended(user_1) == ["Чужая"]

    def test_personal_order(self, user_1, author, author_2, genre, genre_2):
        """Любимый автор выше любимого жанра, нелюбимый автор — вне подборки."""
        rate(user_1, make_book("Прочитанная", author, genre), 5)
        rate(user_1, make_book("Скучная", author_2, genre_2), 2)
        make_book("Того же автора", author, genre_2)
        make_book("Того же жанра", Author.objects.create(name="Третий"), genre)
        make_book("Без сигналов", Author.objects.create(name="Четвёртый"))
        make_book("Нелюбимый автор", author_2)
        assert recommended(user_1) == ["Того же автора", "Того же жанра", "Без сигналов"]

    def test_score_and_reason_on_books(self, user_1, author, genre):
        rate(user_1, make_book("Прочитанная", author, genre), 5)
        make_book("Кандидат", author, genre)
        books, taste = recommend(with_book_stats(Book.objects.all()), user_1)
        assert taste
        assert books[0].recommendation_score == 6
        assert books[0].recommendation_reason == f"Вам понравились книги автора: {author.name}"

    def test_popularity_breaks_ties(self, user_1, user_2, author, author_2):
        rate(user_1, make_book("Прочитанная", author), 5)
        make_book("Непопулярная", author_2)
        rate(user_2, make_book("Популярная", author_2), 5)
        assert recommended(user_1) == ["Популярная", "Непопулярная"]


class TestRecommendationsView:
    """Страница «Что почитать»."""

    url = reverse("recommendations")

    def test_guest(self, client, book):
        soup = get_soup(client.get(self.url))
        assert text_of(soup.h1) == "Что почитать"
        assert [text_of(card.h2.a) for card in soup.select(".book-card")] == [book.title]
        assert "Зарегистрируйтесь" in text_of(soup.select_one(".recommendations-hint"))
        assert not status_buttons(soup)

    def test_breadcrumbs(self, client):
        response = client.get(self.url)
        assert response.context["breadcrumbs"][-1] == {"title": "Что почитать"}

    def test_menu_item_active(self, client):
        link = get_soup(client.get(self.url)).select_one(f'.nav-link[href="{self.url}"]')
        assert "active" in link["class"]

    def test_reader_without_taste(self, auth_client, book):  # pylint: disable=unused-argument
        response = auth_client.get(self.url)
        assert response.context["personal"] is False
        hint = text_of(get_soup(response).select_one(".recommendations-hint"))
        assert hint.startswith("Пока это просто популярные книги.")

    def test_personal(self, auth_client, user_1, author, genre):
        rate(user_1, make_book("Прочитанная", author, genre), 5)
        make_book("Кандидат", author, genre)
        response = auth_client.get(self.url)
        assert response.context["personal"] is True
        soup = get_soup(response)
        card = soup.select_one(".book-card")
        assert text_of(card.h2.a) == "Кандидат"
        assert text_of(card.select_one(".recommendation-reason")) == (
            f"Вам понравились книги автора: {author.name}"
        )
        assert text_of(soup.select_one(".recommendations-hint")).startswith("Книги подобраны")

    def test_status_buttons(self, auth_client, book):
        card = get_soup(auth_client.get(self.url)).select_one(".book-card")
        assert status_buttons(card) == [
            ("Хочу прочитать", "planned"), ("Читаю", "reading"), ("Прочитано", "read")
        ]
        assert card.select_one('input[name="next"]')["value"] == self.url
        assert card.select_one("form")["action"] == reverse("book_status", args=[book.pk])

    def test_book_leaves_after_status(self, auth_client, book):
        auth_client.post(reverse("book_status", args=[book.pk]), {"status": "planned"})
        assert not get_soup(auth_client.get(self.url)).select(".book-card")

    def test_empty(self, client):
        alert = get_soup(client.get(self.url)).select_one(".alert-info")
        assert text_of(alert) == "Предложить пока нечего. Загляните в каталог."

    def test_pagination(self, client, author):
        for number in range(CATALOG_PAGE_SIZE + 1):
            make_book(f"Том {number:02}", author)
        soup = get_soup(client.get(self.url, {"page": 2}))
        assert len(soup.select(".book-card")) == 1
        assert text_of(soup.select_one(".badge.bg-secondary")) == f"Всего: {CATALOG_PAGE_SIZE + 1}"
        assert client.get(self.url, {"page": 3}).status_code == 404
