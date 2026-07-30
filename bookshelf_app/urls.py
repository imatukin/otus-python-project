from django.urls import path
from bookshelf_app.views import index, about, books


urlpatterns = [
    path('', index),
    path('about/', about),
    path('books/', books),
]
