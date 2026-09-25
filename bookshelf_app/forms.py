"""Формы каталога книг и дневника."""

import datetime

from django import forms
from django.db import transaction

from bookshelf_app.diary import TRANSITIONS, change_status
from bookshelf_app.models import (
    MAX_RATING,
    MIN_RATING,
    Author,
    Book,
    Genre,
    ReadingEntry,
    ReadingStatus,
    Review,
)

MIN_PUBLISHED_YEAR = 1450


def _squash_spaces(value):
    """Строка без лишних пробелов внутри и по краям."""
    return " ".join(value.split())


class BookForm(forms.ModelForm):
    """Форма добавления книги в общий каталог."""

    class Meta:
        model = Book
        fields = (
            "title",
            "author",
            "genres",
            "published_year",
            "description",
        )
        labels = {
            "author": "Автор",
            "genres": "Жанры",
        }
        help_texts = {
            "title": "Название книги.",
            "genres": "Выберите жанры.",
            "published_year": "Год издания.",
        }
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control form-control-lg",
                    "placeholder": "Например, «Мастер и Маргарита»",
                }
            ),
            "author": forms.Select(attrs={"class": "form-select"}),
            "genres": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            "published_year": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "1450",
                    "min": MIN_PUBLISHED_YEAR,
                    "max": datetime.date.today().year,
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "Про что эта книга.",
                }
            ),
        }
        error_messages = {
            "title": {"required": "Название книги не заполнено."},
            "author": {"required": "Выберите автора книги."},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Сортировки.
        self.fields["author"].queryset = Author.objects.order_by("name")
        self.fields["author"].empty_label = "— выберите автора —"
        self.fields["genres"].queryset = Genre.objects.order_by("name")

    def clean_title(self):
        """Убираем лишние пробелы в названии."""
        return _squash_spaces(self.cleaned_data["title"])

    def clean_published_year(self):
        """Год издания должен быть правдоподобным."""
        year = self.cleaned_data.get("published_year")
        if year is None:
            return year

        current_year = datetime.date.today().year
        if year < MIN_PUBLISHED_YEAR:
            raise forms.ValidationError(
                "Книгопечатание началось только в %(min)d году.",
                params={"min": MIN_PUBLISHED_YEAR},
            )
        if year > current_year:
            raise forms.ValidationError(
                "Год издания не может быть в будущем (сейчас %(now)d).",
                params={"now": current_year},
            )
        return year

    def clean(self):
        """Защита от повторов"""
        cleaned_data = super().clean()
        title = cleaned_data.get("title")
        author = cleaned_data.get("author")

        if title and author:
            duplicates = Book.objects.filter(title__iexact=title, author=author)
            if self.instance.pk:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                self.add_error(
                    "title",
                    f"Книга «{title}» этого автора уже есть в каталоге.",
                )

        return cleaned_data


class ReadingEntryForm(forms.ModelForm):
    """Правка записи дневника: статус и даты прочтения."""

    class Meta:
        model = ReadingEntry
        fields = ("status", "started_at", "finished_at")
        help_texts = {
            "started_at": "Когда начали читать. Можно оставить пустым.",
            "finished_at": "Когда дочитали или бросили.",
        }
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            # Браузерный календарь понимает только ISO-формат даты.
            "started_at": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"
            ),
            "finished_at": forms.DateInput(
                attrs={"class": "form-control", "type": "date"}, format="%Y-%m-%d"
            ),
        }


class QuickBookForm(forms.Form):
    """Быстрое добавление книги из дневника: только название и автор строкой.

    Книга попадает в каталог черновиком (`is_pending`), а в дневник — сразу с выбранным статусом.
    """

    title = forms.CharField(
        label="Название",
        max_length=Book._meta.get_field("title").max_length,
        error_messages={"required": "Название книги не заполнено."},
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    author = forms.CharField(
        label="Автор",
        max_length=Author._meta.get_field("name").max_length,
        error_messages={"required": "Укажите автора книги."},
        help_text="Имя и фамилия. Если такого автора нет в каталоге, он будет добавлен.",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Например, Михаил Булгаков"}),
    )
    status = forms.ChoiceField(
        label="В дневник как",
        # Книги в дневнике ещё нет — доступны те же статусы, что и у кнопок.
        choices=[(status.value, status.label) for status in TRANSITIONS[None]],
        initial=ReadingStatus.PLANNED,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def clean_title(self):
        """Убираем лишние пробелы в названии."""
        return _squash_spaces(self.cleaned_data["title"])

    def clean_author(self):
        """Убираем лишние пробелы в имени автора."""
        return _squash_spaces(self.cleaned_data["author"])

    def clean(self):
        """Та же книга того же автора уже есть — второй черновик не нужен."""
        cleaned_data = super().clean()
        title = cleaned_data.get("title")
        author = cleaned_data.get("author")
        if title and author and Book.objects.filter(
            title__iexact=title, author__name__iexact=author
        ).exists():
            self.add_error("title", f"Книга «{title}» этого автора уже есть в каталоге — найдите её поиском.")
        return cleaned_data

    @transaction.atomic
    def save(self, user):
        """Заводит книгу-черновик (и автора, если его нет) и добавляет её в дневник `user`."""
        name = self.cleaned_data["author"]
        author = Author.objects.filter(name__iexact=name).order_by("pk").first()
        if author is None:
            author = Author.objects.create(name=name)

        book = Book.objects.create(
            title=self.cleaned_data["title"],
            author=author,
            is_pending=True,
            added_by=user,
        )
        change_status(user, book, self.cleaned_data["status"])
        return book


class ReviewForm(forms.ModelForm):
    """Отзыв о книге: оценка звёздами и текст."""

    rating = forms.TypedChoiceField(
        label="Оценка",
        coerce=int,
        choices=[("", "— выберите оценку —")] + [
            (value, f"{'★' * value}{'☆' * (MAX_RATING - value)} — {value}")
            for value in range(MAX_RATING, MIN_RATING - 1, -1)
        ],
        error_messages={"required": "Поставьте оценку."},
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = Review
        fields = ("rating", "text")
        labels = {"text": "Отзыв"}
        widgets = {
            "text": forms.Textarea(
                attrs={"class": "form-control", "rows": 6, "placeholder": "Что понравилось, что нет."}
            ),
        }
        error_messages = {"text": {"required": "Напишите хотя бы пару слов."}}
