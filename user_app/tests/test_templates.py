"""Тесты шаблонов пользователей: разметку разбираем через BeautifulSoup."""

import pytest
from bs4 import BeautifulSoup
from django.urls import reverse

# Почти все страницы приложения опираются на данные из базы.
pytestmark = pytest.mark.django_db


def get_soup(response):
    """HTML ответа в виде дерева BeautifulSoup."""
    return BeautifulSoup(response.content.decode(), "html.parser")


def text_of(tag):
    """Текст тега без лишних пробелов и переносов строк."""
    return " ".join(tag.get_text().split())


def activity_cards(soup):
    """Две карточки блока активности: книги и отзывы."""
    return soup.select(".row.g-4 .card")


class TestUserFormTemplate:
    """Общий шаблон форм регистрации и входа."""

    def test_register_headers(self, client):
        soup = get_soup(client.get(reverse("register")))
        assert text_of(soup.select_one(".card-header h1")) == "Регистрация"
        assert text_of(soup.select_one(".card-header p")) == (
            "Заведите учётную запись, чтобы вести свой дневник читателя."
        )

    def test_login_headers(self, client):
        soup = get_soup(client.get(reverse("login")))
        assert text_of(soup.select_one(".card-header h1")) == "Вход"
        assert text_of(soup.select_one(".card-header p")) == (
            "Войдите, чтобы добавлять книги и писать отзывы."
        )

    def test_form_attributes(self, client):
        form = get_soup(client.get(reverse("register"))).select_one(".card-body form")
        assert form["method"].lower() == "post"
        assert form.has_attr("novalidate")
        assert form.select_one('input[name="csrfmiddlewaretoken"]') is not None

    def test_all_form_fields_rendered(self, client):
        response = client.get(reverse("register"))
        soup = get_soup(response)
        rendered = {label["for"] for label in soup.select(".card-body form label.form-label")}
        expected = {field.id_for_label for field in response.context["form"]}
        assert rendered == expected

    def test_required_fields_marked(self, client):
        response = client.get(reverse("register"))
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

    def test_help_texts_rendered(self, client):
        soup = get_soup(client.get(reverse("register")))
        hints = [text_of(hint) for hint in soup.select(".form-text")]
        assert "На этот адрес вы будете входить на сайт." in hints

    def test_password_inputs_are_hidden(self, client):
        soup = get_soup(client.get(reverse("register")))
        assert soup.select_one("#id_password1")["type"] == "password"
        assert soup.select_one("#id_password2")["type"] == "password"

    def test_register_buttons(self, client):
        soup = get_soup(client.get(reverse("register")))
        submit = soup.select_one('.card-body form button[type="submit"]')
        assert text_of(submit) == "Зарегистрироваться"
        cancel = soup.select_one("a.btn-outline-secondary")
        assert text_of(cancel) == "Отмена"
        assert cancel["href"] == reverse("index")

    def test_login_buttons(self, client):
        soup = get_soup(client.get(reverse("login")))
        submit = soup.select_one('.card-body form button[type="submit"]')
        assert text_of(submit) == "Войти"

    def test_register_alt_link(self, client):
        soup = get_soup(client.get(reverse("register")))
        note = soup.select_one("p.text-muted.small.mt-3")
        assert "Уже зарегистрированы?" in text_of(note)
        assert note.a["href"] == reverse("login")
        assert text_of(note.a) == "Войти"

    def test_login_alt_link(self, client):
        soup = get_soup(client.get(reverse("login")))
        note = soup.select_one("p.text-muted.small.mt-3")
        assert "Ещё нет учётной записи?" in text_of(note)
        assert note.a["href"] == reverse("register")
        assert text_of(note.a) == "Зарегистрироваться"

    def test_field_errors_rendered(self, client, register_form_data):
        register_form_data["email"] = ""
        soup = get_soup(client.post(reverse("register"), register_form_data))
        invalid = soup.select_one(".field-invalid")
        assert invalid is not None
        assert invalid.select_one("label")["for"] == "id_email"
        assert text_of(invalid.select_one(".text-danger.mt-1")) == "Email не заполнен."

    def test_valid_fields_without_error_class(self, client, register_form_data):
        register_form_data["email"] = ""
        soup = get_soup(client.post(reverse("register"), register_form_data))
        assert len(soup.select(".field-invalid")) == 1

    def test_non_field_errors_rendered(self, client, login_form_data):
        login_form_data["password"] = "неверный"
        soup = get_soup(client.post(reverse("login"), login_form_data))
        alert = soup.select_one(".alert-danger")
        assert alert is not None
        assert text_of(alert) == "Неверный email или пароль."

    def test_no_error_alert_on_clean_form(self, client):
        soup = get_soup(client.get(reverse("login")))
        assert soup.select_one(".alert-danger") is None

    def test_breadcrumbs(self, client):
        soup = get_soup(client.get(reverse("register")))
        crumbs = soup.select(".breadcrumb .breadcrumb-item")
        assert [text_of(crumb) for crumb in crumbs] == ["Главная", "Регистрация"]


