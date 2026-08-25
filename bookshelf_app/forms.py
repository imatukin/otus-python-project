import datetime

from django import forms
from bookshelf_app.models import Author, Book, Genre

MIN_PUBLISHED_YEAR = 1450


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
        return " ".join(self.cleaned_data["title"].split())

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
