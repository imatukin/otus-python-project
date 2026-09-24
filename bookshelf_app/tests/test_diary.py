"""Тесты сборки дневника читателя по колонкам статусов."""

import datetime

import pytest

from bookshelf_app.diary import (
    COLUMNS,
    TRANSITIONS,
    StatusTransitionError,
    build_diary,
    change_status,
    latest_entry,
    status_actions,
    with_diary_status,
)
from bookshelf_app.models import Book, ReadingEntry, ReadingStatus

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

    def test_actions_of_diary_book(self, user_1, entry):  # pylint: disable=unused-argument
        [diary_book] = column(build_diary(user_1), ReadingStatus.READING).books
        assert [action.status for action in diary_book.actions] == [ReadingStatus.READ, ReadingStatus.ABANDONED]


def labels(current):
    """Надписи на кнопках смены статуса."""
    return [action.label for action in status_actions(current)]


class TestStatusActions:
    """Какие кнопки смены статуса показываем."""

    def test_all_statuses_have_transitions(self):
        assert set(TRANSITIONS) == {None, *ReadingStatus.values}

    def test_book_not_in_diary(self):
        assert labels(None) == ["Хочу прочитать", "Читаю", "Прочитано"]

    def test_planned(self):
        assert labels(ReadingStatus.PLANNED) == ["Читаю", "Прочитано"]

    def test_reading(self):
        assert labels("reading") == ["Прочитано", "Бросил"]

    @pytest.mark.parametrize("status", [ReadingStatus.READ, ReadingStatus.ABANDONED])
    def test_finished_offers_rereading(self, status):
        assert labels(status) == ["Хочу прочитать", "Перечитать"]

    def test_action_status_values(self):
        assert [action.status for action in status_actions(None)] == [
            ReadingStatus.PLANNED, ReadingStatus.READING, ReadingStatus.READ,
        ]


class TestLatestEntry:
    """Последняя запись читателя о книге."""

    def test_no_entries(self, user_1, book):
        assert latest_entry(user_1, book) is None

    def test_newest_wins(self, user_1, book):
        ReadingEntry.objects.create(reader=user_1, book=book, status=ReadingStatus.READ)
        second = ReadingEntry.objects.create(reader=user_1, book=book, status=ReadingStatus.PLANNED)
        assert latest_entry(user_1, book) == second

    def test_deleted_skipped(self, user_1, book):
        first = ReadingEntry.objects.create(reader=user_1, book=book, status=ReadingStatus.READ)
        ReadingEntry.objects.create(reader=user_1, book=book, status=ReadingStatus.PLANNED).delete()
        assert latest_entry(user_1, book) == first

    def test_other_reader_ignored(self, user_2, entry, book):  # pylint: disable=unused-argument
        assert latest_entry(user_2, book) is None


class TestWithDiaryStatus:
    """Статус книги в дневнике прямо в выборке каталога."""

    def test_statuses(self, user_1, entries, book, book_of_user_2, books):  # pylint: disable=unused-argument
        statuses = {item.pk: item.diary_status for item in with_diary_status(Book.objects.all(), user_1)}
        assert statuses[book.pk] == ReadingStatus.READ
        assert statuses[book_of_user_2.pk] == ReadingStatus.PLANNED
        assert statuses[books[0].pk] is None

    def test_latest_entry_status(self, user_1, book):
        ReadingEntry.objects.create(reader=user_1, book=book, status=ReadingStatus.READ)
        ReadingEntry.objects.create(reader=user_1, book=book, status=ReadingStatus.READING)
        assert with_diary_status(Book.objects.all(), user_1).get().diary_status == ReadingStatus.READING

    def test_deleted_entry_ignored(self, user_1, entry):
        entry.delete()
        assert with_diary_status(Book.objects.all(), user_1).get().diary_status is None

    def test_other_reader(self, user_2, entry):  # pylint: disable=unused-argument
        assert with_diary_status(Book.objects.all(), user_2).get().diary_status is None


class TestChangeStatus:
    """Смена статуса книги кнопкой."""

    today = datetime.date(2026, 3, 1)

    def test_creates_entry(self, user_1, book):
        entry = change_status(user_1, book, ReadingStatus.PLANNED, today=self.today)
        assert entry.pk is not None
        assert (entry.reader, entry.book, entry.status) == (user_1, book, ReadingStatus.PLANNED)
        assert entry.started_at is None

    def test_reading_sets_start(self, user_1, book):
        entry = change_status(user_1, book, "reading", today=self.today)
        assert entry.started_at == self.today

    def test_updates_unfinished_entry(self, user_1, entry, book):
        changed = change_status(user_1, book, ReadingStatus.READ, today=self.today)
        assert changed.pk == entry.pk
        assert ReadingEntry.objects.count() == 1
        changed.refresh_from_db()
        assert changed.status == ReadingStatus.READ
        assert changed.started_at == entry.started_at
        assert changed.finished_at == self.today

    @pytest.mark.parametrize("status", [ReadingStatus.PLANNED, ReadingStatus.READING])
    def test_finished_starts_new_reading(self, user_1, book, status):
        old = ReadingEntry.objects.create(reader=user_1, book=book, status=ReadingStatus.READ)
        new = change_status(user_1, book, status, today=self.today)
        assert new.pk != old.pk
        old.refresh_from_db()
        assert old.status == ReadingStatus.READ
        [diary_book] = column(build_diary(user_1), status).books
        assert diary_book.history == [old]

    @pytest.mark.parametrize(
        ("current", "status"),
        [
            (None, ReadingStatus.ABANDONED),
            (ReadingStatus.PLANNED, ReadingStatus.PLANNED),
            (ReadingStatus.READING, ReadingStatus.PLANNED),
            (ReadingStatus.READ, ReadingStatus.ABANDONED),
            (None, "nonsense"),
            (None, None),
        ],
    )
    def test_forbidden_transition(self, user_1, book, current, status):
        if current:
            ReadingEntry.objects.create(reader=user_1, book=book, status=current)
        count = ReadingEntry.objects.count()
        with pytest.raises(StatusTransitionError):
            change_status(user_1, book, status)
        assert ReadingEntry.objects.count() == count

    def test_other_readers_entry_untouched(self, user_2, entry, book):
        change_status(user_2, book, ReadingStatus.PLANNED)
        entry.refresh_from_db()
        assert entry.status == ReadingStatus.READING
        assert ReadingEntry.objects.filter(reader=user_2).count() == 1
