"""Тесты моделей приложения пользователей."""

import datetime

import pytest
from django.db import IntegrityError
from django.urls import reverse

from user_app.models import CustomUser


class TestCustomUserManager:
    """Менеджер пользователей: вместо логина — email."""

    @pytest.mark.django_db
    def test_create_user(self, password):
        user = CustomUser.objects.create_user(email="reader@mail.ru", password=password)
        assert user.pk is not None
        assert user.email == "reader@mail.ru"
        assert user.check_password(password)
        assert user.is_active
        assert not user.is_staff
        assert not user.is_superuser

    @pytest.mark.django_db
    def test_password_is_hashed(self, password):
        user = CustomUser.objects.create_user(email="reader@mail.ru", password=password)
        assert user.password != password

    @pytest.mark.django_db
    def test_email_is_required(self, password):
        with pytest.raises(ValueError):
            CustomUser.objects.create_user(email="", password=password)

    @pytest.mark.django_db
    def test_email_domain_is_normalized(self, password):
        user = CustomUser.objects.create_user(email="Reader@MAIL.RU", password=password)
        assert user.email == "Reader@mail.ru"

    @pytest.mark.django_db
    def test_extra_fields_saved(self, password):
        user = CustomUser.objects.create_user(
            email="reader@mail.ru", password=password, username="reader"
        )
        assert user.username == "reader"

    @pytest.mark.django_db
    def test_create_superuser(self, password):
        user = CustomUser.objects.create_superuser(
            email="admin@mail.ru", password=password
        )
        assert user.is_staff
        assert user.is_superuser
        assert user.is_active

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "field", ["is_staff", "is_superuser", "is_active"]
    )
    def test_superuser_flags_cannot_be_disabled(self, password, field):
        with pytest.raises(ValueError):
            CustomUser.objects.create_superuser(
                email="admin@mail.ru", password=password, **{field: False}
            )

    @pytest.mark.django_db
    def test_user_without_password_cannot_login(self):
        user = CustomUser.objects.create_user(email="reader@mail.ru")
        assert not user.has_usable_password()


class TestCustomUser:
    """Модель пользователя."""

    @pytest.mark.django_db
    def test_str_uses_username(self, user_1):
        assert str(user_1) == "user_1"

    @pytest.mark.django_db
    def test_str_falls_back_to_email(self, user_2):
        assert str(user_2) == user_2.email

    @pytest.mark.django_db
    def test_repr(self, user_1):
        assert repr(user_1) == f"{user_1.email} ({user_1.username})"

    @pytest.mark.django_db
    def test_display_name(self, user_1, user_2):
        assert user_1.display_name == user_1.username
        assert user_2.display_name == user_2.email

    @pytest.mark.django_db
    def test_display_name_for_empty_username(self, user_1):
        user_1.username = ""
        assert user_1.display_name == user_1.email

    @pytest.mark.django_db
    def test_get_absolute_url(self, user_1):
        assert user_1.get_absolute_url() == reverse("user_detail", args=[user_1.pk])

    @pytest.mark.django_db
    def test_email_is_unique(self, user_1, password):
        with pytest.raises(IntegrityError):
            CustomUser.objects.create_user(email=user_1.email, password=password)

    @pytest.mark.django_db
    def test_username_is_not_unique(self, user_1, password):
        """Имя пользователя — просто подпись, повторы разрешены."""
        twin = CustomUser.objects.create_user(
            email="twin@mail.ru", password=password, username=user_1.username
        )
        assert twin.username == user_1.username

    @pytest.mark.django_db
    def test_username_field_is_email(self):
        assert CustomUser.USERNAME_FIELD == "email"
        assert not CustomUser.REQUIRED_FIELDS
        assert CustomUser.objects.model is CustomUser

    @pytest.mark.django_db
    def test_optional_fields_may_be_empty(self, user_2):
        assert user_2.username is None
        assert user_2.full_name == ""
        assert user_2.about == ""
        assert user_2.date_of_birth is None
        assert not user_2.avatar

    @pytest.mark.django_db
    def test_profile_fields_saved(self, user_1):
        assert user_1.full_name == "Иванов Иван Иванович"
        assert user_1.about == "Читаю классику."
        assert user_1.date_of_birth == datetime.date(1990, 1, 15)

    @pytest.mark.django_db
    def test_avatar_saved_to_avatars_folder(self, user_1, avatar):
        user_1.avatar = avatar
        user_1.save()
        user_1.refresh_from_db()
        assert user_1.avatar.name.startswith("avatars/")

    @pytest.mark.django_db
    def test_related_books_and_reviews(self, user_1, book, review):
        assert list(user_1.added_books.all()) == [book]
        assert list(user_1.reviews.all()) == [review]
