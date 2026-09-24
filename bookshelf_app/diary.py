"""Дневник читателя: его записи, разложенные по колонкам статусов.

Записей об одной книге у читателя может быть несколько (перечитывал). В колонку книга
попадает по статусу **последней** записи, а более ранние записи — её история прочтений.
"""

from dataclasses import dataclass, field

from .models import ReadingEntry, ReadingStatus

# Порядок колонок на главной и их заголовки: «Читаю сейчас» важнее всего — оно первое.
COLUMNS = (
    (ReadingStatus.READING, 'Читаю сейчас'),
    (ReadingStatus.PLANNED, 'Хочу прочитать'),
    (ReadingStatus.READ, 'Прочитано'),
    (ReadingStatus.ABANDONED, 'Брошено'),
)


@dataclass
class DiaryBook:
    """Книга в дневнике: последняя запись о ней и прошлые записи, от новых к старым."""

    entry: ReadingEntry
    history: list = field(default_factory=list)

    @property
    def book(self):
        """Книга, о которой запись."""
        return self.entry.book

    @property
    def readings_count(self):
        """Сколько всего записей о книге у читателя, включая текущую."""
        return len(self.history) + 1


@dataclass
class DiaryColumn:
    """Колонка дневника — все книги с одним статусом."""

    status: str
    title: str
    books: list = field(default_factory=list)

    @property
    def count(self):
        """Счётчик в заголовке колонки."""
        return len(self.books)


def build_diary(reader):
    """Колонки дневника читателя в порядке `COLUMNS`.

    Удалённые записи и записи об удалённых книгах в дневник не попадают.
    """
    entries = (
        ReadingEntry.objects.filter(reader=reader, book__is_deleted=False)
        .select_related('book__author')
        # pk — на случай записей, созданных в одну и ту же секунду.
        .order_by('-created_at', '-pk')
    )

    books = {}
    for entry in entries:
        if entry.book_id in books:
            books[entry.book_id].history.append(entry)
        else:
            books[entry.book_id] = DiaryBook(entry)

    columns = {status: DiaryColumn(status, title) for status, title in COLUMNS}
    # dict хранит порядок вставки: внутри колонки книги идут от свежих записей к старым.
    for diary_book in books.values():
        columns[diary_book.entry.status].books.append(diary_book)
    return list(columns.values())
