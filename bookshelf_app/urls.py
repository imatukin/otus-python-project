from django.urls import path

from bookshelf_app.views import (
    AboutView,
    BookCreateView,
    BookDetailView,
    BookListView,
    BookUpdateView,
    IndexView,
)

urlpatterns = [
    path("", IndexView.as_view(), name="index"),
    path("about/", AboutView.as_view(), name="about"),
    path("books/", BookListView.as_view(), name="books"),
    path("books/add/", BookCreateView.as_view(), name="book_add"),
    path("books/<int:pk>/", BookDetailView.as_view(), name="book_detail"),
    path("books/<int:pk>/edit/", BookUpdateView.as_view(), name="book_edit"),
]
