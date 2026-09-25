"""Тесты команды наполнения базы демонстрационными данными."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.db.models import QuerySet
from django.utils import timezone

from bookshelf_app.management.demo_data import AUTHORS, GENRES, READERS, REVIEW_TEXTS
from bookshelf_app.models import Author, Book, EventLog, Genre, ReadingEntry, ReadingStatus, Review
from user_app.models import CustomUser

pytestmark = pytest.mark.django_db

BOOKS_COUNT = sum(len(author['books']) for author in AUTHORS)
PENDING_COUNT = sum(book.get('pending', False) for author in AUTHORS for book in author['books'])


def _gen_data(seed=1):
    call_command('gen_data', seed=seed, stdout=StringIO())


class TestGenData:
    """Каталог, читатели, дневники и отзывы."""

    def test_creates_catalog(self):
        _gen_data()
        assert Genre.objects.count() == len(GENRES)
        assert Author.objects.count() == len(AUTHORS)
        assert Book.objects.count() == BOOKS_COUNT
        assert Book.objects.filter(is_pending=True).count() == PENDING_COUNT

        book = Book.objects.get(title='Мастер и Маргарита')
        assert book.author.name == 'Михаил Афанасьевич Булгаков'
        assert book.published_year == 1966
        assert 'Фэнтези' in {genre.name for genre in book.genres.all()}
        assert book.added_by is not None

    def test_pending_books_are_drafts(self):
        _gen_data()
        for book in Book.objects.filter(is_pending=True):
            assert book.description == ''
            assert book.published_year is None
            assert not book.genres.exists()
            # Черновик заведён из дневника — он есть в дневнике добавившего.
            assert book.entries.filter(reader=book.added_by).exists()

    def test_readers_can_log_in(self, client):
        _gen_data()
        assert CustomUser.objects.count() == len(READERS)
        assert client.login(email=READERS[0]['email'], password='12345')

    def test_every_reader_has_diary(self):
        _gen_data()
        for reader in CustomUser.objects.all():
            assert reader.entries.count() >= 6

    def test_entry_dates_are_consistent(self):
        _gen_data()
        today = timezone.localdate()
        for entry in ReadingEntry.objects.all():
            if entry.status == ReadingStatus.PLANNED:
                assert entry.started_at is None and entry.finished_at is None
            elif entry.status == ReadingStatus.READING:
                assert entry.started_at <= today and entry.finished_at is None
            else:
                assert entry.started_at <= entry.finished_at <= today
            assert entry.created_at <= timezone.now()

    def test_reviews_follow_reading(self):
        _gen_data()
        assert Review.objects.exists()
        for review in Review.objects.all():
            finished = review.reader.entries.filter(
                book=review.book, status__in=(ReadingStatus.READ, ReadingStatus.ABANDONED),
            )
            assert finished.exists()
            assert review.text in REVIEW_TEXTS[review.rating]
            assert timezone.localdate(review.created_at) >= finished.earliest('finished_at').finished_at

    def test_repeat_run_does_not_duplicate(self):
        _gen_data(seed=1)
        entries, reviews = ReadingEntry.objects.count(), Review.objects.count()
        _gen_data(seed=2)
        assert Genre.objects.count() == len(GENRES)
        assert Author.objects.count() == len(AUTHORS)
        assert Book.objects.count() == BOOKS_COUNT
        assert CustomUser.objects.count() == len(READERS)
        assert ReadingEntry.objects.count() == entries
        assert Review.objects.count() == reviews

    def test_new_reader_gets_existing_books(self):
        """Читателя, которого нет в базе, команда заведёт — с дневником по уже созданным книгам."""
        _gen_data(seed=1)
        # Физическое удаление в обход мягкого: мягко удалённого команда считает существующим.
        QuerySet.delete(CustomUser.all_objects.filter(email=READERS[0]['email']))
        _gen_data(seed=2)
        reader = CustomUser.objects.get(email=READERS[0]['email'])
        assert reader.entries.count() >= 6
        assert Book.objects.count() == BOOKS_COUNT

    def test_does_not_write_event_log(self):
        _gen_data()
        assert not EventLog.objects.exists()
