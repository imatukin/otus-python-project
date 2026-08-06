from django.urls import path

from bookshelf_app.views import index, about, books, book_add, book_detail, book_edit

urlpatterns = [
    path("", index, name="index"),
    path("about/", about, name="about"),
    path("books/", books, name="books"),
    path("books/add/", book_add, name="book_add"),
    path("books/<int:book_id>/", book_detail, name="book_detail"),
    path("books/<int:book_id>/edit/", book_edit, name="book_edit"),
]
