from django.shortcuts import render
from django.http import HttpResponse


def index(request):
    """Главная страница."""
    return HttpResponse("<h1>Дневник читателя</h1><hr>Мой сайт на Python!")


def about(request):
    """Страница о нас."""
    return HttpResponse("<h2>Страница о нас.</h2><hr>Мой сайт на Python!")
