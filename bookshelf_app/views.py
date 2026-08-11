from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse
from django.views.generic import (
    CreateView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from bookshelf_app.forms import BookForm
from bookshelf_app.models import Book


class IndexView(TemplateView):
    """Главная страница."""

    template_name = "bookshelf_app/index.html"


class AboutView(TemplateView):
    """Страница о нас."""

    template_name = "bookshelf_app/about.html"


class BookBase:
    """Базовая view для книги."""

    model = Book


class BookListView(BookBase, ListView):
    """Список всех книг с автором, жанрами и средней оценкой."""

    template_name = "bookshelf_app/books.html"
    context_object_name = "books"
    extra_context = {"page_title": "Все книги."}


class BookDetailView(BookBase, DetailView):
    """Страница одной книги: информация о книге и список отзывов."""

    template_name = "bookshelf_app/book_detail.html"
    context_object_name = "book"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["reviews"] = self.object.reviews.all().order_by("-created_at")
        context["page_title"] = self.object.title
        return context


class BookCreateView(BookBase, SuccessMessageMixin, CreateView):
    """Добавление книги в общий каталог."""

    form_class = BookForm
    template_name = "bookshelf_app/book_form.html"
    success_message = "Книга «%(title)s» добавлена в каталог."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title="Добавить книгу",
            form_subtitle="Книга попадёт в общий каталог — её увидят все читатели.",
            submit_label="Добавить книгу",
            cancel_url=reverse("books"),
        )
        return context


class BookUpdateView(BookBase, SuccessMessageMixin, UpdateView):
    """Редактирование книги."""

    form_class = BookForm
    template_name = "bookshelf_app/book_form.html"
    success_message = "Книга «%(title)s» обновлена."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title=f"Редактирование: {self.object.title}",
            form_subtitle="Изменения увидят все читатели каталога.",
            submit_label="Сохранить",
            cancel_url=reverse("book_detail", args=[self.object.pk]),
        )
        return context
