"""Тесты шаблонов каталога книг: разметку разбираем через BeautifulSoup."""

import pytest
from bs4 import BeautifulSoup
from django.urls import reverse

from bookshelf_app.models import Review

# Все шаблоны рендерятся через клиент и почти везде опираются на данные из базы.
pytestmark = pytest.mark.django_db


def get_soup(response):
    """HTML ответа в виде дерева BeautifulSoup."""
    return BeautifulSoup(response.content.decode(), "html.parser")


def review_cards(soup):
    """Карточки отзывов на странице книги — их отличает блок с оценкой."""
    return [card for card in soup.select(".card") if card.select_one(".rating")]


def text_of(tag):
    """Текст тега без лишних пробелов и переносов строк."""
    return " ".join(tag.get_text().split())


class TestBaseTemplate:
    """Общий каркас страницы: заголовок, меню, подвал."""

    def test_title(self, client):
        soup = get_soup(client.get(reverse("index")))
        assert text_of(soup.title) == "Главная"

    def test_title_from_page_title(self, client, book):
        soup = get_soup(client.get(book.get_absolute_url()))
        assert text_of(soup.title) == book.title

    def test_layout_blocks(self, client):
        soup = get_soup(client.get(reverse("index")))
        assert soup.header is not None
        assert soup.main is not None
        assert soup.footer is not None

    def test_footer_content(self, client):
        soup = get_soup(client.get(reverse("index")))
        footer = text_of(soup.footer)
        assert "Матукин Иван" in footer
        assert "Проектная работа OUTS" in footer

    def test_bootstrap_connected(self, client):
        soup = get_soup(client.get(reverse("index")))
        styles = [link["href"] for link in soup.find_all("link", rel="stylesheet")]
        scripts = [script["src"] for script in soup.find_all("script", src=True)]
        assert any("bootstrap" in href for href in styles)
        assert any("bootstrap" in src for src in scripts)

    def test_extra_css_block(self, client, book):
        """На странице книги подключается свой блок стилей."""
        soup = get_soup(client.get(book.get_absolute_url()))
        assert any(".rating" in style.get_text() for style in soup.find_all("style"))

    def test_no_messages_by_default(self, client):
        soup = get_soup(client.get(reverse("index")))
        assert not soup.select(".alert-dismissible")

    def test_success_message_shown(self, auth_client, book_form_data):
        """Сообщение об успехе попадает в блок messages на следующей странице."""
        response = auth_client.post(reverse("book_add"), book_form_data, follow=True)
        alert = get_soup(response).select_one(".alert-dismissible")
        assert alert is not None
        assert "«Собачье сердце» добавлена в каталог." in text_of(alert)


