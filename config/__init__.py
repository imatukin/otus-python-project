"""Пакет настроек проекта: при старте Django подхватывается приложение Celery."""

from .celery import app as celery_app

__all__ = ("celery_app",)
