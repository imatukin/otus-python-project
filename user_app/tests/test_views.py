"""Тесты представлений приложения пользователей."""

import pytest
from django.urls import reverse

from user_app.models import CustomUser


class TestRegisterView:
    """Регистрация нового читателя."""

    @pytest.mark.django_db
    def test_status_and_template(self, client):
        response = client.get(reverse("register"))
        assert response.status_code == 200
        assert "user_app/user_form.html" in [t.name for t in response.templates]

    @pytest.mark.django_db
    def test_context(self, client):
        response = client.get(reverse("register"))
        assert response.context["page_title"] == "Регистрация"
        assert response.context["submit_label"] == "Зарегистрироваться"
        assert response.context["cancel_url"] == reverse("index")
        assert response.context["alt_url"] == reverse("login")
        assert response.context["alt_label"] == "Войти"

    @pytest.mark.django_db
    def test_breadcrumbs(self, client):
        response = client.get(reverse("register"))
        titles = [crumb["title"] for crumb in response.context["breadcrumbs"]]
        assert titles == ["Главная", "Регистрация"]

    @pytest.mark.django_db
    def test_user_created(self, client, register_form_data):
        response = client.post(reverse("register"), data=register_form_data)
        assert response.status_code == 302
        assert response.url == reverse("index")
        assert CustomUser.objects.filter(email=register_form_data["email"]).exists()

    @pytest.mark.django_db
    def test_user_logged_in_after_registration(self, client, register_form_data):
        """После регистрации пользователь сразу попадает на сайт."""
        response = client.post(reverse("register"), data=register_form_data, follow=True)
        assert response.context["user"].is_authenticated
        assert response.context["user"].email == register_form_data["email"]

    @pytest.mark.django_db
    def test_success_message(self, client, register_form_data):
        response = client.post(reverse("register"), data=register_form_data, follow=True)
        messages = [str(message) for message in response.context["messages"]]
        assert f"Добро пожаловать, {register_form_data['email']}!" in messages

    @pytest.mark.django_db
    def test_invalid_form_does_not_create_user(self, client, register_form_data):
        register_form_data["password2"] = "другой пароль"
        response = client.post(reverse("register"), data=register_form_data)
        assert response.status_code == 200
        assert not CustomUser.objects.exists()
        assert "password2" in response.context["form"].errors

    @pytest.mark.django_db
    def test_duplicate_email_rejected(self, client, register_form_data, user_1):
        register_form_data["email"] = user_1.email
        response = client.post(reverse("register"), data=register_form_data)
        assert response.status_code == 200
        assert CustomUser.objects.count() == 1


class TestUserLoginView:
    """Вход по email."""

    @pytest.mark.django_db
    def test_status_and_template(self, client):
        response = client.get(reverse("login"))
        assert response.status_code == 200
        assert "user_app/user_form.html" in [t.name for t in response.templates]

    @pytest.mark.django_db
    def test_context(self, client):
        response = client.get(reverse("login"))
        assert response.context["page_title"] == "Вход"
        assert response.context["submit_label"] == "Войти"
        assert response.context["alt_url"] == reverse("register")
        assert response.context["alt_label"] == "Зарегистрироваться"

    @pytest.mark.django_db
    def test_breadcrumbs(self, client):
        response = client.get(reverse("login"))
        titles = [crumb["title"] for crumb in response.context["breadcrumbs"]]
        assert titles == ["Главная", "Вход"]

    @pytest.mark.django_db
    def test_login_success(self, client, login_form_data, user_1):
        response = client.post(reverse("login"), data=login_form_data, follow=True)
        assert response.status_code == 200
        assert response.context["user"] == user_1

    @pytest.mark.django_db
    def test_redirects_to_index(self, client, login_form_data):
        response = client.post(reverse("login"), data=login_form_data)
        assert response.status_code == 302
        assert response.url == reverse("index")

    @pytest.mark.django_db
    def test_redirects_to_next(self, client, login_form_data):
        url = f"{reverse('login')}?next={reverse('profile')}"
        response = client.post(url, data=login_form_data)
        assert response.status_code == 302
        assert response.url == reverse("profile")

    @pytest.mark.django_db
    def test_login_with_email_in_other_case(self, client, login_form_data, user_1):
        login_form_data["username"] = user_1.email.upper()
        response = client.post(reverse("login"), data=login_form_data)
        assert response.status_code == 302

    @pytest.mark.django_db
    def test_wrong_password(self, client, login_form_data):
        login_form_data["password"] = "неверный"
        response = client.post(reverse("login"), data=login_form_data)
        assert response.status_code == 200
        assert not response.context["user"].is_authenticated
        assert response.context["form"].errors["__all__"] == [
            "Неверный email или пароль."
        ]

    @pytest.mark.django_db
    def test_authenticated_user_redirected(self, auth_client):
        """Залогиненного пользователя страница входа отправляет на главную."""
        response = auth_client.get(reverse("login"))
        assert response.status_code == 302
        assert response.url == reverse("index")