class TestMenuTemplate:
    """Меню в шапке сайта."""

    def get_menu_links(self, response):
        """Словарь «текст пункта меню» → тег ссылки."""
        soup = get_soup(response)
        links = soup.select("nav.navbar .nav-link")
        return {text_of(link): link for link in links}

    def test_brand_link(self, client):
        soup = get_soup(client.get(reverse("index")))
        brand = soup.select_one(".navbar-brand")
        assert text_of(brand) == "Дневник читателя"
        assert brand["href"] == reverse("index")

    def test_anonymous_menu_items(self, client):
        links = self.get_menu_links(client.get(reverse("index")))
        assert set(links) == {"Главная", "О сайте", "Все книги", "Вход", "Регистрация"}

    def test_anonymous_menu_hrefs(self, client):
        links = self.get_menu_links(client.get(reverse("index")))
        assert links["Главная"]["href"] == reverse("index")
        assert links["О сайте"]["href"] == reverse("about")
        assert links["Все книги"]["href"] == reverse("books")
        assert links["Вход"]["href"] == reverse("login")
        assert links["Регистрация"]["href"] == reverse("register")

    def test_authenticated_menu_items(self, auth_client, user_1):
        links = self.get_menu_links(auth_client.get(reverse("index")))
        assert "Добавить книгу" in links
        assert user_1.display_name in links
        assert "Выйти" in links
        assert "Вход" not in links
        assert "Регистрация" not in links

    def test_logout_is_post_form(self, auth_client):
        soup = get_soup(auth_client.get(reverse("index")))
        form = soup.select_one(f'form[action="{reverse("logout")}"]')
        assert form is not None
        assert form["method"].lower() == "post"
        assert form.select_one('input[name="csrfmiddlewaretoken"]') is not None

    @pytest.mark.parametrize(
        "url_name, active_title",
        [
            ("index", "Главная"),
            ("about", "О сайте"),
            ("books", "Все книги"),
        ],
    )
    def test_active_item(self, client, url_name, active_title):
        links = self.get_menu_links(client.get(reverse(url_name)))
        active = [title for title, link in links.items() if "active" in link["class"]]
        assert active == [active_title]
        assert links[active_title].get("aria-current") == "page"

    def test_book_detail_highlights_books(self, client, book):
        """На странице книги подсвечен пункт «Все книги», но без aria-current."""
        links = self.get_menu_links(client.get(book.get_absolute_url()))
        assert "active" in links["Все книги"]["class"]
        assert links["Все книги"].get("aria-current") is None


class TestBreadcrumbTemplate:
    """Хлебные крошки."""

    def get_crumbs(self, response):
        """Список пунктов хлебных крошек."""
        return get_soup(response).select(".breadcrumb .breadcrumb-item")

    def test_hidden_on_index(self, client):
        """Одна крошка — навигацию не показываем."""
        assert not get_soup(client.get(reverse("index"))).select(".breadcrumb")

    def test_about_crumbs(self, client):
        crumbs = self.get_crumbs(client.get(reverse("about")))
        assert [text_of(crumb) for crumb in crumbs] == ["Главная", "О сайте"]

    def test_last_crumb_is_active_and_without_link(self, client):
        crumbs = self.get_crumbs(client.get(reverse("about")))
        last = crumbs[-1]
        assert "active" in last["class"]
        assert last.get("aria-current") == "page"
        assert last.find("a") is None

    def test_intermediate_crumbs_are_links(self, client, book):
        crumbs = self.get_crumbs(client.get(book.get_absolute_url()))
        hrefs = [crumb.a["href"] for crumb in crumbs[:-1]]
        assert hrefs == [reverse("index"), reverse("books")]

    def test_book_detail_crumbs(self, client, book):
        crumbs = self.get_crumbs(client.get(book.get_absolute_url()))
        assert [text_of(crumb) for crumb in crumbs] == [
            "Главная",
            "Все книги",
            book.title,
        ]

    def test_book_edit_crumbs(self, auth_client, book):
        crumbs = self.get_crumbs(auth_client.get(reverse("book_edit", args=[book.pk])))
        assert [text_of(crumb) for crumb in crumbs] == [
            "Главная",
            "Все книги",
            book.title,
            "Редактирование",
        ]

    def test_book_delete_crumbs(self, auth_client, book):
        crumbs = self.get_crumbs(auth_client.get(reverse("book_delete", args=[book.pk])))
        assert [text_of(crumb) for crumb in crumbs][-1] == "Удаление"

    def test_book_add_crumbs(self, auth_client):
        crumbs = self.get_crumbs(auth_client.get(reverse("book_add")))
        assert [text_of(crumb) for crumb in crumbs] == [
            "Главная",
            "Все книги",
            "Добавление",
        ]


class TestIndexTemplate:
    """Главная страница."""

    def test_heading(self, client):
        soup = get_soup(client.get(reverse("index")))
        assert text_of(soup.main.h1) == "Это дневник, прочитанных книг."


