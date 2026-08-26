"""Тесты форм приложения пользователей."""

import datetime

import pytest

from user_app.forms import (
    CustomAuthenticationForm,
    CustomUserCreationForm,
    ProfileForm,
)
from user_app.models import CustomUser


class TestCreationFormFields:
    """Состав и оформление полей формы регистрации."""

    def test_fields(self):
        form = CustomUserCreationForm()
        assert list(form.fields) == ["email", "username", "password1", "password2"]

    def test_labels(self):
        form = CustomUserCreationForm()
        assert form.fields["email"].label == "Email"
        assert form.fields["username"].label == "Имя пользователя"
        assert form.fields["password1"].label == "Пароль"
        assert form.fields["password2"].label == "Пароль ещё раз"

    def test_help_texts(self):
        form = CustomUserCreationForm()
        assert form.fields["email"].help_text == "На этот адрес вы будете входить на сайт."
        assert form.fields["password1"].help_text == ""
        assert form.fields["password2"].help_text == "Введите тот же пароль для проверки."

    def test_only_email_and_passwords_are_required(self):
        form = CustomUserCreationForm()
        required = [name for name, field in form.fields.items() if field.required]
        assert required == ["email", "password1", "password2"]

    def test_widget_attrs(self):
        form = CustomUserCreationForm()
        assert form.fields["email"].widget.attrs["autocomplete"] == "email"
        for name in ("password1", "password2"):
            attrs = form.fields[name].widget.attrs
            assert attrs["class"] == "form-control"
            assert attrs["autocomplete"] == "new-password"


class TestCreationFormValid:
    """Корректно заполненная форма регистрации."""

    @pytest.mark.django_db
    def test_form_is_valid(self, register_form_data):
        assert CustomUserCreationForm(data=register_form_data).is_valid()

    @pytest.mark.django_db
    def test_save_creates_user(self, register_form_data, password):
        form = CustomUserCreationForm(data=register_form_data)
        assert form.is_valid()
        user = form.save()
        assert user.pk is not None
        assert user.email == register_form_data["email"]
        assert user.username == register_form_data["username"]
        assert user.check_password(password)

    @pytest.mark.django_db
    def test_username_may_be_empty(self, register_form_data):
        register_form_data["username"] = ""
        form = CustomUserCreationForm(data=register_form_data)
        assert form.is_valid()
        assert form.save().username is None


class TestCreationFormRequired:
    """Обязательные поля формы регистрации."""

    @pytest.mark.django_db
    @pytest.mark.parametrize("field", ["email", "password1", "password2"])
    def test_field_is_required(self, register_form_data, field):
        register_form_data[field] = ""
        form = CustomUserCreationForm(data=register_form_data)
        assert not form.is_valid()
        assert field in form.errors

    @pytest.mark.django_db
    def test_custom_error_message_for_email(self, register_form_data):
        register_form_data["email"] = ""
        form = CustomUserCreationForm(data=register_form_data)
        assert form.errors["email"] == ["Email не заполнен."]

    @pytest.mark.django_db
    def test_custom_error_message_for_password(self, register_form_data):
        register_form_data["password1"] = ""
        form = CustomUserCreationForm(data=register_form_data)
        assert form.errors["password1"] == ["Пароль не заполнен."]

    @pytest.mark.django_db
    def test_invalid_email_message(self, register_form_data):
        register_form_data["email"] = "не почта"
        form = CustomUserCreationForm(data=register_form_data)
        assert form.errors["email"] == ["Похоже, это не адрес электронной почты."]


class TestCreationFormPassword:
    """Проверка паролей при регистрации."""

    @pytest.mark.django_db
    def test_passwords_must_match(self, register_form_data):
        register_form_data["password2"] = "другой пароль"
        form = CustomUserCreationForm(data=register_form_data)
        assert not form.is_valid()
        assert "password2" in form.errors

    @pytest.mark.django_db
    def test_spaces_only_password_rejected(self, register_form_data):
        register_form_data["password1"] = "     "
        register_form_data["password2"] = "     "
        form = CustomUserCreationForm(data=register_form_data)
        assert not form.is_valid()
        assert form.errors["password1"] == [
            "Пароль не может состоять из одних пробелов."
        ]

    @pytest.mark.django_db
    def test_password_with_spaces_inside_is_allowed(self, register_form_data):
        register_form_data["password1"] = "мой пароль"
        register_form_data["password2"] = "мой пароль"
        assert CustomUserCreationForm(data=register_form_data).is_valid()