class TestUserDetailTemplate:
    """Публичная страница читателя."""

    def test_title_and_heading(self, client, user_1):
        soup = get_soup(client.get(user_1.get_absolute_url()))
        assert text_of(soup.title) == user_1.display_name
        assert text_of(soup.select_one("h1.h3")) == user_1.display_name

    def test_heading_for_reader_without_username(self, client, user_2):
        soup = get_soup(client.get(user_2.get_absolute_url()))
        assert text_of(soup.select_one("h1.h3")) == user_2.email

    def test_full_name_and_birth_date(self, client, user_1):
        soup = get_soup(client.get(user_1.get_absolute_url()))
        muted = [text_of(tag) for tag in soup.select(".card-body p.text-muted")]
        assert user_1.full_name in muted
        assert "Дата рождения: 15.01.1990" in muted

    def test_no_full_name_and_birth_date(self, client, user_2):
        soup = get_soup(client.get(user_2.get_absolute_url()))
        assert "Дата рождения" not in text_of(soup.select_one(".card-body"))

    def test_about(self, client, user_1):
        soup = get_soup(client.get(user_1.get_absolute_url()))
        assert user_1.about in text_of(soup.select_one(".card-body .flex-grow-1"))

    def test_about_linebreaks(self, client, user_1):
        user_1.about = "Первая строка\nВторая строка"
        user_1.save()
        soup = get_soup(client.get(user_1.get_absolute_url()))
        assert soup.select_one(".card-body .flex-grow-1 br") is not None

    def test_about_placeholder(self, client, user_2):
        soup = get_soup(client.get(user_2.get_absolute_url()))
        placeholder = soup.select_one(".card-body p.fst-italic")
        assert text_of(placeholder) == "Читатель пока ничего о себе не написал."

    def test_edit_link_for_owner(self, auth_client, user_1):
        soup = get_soup(auth_client.get(user_1.get_absolute_url()))
        link = soup.select_one(f'a[href="{reverse("profile")}"].btn')
        assert text_of(link) == "Редактировать профиль"

    def test_no_edit_link_for_another_reader(self, auth_client_2, user_1):
        soup = get_soup(auth_client_2.get(user_1.get_absolute_url()))
        assert soup.select_one(f'a[href="{reverse("profile")}"].btn') is None

    def test_no_edit_link_for_anonymous(self, client, user_1):
        soup = get_soup(client.get(user_1.get_absolute_url()))
        assert soup.select_one(f'a[href="{reverse("profile")}"].btn') is None

    def test_breadcrumbs(self, client, user_1):
        soup = get_soup(client.get(user_1.get_absolute_url()))
        crumbs = soup.select(".breadcrumb .breadcrumb-item")
        assert [text_of(crumb) for crumb in crumbs] == ["Главная", user_1.display_name]


class TestAvatarTemplate:
    """Аватар читателя."""

    def test_placeholder_with_first_letter(self, client, user_1):
        soup = get_soup(client.get(user_1.get_absolute_url()))
        placeholder = soup.select_one("span.rounded-circle")
        assert text_of(placeholder) == user_1.display_name[0].upper()
        assert placeholder["aria-hidden"] == "true"
        assert soup.select_one("img.rounded-circle") is None

    def test_image_shown(self, client, user_1, avatar):
        user_1.avatar = avatar
        user_1.save()
        soup = get_soup(client.get(user_1.get_absolute_url()))
        image = soup.select_one("img.rounded-circle")
        assert image["src"] == user_1.avatar.url
        assert image["alt"] == f"Аватар {user_1.display_name}"
        assert soup.select_one("span.rounded-circle") is None

    def test_shown_on_profile_page(self, auth_client, user_1):
        soup = get_soup(auth_client.get(reverse("profile")))
        assert text_of(soup.select_one("span.rounded-circle")) == (
            user_1.display_name[0].upper()
        )


