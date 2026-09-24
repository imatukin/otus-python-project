"""Тесты мягкого удаления пользователя: вход, сессии, регистрация, страница читателя, админка."""

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth import authenticate
from django.contrib.auth.models import AbstractUser
from django.urls import reverse

from bookshelf_app.models import Book, Review
from user_app.forms import CustomUserCreationForm
from user_app.models import CustomUser

pytestmark = pytest.mark.django_db


class TestModel:
    """Пометка и менеджеры."""

    def test_delete_is_soft(self, user_1, superuser):
        user_1.delete(user=superuser)
        user = CustomUser.all_objects.get(pk=user_1.pk)
        assert user.is_deleted is True
        assert user.deleted_by == superuser

    def test_default_manager_hides_deleted(self, user_1, user_2):
        user_1.delete()
        assert list(CustomUser.objects.all()) == [user_2]
        assert CustomUser._default_manager.model is CustomUser  # pylint: disable=protected-access
        assert set(CustomUser.all_objects.all()) == {user_1, user_2}

    def test_manager_keeps_user_methods(self, password):
        """Менеджер по умолчанию умеет create_user — на нём работает createsuperuser."""
        assert hasattr(CustomUser._default_manager, "create_superuser")  # pylint: disable=protected-access
        user = CustomUser.objects.create_user(email="new@mail.ru", password=password)
        assert user.pk is not None

    def test_meta_from_abstract_user(self):
        """Настройки AbstractUser.Meta не потерялись из-за второго родителя."""
        assert CustomUser._meta.verbose_name == AbstractUser._meta.verbose_name

    def test_books_and_reviews_kept(self, user_1, book, review):
        user_1.delete()
        assert Book.objects.filter(pk=book.pk).exists()
        assert Review.objects.filter(pk=review.pk).exists()


class TestAuthentication:
    """Удалённый пользователь не может войти, открытые сессии гаснут."""

    def test_authenticate_fails(self, user_1, password):
        user_1.delete()
        assert authenticate(username=user_1.email, password=password) is None

    def test_login_form_standard_error(self, client, login_form_data, user_1):
        user_1.delete()
        response = client.post(reverse("login"), data=login_form_data)
        assert response.status_code == 200
        assert not response.context["user"].is_authenticated
        assert response.context["form"].errors["__all__"] == ["Неверный email или пароль."]

    def test_session_invalidated(self, auth_client, user_1):
        user_1.delete()
        response = auth_client.get(reverse("profile"))
        assert response.status_code == 302
        assert response.url.startswith(reverse("login"))

    def test_restored_user_can_login(self, client, login_form_data, user_1):
        user_1.delete()
        CustomUser.all_objects.get(pk=user_1.pk).restore()
        response = client.post(reverse("login"), data=login_form_data)
        assert response.status_code == 302


class TestRegistration:
    """Email удалённого остаётся занятым."""

    def test_email_taken(self, register_form_data, user_1):
        user_1.delete()
        register_form_data["email"] = user_1.email.upper()
        form = CustomUserCreationForm(data=register_form_data)
        assert not form.is_valid()
        # Сообщение то же, что и для живого пользователя: не раскрываем, что запись удалена.
        assert form.errors["email"] == [
            f"Читатель с адресом «{user_1.email}» уже зарегистрирован."
        ]

    def test_register_view_does_not_create_user(self, client, register_form_data, user_1):
        user_1.delete()
        register_form_data["email"] = user_1.email
        response = client.post(reverse("register"), data=register_form_data)
        assert response.status_code == 200
        assert CustomUser.all_objects.filter(email=user_1.email).count() == 1


class TestDeletedReaderPage:
    """Страница удалённого читателя остаётся, его книги и отзывы видны."""

    def test_page_available(self, client, user_1, book, review):
        user_1.delete()
        response = client.get(user_1.get_absolute_url())
        assert response.status_code == 200
        assert list(response.context["books"]) == [book]
        assert list(response.context["reviews"]) == [review]

    def test_deleted_badge(self, client, user_1):
        user_1.delete()
        soup = BeautifulSoup(client.get(user_1.get_absolute_url()).content.decode(), "html.parser")
        assert soup.select_one(".reader-deleted").get_text(strip=True) == "Учётная запись удалена"

    def test_no_badge_for_alive(self, client, user_1):
        soup = BeautifulSoup(client.get(user_1.get_absolute_url()).content.decode(), "html.parser")
        assert soup.select_one(".reader-deleted") is None

    def test_deleted_books_and_reviews_hidden(self, client, user_1, books, reviews):
        books[0].delete()
        reviews[0].delete()
        response = client.get(user_1.get_absolute_url())
        assert books[0] not in list(response.context["books"])
        assert list(response.context["reviews"]) == [reviews[1]]


class TestAdmin:
    """Пользователи в админке."""

    def test_changelist_shows_deleted(self, client, superuser, user_1):
        client.force_login(superuser)
        user_1.delete()
        response = client.get(reverse("admin:user_app_customuser_changelist"))
        assert user_1 in list(response.context["cl"].queryset)

    def test_change_page_has_deletion_block(self, client, superuser, user_1):
        client.force_login(superuser)
        user_1.delete()
        response = client.get(reverse("admin:user_app_customuser_change", args=[user_1.pk]))
        assert response.status_code == 200
        assert [fieldset.name for fieldset in response.context["adminform"]][-1] == "Удаление"

    def test_add_page_uses_add_fieldsets(self, client, superuser):
        client.force_login(superuser)
        response = client.get(reverse("admin:user_app_customuser_add"))
        assert "is_deleted" not in response.context["adminform"].form.fields

    def test_delete_confirmation_has_no_cascade(self, client, superuser, user_1, book, review):
        """Пользователь удаляется один: книги и отзывы остаются на сайте."""
        client.force_login(superuser)
        url = reverse("admin:user_app_customuser_delete", args=[user_1.pk])
        response = client.get(url)
        assert len(response.context["deleted_objects"]) == 1
        client.post(url, {"post": "yes"})
        assert CustomUser.all_objects.get(pk=user_1.pk).is_deleted is True
        assert Book.objects.filter(pk=book.pk).exists()
        assert Review.objects.filter(pk=review.pk).exists()

    def test_restore_action(self, client, superuser, user_1, password):
        client.force_login(superuser)
        user_1.delete()
        client.post(
            reverse("admin:user_app_customuser_changelist"),
            {"action": "restore_selected", "_selected_action": [user_1.pk]},
        )
        assert authenticate(username=user_1.email, password=password) == user_1
