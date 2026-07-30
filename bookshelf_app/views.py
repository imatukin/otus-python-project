from django.db.models import Avg, Count
from django.shortcuts import render
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
        "page_title": "Все книги."
    }
    return render(request, "bookshelf_app/books.html", context)
