"""Админка пользователей."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from user_app.models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Пользователи в админке."""

    list_display = ("email", "username", "full_name", "date_of_birth", "is_staff")
    search_fields = ("email", "username", "full_name")
    ordering = ("email",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Профиль читателя",
            {"fields": ("username", "full_name", "about", "date_of_birth", "avatar")},
        ),
        (
            "Права доступа",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Даты", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "username", "password1", "password2"),
            },
        ),
    )
