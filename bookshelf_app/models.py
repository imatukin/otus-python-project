from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse

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
