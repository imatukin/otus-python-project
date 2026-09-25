"""Команда наполнения базы демонстрационными данными."""

import datetime
import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from bookshelf_app.management.demo_data import AUTHORS, GENRES, READERS, REVIEW_TEXTS
from bookshelf_app.models import Author, Book, Genre, ReadingEntry, ReadingStatus, Review

User = get_user_model()

# Пароль у всех демонстрационных читателей одинаковый — чтобы можно было войти.
DEMO_PASSWORD = "12345"

# Сколько книг попадает в дневник одного читателя.
DIARY_SIZE = (6, 12)

# С какой вероятностью у книги в дневнике тот или иной статус.
STATUS_WEIGHTS = {
    ReadingStatus.READ: 45,
    ReadingStatus.PLANNED: 25,
    ReadingStatus.READING: 15,
    ReadingStatus.ABANDONED: 15,
}
MAX_READING = 3  # больше трёх книг одновременно читают редко

REREAD_CHANCE = 0.15
# Вероятность отзыва и распределение оценок: прочитанное хвалят чаще, брошенное — ругают.
REVIEW_CHANCE = {ReadingStatus.READ: 0.6, ReadingStatus.ABANDONED: 0.4}
RATING_WEIGHTS = {
    ReadingStatus.READ: {5: 40, 4: 35, 3: 18, 2: 7},
    ReadingStatus.ABANDONED: {3: 20, 2: 45, 1: 35},
}


def _moment(day, rnd):
    """Случайное время дня `day`, но не позже текущего момента — для полей с датой и временем."""
    moment = datetime.datetime.combine(day, datetime.time(rnd.randint(8, 23), rnd.randint(0, 59)))
    return min(timezone.make_aware(moment), timezone.now())