class TestReaderActivityTemplate:
    """Блок «книги и отзывы читателя»."""

    def test_headings(self, client, user_1):
        soup = get_soup(client.get(user_1.get_absolute_url()))
        headings = [text_of(card.select_one("h2")) for card in activity_cards(soup)]
        assert headings == ["Добавленные книги", "Отзывы"]

    def test_counters(self, client, user_1, books, reviews):  # pylint: disable=unused-argument
        soup = get_soup(client.get(user_1.get_absolute_url()))
        counters = [
            text_of(card.select_one(".badge.bg-secondary")) for card in activity_cards(soup)
        ]
        # Фикстура reviews заводит читателю ещё книги, поэтому считаем их по базе.
        assert counters == [str(user_1.added_books.count()), str(len(reviews))]

    def test_book_links(self, client, user_1, book):
        soup = get_soup(client.get(user_1.get_absolute_url()))
        item = activity_cards(soup)[0].select_one(".list-group-item")
        assert text_of(item.a) == book.title
        assert item.a["href"] == book.get_absolute_url()
        assert text_of(item.select_one("span.text-muted")) == book.author.name

    def test_books_sorted_by_title(self, client, user_1, books):
        soup = get_soup(client.get(user_1.get_absolute_url()))
        items = activity_cards(soup)[0].select(".list-group-item a")
        assert [text_of(item) for item in items] == sorted(
            book.title for book in books
        )

    def test_empty_books_placeholder(self, client, user_1):
        soup = get_soup(client.get(user_1.get_absolute_url()))
        item = activity_cards(soup)[0].select_one(".list-group-item")
        assert text_of(item) == "Книг в каталог пока не добавлено."

    def test_review_item(self, client, user_1, review):
        soup = get_soup(client.get(user_1.get_absolute_url()))
        item = activity_cards(soup)[1].select_one(".list-group-item")
        assert text_of(item.a) == review.book.title
        assert item.a["href"] == review.book.get_absolute_url()
        assert review.text in text_of(item)

    def test_review_rating_stars(self, client, user_1, review):
        soup = get_soup(client.get(user_1.get_absolute_url()))
        rating = activity_cards(soup)[1].select_one(".rating")
        assert rating["title"] == f"Оценка: {review.rating} из 5"
        assert text_of(rating).replace(" ", "") == "★" * review.rating

    # reviews нужен как данные в базе, обращаться к нему в тесте не требуется.
    def test_partial_rating_stars(self, client, user_1, reviews):  # pylint: disable=unused-argument
        soup = get_soup(client.get(user_1.get_absolute_url()))
        ratings = activity_cards(soup)[1].select(".rating")
        assert "★★★☆☆" in [text_of(rating).replace(" ", "") for rating in ratings]

    def test_reviews_ordered_by_date_desc(self, client, user_1, reviews):
        soup = get_soup(client.get(user_1.get_absolute_url()))
        items = activity_cards(soup)[1].select(".list-group-item")
        titles = [text_of(item.a) for item in items]
        assert titles == [review.book.title for review in reversed(reviews)]

    def test_review_text_truncated(self, client, user_1, review):
        review.text = " ".join(f"слово{number}" for number in range(1, 31))
        review.save()
        soup = get_soup(client.get(user_1.get_absolute_url()))
        text = text_of(activity_cards(soup)[1].select_one("p.small"))
        assert text.startswith("слово1 слово2")
        assert text.endswith("слово25 …")

    def test_empty_reviews_placeholder(self, client, user_1):
        soup = get_soup(client.get(user_1.get_absolute_url()))
        item = activity_cards(soup)[1].select_one(".list-group-item")
        assert text_of(item) == "Отзывов пока нет."

    def test_shown_on_profile_page(self, auth_client, book):
        soup = get_soup(auth_client.get(reverse("profile")))
        item = activity_cards(soup)[0].select_one(".list-group-item")
        assert text_of(item.a) == book.title


