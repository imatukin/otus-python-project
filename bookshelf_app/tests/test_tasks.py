"""Тесты фоновых задач Celery."""

import logging

import pytest
from django.urls import reverse

from bookshelf_app.models import Book
from bookshelf_app.tasks import log_new_book_task


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


class TestLogNewBookTask:
    """Задача логирования новой книги."""

    def test_returns_message(self):
        """Задача вызванная напрямую (как обычная функция)."""
        result = log_new_book_task(
            book_id=1,
            title="Мастер и Маргарита",
            author="Михаил Булгаков",
            added_by="user_1",
        )
        assert "Мастер и Маргарита" in result
        assert "Михаил Булгаков" in result
        assert "id=1" in result
        assert "user_1" in result

    def test_writes_to_log(self, task_logs):
        """Сообщение уходит в лог — его видно в консоли воркера."""
        log_new_book_task(1, "Собачье сердце", "Михаил Булгаков", "user_1")
        assert "Собачье сердце" in task_logs.text

    def test_delay_executes_task(self):
        """Задача ставится в очередь через .delay() и выполняется."""
        async_result = log_new_book_task.delay(
            book_id=7,
            title="Белая гвардия",
            author="Михаил Булгаков",
            added_by="user_1",
        )
        assert async_result.successful()
        assert "Белая гвардия" in async_result.get()

    def test_task_is_registered(self):
        """Задача зарегистрирована в приложении Celery под своим именем."""
        assert log_new_book_task.name == "bookshelf_app.tasks.log_new_book_task"


class TestBookCreateViewEnqueuesTask:
    """Добавление книги через форму ставит фоновую задачу."""

    @pytest.mark.django_db
    def test_task_called_with_book_data(self, auth_client, book_form_data, user_1, mocker):
        """В задачу уходят данные уже сохранённой книги (с pk)."""
        delay = mocker.patch("bookshelf_app.views.log_new_book_task.delay")

        response = auth_client.post(reverse("book_add"), data=book_form_data)

        assert response.status_code == 302
        book = Book.objects.get(title=book_form_data["title"])
        delay.assert_called_once_with(
            book_id=book.pk,
            title=book.title,
            author=str(book.author),
            added_by=str(user_1),
        )

    @pytest.mark.django_db
    def test_no_task_on_invalid_form(self, auth_client, book_form_data, mocker):
        """Форма не прошла валидацию — задача не ставится."""
        delay = mocker.patch("bookshelf_app.views.log_new_book_task.delay")

        response = auth_client.post(
            reverse("book_add"), data={**book_form_data, "title": ""}
        )

        assert response.status_code == 200
        delay.assert_not_called()

    @pytest.mark.django_db
    def test_task_runs_on_book_create(self, auth_client, book_form_data, task_logs):
        """Сквозная проверка: после добавления книги задача выполнилась."""
        auth_client.post(reverse("book_add"), data=book_form_data)
        assert book_form_data["title"] in task_logs.text
