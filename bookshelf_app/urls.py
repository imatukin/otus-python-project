from django.urls import path

from bookshelf_app.views import index, about, books, book_detail

urlpatterns = [
    path("", index, name="index"),
    path("about/", about, name="about"),
    path("books/", books, name="books"),
    path("books/<int:book_id>/", book_detail, name="book_detail"),
]