class TestAboutTemplate:
    """Страница «О сайте»."""

    def test_headings(self, client):
        soup = get_soup(client.get(reverse("about")))
        assert text_of(soup.main.h1) == "О сайте"
        assert [text_of(h2) for h2 in soup.main.find_all("h2")] == [
            "Разработчик",
            "О проекте",
        ]

    def test_developer_name(self, client):
        soup = get_soup(client.get(reverse("about")))
        assert "Матукин Иван" in [text_of(tag) for tag in soup.main.find_all("strong")]

    def test_lead_paragraph(self, client):
        soup = get_soup(client.get(reverse("about")))
        assert "дневник прочитанных книг" in text_of(soup.select_one("p.lead"))


class TestBooksTemplate:
    """Список книг."""

    def get_cards(self, response):
        """Карточки книг на странице списка."""
        return get_soup(response).select(".book-card")

    def test_heading_and_counter(self, client, books):
        soup = get_soup(client.get(reverse("books")))
        assert text_of(soup.main.h1) == "Все книги."
        assert text_of(soup.select_one(".badge.bg-secondary")) == f"Всего: {len(books)}"

    # book_of_user_2 нужен как данные в базе, обращаться к нему в тесте не требуется.
    def test_card_per_book(self, client, books, book_of_user_2):  # pylint: disable=unused-argument
        cards = self.get_cards(client.get(reverse("books")))
        assert len(cards) == len(books) + 1

    def test_card_titles_link_to_detail(self, client, book):
        card = self.get_cards(client.get(reverse("books")))[0]
        link = card.select_one(".card-title a")
        assert text_of(link) == book.title
        assert link["href"] == reverse("book_detail", args=[book.pk])

    def test_card_author_and_year(self, client, book):
        card = self.get_cards(client.get(reverse("books")))[0]
        assert text_of(card.select_one("p.text-muted.small")) == (
            f"{book.author.name} · {book.published_year} г."
        )

    def test_card_without_year(self, client, book_of_user_2, author_2):
        book_of_user_2.published_year = None
        book_of_user_2.save()
        card = self.get_cards(client.get(reverse("books")))[0]
        assert text_of(card.select_one("p.text-muted.small")) == author_2.name

    def test_card_genres(self, client, book, genres):
        book.genres.set(genres)
        card = self.get_cards(client.get(reverse("books")))[0]
        badges = card.select(".badge.bg-light")
        assert [text_of(badge) for badge in badges] == [genre.name for genre in genres]

    def test_card_description_truncated(self, client, book):
        book.description = " ".join(f"слово{number}" for number in range(1, 31))
        book.save()
        card = self.get_cards(client.get(reverse("books")))[0]
        description = text_of(card.select_one(".card-text"))
        assert description.startswith("слово1 слово2")
        assert description.endswith("слово20 …")

    def test_card_without_description(self, client, book_of_user_2):  # pylint: disable=unused-argument
        card = self.get_cards(client.get(reverse("books")))[0]
        assert text_of(card.select_one(".card-text")) == "Описание пока не добавлено."

    def test_card_footer_links_to_reader(self, client, book, user_1):  # pylint: disable=unused-argument
        card = self.get_cards(client.get(reverse("books")))[0]
        link = card.select_one(".card-footer a")
        assert text_of(link) == user_1.display_name
        assert link["href"] == user_1.get_absolute_url()

    def test_empty_catalog(self, client):
        response = client.get(reverse("books"))
        assert not self.get_cards(response)
        assert text_of(get_soup(response).select_one(".alert-info")) == (
            "Книг нет — каталог пока пуст."
        )

    def test_add_button_hidden_for_anonymous(self, client):
        soup = get_soup(client.get(reverse("books")))
        assert soup.select_one(f'a[href="{reverse("book_add")}"].btn') is None

    def test_add_button_shown_for_authenticated(self, auth_client):
        soup = get_soup(auth_client.get(reverse("books")))
        button = soup.select_one(f'a[href="{reverse("book_add")}"].btn')
        assert text_of(button) == "Добавить книгу"


