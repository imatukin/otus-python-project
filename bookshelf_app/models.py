"""Модели каталога (автор, жанр, книга, отзыв) и дневника чтения."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

MIN_RATING = 1
MAX_RATING = 5


class Author(models.Model):
    """Автор книги."""
    name = models.CharField('ФИО', max_length=200)
    bio = models.TextField('Биография', blank=True)
    birth_date = models.DateField('Дата рождения', blank=True, null=True)

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name


class Genre(models.Model):
    """Жанр книги (тег)."""
    name = models.CharField('Название', max_length=50, unique=True)

    def __repr__(self):
        return self.name

    def __str__(self):
        return self.name


class Book(models.Model):
    """Книга из общего каталога."""
    title = models.CharField('Название', max_length=200)
    description = models.TextField('Описание', blank=True)
    author = models.ForeignKey(
        Author,
        on_delete=models.PROTECT,
        related_name='books',
    )
    genres = models.ManyToManyField(
        Genre,
        related_name='books',
        blank=True,
    )
    published_year = models.PositiveIntegerField('Год издания', blank=True, null=True)
    is_pending = models.BooleanField(
        'Требует дозаполнения',
        default=False,
        help_text='Книга заведена быстрой формой из дневника: заполнены только название и автор.',
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Кто добавил',
        on_delete=models.CASCADE,
        related_name='added_books',
    )

    def __repr__(self):
        return f'{self.title} ({self.author})'

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        """Ссылка на страницу книги — сюда возвращаемся после создания/редактирования."""
        return reverse('book_detail', args=[self.pk])


class Review(models.Model):
    """Отзыв читателя о книге."""
    book = models.ForeignKey(
        Book,
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    reader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Читатель',
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    text = models.TextField('Текст отзыва')
    rating = models.PositiveSmallIntegerField(
        'Оценка',
        validators=[MinValueValidator(MIN_RATING), MaxValueValidator(MAX_RATING)],
    )
    created_at = models.DateTimeField('Дата создания', auto_now_add=True)

    def __repr__(self):
        return f'Review by {self.reader} on {self.book}: {self.text[:10]}'

    def __str__(self):
        return f'Отзыв {self.reader} на «{self.book}»'


class ReadingStatus(models.TextChoices):
    """Стадия чтения книги в дневнике."""

    PLANNED = 'planned', 'Хочу прочитать'
    READING = 'reading', 'Читаю'
    READ = 'read', 'Прочитано'
    ABANDONED = 'abandoned', 'Брошено'


class ReadingEntry(models.Model):
    """Запись дневника — одно прочтение книги одним читателем.

    Ограничения уникальности нет намеренно: книгу можно перечитывать,
    и каждое прочтение — отдельная запись истории.
    """

    reader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name='Читатель',
        on_delete=models.CASCADE,
        related_name='entries',
    )
    book = models.ForeignKey(
        Book,
        verbose_name='Книга',
        on_delete=models.CASCADE,
        related_name='entries',
    )
    status = models.CharField(
        'Статус',
        max_length=10,
        choices=ReadingStatus.choices,
        default=ReadingStatus.PLANNED,
    )
    started_at = models.DateField('Начато', blank=True, null=True)
    finished_at = models.DateField('Закончено', blank=True, null=True)
    created_at = models.DateTimeField('Добавлено в дневник', auto_now_add=True)
    updated_at = models.DateTimeField('Изменено', auto_now=True)

    class Meta:
        verbose_name = 'запись дневника'
        verbose_name_plural = 'записи дневника'
        ordering = ('-created_at',)

    def __repr__(self):
        return f'ReadingEntry({self.reader}, {self.book}, {self.status})'

    def __str__(self):
        return f'«{self.book}» — {self.get_status_display().lower()}'

    def clean(self):
        """Прочтение не может закончиться раньше, чем началось."""
        super().clean()
        if self.started_at and self.finished_at and self.finished_at < self.started_at:
            raise ValidationError(
                {'finished_at': 'Дата окончания раньше даты начала чтения.'}
            )

    def apply_status(self, status, today=None):
        """Меняет статус и проставляет даты, которых ещё нет.

        Даты — подсказка, а не догма: пользователь потом правит их руками
        (например, отмечает книгу, прочитанную в прошлом году).
        """
        today = today or timezone.localdate()
        self.status = status

        if status == ReadingStatus.READING and self.started_at is None:
            self.started_at = today
        elif status in (ReadingStatus.READ, ReadingStatus.ABANDONED):
            if self.started_at is None:
                self.started_at = today
            if self.finished_at is None:
                self.finished_at = today

        return self
