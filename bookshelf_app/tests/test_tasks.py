"""Тесты фоновых задач Celery."""

import datetime
import logging

import pytest
from django.utils import timezone

from bookshelf_app.models import EventLog
from bookshelf_app.tasks import log_event_task


@pytest.fixture
def task_logs(caplog):
    """caplog, который видит записи задач.

    В настройках у логгера `bookshelf_app` стоит propagate=False (чтобы
    сообщение не дублировалось в корневом логгере), а caplog слушает как раз
    корневой. На время теста включаем передачу записей наверх.
    """
    logger = logging.getLogger("bookshelf_app")
    propagate = logger.propagate
    logger.propagate = True
    caplog.set_level(logging.INFO, logger="bookshelf_app")
    yield caplog
    logger.propagate = propagate


@pytest.fixture
def event_data(user_1):
    """Событие в том виде, в каком оно уходит в очередь: только простые значения."""
    return {
        "object_type": EventLog.ObjectType.BOOK,
        "object_id": 7,
        "object_repr": "Белая гвардия",
        "action": EventLog.Action.UPDATED,
        "user_id": user_1.pk,
        "changes": {"title": {"old": "Гвардия", "new": "Белая гвардия"}},
        "created_at": datetime.datetime(2026, 9, 1, 12, 30, tzinfo=datetime.timezone.utc).isoformat(),
    }


@pytest.mark.django_db
class TestLogEventTask:
    """Задача записи события журнала."""

    def test_creates_record(self, event_data, user_1):
        event_id = log_event_task(event_data)
        event = EventLog.objects.get(pk=event_id)
        assert event.user == user_1
        assert event.action == EventLog.Action.UPDATED
        assert event.object_type == EventLog.ObjectType.BOOK
        assert event.object_id == 7
        assert event.object_repr == "Белая гвардия"
        assert event.changes == {"title": {"old": "Гвардия", "new": "Белая гвардия"}}

    def test_keeps_event_time(self, event_data):
        """Время — когда событие случилось, а не когда до него дошёл воркер."""
        event = EventLog.objects.get(pk=log_event_task(event_data))
        assert event.created_at == datetime.datetime(2026, 9, 1, 12, 30, tzinfo=datetime.timezone.utc)
        assert event.created_at < timezone.now()

    def test_without_user(self, event_data):
        event = EventLog.objects.get(pk=log_event_task({**event_data, "user_id": None}))
        assert event.user is None
        assert "неизвестно" in str(event)

    def test_writes_to_log(self, event_data, task_logs):
        """Событие дублируется в лог — его видно в консоли воркера."""
        log_event_task(event_data)
        assert "Изменение: книга «Белая гвардия»" in task_logs.text

    def test_delay_executes_task(self, event_data):
        """Задача ставится в очередь через .delay() и выполняется."""
        async_result = log_event_task.delay(event_data)
        assert async_result.successful()
        assert EventLog.objects.filter(pk=async_result.get()).exists()

    def test_task_is_registered(self):
        """Задача зарегистрирована в приложении Celery под своим именем."""
        assert log_event_task.name == "bookshelf_app.tasks.log_event_task"