class TestBookDetailTemplate:
    """Страница книги."""

    def test_title_author_and_year(self, client, book):
        soup = get_soup(client.get(book.get_absolute_url()))
        assert text_of(soup.select_one("h1.card-title")) == book.title
        assert text_of(soup.select_one(".card-body > p.text-muted")) == (
            f"{book.author.name} · {book.published_year} г."
        )

    def test_description(self, client, book):
        soup = get_soup(client.get(book.get_absolute_url()))
        assert text_of(soup.select_one("p.card-text")) == book.description

    def test_placeholder_without_description(self, client, book_of_user_2):  # pylint: disable=unused-argument
        soup = get_soup(client.get(book_of_user_2.get_absolute_url()))
        placeholder = soup.select_one("p.card-text.fst-italic")
        assert text_of(placeholder) == "Описание пока не добавлено."

    def test_genres(self, client, book, genres):
        book.genres.set(genres)
        soup = get_soup(client.get(book.get_absolute_url()))
        badges = soup.select(".card-body .badge.bg-light")
        assert [text_of(badge) for badge in badges] == [genre.name for genre in genres]

    def test_author_bio(self, client, book, author):  # pylint: disable=unused-argument
        soup = get_soup(client.get(book.get_absolute_url()))
        assert text_of(soup.select_one("h2.h6")) == "Об авторе"
        assert author.bio in text_of(soup.select_one(".card-body"))

    def test_no_author_bio_block(self, client, book_of_user_2):  # pylint: disable=unused-argument
        soup = get_soup(client.get(book_of_user_2.get_absolute_url()))
        assert soup.select_one("h2.h6") is None

    def test_added_by_link(self, client, book, user_1):
        soup = get_soup(client.get(book.get_absolute_url()))
        link = soup.select_one(".card-footer a")
        assert text_of(link) == user_1.display_name
        assert link["href"] == user_1.get_absolute_url()

    def test_edit_buttons_hidden_for_anonymous(self, client, book):
        soup = get_soup(client.get(book.get_absolute_url()))
        assert soup.select_one(f'a[href="{reverse("book_edit", args=[book.pk])}"]') is None
        assert soup.select_one(f'a[href="{reverse("book_delete", args=[book.pk])}"]') is None

    def test_edit_buttons_shown_for_authenticated(self, auth_client, book):
        soup = get_soup(auth_client.get(book.get_absolute_url()))
        edit = soup.select_one(f'a[href="{reverse("book_edit", args=[book.pk])}"]')
        delete = soup.select_one(f'a[href="{reverse("book_delete", args=[book.pk])}"]')
        assert text_of(edit) == "Редактировать"
        assert text_of(delete) == "Удалить"

    def test_reviews_counter(self, client, book, reviews):
        soup = get_soup(client.get(book.get_absolute_url()))
        counter = soup.select_one(".badge.bg-secondary")
        assert text_of(counter) == f"Всего: {len(reviews)}"

    def test_reviews_ordered_by_date_desc(self, client, book, reviews):
        """Свежие отзывы показываем первыми."""
        soup = get_soup(client.get(book.get_absolute_url()))
        texts = [text_of(card.select_one(".card-text")) for card in review_cards(soup)]
        assert texts == [review.text for review in reversed(reviews)]

    def test_review_author_and_rating(self, client, book, review, user_2):
        soup = get_soup(client.get(book.get_absolute_url()))
        reader_link = soup.select_one(".fw-semibold")
        rating = soup.select_one(".rating")
        assert text_of(reader_link) == user_2.display_name
        assert reader_link["href"] == user_2.get_absolute_url()
        assert rating["title"] == f"Оценка: {review.rating} из 5"
        assert text_of(rating).replace(" ", "") == "★" * review.rating

    def test_partial_rating_stars(self, client, book, user_1):
        Review.objects.create(book=book, reader=user_1, text="Средне.", rating=3)
        soup = get_soup(client.get(book.get_absolute_url()))
        assert text_of(soup.select_one(".rating")).replace(" ", "") == "★★★☆☆"

    def test_review_text(self, client, book, review):
        soup = get_soup(client.get(book.get_absolute_url()))
        card = review_cards(soup)[0]
        assert text_of(card.select_one(".card-text")) == review.text

    def test_review_linebreaks(self, client, book, user_1):
        Review.objects.create(
            book=book, reader=user_1, text="Первая строка\nВторая строка", rating=4
        )
        soup = get_soup(client.get(book.get_absolute_url()))
        assert soup.select_one(".card-text br") is not None

    def test_no_reviews_placeholder(self, client, book):
        soup = get_soup(client.get(book.get_absolute_url()))
        assert text_of(soup.select_one(".alert-info")) == "Отзывов пока нет — будьте первым."


