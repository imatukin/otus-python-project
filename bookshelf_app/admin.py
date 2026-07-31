from django.contrib import admin
from .models import Author, Book, Genre, Reader, Review


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    list_display = ("name", "birth_date")


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "published_year", "genres_list")
    ordering = ("author",)
    list_filter = ("genres",)
    search_fields = ("title", "author")

    def genres_list(self, obj):
        return ", ".join([genre.name for genre in obj.genres.all()])

    genres_list.short_description = "Жанры"


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    pass


@admin.register(Reader)
class ReaderAdmin(admin.ModelAdmin):
    list_display = ("full_name", "nickname", "birth_date")
    search_fields = ("full_name", "nickname")
    pass


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    pass
