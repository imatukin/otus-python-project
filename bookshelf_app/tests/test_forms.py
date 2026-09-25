"""Тесты форм каталога книг."""

import datetime

import pytest

from bookshelf_app.forms import (
    MIN_PUBLISHED_YEAR,
    BookFilterForm,
    BookForm,
    QuickBookForm,
    ReadingEntryForm,
    ReviewForm,
)
from bookshelf_app.models import Author, Book, ReadingEntry, ReadingStatus

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


class TestReadingEntryForm:
    """Правка записи дневника."""

    def test_fields(self):
        assert list(ReadingEntryForm().fields) == ["status", "started_at", "finished_at"]

    def test_date_widgets(self):
        form = ReadingEntryForm()
        for name in ("started_at", "finished_at"):
            assert form.fields[name].widget.input_type == "date"

    @pytest.mark.django_db
    def test_initial_dates_in_iso(self, entry):
        html = str(ReadingEntryForm(instance=entry)["started_at"])
        assert 'value="2026-01-10"' in html

    @pytest.mark.django_db
    def test_valid(self, entry):
        form = ReadingEntryForm(
            {"status": "read", "started_at": "2026-01-10", "finished_at": "2026-02-01"}, instance=entry
        )
        assert form.is_valid(), form.errors
        form.save()
        entry.refresh_from_db()
        assert entry.status == ReadingStatus.READ
        assert entry.finished_at == datetime.date(2026, 2, 1)

    @pytest.mark.django_db
    def test_dates_optional(self, entry):
        form = ReadingEntryForm({"status": "planned", "started_at": "", "finished_at": ""}, instance=entry)
        assert form.is_valid(), form.errors

    @pytest.mark.django_db
    def test_finish_before_start(self, entry):
        form = ReadingEntryForm(
            {"status": "read", "started_at": "2026-02-01", "finished_at": "2026-01-01"}, instance=entry
        )
        assert not form.is_valid()
        assert form.errors["finished_at"] == ["Дата окончания раньше даты начала чтения."]

    @pytest.mark.django_db
    def test_unknown_status(self, entry):
        form = ReadingEntryForm({"status": "lost"}, instance=entry)
        assert "status" in form.errors


@pytest.fixture
def quick_data():
    """Корректные данные для QuickBookForm."""
    return {"title": "Белая гвардия", "author": "Михаил Булгаков", "status": "planned"}


class TestQuickBookForm:
    """Быстрое добавление книги из дневника."""

    def test_fields(self):
        assert list(QuickBookForm().fields) == ["title", "author", "status"]

    def test_status_choices_are_first_steps(self):
        values = [value for value, _ in QuickBookForm().fields["status"].choices]
        assert values == ["planned", "reading", "read"]

    def test_status_default(self):
        assert QuickBookForm().fields["status"].initial == ReadingStatus.PLANNED

    @pytest.mark.parametrize("field", ["title", "author"])
    def test_required(self, quick_data, field):
        quick_data[field] = ""
        form = QuickBookForm(quick_data)
        assert not form.is_valid()
        assert field in form.errors

    def test_error_messages(self):
        form = QuickBookForm({"status": "planned"})
        assert form.errors["title"] == ["Название книги не заполнено."]
        assert form.errors["author"] == ["Укажите автора книги."]

    @pytest.mark.django_db
    def test_spaces_squashed(self, quick_data):
        quick_data.update(title="  Белая   гвардия ", author=" Михаил  Булгаков ")
        form = QuickBookForm(quick_data)
        assert form.is_valid(), form.errors
        assert form.cleaned_data["title"] == "Белая гвардия"
        assert form.cleaned_data["author"] == "Михаил Булгаков"

    @pytest.mark.django_db
    def test_abandoned_not_allowed(self, quick_data):
        quick_data["status"] = "abandoned"
        assert "status" in QuickBookForm(quick_data).errors

    @pytest.mark.django_db
    def test_duplicate_rejected(self, book, quick_data):
        quick_data.update(title=book.title.upper(), author=book.author.name.lower())
        form = QuickBookForm(quick_data)
        assert not form.is_valid()
        assert "уже есть в каталоге" in form.errors["title"][0]

    @pytest.mark.django_db
    def test_same_title_other_author_allowed(self, book, quick_data):
        quick_data["title"] = book.title
        quick_data["author"] = "Другой автор"
        assert QuickBookForm(quick_data).is_valid()

    @pytest.mark.django_db
    def test_save_uses_existing_author(self, author, user_1, quick_data):
        quick_data["author"] = author.name.upper()
        form = QuickBookForm(quick_data)
        assert form.is_valid(), form.errors
        book = form.save(user_1)
        assert book.author == author
        assert Author.objects.count() == 1

    @pytest.mark.django_db
    def test_save_creates_author(self, user_1, quick_data):
        form = QuickBookForm(quick_data)
        assert form.is_valid(), form.errors
        book = form.save(user_1)
        assert book.author.name == "Михаил Булгаков"

    @pytest.mark.django_db
    def test_deleted_author_not_reused(self, author, user_1, quick_data):
        author.delete()
        form = QuickBookForm(quick_data)
        assert form.is_valid(), form.errors
        assert form.save(user_1).author != author

    @pytest.mark.django_db
    def test_save_creates_pending_book_and_entry(self, user_1, quick_data):
        quick_data["status"] = "reading"
        form = QuickBookForm(quick_data)
        assert form.is_valid(), form.errors
        book = form.save(user_1)

        book = Book.objects.get(pk=book.pk)
        assert book.title == "Белая гвардия"
        assert book.is_pending is True
        assert book.added_by == user_1
        entry = ReadingEntry.objects.get(book=book)
        assert (entry.reader, entry.status) == (user_1, ReadingStatus.READING)
        assert entry.started_at is not None


