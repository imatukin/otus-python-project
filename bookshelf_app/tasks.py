"""Фоновые задачи каталога книг (Celery)."""

import logging

from celery import shared_task

# Отдельный логгер задачи: его вывод видно в консоли celery-воркера.
logger = logging.getLogger(__name__)


@shared_task
def log_new_book_task(book_id, title, author, added_by):
    """Пишет в консоль воркера информацию о новой книге в каталоге."""
    message = (
        f'Новая книга в каталоге: «{title}» ({author}), '
        f'id={book_id}, добавил: {added_by}'
    )
    logger.info(message)
    return message
