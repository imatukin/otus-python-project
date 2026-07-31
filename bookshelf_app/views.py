from django.shortcuts import get_object_or_404, render
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
