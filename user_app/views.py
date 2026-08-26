"""Представления пользователей: регистрация, вход, профиль."""

from django.contrib.auth import get_user_model, login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, UpdateView

from bookshelf_app.views import Breadcrumbs
from user_app.forms import (
    CustomAuthenticationForm,
    CustomUserCreationForm,
    ProfileForm,
)

User = get_user_model()


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


class UserDetailView(Breadcrumbs, DetailView):
    """Публичная страница читателя: его книги и отзывы."""

    model = User
    template_name = "user_app/user_detail.html"
    context_object_name = "reader"

    def get_breadcrumbs(self):
        return super().get_breadcrumbs() + [{"title": self.object.display_name}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title=self.object.display_name,
            books=self.object.added_books.select_related("author").order_by("title"),
            reviews=(
                self.object.reviews.select_related("book").order_by("-created_at")
            ),
            is_own_profile=self.object == self.request.user,
        )
        return context


class ProfileView(LoginRequiredMixin, Breadcrumbs, SuccessMessageMixin, UpdateView):
    """Свой профиль — просмотр и редактирование."""

    form_class = ProfileForm
    template_name = "user_app/profile.html"
    success_url = reverse_lazy("profile")
    success_message = "Профиль сохранён."

    def get_object(self, queryset=None):
        return self.request.user

    def get_breadcrumbs(self):
        return super().get_breadcrumbs() + [{"title": "Мой профиль"}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title="Мой профиль",
            form_subtitle="Так вас увидят другие читатели.",
            submit_label="Сохранить",
            cancel_url=reverse("index"),
            books=self.object.added_books.select_related("author").order_by("title"),
            reviews=(
                self.object.reviews.select_related("book").order_by("-created_at")
            ),
        )
        return context
