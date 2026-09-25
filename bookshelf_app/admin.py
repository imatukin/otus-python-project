"""Админка каталога (авторы, книги, жанры, отзывы), дневника чтения и журнала событий."""

from collections import Counter

from django.contrib import admin, messages
from django.contrib.admin.options import IS_POPUP_VAR
from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.text import capfirst

from .events import OBJECT_TYPES, log_created, log_deleted, log_restored, log_updated, snapshot, stored_snapshot
from .models import MAX_RATING, Author, Book, EventLog, Genre, ReadingEntry, Review
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
        count = 0
        for obj in queryset.filter(is_deleted=True):
            self.restore_model(request, obj)
            count += 1
        self.message_user(request, f"Восстановлено записей: {count}.", messages.SUCCESS)

    def restore_model(self, request, obj):  # pylint: disable=unused-argument
        """Восстанавливает один объект; `request` нужен наследникам, которые пишут журнал."""
        obj.restore()

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


class EventLogMixin(SoftDeleteAdmin):
    """Книги и авторы: всё, что с ними делают в админке, пишется в журнал событий."""

    def save_model(self, request, obj, form, change):
        # Старые значения берём из базы до сохранения; жанры сохранятся позже, в save_related,
        # поэтому сравнение — там же. Снимок переносим на форме: она общая у обоих методов.
        form.event_old_snapshot = stored_snapshot(obj) if change else None
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if change:
            log_updated(form.instance, request.user, form.event_old_snapshot)
        else:
            log_created(form.instance, request.user)

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        log_deleted(obj, request.user)

    def delete_queryset(self, request, queryset):
        # По одному, а не выборкой целиком: каждому объекту — своё событие.
        for obj in queryset:
            self.delete_model(request, obj)

    def restore_model(self, request, obj):
        super().restore_model(request, obj)
        log_restored(obj, request.user)


@admin.register(Author)
class AuthorAdmin(EventLogMixin):
    """Авторы в админке."""

    list_display = ("name", "birth_date")


@admin.register(Book)
class BookAdmin(EventLogMixin):
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
    def confirm_pending(self, request, queryset):
        """Снимает с книг пометку «требует дозаполнения» — каждое снятие попадает в журнал."""
        for book in queryset.filter(is_pending=True):
            old = snapshot(book)
            book.is_pending = False
            book.save(update_fields=("is_pending",))
            log_updated(book, request.user, old)

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


class EventUserFilter(admin.SimpleListFilter):
    """Фильтр по пользователю — включая удалённых: штатный фильтр по FK их не видит."""

    title = "пользователь"
    parameter_name = "user"

    def lookups(self, request, model_admin):
        users = get_user_model().all_objects.filter(events__isnull=False).distinct().order_by("email")
        return [(user.pk, str(user)) for user in users]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(user_id=self.value())
        return queryset


@admin.register(EventLog)
class EventLogAdmin(admin.ModelAdmin):
    """Журнал событий — только для чтения: записи не создаются, не правятся и не удаляются руками."""

    list_display = ("created_at", "user", "action", "object_type", "object_link", "changed_fields")
    list_filter = (EventUserFilter, "object_type", "action", "created_at")
    list_select_related = ("user",)
    date_hierarchy = "created_at"
    search_fields = ("object_repr",)
    fields = ("created_at", "user", "action", "object_type", "object_link", "changes_table")
    readonly_fields = ("object_link", "changes_table")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Объект", ordering="object_repr")
    def object_link(self, obj):
        """Название объекта ссылкой на его страницу в админке."""
        url = reverse(f"admin:bookshelf_app_{obj.object_type}_change", args=[obj.object_id])
        return format_html('<a href="{}">{}</a>', url, obj.object_repr)

    @admin.display(description="Поля")
    def changed_fields(self, obj):
        """Какие поля затронуло событие — для списка."""
        return ", ".join(self._label(obj, name) for name in obj.changes)

    @admin.display(description="Изменения")
    def changes_table(self, obj):
        """Изменения таблицей: поле, было, стало."""
        if not obj.changes:
            return "—"
        rows = format_html_join(
            "",
            "<tr><td>{}</td><td>{}</td><td>{}</td></tr>",
            (
                (self._label(obj, name), self._display(change["old"]), self._display(change["new"]))
                for name, change in obj.changes.items()
            ),
        )
        return format_html(
            "<table><thead><tr><th>Поле</th><th>Было</th><th>Стало</th></tr></thead>"
            "<tbody>{}</tbody></table>",
            rows,
        )

    @staticmethod
    def _label(obj, name):
        """Название поля по-человечески; поля, которого у модели уже нет, — как записано."""
        models = {object_type: model for model, object_type in OBJECT_TYPES.items()}
        try:
            return capfirst(models[obj.object_type]._meta.get_field(name).verbose_name)
        except (KeyError, FieldDoesNotExist):
            return name

    @staticmethod
    def _display(value):
        """Значение из журнала для людей: пустое — прочерком, список — через запятую."""
        if value in (None, "", []):
            return "—"
        if isinstance(value, list):
            return ", ".join(value)
        if isinstance(value, bool):
            return "да" if value else "нет"
        return value
