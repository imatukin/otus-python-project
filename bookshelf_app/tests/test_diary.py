"""Тесты сборки дневника читателя по колонкам статусов."""

import datetime

import pytest

from bookshelf_app.diary import COLUMNS, build_diary
from bookshelf_app.models import ReadingEntry, ReadingStatus

pytestmark = pytest.mark.django_db


def column(columns, status):
    """Колонка с нужным статусом."""
    return next(item for item in columns if item.status == status)


def titles(columns, status):
    """Названия книг в колонке."""
    return [item.book.title for item in column(columns, status).books]


class TestBuildDiary:
    """Раскладка записей по колонкам."""

    def test_columns_order_and_titles(self, user_1):
        columns = build_diary(user_1)
        assert [(item.status, item.title) for item in columns] == [
            (ReadingStatus.READING, "Читаю сейчас"),
            (ReadingStatus.PLANNED, "Хочу прочитать"),
            (ReadingStatus.READ, "Прочитано"),
            (ReadingStatus.ABANDONED, "Брошено"),
        ]

    def test_all_statuses_have_column(self):
        assert {status for status, _ in COLUMNS} == set(ReadingStatus.values)

    def test_empty_diary(self, user_1):
        assert all(item.count == 0 for item in build_diary(user_1))

    def test_entries_by_status(self, user_1, entries, book, book_of_user_2):  # pylint: disable=unused-argument
        columns = build_diary(user_1)
        assert titles(columns, ReadingStatus.READ) == [book.title]
        assert titles(columns, ReadingStatus.PLANNED) == [book_of_user_2.title]
        assert column(columns, ReadingStatus.READING).count == 0

    def test_other_readers_not_included(self, user_2, entries):  # pylint: disable=unused-argument
        assert all(item.count == 0 for item in build_diary(user_2))

    def test_latest_entry_wins(self, user_1, book):
        """Перечитываемая книга — в «Читаю сейчас», прошлое прочтение уходит в историю."""
        first = ReadingEntry.objects.create(reader=user_1, book=book, status=ReadingStatus.READ)
        second = ReadingEntry.objects.create(reader=user_1, book=book, status=ReadingStatus.READING)
        columns = build_diary(user_1)

        assert column(columns, ReadingStatus.READ).count == 0
        [diary_book] = column(columns, ReadingStatus.READING).books
        assert diary_book.entry == second
        assert diary_book.history == [first]
        assert diary_book.readings_count == 2
        assert diary_book.book == book

    def test_history_newest_first(self, user_1, book):
        created = [
            ReadingEntry.objects.create(reader=user_1, book=book, status=status)
            for status in (ReadingStatus.ABANDONED, ReadingStatus.READ, ReadingStatus.PLANNED)
        ]
        [diary_book] = column(build_diary(user_1), ReadingStatus.PLANNED).books
        assert diary_book.history == [created[1], created[0]]

    def test_same_created_at_uses_pk(self, user_1, book):
        """Записи с одинаковым временем создания различаем по pk — позже созданная новее."""
        moment = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        first = ReadingEntry.objects.create(reader=user_1, book=book, status=ReadingStatus.READ)
        second = ReadingEntry.objects.create(reader=user_1, book=book, status=ReadingStatus.READING)
        ReadingEntry.objects.filter(pk__in=[first.pk, second.pk]).update(created_at=moment)
        [diary_book] = column(build_diary(user_1), ReadingStatus.READING).books
        assert diary_book.entry == second

    def test_books_in_column_newest_first(self, user_1, books):
        for item in books:
            ReadingEntry.objects.create(reader=user_1, book=item, status=ReadingStatus.PLANNED)
        assert titles(build_diary(user_1), ReadingStatus.PLANNED) == [item.title for item in reversed(books)]

    def test_deleted_entry_skipped(self, user_1, entry):
        entry.delete()
        assert all(item.count == 0 for item in build_diary(user_1))

    def test_deleted_latest_entry_reveals_previous(self, user_1, book):
        """Удалил последнюю запись — книга возвращается в колонку предыдущей."""
        ReadingEntry.objects.create(reader=user_1, book=book, status=ReadingStatus.READ)
        ReadingEntry.objects.create(reader=user_1, book=book, status=ReadingStatus.READING).delete()
        assert titles(build_diary(user_1), ReadingStatus.READ) == [book.title]

    def test_entry_of_deleted_book_skipped(self, user_1, entry, book):
        """Даже если запись жива (например, админ восстановил только её), удалённой книги нет."""
        book.delete()
        ReadingEntry.all_objects.filter(pk=entry.pk).update(is_deleted=False, deleted_at=None)
        assert all(item.count == 0 for item in build_diary(user_1))

    def test_query_count(self, user_1, books, django_assert_num_queries):
        for item in books:
            ReadingEntry.objects.create(reader=user_1, book=item)
        with django_assert_num_queries(1):
            columns = build_diary(user_1)
            names = [diary_book.book.author.name for item in columns for diary_book in item.books]
        assert len(names) == len(books)
