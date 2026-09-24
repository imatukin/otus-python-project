"""Админка каталога (авторы, книги, жанры, отзывы) и дневника чтения."""

from collections import Counter

from django.contrib import admin, messages
from django.contrib.admin.options import IS_POPUP_VAR
from django.utils.text import capfirst

from .models import MAX_RATING, Author, Book, Genre, ReadingEntry, Review
from .soft_delete import SoftDeleteModel

SOFT_DELETE_FIELDS = ("is_deleted", "deleted_at", "deleted_by")


def _describe(obj):
    """Строка «Тип: объект» — так админка перечисляет удаляемое."""
    return f"{capfirst(obj._meta.verbose_name)}: {obj}"


class SoftDeleteAdmin(admin.ModelAdmin):
    """Примесь для моделей с мягким удалением.

    Админка видит и удалённые записи (менеджер `all_objects`), может отфильтровать их
    и восстановить. Штатное удаление Django здесь тоже мягкое: `delete()` модели
    и выборки только ставят пометку, а кто удалил — берём из запроса.
    """

    def get_queryset(self, request):
        queryset = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            queryset = queryset.order_by(*ordering)
        return queryset

    def get_list_display(self, request):
        return (*super().get_list_display(request), "is_deleted")

    def get_list_filter(self, request):
        return (*super().get_list_filter(request), "is_deleted")

    def get_exclude(self, request, obj=None):
        # Пометку ставят и снимают только удаление и действие «восстановить»,
        # иначе каскад по связанным записям разойдётся с самим объектом.
        return (*(super().get_exclude(request, obj) or ()), *SOFT_DELETE_FIELDS)

    def get_readonly_fields(self, request, obj=None):
        readonly = super().get_readonly_fields(request, obj)
        return (*readonly, *SOFT_DELETE_FIELDS) if obj is not None else readonly

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        # Без объявленных fieldsets поля пометки и так попадут в форму как readonly.
        if self.fieldsets and obj is not None:
            fieldsets = (*fieldsets, ("Удаление", {"fields": SOFT_DELETE_FIELDS}))
        return fieldsets

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Иначе у удалённой записи, ссылающейся на удалённый объект, форма не сохранится:
        # ModelChoiceField не найдёт значение среди живых.
        related = db_field.remote_field.model
        if "queryset" not in kwargs and issubclass(related, SoftDeleteModel):
            kwargs["queryset"] = related.all_objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_deleted_objects(self, objs, request):
        """Что покажет страница подтверждения: объект и то, что пометится вместе с ним.

        Штатный сборщик Django обходит связи по on_delete и соврал бы: физического
        каскада у нас нет, связи описаны в `soft_delete_cascade` / `soft_delete_protect`.
        """
        deleted, model_count, protected = [], Counter(), []
        for obj in objs:
            deleted.append(_describe(obj))
            model_count[obj._meta.verbose_name_plural] += 1

            children = []
            for name, queryset in obj.deleted_related().items():
                items = list(queryset)
                model_count[name] += len(items)
                children.extend(_describe(item) for item in items)
            if children:
                deleted.append(children)

            protected.extend(_describe(item) for item in obj.protected_related())
        return deleted, dict(model_count), set(), protected

    def delete_model(self, request, obj):
        obj.delete(user=request.user)

    def delete_queryset(self, request, queryset):
        queryset.delete(user=request.user)

    @admin.action(description="Восстановить выбранные", permissions=["change"])
    def restore_selected(self, request, queryset):
        """Снимает пометку «удалено» — вместе с тем, что было удалено каскадом."""
        count = queryset.filter(is_deleted=True).restore()
        self.message_user(request, f"Восстановлено записей: {count}.", messages.SUCCESS)

    def get_actions(self, request):
        # Действие добавляем здесь, а не в `actions`: наследники задают свои `actions`
        # и затёрли бы его.
        actions = super().get_actions(request)
        # Во всплывающих окнах выбора Django действия не показывает — не показываем и мы.
        popup = IS_POPUP_VAR in request.GET
        if self.actions is not None and not popup and self.has_change_permission(request):
            func, name, description = self.get_action("restore_selected")
            actions[name] = (func, name, description)
        return actions


@admin.register(Author)
class AuthorAdmin(SoftDeleteAdmin):
    """Авторы в админке."""

    list_display = ("name", "birth_date")


@admin.register(Book)
class BookAdmin(SoftDeleteAdmin):
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
class ReviewAdmin(SoftDeleteAdmin):
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
class ReadingEntryAdmin(SoftDeleteAdmin):
    """Записи дневника в админке."""

    list_display = ("reader", "book", "status", "started_at", "finished_at")
    list_filter = ("status",)
    search_fields = ("book__title", "reader__email")
    autocomplete_fields = ("book",)
    readonly_fields = ("created_at", "updated_at")