class TestReviewForm:
    """Отзыв о книге."""

    def test_fields(self):
        assert list(ReviewForm().fields) == ["rating", "text"]

    def test_rating_choices(self):
        choices = ReviewForm().fields["rating"].choices
        assert choices[0] == ("", "— выберите оценку —")
        assert [value for value, _ in choices[1:]] == [5, 4, 3, 2, 1]
        assert choices[-1] == (1, "★☆☆☆☆ — 1")

    def test_valid(self):
        form = ReviewForm({"rating": "4", "text": " Хорошо. "})
        assert form.is_valid(), form.errors
        assert form.cleaned_data == {"rating": 4, "text": "Хорошо."}

    def test_required(self):
        form = ReviewForm({"rating": "", "text": "   "})
        assert form.errors == {"rating": ["Поставьте оценку."], "text": ["Напишите хотя бы пару слов."]}

    @pytest.mark.parametrize("rating", ["0", "6", "abc"])
    def test_rating_out_of_range(self, rating):
        assert "rating" in ReviewForm({"rating": rating, "text": "Текст"}).errors


@pytest.mark.django_db
class TestBookFilterForm:
    """Фильтры каталога."""

    def filtered(self, data):
        """Книги, оставшиеся после фильтров."""
        return set(BookFilterForm(data).filter(Book.objects.all()))

    def test_all_fields_optional(self, book, book_of_user_2):
        assert self.filtered({}) == {book, book_of_user_2}

    def test_title_search_ignores_case_and_spaces(self, book, book_of_user_2):  # pylint: disable=unused-argument
        assert self.filtered({"q": "  мастер   и "}) == {book}

    def test_search_by_author_name(self, book, book_of_user_2):  # pylint: disable=unused-argument
        assert self.filtered({"q": "достоевский"}) == {book_of_user_2}

    def test_search_by_description(self, book, book_of_user_2):  # pylint: disable=unused-argument
        assert self.filtered({"q": "добре"}) == {book}

    def test_search_by_genre_name(self, book, book_of_user_2):  # pylint: disable=unused-argument
        assert self.filtered({"q": "роман"}) == {book}

    def test_search_words_combine(self, book, book_of_user_2, books):  # pylint: disable=unused-argument
        """Каждое слово должно найтись — в любом из полей."""
        assert self.filtered({"q": "булгаков маргарита"}) == {book}
        assert self.filtered({"q": "булгаков наказание"}) == set()

    def test_search_no_duplicates_by_genres(self, book, genre_2):
        """У книги два жанра со словом «роман» — в выдаче она одна."""
        genre_2.name = "Роман-эпопея"
        genre_2.save()
        book.genres.add(genre_2)
        assert list(BookFilterForm({"q": "роман"}).filter(Book.objects.all())) == [book]

    def test_genre(self, book, book_of_user_2, genre_2):  # pylint: disable=unused-argument
        book_of_user_2.genres.add(genre_2)
        assert self.filtered({"genre": genre_2.pk}) == {book_of_user_2}

    def test_author(self, book, book_of_user_2, author):  # pylint: disable=unused-argument
        assert self.filtered({"author": author.pk}) == {book}

    def test_filters_combine(self, book, books, genre_2):
        books[0].genres.add(genre_2)
        assert self.filtered({"q": "книга", "genre": genre_2.pk, "author": book.author.pk}) == {books[0]}

    def test_invalid_value_is_skipped(self, book, book_of_user_2, author):  # pylint: disable=unused-argument
        """Несуществующий жанр — не ошибка, а пропущенный фильтр; остальные работают."""
        assert self.filtered({"genre": "404", "author": author.pk}) == {book}

    def test_deleted_author_not_in_choices(self, author, author_2):
        author_2.delete()
        assert list(BookFilterForm().fields["author"].queryset) == [author]

    def test_is_active(self, author):
        empty = BookFilterForm({"q": "  "})
        empty.filter(Book.objects.all())
        assert not empty.is_active
        filled = BookFilterForm({"author": author.pk})
        filled.filter(Book.objects.all())
        assert filled.is_active

    def test_unbound_form_is_not_active(self):
        form = BookFilterForm()
        assert set(form.filter(Book.objects.all())) == set()
        assert not form.is_active