class Command(BaseCommand):
    """Заполняет базу демонстрационными данными: каталог, отзывы и дневники читателей.

    Каталог — настоящие книги и авторы, читатели — вымышленные. Повторный запуск ничего
    не дублирует: существующие жанры, авторы, книги и читатели пропускаются, дневники
    и отзывы заводятся только новым читателям.
    """

    help = "Наполнение базы демонстрационными данными: книги, авторы, читатели, дневники, отзывы"

    def add_arguments(self, parser):
        parser.add_argument(
            '--seed', type=int, default=None,
            help='Зерно генератора случайных чисел — для воспроизводимых дневников и отзывов.',
        )

    def handle(self, *args, **options):
        """Создаёт каталог, читателей, их дневники и отзывы в одной транзакции."""
        rnd = random.Random(options['seed'])
        today = timezone.localdate()

        with transaction.atomic():
            readers, new_readers = self._create_readers()
            genres = self._create_genres()
            books, pending = self._create_catalog(genres, readers, rnd)
            for reader in new_readers:
                self._create_diary(reader, books, pending.get(reader.pk, []), today, rnd)

        self.stdout.write(f"Пароль всех читателей: {DEMO_PASSWORD}")
        self.stdout.write("Закончено")

    def _create_readers(self):
        """Заводит читателей, которых ещё нет; возвращает всех и отдельно новых."""
        readers, new_readers = [], []
        for data in READERS:
            reader = User.all_objects.filter(email=data['email']).first()
            if reader is None:
                reader = User.objects.create_user(password=DEMO_PASSWORD, **data)
                new_readers.append(reader)
                self.stdout.write(f"Создан читатель {reader.display_name}")
            readers.append(reader)
        return readers, new_readers

    @staticmethod
    def _create_genres():
        """Заводит жанры; возвращает словарь «название — жанр»."""
        return {name: Genre.objects.get_or_create(name=name)[0] for name in GENRES}

    def _create_catalog(self, genres, readers, rnd):
        """Заводит авторов и книги.

        Возвращает законченные книги и словарь «pk читателя — его черновики»:
        черновик как будто заведён этим читателем из дневника и попадёт в его дневник.
        """
        books, pending = [], {}
        for data in AUTHORS:
            author, created = Author.all_objects.get_or_create(
                name=data['name'],
                defaults={'bio': data['bio'], 'birth_date': data['birth_date']},
            )
            if created:
                self.stdout.write(f"Создан автор {author.name}")

            for book_data in data['books']:
                is_pending = book_data.get('pending', False)
                added_by = rnd.choice(readers)
                book, created = Book.all_objects.get_or_create(
                    title=book_data['title'],
                    author=author,
                    defaults={
                        'description': book_data.get('description', ''),
                        'published_year': book_data.get('year'),
                        'is_pending': is_pending,
                        'added_by': added_by,
                    },
                )
                if not created:
                    continue
                if is_pending:
                    pending.setdefault(added_by.pk, []).append(book)
                    self.stdout.write(f"Создан черновик «{book.title}»")
                else:
                    book.genres.set(genres[name] for name in book_data['genres'])
                    books.append(book)
                    self.stdout.write(f"Создана книга «{book.title}»")
        # Книги, заведённые прошлыми запусками, тоже годятся для дневников новых читателей.
        known = {book.pk for book in books}
        books += Book.objects.filter(is_pending=False).exclude(pk__in=known)
        return books, pending

    def _create_diary(self, reader, books, drafts, today, rnd):
        """Заполняет дневник читателя записями в разных статусах и пишет отзывы."""
        chosen = rnd.sample(books, min(rnd.randint(*DIARY_SIZE), len(books)))
        reading = 0
        for book in chosen:
            status = rnd.choices(list(STATUS_WEIGHTS), weights=list(STATUS_WEIGHTS.values()))[0]
            if status == ReadingStatus.READING:
                reading += 1
                if reading > MAX_READING:
                    status = ReadingStatus.PLANNED
            entry = self._add_entry(reader, book, status, today, rnd)

            if status in REVIEW_CHANCE and rnd.random() < REVIEW_CHANCE[status]:
                self._add_review(reader, book, entry, today, rnd)

            # Прочитанное давно иногда перечитывают — это новая запись в истории.
            if (status == ReadingStatus.READ and entry.finished_at <= today - datetime.timedelta(days=60)
                    and rnd.random() < REREAD_CHANCE):
                self._add_entry(reader, book, ReadingStatus.READING, today, rnd)
                self.stdout.write(f"{reader.display_name} перечитывает «{book.title}»")

        # Черновики читатель завёл из дневника — значит, собирается их читать.
        for book in drafts:
            self._add_entry(reader, book, ReadingStatus.PLANNED, today, rnd)

    def _add_entry(self, reader, book, status, today, rnd):
        """Создаёт запись дневника с правдоподобными датами в прошлом."""
        days_ago = datetime.timedelta
        if status == ReadingStatus.PLANNED:
            started, added = None, today - days_ago(days=rnd.randint(0, 200))
        elif status == ReadingStatus.READING:
            started = added = today - days_ago(days=rnd.randint(0, 40))
        else:
            started = added = today - days_ago(days=rnd.randint(15, 900))

        entry = ReadingEntry(reader=reader, book=book)
        if status in (ReadingStatus.READ, ReadingStatus.ABANDONED):
            longest = 60 if status == ReadingStatus.READ else 20
            entry.finished_at = min(started + days_ago(days=rnd.randint(3, longest)), today)
        entry.started_at = started
        entry.apply_status(status, today=started)
        entry.save()
        # created_at — auto_now_add, поэтому дату добавления в дневник ставим отдельно.
        entry.created_at = _moment(added, rnd)
        ReadingEntry.all_objects.filter(pk=entry.pk).update(created_at=entry.created_at)

        self.stdout.write(f"{reader.display_name}: «{book.title}» — {entry.get_status_display()}")
        return entry

    def _add_review(self, reader, book, entry, today, rnd):
        """Пишет отзыв на книгу вскоре после окончания чтения."""
        weights = RATING_WEIGHTS[entry.status]
        rating = rnd.choices(list(weights), weights=list(weights.values()))[0]
        review = Review.objects.create(
            book=book,
            reader=reader,
            text=rnd.choice(REVIEW_TEXTS[rating]),
            rating=rating,
        )
        written = min(entry.finished_at + datetime.timedelta(days=rnd.randint(0, 5)), today)
        Review.all_objects.filter(pk=review.pk).update(created_at=_moment(written, rnd))
        self.stdout.write(f"Создан отзыв {reader.display_name} на «{book.title}»: {rating}")