class TestUserLogoutView:
    """Выход из учётной записи."""

    @pytest.mark.django_db
    def test_logout(self, auth_client):
        response = auth_client.post(reverse("logout"))
        assert response.status_code == 302
        assert response.url == reverse("index")

    @pytest.mark.django_db
    def test_user_is_anonymous_after_logout(self, auth_client):
        response = auth_client.post(reverse("logout"), follow=True)
        assert not response.context["user"].is_authenticated

    @pytest.mark.django_db
    def test_get_is_not_allowed(self, auth_client):
        """Выход только POST-запросом."""
        response = auth_client.get(reverse("logout"))
        assert response.status_code == 405


class TestUserDetailView:
    """Публичная страница читателя."""

    @pytest.mark.django_db
    def test_status_and_template(self, client, user_1):
        response = client.get(user_1.get_absolute_url())
        assert response.status_code == 200
        assert "user_app/user_detail.html" in [t.name for t in response.templates]

    @pytest.mark.django_db
    def test_context_object(self, client, user_1):
        response = client.get(user_1.get_absolute_url())
        assert response.context["reader"] == user_1
        assert response.context["page_title"] == user_1.display_name

    @pytest.mark.django_db
    def test_missing_user_returns_404(self, client):
        response = client.get(reverse("user_detail", args=[404]))
        assert response.status_code == 404

    @pytest.mark.django_db
    def test_available_for_anonymous(self, client, user_1):
        response = client.get(user_1.get_absolute_url())
        assert response.status_code == 200

    @pytest.mark.django_db
    def test_breadcrumbs(self, client, user_1):
        response = client.get(user_1.get_absolute_url())
        titles = [crumb["title"] for crumb in response.context["breadcrumbs"]]
        assert titles == ["Главная", user_1.display_name]

    @pytest.mark.django_db
    def test_books_in_context(self, client, user_1, books):
        response = client.get(user_1.get_absolute_url())
        assert list(response.context["books"]) == sorted(
            books, key=lambda item: item.title
        )

    @pytest.mark.django_db
    def test_reviews_ordered_by_date_desc(self, client, user_1, reviews):
        response = client.get(user_1.get_absolute_url())
        assert list(response.context["reviews"]) == sorted(
            reviews, key=lambda item: item.created_at, reverse=True
        )

    @pytest.mark.django_db
    # book нужен как данные в базе, обращаться к нему в тесте не требуется.
    def test_books_of_another_reader_not_shown(self, client, user_2, book):  # pylint: disable=unused-argument
        response = client.get(user_2.get_absolute_url())
        assert not list(response.context["books"])

    @pytest.mark.django_db
    def test_is_own_profile_for_owner(self, auth_client, user_1):
        response = auth_client.get(user_1.get_absolute_url())
        assert response.context["is_own_profile"] is True

    @pytest.mark.django_db
    def test_is_own_profile_for_another_reader(self, auth_client_2, user_1):
        response = auth_client_2.get(user_1.get_absolute_url())
        assert response.context["is_own_profile"] is False

    @pytest.mark.django_db
    def test_is_own_profile_for_anonymous(self, client, user_1):
        response = client.get(user_1.get_absolute_url())
        assert response.context["is_own_profile"] is False


