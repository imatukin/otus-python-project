from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

User = get_user_model()

EMAIL_WIDGET_ATTRS = {
    "class": "form-control form-control-lg",
    "placeholder": "reader@example.com",
    "autocomplete": "email",
}


class CustomUserCreationForm(UserCreationForm):
    """
    Форма регистрации нового читателя.
    """

    email = forms.EmailField(
        required=True,
        label="Email",
        help_text="На этот адрес вы будете входить на сайт.",
        widget=forms.EmailInput(attrs=EMAIL_WIDGET_ATTRS),
        error_messages={
            "required": "Email не заполнен.",
            "invalid": "Похоже, это не адрес электронной почты.",
        },
    )

    class Meta:
        model = User
        fields = ("email", "username")
        labels = {"username": "Имя пользователя"}
        help_texts = {
            "username": "Так вас будут видеть другие читатели. Можно не заполнять.",
        }
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Например, «Иван»",
                    "autocomplete": "nickname",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # UserCreationForm объявляет пароли сам — доводим их до стиля проекта.
        self.fields["password1"].label = "Пароль"
        self.fields["password1"].help_text = ""
        self.fields["password1"].error_messages["required"] = "Пароль не заполнен."
        self.fields["password1"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Придумайте пароль",
                "autocomplete": "new-password",
            }
        )
        self.fields["password2"].label = "Пароль ещё раз"
        self.fields["password2"].help_text = "Введите тот же пароль для проверки."
        self.fields["password2"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Повторите пароль",
                "autocomplete": "new-password",
            }
        )

    def clean_password1(self):
        """Сложность не проверяем, но пробелы паролем не считаются."""
        password = self.cleaned_data["password1"]
        if not password.strip():
            raise forms.ValidationError("Пароль не может состоять из одних пробелов.")
        return password

    def clean_username(self):
        """Имя необязательное — убираем лишние пробелы, пустое пишем как NULL."""
        # username на модели с null=True, поэтому пустое поле приходит как None.
        username = self.cleaned_data["username"] or ""
        return " ".join(username.split()) or None

    def clean_email(self):
        """Email храним в нижнем регистре и следим за уникальностью."""
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "Читатель с адресом «%(email)s» уже зарегистрирован.",
                params={"email": email},
            )
        return email


class CustomAuthenticationForm(AuthenticationForm):
    """Форма входа по email."""

    username = forms.EmailField(
        required=True,
        label="Email",
        widget=forms.EmailInput(attrs=EMAIL_WIDGET_ATTRS),
        error_messages={
            "required": "Email не заполнен.",
            "invalid": "Похоже, это не адрес электронной почты.",
        },
    )

    error_messages = {
        "invalid_login": "Неверный email или пароль.",
        "inactive": "Учётная запись отключена.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password"].label = "Пароль"
        self.fields["password"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "Ваш пароль",
                "autocomplete": "current-password",
            }
        )

    def clean_username(self):
        """Приводим email к тому же виду, в котором он сохранён."""
        return self.cleaned_data["username"].strip().lower()