class TestCreationFormCleanUsername:
    """Чистка имени пользователя при регистрации."""

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("  Иван  ", "Иван"),
            ("Иван   Иванович", "Иван Иванович"),
            ("Иван\nИванович", "Иван Иванович"),
            ("", None),
            ("    ", None),
        ],
    )
    def test_extra_spaces_removed(self, register_form_data, raw, expected):
        register_form_data["username"] = raw
        form = CustomUserCreationForm(data=register_form_data)
        assert form.is_valid()
        assert form.cleaned_data["username"] == expected


class TestCreationFormCleanEmail:
    """Чистка и проверка email при регистрации."""

    @pytest.mark.django_db
    def test_email_is_lowercased_and_stripped(self, register_form_data):
        register_form_data["email"] = "  Reader@Mail.RU  "
        form = CustomUserCreationForm(data=register_form_data)
        assert form.is_valid()
        assert form.cleaned_data["email"] == "reader@mail.ru"

    @pytest.mark.django_db
    def test_duplicate_email_rejected(self, register_form_data, user_1):
        register_form_data["email"] = user_1.email
        form = CustomUserCreationForm(data=register_form_data)
        assert not form.is_valid()
        assert form.errors["email"] == [
            f"Читатель с адресом «{user_1.email}» уже зарегистрирован."
        ]

    @pytest.mark.django_db
    def test_duplicate_check_is_case_insensitive(self, register_form_data, user_1):
        register_form_data["email"] = user_1.email.upper()
        assert not CustomUserCreationForm(data=register_form_data).is_valid()


class TestAuthenticationFormFields:
    """Состав и оформление полей формы входа."""

    def test_fields(self):
        form = CustomAuthenticationForm()
        assert list(form.fields) == ["username", "password"]

    def test_labels(self):
        form = CustomAuthenticationForm()
        assert form.fields["username"].label == "Email"
        assert form.fields["password"].label == "Пароль"

    def test_widget_attrs(self):
        form = CustomAuthenticationForm()
        assert form.fields["username"].widget.attrs["autocomplete"] == "email"
        assert form.fields["password"].widget.attrs["autocomplete"] == "current-password"


class TestAuthenticationForm:
    """Вход по email."""

    @pytest.mark.django_db
    def test_valid_credentials(self, login_form_data, user_1):
        form = CustomAuthenticationForm(data=login_form_data)
        assert form.is_valid()
        assert form.get_user() == user_1

    @pytest.mark.django_db
    def test_email_is_lowercased_and_stripped(self, login_form_data, user_1):
        login_form_data["username"] = f"  {user_1.email.upper()}  "
        form = CustomAuthenticationForm(data=login_form_data)
        assert form.is_valid()
        assert form.cleaned_data["username"] == user_1.email

    @pytest.mark.django_db
    def test_wrong_password(self, login_form_data):
        login_form_data["password"] = "неверный"
        form = CustomAuthenticationForm(data=login_form_data)
        assert not form.is_valid()
        assert form.errors["__all__"] == ["Неверный email или пароль."]

    @pytest.mark.django_db
    def test_unknown_email(self, login_form_data):
        login_form_data["username"] = "nobody@mail.ru"
        form = CustomAuthenticationForm(data=login_form_data)
        assert not form.is_valid()
        assert form.errors["__all__"] == ["Неверный email или пароль."]

    @pytest.mark.django_db
    def test_inactive_user(self, login_form_data, user_1):
        user_1.is_active = False
        user_1.save()
        form = CustomAuthenticationForm(data=login_form_data)
        assert not form.is_valid()
        # Неактивный пользователь не проходит аутентификацию — сообщение общее.
        assert form.errors["__all__"] == ["Неверный email или пароль."]

    @pytest.mark.django_db
    def test_invalid_email_message(self, login_form_data):
        login_form_data["username"] = "не почта"
        form = CustomAuthenticationForm(data=login_form_data)
        assert form.errors["username"] == ["Похоже, это не адрес электронной почты."]

    @pytest.mark.django_db
    @pytest.mark.parametrize("field", ["username", "password"])
    def test_field_is_required(self, login_form_data, field):
        login_form_data[field] = ""
        form = CustomAuthenticationForm(data=login_form_data)
        assert not form.is_valid()
        assert field in form.errors


class TestProfileFormFields:
    """Состав и оформление полей формы профиля."""

    def test_fields(self):
        form = ProfileForm()
        assert list(form.fields) == [
            "username",
            "full_name",
            "about",
            "date_of_birth",
            "avatar",
        ]

    def test_labels(self):
        form = ProfileForm()
        assert [field.label for field in form] == [
            "Имя пользователя",
            "ФИО",
            "О себе",
            "Дата рождения",
            "Аватар",
        ]

    def test_all_fields_are_optional(self):
        form = ProfileForm()
        assert not any(field.field.required for field in form)

    def test_widgets(self):
        form = ProfileForm()
        assert form.fields["about"].widget.attrs["rows"] == 4
        assert form.fields["date_of_birth"].widget.input_type == "date"
        assert form.fields["avatar"].widget.attrs["accept"] == "image/*"


