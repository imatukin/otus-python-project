"""Маршруты каталога книг."""

from django.urls import path

from bookshelf_app.views import (
    AboutView,
    BookCreateView,
    BookDeleteView,
    BookDetailView,
    BookListView,
    BookUpdateView,
    DiaryAddView,
    IndexView,
    ReadingEntryDeleteView,
    ReadingEntryUpdateView,
    ReadingStatusView,
)

urlpatterns = [
    path("", IndexView.as_view(), name="index"),
    path("about/", AboutView.as_view(), name="about"),
    path("books/", BookListView.as_view(), name="books"),
    path("books/add/", BookCreateView.as_view(), name="book_add"),
    path("books/<int:pk>/", BookDetailView.as_view(), name="book_detail"),
    path("books/<int:pk>/edit/", BookUpdateView.as_view(), name="book_edit"),
    path("books/<int:pk>/delete/", BookDeleteView.as_view(), name="book_delete"),
    path("books/<int:pk>/status/", ReadingStatusView.as_view(), name="book_status"),
    path("diary/add/", DiaryAddView.as_view(), name="diary_add"),
    path("diary/entries/<int:pk>/edit/", ReadingEntryUpdateView.as_view(), name="entry_edit"),
    path("diary/entries/<int:pk>/delete/", ReadingEntryDeleteView.as_view(), name="entry_delete"),
]
