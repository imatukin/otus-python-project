"""Дневник читателя: его записи, разложенные по колонкам статусов.

Записей об одной книге у читателя может быть несколько (перечитывал). В колонку книга
попадает по статусу **последней** записи, а более ранние записи — её история прочтений.

Здесь же — смена статуса кнопками: какие переходы разрешены и когда вместо правки
последней записи заводится новая (книгу начали перечитывать).
"""

from dataclasses import dataclass, field

from django.db.models import OuterRef, Subquery

from .models import ReadingEntry, ReadingStatus

# Порядок колонок на главной и их заголовки: «Читаю сейчас» важнее всего — оно первое.
COLUMNS = (
    (ReadingStatus.READING, 'Читаю сейчас'),
    (ReadingStatus.PLANNED, 'Хочу прочитать'),
    (ReadingStatus.READ, 'Прочитано'),
    (ReadingStatus.ABANDONED, 'Брошено'),
)

# Статусы, которыми прочтение заканчивается: следующий шаг после них — уже новое прочтение.
FINISHED = (ReadingStatus.READ, ReadingStatus.ABANDONED)

# Куда можно перевести книгу из текущего статуса последней записи (None — книги в дневнике нет).
TRANSITIONS = {
    None: (ReadingStatus.PLANNED, ReadingStatus.READING, ReadingStatus.READ),
    ReadingStatus.PLANNED: (ReadingStatus.READING, ReadingStatus.READ),
    ReadingStatus.READING: (ReadingStatus.READ, ReadingStatus.ABANDONED),
    ReadingStatus.READ: (ReadingStatus.PLANNED, ReadingStatus.READING),
    ReadingStatus.ABANDONED: (ReadingStatus.PLANNED, ReadingStatus.READING),
}

# Надписи на кнопках: «Бросил», а не «Брошено» — кнопка говорит, что делает читатель.
ACTION_LABELS = {
    ReadingStatus.PLANNED: 'Хочу прочитать',
    ReadingStatus.READING: 'Читаю',
    ReadingStatus.READ: 'Прочитано',
    ReadingStatus.ABANDONED: 'Бросил',
}


class StatusTransitionError(ValueError):
    """Из текущего статуса в запрошенный перейти нельзя."""


@dataclass(frozen=True)
class StatusAction:
    """Кнопка смены статуса: какой статус ставит и что на ней написано."""

    status: str
    label: str


def status_actions(current):
    """Кнопки смены статуса для книги, последняя запись о которой в статусе `current`."""
    actions = []
    for status in TRANSITIONS[current]:
        label = ACTION_LABELS[status]
        if current in FINISHED and status == ReadingStatus.READING:
            label = 'Перечитать'
        actions.append(StatusAction(status, label))
    return actions


def latest_entry(reader, book):
    """Последняя неудалённая запись читателя о книге или None."""
    return (
        ReadingEntry.objects.filter(reader=reader, book=book)
        .order_by('-created_at', '-pk')
        .first()
    )


def with_diary_status(queryset, reader):
    """Добавляет к выборке книг `diary_status` — статус последней записи читателя (или None)."""
    latest = (
        ReadingEntry.objects.filter(reader=reader, book=OuterRef('pk'))
        .order_by('-created_at', '-pk')
        .values('status')[:1]
    )
    return queryset.annotate(diary_status=Subquery(latest))


def change_status(reader, book, status, today=None):
    """Переводит книгу в дневнике читателя в статус `status` и возвращает запись.

    Пока прочтение не закончено, меняется последняя запись. Если оно уже закончено
    (прочитано или брошено), а книгу снова хотят читать — заводится новая запись,
    старая остаётся в истории прочтений.
    """
    entry = latest_entry(reader, book)
    current = entry.status if entry else None
    if status not in TRANSITIONS[current]:
        raise StatusTransitionError(f'Нельзя перейти из статуса {current!r} в {status!r}.')

    if entry is None or current in FINISHED:
        entry = ReadingEntry(reader=reader, book=book)
    entry.apply_status(status, today=today)
    entry.save()
    return entry


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

    @property
    def actions(self):
        """Кнопки смены статуса на карточке книги."""
        return status_actions(self.entry.status)


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