class TestProfileView:
    """Свой профиль — просмотр и редактирование."""

    @pytest.mark.django_db
    def test_anonymous_redirected_to_login(self, client):
        url = reverse("profile")
        response = client.get(url)
        assert response.status_code == 302
        assert response.url == f"{reverse('login')}?next={url}"

    @pytest.mark.django_db
    def test_status_and_template(self, auth_client):
        response = auth_client.get(reverse("profile"))
        assert response.status_code == 200
        assert "user_app/profile.html" in [t.name for t in response.templates]

    @pytest.mark.django_db
    def test_edits_current_user(self, auth_client, user_1):
        response = auth_client.get(reverse("profile"))
        assert response.context["form"].instance == user_1

    @pytest.mark.django_db
    def test_context(self, auth_client):
        response = auth_client.get(reverse("profile"))
        assert response.context["page_title"] == "Мой профиль"
        assert response.context["submit_label"] == "Сохранить"
        assert response.context["cancel_url"] == reverse("index")

    @pytest.mark.django_db
    def test_breadcrumbs(self, auth_client):
        response = auth_client.get(reverse("profile"))
        titles = [crumb["title"] for crumb in response.context["breadcrumbs"]]
        assert titles == ["Главная", "Мой профиль"]

    @pytest.mark.django_db
    def test_books_and_reviews_in_context(self, auth_client, user_1, books, reviews):  # pylint: disable=unused-argument
        response = auth_client.get(reverse("profile"))
        assert list(response.context["books"]) == list(
            user_1.added_books.order_by("title")
        )
        assert list(response.context["reviews"]) == sorted(
            reviews, key=lambda item: item.created_at, reverse=True
        )

    @pytest.mark.django_db
    def test_profile_updated(self, auth_client, user_1, profile_form_data):
        profile_form_data["username"] = "Новое имя"
        response = auth_client.post(reverse("profile"), data=profile_form_data)
        user_1.refresh_from_db()
        assert response.status_code == 302
        assert response.url == reverse("profile")
        assert user_1.username == "Новое имя"

    @pytest.mark.django_db
    def test_avatar_uploaded(self, auth_client, user_1, profile_form_data, avatar):
        profile_form_data["avatar"] = avatar
        response = auth_client.post(reverse("profile"), data=profile_form_data)
        user_1.refresh_from_db()
        assert response.status_code == 302
        assert user_1.avatar.name.startswith("avatars/")

    @pytest.mark.django_db
    def test_success_message(self, auth_client, profile_form_data):
        response = auth_client.post(
            reverse("profile"), data=profile_form_data, follow=True
        )
        messages = [str(message) for message in response.context["messages"]]
        assert "Профиль сохранён." in messages

    @pytest.mark.django_db
    def test_invalid_form_does_not_change_profile(
        self, auth_client, user_1, profile_form_data
    ):
        profile_form_data["date_of_birth"] = "вчера"
        profile_form_data["username"] = "Новое имя"
        response = auth_client.post(reverse("profile"), data=profile_form_data)
        user_1.refresh_from_db()
        assert response.status_code == 200
        assert user_1.username == "user_1"
        assert "date_of_birth" in response.context["form"].errors

    @pytest.mark.django_db
    def test_cannot_edit_another_user(self, auth_client_2, user_1, profile_form_data):
        """Форма всегда правит того, кто вошёл, — чужой профиль не задеть."""
        profile_form_data["username"] = "Чужое имя"
        auth_client_2.post(reverse("profile"), data=profile_form_data)
        user_1.refresh_from_db()
        assert user_1.username == "user_1"
