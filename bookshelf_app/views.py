from django.shortcuts import render
from django.http import HttpResponse


def index(request):
    """Главная страница."""
    return render(request, "bookshelf_app/index.html")


def about(request):
    """Страница о нас."""
    return render(request, "bookshelf_app/about.html")

def books(request):
    """Список всех книг."""
    return render(request, "bookshelf_app/books.html")