class TestBookFormTemplate:
    """Форма добавления и редактирования книги."""

    def test_add_page_headers(self, auth_client):
        soup = get_soup(auth_client.get(reverse("book_add")))
        assert text_of(soup.select_one(".card-header h1")) == "Добавить книгу"
        assert text_of(soup.select_one(".card-header p")) == (
            "Книга попадёт в общий каталог — её увидят все читатели."
        )

    def test_edit_page_headers(self, auth_client, book):
        soup = get_soup(auth_client.get(reverse("book_edit", args=[book.pk])))
        assert text_of(soup.select_one(".card-header h1")) == (
            f"Редактирование: {book.title}"
        )

    def test_form_attributes(self, auth_client):
        form = get_soup(auth_client.get(reverse("book_add"))).select_one(".card-body form")
        assert form["method"].lower() == "post"
        assert form.has_attr("novalidate")
        assert form.select_one('input[name="csrfmiddlewaretoken"]') is not None

    def test_all_form_fields_rendered(self, auth_client):
        response = auth_client.get(reverse("book_add"))
        soup = get_soup(response)
        rendered = {label["for"] for label in soup.select(".card-body form label.form-label")}
        expected = {field.id_for_label for field in response.context["form"]}
        assert rendered == expected

    def test_required_fields_marked(self, auth_client):
        response = auth_client.get(reverse("book_add"))
        soup = get_soup(response)
        marked = {
            label["for"]
            for label in soup.select("label.form-label")
            if label.select_one("span.text-danger")
        }
        expected = {
            field.id_for_label for field in response.context["form"] if field.field.required
        }
        assert marked == expected

    def test_genres_rendered_as_checkboxes(self, auth_client, genres):
        soup = get_soup(auth_client.get(reverse("book_add")))
        checks = soup.select(".genre-list .form-check")
        assert len(checks) == len(genres)
        labels = [text_of(check.label) for check in checks]
        assert labels == [genre.name for genre in genres]
        assert all(
            check.select_one('input[type="checkbox"]') is not None for check in checks
        )

    def test_genres_empty_placeholder(self, auth_client):
        soup = get_soup(auth_client.get(reverse("book_add")))
        assert not soup.select(".genre-list .form-check")
        assert "Жанров пока нет." in text_of(soup.select_one(".genre-list"))

    def test_edit_form_prefilled(self, auth_client, book, genre):
        soup = get_soup(auth_client.get(reverse("book_edit", args=[book.pk])))
        assert soup.select_one("#id_title")["value"] == book.title
        assert text_of(soup.select_one("#id_description")) == book.description
        checked = soup.select('.genre-list input[checked]')
        assert [check["value"] for check in checked] == [str(genre.pk)]

    def test_buttons(self, auth_client):
        soup = get_soup(auth_client.get(reverse("book_add")))
        submit = soup.select_one('.card-body form button[type="submit"]')
        assert text_of(submit) == "Добавить книгу"
        cancel = soup.select_one("a.btn-outline-secondary")
        assert text_of(cancel) == "Отмена"
        assert cancel["href"] == reverse("books")

    def test_edit_buttons(self, auth_client, book):
        soup = get_soup(auth_client.get(reverse("book_edit", args=[book.pk])))
        submit = soup.select_one('.card-body form button[type="submit"]')
        assert text_of(submit) == "Сохранить"
        assert soup.select_one("a.btn-outline-secondary")["href"] == book.get_absolute_url()

    def test_required_hint(self, auth_client):
        soup = get_soup(auth_client.get(reverse("book_add")))
        assert "обязательны для заполнения" in text_of(soup.select_one("main"))

    def test_field_errors_rendered(self, auth_client, book_form_data):
        book_form_data["title"] = ""
        soup = get_soup(auth_client.post(reverse("book_add"), book_form_data))
        invalid = soup.select_one(".field-invalid")
        assert invalid is not None
        assert invalid.select_one("label")["for"] == "id_title"
        assert text_of(invalid.select_one(".text-danger.mt-1")) == (
            "Название книги не заполнено."
        )

    def test_valid_fields_without_error_class(self, auth_client, book_form_data):
        book_form_data["title"] = ""
        soup = get_soup(auth_client.post(reverse("book_add"), book_form_data))
        assert len(soup.select(".field-invalid")) == 1


