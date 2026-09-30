"""Раздел «Что почитать»: книги, подобранные по оценкам и дневнику читателя.

Сначала для каждой книги, о которой читатель что-то сказал, считается **сигнал**:
средняя оценка его отзывов минус 3 (5 → +2 … 1 → −2), а если отзывов нет — дневник:
прочитал — слабый плюс, бросил — минус. Из сигналов книг складывается **вкус** —
средний сигнал по каждому автору и жанру. Балл книги-кандидата —
`AUTHOR_WEIGHT × вкус к автору + GENRE_WEIGHT × средний вкус к её жанрам`
(жанры, о которых читатель ничего не говорил, в среднее не идут).

Кандидаты — книги, которых нет ни в дневнике читателя, ни в его отзывах; черновики не
предлагаем. Книги с отрицательным баллом не показываем. Равные баллы — и весь список
для гостя или читателя без оценок — упорядочены по популярности: средней оценке
и числу прочтений.
"""

from collections import defaultdict
from statistics import mean

from .models import Book, ReadingEntry, ReadingStatus, Review

# Автор говорит о вкусе больше, чем жанр: жанров у книги несколько и они шире.
AUTHOR_WEIGHT = 2
GENRE_WEIGHT = 1

# Сигнал книги без отзыва: прочитал до конца — слабый плюс, бросил — минус.
READ_SIGNAL = 0.5
ABANDONED_SIGNAL = -1

# Оценка, которая не говорит ни «за», ни «против».
NEUTRAL_RATING = 3


def book_signals(reader):
    """Сигналы книг читателя: {id книги: число}, плюс — понравилась, минус — нет.

    Отзыв важнее дневника: если отзывы на книгу есть, записи о ней не учитываются.
    Удалённые отзывы, записи и книги не считаются.
    """
    ratings = defaultdict(list)
    for book_id, rating in Review.objects.filter(reader=reader, book__is_deleted=False).values_list(
        "book_id", "rating"
    ):
        ratings[book_id].append(rating)
    signals = {book_id: mean(values) - NEUTRAL_RATING for book_id, values in ratings.items()}

    statuses = defaultdict(set)
    for book_id, status in ReadingEntry.objects.filter(
        reader=reader,
        book__is_deleted=False,
        status__in=(ReadingStatus.READ, ReadingStatus.ABANDONED),
    ).values_list("book_id", "status"):
        statuses[book_id].add(status)
    for book_id, book_statuses in statuses.items():
        if book_id not in signals:
            # Бросил, а потом всё-таки дочитал — книга скорее понравилась.
            signals[book_id] = READ_SIGNAL if ReadingStatus.READ in book_statuses else ABANDONED_SIGNAL
    return signals


class Taste:
    """Вкус читателя: средний сигнал его книг по каждому автору и жанру."""

    def __init__(self, signals):
        by_author = defaultdict(list)
        by_genre = defaultdict(list)
        books = Book.objects.filter(pk__in=signals).select_related("author").prefetch_related("genres")
        for book in books:
            signal = signals[book.pk]
            by_author[book.author].append(signal)
            for genre in book.genres.all():
                by_genre[genre].append(signal)
        self.authors = {author.pk: (author, mean(values)) for author, values in by_author.items()}
        self.genres = {genre.pk: (genre, mean(values)) for genre, values in by_genre.items()}

    def __bool__(self):
        """Вкус есть, если читатель оценил или дочитал / бросил хоть одну книгу."""
        return bool(self.authors)

    def score(self, book):
        """Балл книги и объяснение, почему она предложена (или None)."""
        author, author_taste = self.authors.get(book.author_id, (None, 0))
        genre_tastes = [self.genres[genre.pk] for genre in book.genres.all() if genre.pk in self.genres]
        genre_taste = mean(taste for _, taste in genre_tastes) if genre_tastes else 0
        score = AUTHOR_WEIGHT * author_taste + GENRE_WEIGHT * genre_taste

        reason = None
        if author_taste > 0:
            reason = f"Вам понравились книги автора: {author.name}"
        else:
            liked = [(taste, genre.name) for genre, taste in genre_tastes if taste > 0]
            if liked:
                reason = f"Вы любите жанр «{max(liked)[1]}»"
        return score, reason


def popularity(book):
    """Ключ сортировки по популярности: сначала выше средняя оценка, потом больше прочтений."""
    return -(book.avg_rating or 0), -book.readings_count


def recommend(books, reader=None):
    """Книги из выборки `books`, отсортированные по релевантности для читателя.

    `books` должна нести аннотации `avg_rating` и `readings_count` (`views.with_book_stats`).
    Каждой книге проставляются `recommendation_score` и `recommendation_reason`.
    Гостю (`reader=None`) и читателю без оценок — просто популярные книги.
    Возвращает пару: список книг и `Taste` (ложный, если подборка не личная).
    """
    books = books.filter(is_pending=False).select_related("author").prefetch_related("genres")
    signals = {}
    if reader is not None:
        signals = book_signals(reader)
        diary = ReadingEntry.objects.filter(reader=reader).values("book_id")
        books = books.exclude(pk__in=diary).exclude(pk__in=signals)
    taste = Taste(signals)

    result = []
    for book in books:
        book.recommendation_score, book.recommendation_reason = taste.score(book)
        if book.recommendation_score >= 0:
            result.append(book)
    result.sort(key=lambda book: (-book.recommendation_score, *popularity(book), book.title, book.pk))
    return result, taste
