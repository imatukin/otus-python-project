"""Представления каталога: список книг, страница книги и её редактирование."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse, reverse_lazy
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    TemplateView,
    UpdateView,
)

from bookshelf_app.forms import BookForm
from bookshelf_app.models import Book
from .tasks import log_new_book_task


class Breadcrumbs:
    """Цепочка навигации."""

    def get_breadcrumbs(self):
        """Базовая цепочка — только ссылка на главную."""
        return [{"title": "Главная", "url": reverse("index")}]

    def get_context_data(self, **kwargs):
        """Кладёт цепочку навигации в контекст шаблона."""
        # Примесь всегда используется вместе с CBV, поэтому get_context_data у super() есть.
        context = super().get_context_data(**kwargs)  # pylint: disable=no-member
        context["breadcrumbs"] = self.get_breadcrumbs()
        return context


class IndexView(TemplateView):
    """Главная страница."""

    template_name = "bookshelf_app/index.html"


class AboutView(Breadcrumbs, TemplateView):
    """Страница о нас."""

    template_name = "bookshelf_app/about.html"

    def get_breadcrumbs(self):
        return super().get_breadcrumbs() + [{"title": "О сайте"}]


class BookBase(Breadcrumbs):
    """Базовая view для книги."""

    model = Book

    def get_breadcrumbs(self):
        return super().get_breadcrumbs() + [
            {"title": "Все книги", "url": reverse("books")}
        ]


class BookObjectBase(BookBase):
    """Базовая view для страниц конкретной книги."""

    # self.object появляется из SingleObjectMixin у конкретных view.
    # pylint: disable=no-member

    def get_breadcrumbs(self):
        return super().get_breadcrumbs() + [
            {"title": self.object.title, "url": self.object.get_absolute_url()}
        ]


class BookListView(BookBase, ListView):
    """Список всех книг с автором, жанрами и средней оценкой."""

    template_name = "bookshelf_app/books.html"
    context_object_name = "books"
    extra_context = {"page_title": "Все книги."}

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("author", "added_by")
            .prefetch_related("genres")
        )


class BookDetailView(BookObjectBase, DetailView):
    """Страница одной книги: информация о книге и список отзывов."""

    template_name = "bookshelf_app/book_detail.html"
    context_object_name = "book"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["reviews"] = (
            self.object.reviews.select_related("reader").order_by("-created_at")
        )
        context["page_title"] = self.object.title
        return context


class BookCreateView(LoginRequiredMixin, BookBase, SuccessMessageMixin, CreateView):
    """Добавление книги в общий каталог."""

    form_class = BookForm
    template_name = "bookshelf_app/book_form.html"
    success_message = "Книга «%(title)s» добавлена в каталог."

    def get_breadcrumbs(self):
        return super().get_breadcrumbs() + [{"title": "Добавление"}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title="Добавить книгу",
            form_subtitle="Книга попадёт в общий каталог — её увидят все читатели.",
            submit_label="Добавить книгу",
            cancel_url=reverse("books"),
        )
        return context

    def form_valid(self, form):
        """Книгу в каталог добавляет тот, кто заполнил форму."""
        form.instance.added_by = self.request.user
        response = super().form_valid(form)

        book = self.object
        log_new_book_task.delay(
            book_id=book.pk,
            title=book.title,
            author=str(book.author),
            added_by=str(book.added_by),
        )
        return response


class BookUpdateView(LoginRequiredMixin, BookObjectBase, SuccessMessageMixin, UpdateView):
    """Редактирование книги."""

    form_class = BookForm
    template_name = "bookshelf_app/book_form.html"
    success_message = "Книга «%(title)s» обновлена."

    def get_breadcrumbs(self):
        return super().get_breadcrumbs() + [{"title": "Редактирование"}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title=f"Редактирование: {self.object.title}",
            form_subtitle="Изменения увидят все читатели каталога.",
            submit_label="Сохранить",
            cancel_url=reverse("book_detail", args=[self.object.pk]),
        )
        return context


class BookDeleteView(LoginRequiredMixin, BookObjectBase, SuccessMessageMixin, DeleteView):
    """Удаление книги."""

    template_name = "bookshelf_app/book_delete.html"
    context_object_name = "book"
    success_url = reverse_lazy("books")

    def get_breadcrumbs(self):
        return super().get_breadcrumbs() + [{"title": "Удаление"}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Удаление: {self.object.title}"
        return context

    def get_success_message(self, cleaned_data):
        return f"Книга «{self.object.title}» удалена из каталога."
