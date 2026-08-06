from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from bookshelf_app.forms import BookForm
from bookshelf_app.models import Book


def index(request):
    """Главная страница."""
    return render(request, "bookshelf_app/index.html")


def about(request):
    """Страница о нас."""
    return render(request, "bookshelf_app/about.html")


def books(request):
    """Список всех книг с автором, жанрами и средней оценкой."""
    books = Book.objects.all()
    context = {
        "books": books,
        "page_title": "Все книги.",
    }
    return render(request, "bookshelf_app/books.html", context)


def book_add(request):
    """Добавление книги в общий каталог."""
    if request.method == "POST":
        form = BookForm(request.POST)
        if form.is_valid():
            book = form.save()
            messages.success(request, f"Книга «{book.title}» добавлена в каталог.")
            return redirect("book_detail", book_id=book.pk)
    else:
        form = BookForm()

    context = {
        "form": form,
        "page_title": "Добавить книгу",
        "form_subtitle": "Книга попадёт в общий каталог — её увидят все читатели.",
        "submit_label": "Добавить книгу",
        "cancel_url": reverse("books"),
    }
    return render(request, "bookshelf_app/book_form.html", context)


def book_detail(request, book_id):
    """Страница одной книги: информация о книге и список отзывов."""
    book = get_object_or_404(Book, pk=book_id)
    reviews = book.reviews.all().order_by("-created_at")
    context = {
        "book": book,
        "reviews": reviews,
        "page_title": book.title,
    }
    return render(request, "bookshelf_app/book_detail.html", context)


def book_edit(request, book_id):
    """Редактирование книги."""
    book = get_object_or_404(Book, pk=book_id)

    if request.method == "POST":
        form = BookForm(request.POST, instance=book)
        if form.is_valid():
            book = form.save()
            messages.success(request, f"Книга «{book.title}» обновлена.")
            return redirect("book_detail", book_id=book.pk)
    else:
        form = BookForm(instance=book)

    context = {
        "form": form,
        "book": book,
        "page_title": f"Редактирование: {book.title}",
        "form_subtitle": "Изменения увидят все читатели каталога.",
        "submit_label": "Сохранить",
        "cancel_url": reverse("book_detail", args=[book.pk]),
    }
    return render(request, "bookshelf_app/book_form.html", context)
