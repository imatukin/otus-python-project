"""Тесты форм каталога книг."""

import datetime

import pytest

from bookshelf_app.forms import MIN_PUBLISHED_YEAR, BookForm

CURRENT_YEAR = datetime.date.today().year


class TestBookFormFields:
    """Состав и оформление полей формы."""

    def test_fields(self):
        form = BookForm()
        assert list(form.fields) == [
            "title",
            "author",
            "genres",
            "published_year",
            "description",
        ]

    def test_labels(self):
        form = BookForm()
        assert form.fields["author"].label == "Автор"
        assert form.fields["genres"].label == "Жанры"

    @pytest.mark.django_db
    def test_empty_label_for_author(self):
        form = BookForm()
        assert form.fields["author"].empty_label == "— выберите автора —"

    @pytest.mark.django_db
    def test_querysets_are_sorted(self, author, author_2, genre, genre_2):
        form = BookForm()
        assert list(form.fields["author"].queryset) == sorted(
            [author, author_2], key=lambda item: item.name
        )
        assert list(form.fields["genres"].queryset) == sorted(
            [genre, genre_2], key=lambda item: item.name
        )


class TestBookFormValid:
    """Корректно заполненная форма."""

    @pytest.mark.django_db
    def test_form_is_valid(self, author, genre):
        data = {
            "title": "Собачье сердце",
            "author": author.pk,
            "genres": [genre.pk],
            "published_year": 1925,
            "description": "Повесть о профессоре Преображенском.",
        }
        assert BookForm(data=data).is_valid()

    @pytest.mark.django_db
    def test_save_creates_book(self, author, genre, genre_2, user_1):
        data = {
            "title": "Собачье сердце",
            "author": author.pk,
            "genres": [genre.pk, genre_2.pk],
            "published_year": 1925,
            "description": "Повесть о профессоре Преображенском.",
        }
        form = BookForm(data=data)
        assert form.is_valid()
        book = form.save(commit=False)
        book.added_by = user_1
        book.save()
        form.save_m2m()
        assert book.pk is not None
        assert book.genres.count() == 2

    @pytest.mark.django_db
    def test_optional_fields_may_be_empty(self, author):
        data = {
            "title": "Собачье сердце",
            "author": author.pk,
            "genres": [],
            "published_year": "",
            "description": "",
        }
        form = BookForm(data=data)
        assert form.is_valid()
        assert form.cleaned_data["published_year"] is None


class TestBookFormRequired:
    """Обязательные поля."""

    @pytest.mark.django_db
    @pytest.mark.parametrize("field", ["title", "author"])
    def test_field_is_required(self, author, field):
        data = {
            "title": "Собачье сердце",
            "author": author.pk,
            "published_year": 1925,
        }
        data[field] = ""
        form = BookForm(data=data)
        assert not form.is_valid()
        assert field in form.errors

    @pytest.mark.django_db
    def test_custom_error_message_for_title(self, author):
        data = {
            "title": "",
            "author": author.pk,
        }
        form = BookForm(data=data)
        assert form.errors["title"] == ["Название книги не заполнено."]

    @pytest.mark.django_db
    def test_custom_error_message_for_author(self):
        data = {
            "title": "Собачье сердце",
            "author": "",
        }
        form = BookForm(data=data)
        assert form.errors["author"] == ["Выберите автора книги."]


class TestCleanTitle:
    """Чистка названия книги."""

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("  Мастер и Маргарита  ", "Мастер и Маргарита"),
            ("Мастер   и   Маргарита", "Мастер и Маргарита"),
            ("Мастер\nи\tМаргарита", "Мастер и Маргарита"),
        ],
    )
    def test_extra_spaces_removed(self, author, raw, expected):
        data = {
            "title": raw,
            "author": author.pk,
        }
        form = BookForm(data=data)
        assert form.is_valid()
        assert form.cleaned_data["title"] == expected


class TestCleanPublishedYear:
    """Проверка года издания."""

    @pytest.mark.django_db
    @pytest.mark.parametrize("year", [MIN_PUBLISHED_YEAR, 1967, CURRENT_YEAR])
    def test_valid_year(self, author, year):
        data = {
            "title": "Собачье сердце",
            "author": author.pk,
            "published_year": year,
        }
        form = BookForm(data=data)
        assert form.is_valid()
        assert form.cleaned_data["published_year"] == year

    @pytest.mark.django_db
    def test_year_before_printing(self, author):
        data = {
            "title": "Собачье сердце",
            "author": author.pk,
            "published_year": MIN_PUBLISHED_YEAR - 1,
        }
        form = BookForm(data=data)
        assert not form.is_valid()
        assert form.errors["published_year"] == [
            f"Книгопечатание началось только в {MIN_PUBLISHED_YEAR} году."
        ]

    @pytest.mark.django_db
    def test_year_in_future(self, author):
        data = {
            "title": "Собачье сердце",
            "author": author.pk,
            "published_year": CURRENT_YEAR + 1,
        }
        form = BookForm(data=data)
        assert not form.is_valid()
        assert form.errors["published_year"] == [
            f"Год издания не может быть в будущем (сейчас {CURRENT_YEAR})."
        ]

    @pytest.mark.django_db
    def test_negative_year_rejected_by_field(self, author):
        data = {
            "title": "Собачье сердце",
            "author": author.pk,
            "published_year": -5,
        }
        assert not BookForm(data=data).is_valid()


class TestDuplicates:
    """Защита от повторов: одно название у одного автора."""

    @pytest.mark.django_db
    def test_duplicate_rejected(self, book):
        data = {
            "title": book.title,
            "author": book.author.pk,
        }
        form = BookForm(data=data)
        assert not form.is_valid()
        assert form.errors["title"] == [
            f"Книга «{book.title}» этого автора уже есть в каталоге."
        ]

    @pytest.mark.django_db
    def test_duplicate_is_case_insensitive(self, book):
        # Латиница: sqlite сравнивает без учёта регистра только ASCII,
        # для кириллицы iexact на этой базе работает как обычное сравнение.
        book.title = "Animal Farm"
        book.save()
        data = {
            "title": "ANIMAL FARM",
            "author": book.author.pk,
        }
        assert not BookForm(data=data).is_valid()

    @pytest.mark.django_db
    def test_same_title_for_another_author_is_allowed(self, book, author_2):
        data = {
            "title": book.title,
            "author": author_2.pk,
        }
        assert BookForm(data=data).is_valid()

    @pytest.mark.django_db
    def test_editing_own_book_is_not_a_duplicate(self, book):
        """При редактировании книга не считает дублем саму себя."""
        data = {
            "title": book.title,
            "author": book.author.pk,
        }
        assert BookForm(data=data, instance=book).is_valid()

    @pytest.mark.django_db
    def test_duplicate_check_ignores_extra_spaces(self, book):
        data = {
            "title": f"  {book.title}  ",
            "author": book.author.pk,
        }
        assert not BookForm(data=data).is_valid()