class TestProfileFormValid:
    """Корректно заполненная форма профиля."""

    @pytest.mark.django_db
    def test_form_is_valid(self, profile_form_data, user_1):
        assert ProfileForm(data=profile_form_data, instance=user_1).is_valid()

    @pytest.mark.django_db
    def test_save_updates_user(self, profile_form_data, user_1):
        profile_form_data["username"] = "Новое имя"
        form = ProfileForm(data=profile_form_data, instance=user_1)
        assert form.is_valid()
        user = form.save()
        user_1.refresh_from_db()
        assert user == user_1
        assert user_1.username == "Новое имя"
        assert user_1.date_of_birth == datetime.date(1990, 1, 15)

    @pytest.mark.django_db
    def test_email_is_not_editable(self, profile_form_data, user_1):
        profile_form_data["email"] = "hacker@mail.ru"
        form = ProfileForm(data=profile_form_data, instance=user_1)
        assert form.is_valid()
        form.save()
        user_1.refresh_from_db()
        assert user_1.email == "user_1@mail.ru"

    @pytest.mark.django_db
    def test_empty_form_is_valid(self, user_1):
        """Все поля профиля необязательные — можно очистить любое."""
        form = ProfileForm(data={}, instance=user_1)
        assert form.is_valid()
        user = form.save()
        assert user.username is None
        assert user.full_name == ""
        assert user.about == ""
        assert user.date_of_birth is None

    @pytest.mark.django_db
    def test_avatar_uploaded(self, profile_form_data, user_1, avatar):
        form = ProfileForm(
            data=profile_form_data, files={"avatar": avatar}, instance=user_1
        )
        assert form.is_valid()
        user = form.save()
        assert user.avatar.name.startswith("avatars/")

    @pytest.mark.django_db
    def test_invalid_date_rejected(self, profile_form_data, user_1):
        profile_form_data["date_of_birth"] = "вчера"
        form = ProfileForm(data=profile_form_data, instance=user_1)
        assert not form.is_valid()
        assert "date_of_birth" in form.errors

    @pytest.mark.django_db
    def test_not_an_image_rejected(self, profile_form_data, user_1):
        # SimpleUploadedFile проще собрать прямо здесь: файл заведомо битый.
        # pylint: disable=import-outside-toplevel
        from django.core.files.uploadedfile import SimpleUploadedFile

        broken = SimpleUploadedFile("avatar.png", b"not an image", content_type="image/png")
        form = ProfileForm(
            data=profile_form_data, files={"avatar": broken}, instance=user_1
        )
        assert not form.is_valid()
        assert "avatar" in form.errors


class TestProfileFormClean:
    """Чистка полей профиля."""

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("  Иван  ", "Иван"),
            ("Иван   Иванович", "Иван Иванович"),
            ("", None),
            ("   ", None),
        ],
    )
    def test_clean_username(self, profile_form_data, user_1, raw, expected):
        profile_form_data["username"] = raw
        form = ProfileForm(data=profile_form_data, instance=user_1)
        assert form.is_valid()
        assert form.cleaned_data["username"] == expected

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("  Иванов Иван  ", "Иванов Иван"),
            ("Иванов   Иван\tИванович", "Иванов Иван Иванович"),
            ("", ""),
            ("   ", ""),
        ],
    )
    def test_clean_full_name(self, profile_form_data, user_1, raw, expected):
        profile_form_data["full_name"] = raw
        form = ProfileForm(data=profile_form_data, instance=user_1)
        assert form.is_valid()
        assert form.cleaned_data["full_name"] == expected

    @pytest.mark.django_db
    def test_duplicate_username_is_allowed(self, profile_form_data, user_1, user_2):
        """Имя пользователя не уникально — тёзки допустимы."""
        user_2.username = "Иван"
        user_2.save()
        profile_form_data["username"] = "Иван"
        form = ProfileForm(data=profile_form_data, instance=user_1)
        assert form.is_valid()
        assert form.save().username == "Иван"

    @pytest.mark.django_db
    def test_user_count_unchanged(self, profile_form_data, user_1):
        """Форма профиля правит существующего пользователя, а не создаёт нового."""
        form = ProfileForm(data=profile_form_data, instance=user_1)
        assert form.is_valid()
        form.save()
        assert CustomUser.objects.count() == 1
