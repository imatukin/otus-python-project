"""Фоновые задачи каталога книг (Celery)."""

import datetime
import logging

from celery import shared_task

from .models import EventLog

# Отдельный логгер задачи: его вывод видно в консоли celery-воркера.
logger = logging.getLogger(__name__)


@shared_task
def log_event_task(event):
    """Записывает событие журнала в БД (и дублирует строкой в консоль воркера).

    `event` — словарь полей `EventLog` из простых значений: задача уходит в очередь в JSON.
    `created_at` в нём — время события в ISO-формате. Возвращает id записи журнала.
    """
    record = EventLog.objects.create(
        **{**event, 'created_at': datetime.datetime.fromisoformat(event['created_at'])}
    )
    logger.info('Журнал событий: %s, id=%s', record, record.object_id)
    return record.pk