class TestProfileTemplate:
    """Страница «Мой профиль»."""

    def test_headers(self, auth_client):
        soup = get_soup(auth_client.get(reverse("profile")))
        assert text_of(soup.select_one(".card-header h1")) == "Мой профиль"
        assert text_of(soup.select_one(".card-header p")) == (
            "Так вас увидят другие читатели."
        )

    def test_link_to_public_page(self, auth_client, user_1):
        soup = get_soup(auth_client.get(reverse("profile")))
        link = soup.select_one(f'a[href="{user_1.get_absolute_url()}"].btn')
        assert text_of(link) == "Как видят другие"

    def test_display_name_and_email(self, auth_client, user_1):
        soup = get_soup(auth_client.get(reverse("profile")))
        assert text_of(soup.select_one(".card-body .fw-semibold")) == user_1.display_name
        assert user_1.email in text_of(soup.select_one(".card-body"))

    def test_form_accepts_files(self, auth_client):
        form = get_soup(auth_client.get(reverse("profile"))).select_one(".card-body form")
        assert form["method"].lower() == "post"
        assert form["enctype"] == "multipart/form-data"
        assert form.has_attr("novalidate")
        assert form.select_one('input[name="csrfmiddlewaretoken"]') is not None

    def test_all_form_fields_rendered(self, auth_client):
        response = auth_client.get(reverse("profile"))
        soup = get_soup(response)
        rendered = {label["for"] for label in soup.select(".card-body form label.form-label")}
        expected = {field.id_for_label for field in response.context["form"]}
        assert rendered == expected

    def test_no_required_marks(self, auth_client):
        """Все поля профиля необязательные — звёздочек нет."""
        soup = get_soup(auth_client.get(reverse("profile")))
        marked = [
            label for label in soup.select("label.form-label")
            if label.select_one("span.text-danger")
        ]
        assert not marked

    def test_form_prefilled(self, auth_client, user_1):
        soup = get_soup(auth_client.get(reverse("profile")))
        assert soup.select_one("#id_username")["value"] == user_1.username
        assert soup.select_one("#id_full_name")["value"] == user_1.full_name
        assert text_of(soup.select_one("#id_about")) == user_1.about
        assert soup.select_one("#id_date_of_birth")["value"] == "1990-01-15"

    def test_buttons(self, auth_client):
        soup = get_soup(auth_client.get(reverse("profile")))
        submit = soup.select_one('.card-body form button[type="submit"]')
        assert text_of(submit) == "Сохранить"
        cancel = soup.select_one(".card-body a.btn-outline-secondary")
        assert text_of(cancel) == "Отмена"
        assert cancel["href"] == reverse("index")

    def test_field_errors_rendered(self, auth_client, profile_form_data):
        profile_form_data["date_of_birth"] = "вчера"
        soup = get_soup(auth_client.post(reverse("profile"), profile_form_data))
        invalid = soup.select_one(".field-invalid")
        assert invalid is not None
        assert invalid.select_one("label")["for"] == "id_date_of_birth"
        assert len(soup.select(".field-invalid")) == 1

    def test_success_message_shown(self, auth_client, profile_form_data):
        response = auth_client.post(reverse("profile"), profile_form_data, follow=True)
        alert = get_soup(response).select_one(".alert-dismissible")
        assert alert is not None
        assert "Профиль сохранён." in text_of(alert)

    def test_breadcrumbs(self, auth_client):
        soup = get_soup(auth_client.get(reverse("profile")))
        crumbs = soup.select(".breadcrumb .breadcrumb-item")
        assert [text_of(crumb) for crumb in crumbs] == ["Главная", "Мой профиль"]


class TestMenuForReader:
    """Меню шапки в части, связанной с пользователем."""

    def test_profile_link_for_authenticated(self, auth_client, user_1):
        soup = get_soup(auth_client.get(reverse("index")))
        links = {text_of(link): link for link in soup.select("nav.navbar .nav-link")}
        assert user_1.display_name in links
        assert links[user_1.display_name]["href"] == reverse("profile")

    def test_email_in_menu_without_username(self, auth_client_2, user_2):
        soup = get_soup(auth_client_2.get(reverse("index")))
        links = [text_of(link) for link in soup.select("nav.navbar .nav-link")]
        assert user_2.email in links

    def test_login_and_register_for_anonymous(self, client):
        soup = get_soup(client.get(reverse("index")))
        hrefs = [link["href"] for link in soup.select("nav.navbar .nav-link")]
        assert reverse("login") in hrefs
        assert reverse("register") in hrefs