class TestBookDeleteTemplate:
    """Страница подтверждения удаления книги."""

    def test_headers(self, auth_client, book):
        soup = get_soup(auth_client.get(reverse("book_delete", args=[book.pk])))
        assert text_of(soup.select_one(".card-header h1")) == "Удалить книгу?"
        assert "Действие необратимо" in text_of(soup.select_one(".card-header p"))

    def test_book_info(self, auth_client, book):
        soup = get_soup(auth_client.get(reverse("book_delete", args=[book.pk])))
        assert text_of(soup.select_one(".card-body h2")) == book.title
        assert text_of(soup.select_one(".card-body p.text-muted")) == (
            f"{book.author.name} · {book.published_year} г."
        )
        assert text_of(soup.select_one(".card-body p.card-text")) == book.description

    def test_genres(self, auth_client, book, genres):
        book.genres.set(genres)
        soup = get_soup(auth_client.get(reverse("book_delete", args=[book.pk])))
        badges = soup.select(".card-body .badge.bg-light")
        assert [text_of(badge) for badge in badges] == [genre.name for genre in genres]

    def test_added_by_link(self, auth_client, book, user_1):
        soup = get_soup(auth_client.get(reverse("book_delete", args=[book.pk])))
        link = soup.select_one(".card-body a")
        assert text_of(link) == user_1.display_name
        assert link["href"] == user_1.get_absolute_url()

    def test_reviews_warning(self, auth_client, book, reviews):
        soup = get_soup(auth_client.get(reverse("book_delete", args=[book.pk])))
        warning = soup.select_one(".alert-warning")
        assert warning is not None
        assert f"{len(reviews)} шт." in text_of(warning)

    def test_no_warning_without_reviews(self, auth_client, book):
        soup = get_soup(auth_client.get(reverse("book_delete", args=[book.pk])))
        assert soup.select_one(".alert-warning") is None

    def test_confirm_form(self, auth_client, book):
        soup = get_soup(auth_client.get(reverse("book_delete", args=[book.pk])))
        form = soup.select_one(".card-footer form")
        assert form["method"].lower() == "post"
        assert form.select_one('input[name="csrfmiddlewaretoken"]') is not None
        assert text_of(form.select_one('button[type="submit"]')) == "Удалить книгу"

    def test_cancel_link(self, auth_client, book):
        soup = get_soup(auth_client.get(reverse("book_delete", args=[book.pk])))
        cancel = soup.select_one(".card-footer a")
        assert text_of(cancel) == "Отмена"
        assert cancel["href"] == book.get_absolute_url()
