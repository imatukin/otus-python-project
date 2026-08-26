"""Общие фикстуры для тестов приложения пользователей."""

import datetime
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from bookshelf_app.models import Author, Book, Review
from user_app.models import CustomUser

PASSWORD = "12345"


# --- Пользователи ---

@pytest.fixture
def password():
    """Пароль, которым заводятся все тестовые пользователи."""
    return PASSWORD


@pytest.fixture
def user_1():
    """Читатель с заполненным профилем."""
    return CustomUser.objects.create_user(
        email="user_1@mail.ru",
        password=PASSWORD,
        username="user_1",
        full_name="Иванов Иван Иванович",
        about="Читаю классику.",
        date_of_birth=datetime.date(1990, 1, 15),
    )


@pytest.fixture
def user_2():
    """Второй читатель — без имени, чтобы проверять показ email."""
    return CustomUser.objects.create_user(
        email="user_2@mail.ru",
        password=PASSWORD,
    )


@pytest.fixture
def superuser():
    """Администратор сайта."""
    return CustomUser.objects.create_superuser(
        email="admin@mail.ru",
        password=PASSWORD,
        username="admin",
    )


@pytest.fixture
def auth_client(client, user_1):
    """Клиент, залогиненный под user_1."""
    client.force_login(user_1)
    return client


@pytest.fixture
def auth_client_2(client, user_2):
    """Клиент, залогиненный под user_2 — для проверок чужих страниц."""
    client.force_login(user_2)
    return client


# --- Книги и отзывы читателя ---

@pytest.fixture
def author():
    """Автор книг, добавленных читателем."""
    return Author.objects.create(name="Михаил Булгаков")


@pytest.fixture
def book(author, user_1):
    """Книга, добавленная user_1."""
    return Book.objects.create(
        title="Мастер и Маргарита",
        description="Роман о добре и зле.",
        author=author,
        published_year=1967,
        added_by=user_1,
    )


@pytest.fixture
def books(author, user_1):
    """Несколько книг user_1 — для блока активности читателя."""
    return [
        Book.objects.create(
            title=f"Книга {number}",
            author=author,
            published_year=1900 + number,
            added_by=user_1,
        )
        for number in range(1, 4)
    ]


@pytest.fixture
def review(book, user_1):
    """Отзыв user_1 на свою книгу."""
    return Review.objects.create(
        book=book,
        reader=user_1,
        text="Отличная книга, перечитываю каждый год.",
        rating=5,
    )


@pytest.fixture
def reviews(book, author, user_1):
    """Несколько отзывов user_1 — для блока активности читателя."""
    other = Book.objects.create(title="Собачье сердце", author=author, added_by=user_1)
    return [
        Review.objects.create(book=item, reader=user_1, text=text, rating=rating)
        for item, text, rating in (
            (book, "Понравилось.", 5),
            (other, "Тяжело читать.", 3),
        )
    ]


# --- Данные для форм ---

@pytest.fixture
def register_form_data():
    """Корректные данные для CustomUserCreationForm."""
    return {
        "email": "new_reader@mail.ru",
        "username": "Новый читатель",
        "password1": PASSWORD,
        "password2": PASSWORD,
    }


@pytest.fixture
def login_form_data(user_1):
    """Корректные данные для CustomAuthenticationForm."""
    return {"username": user_1.email, "password": PASSWORD}


@pytest.fixture
def profile_form_data():
    """Корректные данные для ProfileForm."""
    return {
        "username": "Иван",
        "full_name": "Иванов Иван Иванович",
        "about": "Читаю классику.",
        "date_of_birth": "1990-01-15",
    }


@pytest.fixture
def avatar():
    """Небольшая картинка-аватар для загрузки в профиль."""
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buffer, format="PNG")
    return SimpleUploadedFile("avatar.png", buffer.getvalue(), content_type="image/png")


# --- Защита данных проекта ---

@pytest.fixture(autouse=True)
def _protect_project_db(request):
    """Страховка: тесты не должны открывать боевую БД проекта.

    pytest-django и так поднимает отдельную тестовую базу (для sqlite —
    в памяти), но проверяем это явно, чтобы db.sqlite3 нельзя было задеть
    даже при случайной правке настроек.
    """
    if "django_db" not in request.node.keywords and "db" not in request.fixturenames:
        # Тест вообще не работает с базой — проверять нечего.
        yield
        return

    # Импорт внутри фикстуры: Django настраивается позже импорта conftest.
    # pylint: disable=import-outside-toplevel
    from django.conf import settings
    from django.db import connections

    project_db = str(settings.BASE_DIR / "db.sqlite3")
    for connection in connections.all():
        name = str(connection.settings_dict["NAME"])
        assert name != project_db, f"Тесты подключились к боевой БД: {name}"
    yield


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    """Загруженные в тестах файлы (аватары) пишем во временную папку."""
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT
