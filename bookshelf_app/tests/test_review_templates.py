"""Тесты шаблонов отзывов и статистики книги: разметку разбираем через BeautifulSoup."""

import pytest
from django.urls import reverse

from bookshelf_app.models import Book, ReadingEntry
from bookshelf_app.tests.test_templates import get_soup, review_cards, text_of

pytestmark = pytest.mark.django_db


class TestBookStatsTemplate:
    """Средняя оценка и число прочтений."""

    def test_catalog_without_reviews(self, client, book):  # pylint: disable=unused-argument
        stats = get_soup(client.get(reverse("books"))).select_one(".book-card .book-stats")
        assert text_of(stats) == "оценок нет · прочтений: 0"

    def test_catalog_with_reviews(self, client, book, reviews, user_1):  # pylint: disable=unused-argument
        ReadingEntry.objects.create(reader=user_1, book=book, status="read")
        stats = get_soup(client.get(reverse("books"))).select_one(".book-card .book-stats")
        # Оценки 5 и 3, дробь — по-русски, через запятую.
        assert text_of(stats) == "★ 4,0 · прочтений: 1"

    def test_detail(self, client, book, review):  # pylint: disable=unused-argument
        stats = get_soup(client.get(book.get_absolute_url())).select_one(".book-stats")
        assert text_of(stats) == "★ 5,0 · прочтений: 0"

    def test_stats_not_counted_as_review(self, client, book, review):  # pylint: disable=unused-argument
        assert len(review_cards(get_soup(client.get(book.get_absolute_url())))) == 1


class TestBookDetailReviewsTemplate:
    """Кнопки отзывов на странице книги."""

    def test_add_button_hidden_for_guest(self, client, book):
        assert get_soup(client.get(book.get_absolute_url())).select_one(".review-add") is None

    def test_add_button(self, auth_client, book):
        button = get_soup(auth_client.get(book.get_absolute_url())).select_one(".review-add")
        assert text_of(button) == "Написать отзыв"
        assert button["href"] == reverse("review_add", args=[book.pk])

    def test_own_review_actions(self, auth_client, book, reviews):
        soup = get_soup(auth_client.get(book.get_absolute_url()))
        own = reviews[0]
        actions = [card.select_one(".review-actions") for card in review_cards(soup)]
        # Отзывы — от новых к старым: сначала чужой (reviews[1]), потом свой.
        assert actions[0] is None
        assert [(text_of(link), link["href"]) for link in actions[1].select("a")] == [
            ("Изменить", reverse("review_edit", args=[own.pk])),
            ("Удалить", reverse("review_delete", args=[own.pk])),
        ]

    def test_no_actions_for_guest(self, client, book, reviews):  # pylint: disable=unused-argument
        assert get_soup(client.get(book.get_absolute_url())).select_one(".review-actions") is None


class TestReviewFormTemplate:
    """Формы отзыва — на общем шаблоне формы."""

    def test_create_form(self, auth_client, book):
        soup = get_soup(auth_client.get(reverse("review_add", args=[book.pk])))
        assert text_of(soup.select_one(".card-header h1")) == f"Отзыв: {book.title}"
        assert soup.select_one('select[name="rating"]') is not None
        assert soup.select_one('textarea[name="text"]') is not None
        assert text_of(soup.main.select_one("button[type=submit]")) == "Опубликовать"
        assert soup.select_one("form a.btn-outline-danger") is None

    def test_edit_form_has_delete(self, auth_client, book, reviews):  # pylint: disable=unused-argument
        own = reviews[0]
        soup = get_soup(auth_client.get(reverse("review_edit", args=[own.pk])))
        assert soup.select_one('select[name="rating"] option[selected]')["value"] == str(own.rating)
        assert soup.select_one("form a.btn-outline-danger")["href"] == reverse("review_delete", args=[own.pk])

    def test_errors_shown(self, auth_client, book):
        response = auth_client.post(reverse("review_add", args=[book.pk]), {"rating": "", "text": ""})
        errors = [text_of(tag) for tag in get_soup(response).select(".field-invalid .text-danger.small")]
        assert errors == ["Поставьте оценку.", "Напишите хотя бы пару слов."]


class TestReviewDeleteTemplate:
    """Подтверждение удаления отзыва."""

    def test_content(self, auth_client, book, reviews):  # pylint: disable=unused-argument
        own = reviews[0]
        soup = get_soup(auth_client.get(reverse("review_delete", args=[own.pk])))
        assert text_of(soup.main.h1) == "Удалить отзыв?"
        assert text_of(soup.main.h2) == book.title
        assert text_of(soup.select_one(".rating")) == "★★★★★"
        assert text_of(soup.select_one(".review-text")) == own.text
        form = soup.select_one(".card-footer form")
        assert form["method"] == "post"
        assert form.select_one("a")["href"] == reverse("review_edit", args=[own.pk])


class TestReviewOfferTemplate:
    """Предложение написать отзыв после «Прочитано» — ссылкой в сообщении."""

    def test_link_in_message(self, auth_client, book, entry):  # pylint: disable=unused-argument
        response = auth_client.post(reverse("book_status", args=[book.pk]), {"status": "read"}, follow=True)
        link = get_soup(response).select_one(".alert-dismissible a.review-offer")
        assert text_of(link) == "Написать отзыв?"
        assert link["href"] == reverse("review_add", args=[book.pk])

    def test_title_escaped(self, auth_client, author, user_1):
        book = Book.objects.create(title="<b>Жирная</b>", author=author, added_by=user_1)
        response = auth_client.post(reverse("book_status", args=[book.pk]), {"status": "read"}, follow=True)
        alert = get_soup(response).select_one(".alert-dismissible")
        assert alert.select_one("b") is None
        assert "<b>Жирная</b>" in text_of(alert)
