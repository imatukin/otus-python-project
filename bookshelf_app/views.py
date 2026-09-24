"""Представления каталога и дневника: книги, смена статуса, записи дневника."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from bookshelf_app.diary import (
    StatusTransitionError,
    build_diary,
    change_status,
    latest_entry,
    status_actions,
    with_diary_status,
)
from bookshelf_app.forms import BookForm, QuickBookForm, ReadingEntryForm
from bookshelf_app.models import Book, ReadingEntry
from .tasks import log_new_book_task

# Сколько книг показываем в результатах поиска при быстром добавлении.
SEARCH_LIMIT = 20


def log_new_book(book):
    """Ставит фоновую задачу «в каталог добавлена книга» — книга уже должна быть сохранена."""
    log_new_book_task.delay(
        book_id=book.pk,
        title=book.title,
        author=str(book.author),
        added_by=str(book.added_by),
    )


def with_status_actions(books, user):
    """Выборка книг, у каждой из которых есть кнопки смены статуса (`book.status_actions`).

    Гостю кнопки не положены — выборка возвращается как есть.
    """
    if not user.is_authenticated:
        return books
    books = with_diary_status(books, user)
    for book in books:
        book.status_actions = status_actions(book.diary_status)
    return books


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


def diary_context(reader):
    """Колонки дневника и общий счётчик — для главной и страниц читателя."""
    columns = build_diary(reader)
    return {"columns": columns, "diary_total": sum(column.count for column in columns)}


class IndexView(TemplateView):
    """Главная страница: гостю — приветствие, читателю — его дневник по колонкам статусов."""

    template_name = "bookshelf_app/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated:
            context.update(diary_context(self.request.user))
        return context


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["books"] = with_status_actions(context["books"], self.request.user)
        return context


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
        context["can_delete"] = self.object.can_be_deleted_by(self.request.user)
        if self.request.user.is_authenticated:
            entry = latest_entry(self.request.user, self.object)
            context["entry"] = entry
            context["status_actions"] = status_actions(entry.status if entry else None)
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
        log_new_book(self.object)
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

    def form_valid(self, form):
        """Сохранённая полной формой книга — уже не черновик из быстрого добавления."""
        form.instance.is_pending = False
        return super().form_valid(form)


class BookDeleteView(LoginRequiredMixin, UserPassesTestMixin, BookObjectBase, DeleteView):
    """Удаление книги — мягкое: книга, её отзывы и записи дневника помечаются удалёнными.

    Удалить книгу может только добавивший её читатель или администратор.
    """

    template_name = "bookshelf_app/book_delete.html"
    context_object_name = "book"
    success_url = reverse_lazy("books")

    def test_func(self):
        return self.get_object().can_be_deleted_by(self.request.user)

    def get_breadcrumbs(self):
        return super().get_breadcrumbs() + [{"title": "Удаление"}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Удаление: {self.object.title}"
        context["reviews_count"] = self.object.reviews.count()
        context["entries_count"] = self.object.entries.count()
        return context

    def form_valid(self, form):
        """Помечаем книгу удалённой от имени того, кто нажал кнопку."""
        self.object.delete(user=self.request.user)
        messages.success(self.request, f"Книга «{self.object.title}» удалена из каталога.")
        return HttpResponseRedirect(self.get_success_url())


class ReadingStatusView(LoginRequiredMixin, View):
    """Смена статуса книги в дневнике кнопкой: POST с полем `status`.

    После смены возвращаемся туда, откуда нажали кнопку (`next`), иначе — на страницу книги.
    """

    http_method_names = ["post"]

    def post(self, request, pk):
        """Меняет статус и возвращает на исходную страницу."""
        book = get_object_or_404(Book, pk=pk)
        try:
            entry = change_status(request.user, book, request.POST.get("status"))
        except StatusTransitionError:
            messages.error(request, f"Статус книги «{book.title}» так поменять нельзя.")
        else:
            messages.success(request, f"Дневник обновлён: {entry}.")
        return HttpResponseRedirect(self.get_redirect_url(book))

    def get_redirect_url(self, book):
        """Адрес из `next`, если он ведёт на наш сайт, иначе — страница книги."""
        url = self.request.POST.get("next")
        if url and url_has_allowed_host_and_scheme(
            url, allowed_hosts={self.request.get_host()}, require_https=self.request.is_secure()
        ):
            return url
        return book.get_absolute_url()


class EntryBase(LoginRequiredMixin, Breadcrumbs):
    """Базовая view для своей записи дневника: чужие записи и записи удалённых книг — 404."""

    # self.object появляется из SingleObjectMixin у конкретных view.
    # pylint: disable=no-member

    model = ReadingEntry
    success_url = reverse_lazy("index")

    def get_queryset(self):
        """Только свои записи о неудалённых книгах."""
        return ReadingEntry.objects.filter(
            reader=self.request.user, book__is_deleted=False
        ).select_related("book")

    def get_breadcrumbs(self):
        book = self.object.book
        return super().get_breadcrumbs() + [{"title": book.title, "url": book.get_absolute_url()}]


class ReadingEntryUpdateView(EntryBase, UpdateView):
    """Правка записи дневника: статус и даты."""

    form_class = ReadingEntryForm
    template_name = "bookshelf_app/book_form.html"

    def get_breadcrumbs(self):
        return super().get_breadcrumbs() + [{"title": "Запись дневника"}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_title=f"Запись дневника: {self.object.book.title}",
            form_subtitle="Статус и даты прочтения. Даты при смене статуса кнопками ставятся сами, "
                          "здесь их можно поправить.",
            submit_label="Сохранить",
            cancel_url=reverse("index"),
            delete_url=reverse("entry_delete", args=[self.object.pk]),
        )
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Запись сохранена: {form.instance}.")
        return super().form_valid(form)


class ReadingEntryDeleteView(EntryBase, DeleteView):
    """Удаление записи дневника — мягкое, как и всё на сайте."""

    template_name = "bookshelf_app/entry_delete.html"
    context_object_name = "entry"

    def get_breadcrumbs(self):
        return super().get_breadcrumbs() + [{"title": "Удаление записи"}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Удаление записи: {self.object.book.title}"
        return context

    def form_valid(self, form):
        """Помечаем запись удалённой от имени читателя."""
        self.object.delete(user=self.request.user)
        messages.success(self.request, f"Запись о книге «{self.object.book.title}» удалена из дневника.")
        return HttpResponseRedirect(self.get_success_url())


class DiaryAddView(LoginRequiredMixin, Breadcrumbs, FormView):
    """Добавление книги в дневник: поиск по каталогу, а если книги нет — короткая форма.

    Строка поиска — в GET-параметре `q`; форма отправляется на тот же адрес,
    так что при ошибке запрос не теряется.
    """

    form_class = QuickBookForm
    template_name = "bookshelf_app/diary_add.html"
    success_url = reverse_lazy("index")

    def get_query(self):
        """Строка поиска без лишних пробелов."""
        return " ".join(self.request.GET.get("q", "").split())

    def get_initial(self):
        """Название книги в форме — то, что искали."""
        return {**super().get_initial(), "title": self.get_query()}

    def get_breadcrumbs(self):
        return super().get_breadcrumbs() + [{"title": "Добавить в дневник"}]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.get_query()
        results = []
        if query:
            books = (
                Book.objects.filter(title__icontains=query)
                .select_related("author")
                .order_by("title")[:SEARCH_LIMIT]
            )
            results = with_status_actions(books, self.request.user)
        context.update(page_title="Добавить книгу в дневник", query=query, results=results)
        return context

    def form_valid(self, form):
        book = form.save(self.request.user)
        log_new_book(book)
        messages.success(
            self.request,
            f"Книга «{book.title}» добавлена в каталог черновиком и в ваш дневник.",
        )
        return super().form_valid(form)
