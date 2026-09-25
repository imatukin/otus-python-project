"""Тесты шаблона каталога: фильтры, пагинация и пометка «в моём дневнике»."""

import pytest
from django.urls import reverse

from bookshelf_app.models import Book
from bookshelf_app.tests.test_templates import get_soup, text_of
from bookshelf_app.views import CATALOG_PAGE_SIZE

pytestmark = pytest.mark.django_db


class TestBookFiltersTemplate:
    """Фильтры, пометка «в моём дневнике» и пагинация в каталоге."""

    @pytest.fixture
    def many_books(self, author, user_1):
        """Три страницы каталога."""
        return [
            Book.objects.create(title=f"Том {number:02}", author=author, added_by=user_1)
            for number in range(1, CATALOG_PAGE_SIZE * 2 + 2)
        ]

    def test_form_is_get_and_keeps_values(self, client, author, genre):
        soup = get_soup(client.get(reverse("books"), {"q": "мастер", "genre": genre.pk, "author": author.pk}))
        form = soup.select_one("form.book-filters")
        assert form["method"] == "get"
        assert form.select_one('input[name="q"]')["value"] == "мастер"
        assert form.select_one('select[name="genre"] option[selected]')["value"] == str(genre.pk)
        assert form.select_one('select[name="author"] option[selected]')["value"] == str(author.pk)

    def test_empty_choices(self, client):
        form = get_soup(client.get(reverse("books"))).select_one("form.book-filters")
        assert text_of(form.select_one('select[name="genre"] option')) == "Все жанры"
        assert text_of(form.select_one('select[name="author"] option')) == "Все авторы"

    def test_reset_link_only_with_filters(self, client):
        assert get_soup(client.get(reverse("books"))).select_one(".reset-filters") is None
        link = get_soup(client.get(reverse("books"), {"q": "мастер"})).select_one(".reset-filters")
        assert link["href"] == reverse("books")

    def test_nothing_found(self, client, book):  # pylint: disable=unused-argument
        soup = get_soup(client.get(reverse("books"), {"q": "нет такой"}))
        assert text_of(soup.select_one(".alert-info")) == "По этим фильтрам книг не нашлось."

    def test_counter_counts_all_pages(self, client, many_books):
        badge = get_soup(client.get(reverse("books"))).select_one(".badge.bg-secondary")
        assert text_of(badge) == f"Всего: {len(many_books)}"

    def test_no_pagination_on_single_page(self, client, book):  # pylint: disable=unused-argument
        assert get_soup(client.get(reverse("books"))).select_one(".pagination") is None

    def test_pagination_links(self, client, many_books):  # pylint: disable=unused-argument
        soup = get_soup(client.get(reverse("books"), {"page": 2}))
        pages = soup.select(".pagination .page-item")
        assert [text_of(page) for page in pages] == ["«", "1", "2", "3", "»"]
        assert "active" in pages[2]["class"]
        assert pages[0].a["href"] == "?page=1"
        assert pages[-1].a["href"] == "?page=3"

    def test_pagination_edges_disabled(self, client, many_books):  # pylint: disable=unused-argument
        pages = get_soup(client.get(reverse("books"))).select(".pagination .page-item")
        assert "disabled" in pages[0]["class"]
        assert pages[0].a is None
        last = get_soup(client.get(reverse("books"), {"page": 3})).select(".pagination .page-item")[-1]
        assert "disabled" in last["class"]

    def test_pagination_keeps_filters(self, client, many_books, author):  # pylint: disable=unused-argument
        soup = get_soup(client.get(reverse("books"), {"author": author.pk}))
        assert soup.select_one(".pagination a.page-link")["href"] == f"?author={author.pk}&page=2"

    def test_diary_badge(self, auth_client, entries, book, book_of_user_2):  # pylint: disable=unused-argument
        cards = get_soup(auth_client.get(reverse("books"))).select(".book-card")
        badges = {text_of(card.h2.a): card.select_one(".diary-badge") for card in cards}
        assert text_of(badges[book.title]) == "В моём дневнике: прочитано"
        assert text_of(badges[book_of_user_2.title]) == "В моём дневнике: хочу прочитать"

    def test_no_diary_badge_for_new_book(self, auth_client, book):  # pylint: disable=unused-argument
        assert get_soup(auth_client.get(reverse("books"))).select_one(".diary-badge") is None

    def test_no_diary_badge_for_guest(self, client, entry):  # pylint: disable=unused-argument
        assert get_soup(client.get(reverse("books"))).select_one(".diary-badge") is None
