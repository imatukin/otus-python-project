from django.contrib.auth import login
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView

from bookshelf_app.views import Breadcrumbs
from user_app.forms import CustomAuthenticationForm, CustomUserCreationForm


class RegisterView(Breadcrumbs, SuccessMessageMixin, CreateView):
    """Регистрация нового читателя."""

    form_class = CustomUserCreationForm
    template_name = "user_app/user_form.html"
    success_url = reverse_lazy("index")
    success_message = "Добро пожаловать, %(email)s!"

    def get_breadcrumbs(self):
        return super().get_breadcrumbs() + [{"title": "Регистрация"}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title="Регистрация",
            form_subtitle="Заведите учётную запись, чтобы вести свой дневник читателя.",
            submit_label="Зарегистрироваться",
            cancel_url=reverse("index"),
            alt_text="Уже зарегистрированы?",
            alt_label="Войти",
            alt_url=reverse("login"),
        )
        return context

    def form_valid(self, form):
        """После регистрации сразу пускаем пользователя на сайт."""
        response = super().form_valid(form)
        login(self.request, self.object)
        return response


class UserLoginView(Breadcrumbs, LoginView):
    """Вход по email."""

    form_class = CustomAuthenticationForm
    template_name = "user_app/user_form.html"
    redirect_authenticated_user = True

    def get_breadcrumbs(self):
        return super().get_breadcrumbs() + [{"title": "Вход"}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title="Вход",
            form_subtitle="Войдите, чтобы добавлять книги и писать отзывы.",
            submit_label="Войти",
            cancel_url=reverse("index"),
            alt_text="Ещё нет учётной записи?",
            alt_label="Зарегистрироваться",
            alt_url=reverse("register"),
        )
        return context


class UserLogoutView(LogoutView):
    """Выход из учётной записи."""

    next_page = reverse_lazy("index")
