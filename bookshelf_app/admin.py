"""Админка каталога (авторы, книги, жанры, отзывы) и дневника чтения."""

from django.contrib import admin

from .models import MAX_RATING, Author, Book, Genre, ReadingEntry, Review


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    """Авторы в админке."""

    list_display = ("name", "birth_date")


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    """Книги в админке."""

    list_display = (
        "title",
        "author",
        "published_year",
        "genres_list",
        "added_by",
        "is_pending",
    )
    ordering = ("author",)
    list_filter = ("genres", "is_pending")
    search_fields = ("title", "author__name")

    def genres_list(self, obj):
        """Жанры книги одной строкой — для списка книг."""
        return ", ".join([genre.name for genre in obj.genres.all()])

    genres_list.short_description = "Жанры"

    @admin.action(description="Подтвердить: книга дозаполнена")
    def confirm_pending(self, request, queryset):  # pylint: disable=unused-argument
        """Снимает с книг пометку «требует дозаполнения»."""
        queryset.update(is_pending=False)

    actions = (confirm_pending,)


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    """Жанры в админке."""


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    """Отзывы в админке."""

    list_display = ("reader", "book", "rating", "text")
    readonly_fields = ("text", "rating", "created_at")
    fieldsets = (
        (None, {"fields": ("book", "reader")}),
        (
            "Дополнительная информация",
            {"fields": ("text", "rating", "created_at"), "classes": ("collapse",)},
        ),
    )

    @admin.action(description="Увеличить рейтинг на 1")
    def up_rating(self, request, queryset):  # pylint: disable=unused-argument
        """Поднимает оценку на балл"""
        for review in queryset:
            if review.rating >= MAX_RATING:
                continue
            review.rating += 1
            review.save(update_fields=("rating",))

    actions = (up_rating,)


@admin.register(ReadingEntry)
class ReadingEntryAdmin(admin.ModelAdmin):
    """Записи дневника в админке."""

    list_display = ("reader", "book", "status", "started_at", "finished_at")
    list_filter = ("status",)
    search_fields = ("book__title", "reader__email")
    autocomplete_fields = ("book",)
    readonly_fields = ("created_at", "updated_at")
