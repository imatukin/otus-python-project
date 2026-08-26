"""Общие фикстуры для тестов каталога книг."""

import datetime

import pytest

from bookshelf_app.models import Author, Book, Genre, Review
from user_app.models import CustomUser

PASSWORD = "12345"


# --- Пользователи ---

@pytest.fixture
def password():
    """Пароль, которым заводятся все тестовые пользователи."""
    return PASSWORD


@pytest.fixture
def user_1():
    """Обычный читатель."""
    return CustomUser.objects.create_user(
        email="user_1@mail.ru",
        password=PASSWORD,
        username="user_1",
    )


@pytest.fixture
def user_2():
    """Второй читатель — для проверок чужих объектов."""
    return CustomUser.objects.create_user(
        email="user_2@mail.ru",
        password=PASSWORD,
        username="user_2",
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
    """Клиент, залогиненный под user_2 — для проверок чужих объектов."""
    client.force_login(user_2)
    return client


@pytest.fixture
def admin_auth_client(client, superuser):
    """Клиент, залогиненный под администратором."""
    client.force_login(superuser)
    return client


# --- Справочники ---

@pytest.fixture
def author():
    """Автор с заполненной биографией и датой рождения."""
    return Author.objects.create(
        name="Михаил Булгаков",
        bio="Русский писатель и драматург.",
        birth_date=datetime.date(1891, 5, 15),
    )


@pytest.fixture
def author_2():
    """Второй автор — минимально заполненный."""
    return Author.objects.create(name="Фёдор Достоевский")


@pytest.fixture
def genre():
    """Жанр «Роман»."""
    return Genre.objects.create(name="Роман")


@pytest.fixture
def genre_2():
    """Второй жанр — для книг с несколькими жанрами."""
    return Genre.objects.create(name="Фантастика")


@pytest.fixture
def genres(genre, genre_2):
    """Пара жанров списком."""
    return [genre, genre_2]


# --- Книги ---

@pytest.fixture
def book(author, genre, user_1):
    """Книга, добавленная user_1."""
    book = Book.objects.create(
        title="Мастер и Маргарита",
        description="Роман о добре и зле.",
        author=author,
        published_year=1967,
        added_by=user_1,
    )
    book.genres.add(genre)
    return book


@pytest.fixture
def book_of_user_2(author_2, user_2):
    """Книга, добавленная другим пользователем."""
    return Book.objects.create(
        title="Преступление и наказание",
        author=author_2,
        published_year=1866,
        added_by=user_2,
    )


@pytest.fixture
def books(author, genre, user_1):
    """Несколько книг одного автора — для списка и пагинации."""
    created = []
    for number in range(1, 4):
        item = Book.objects.create(
            title=f"Книга {number}",
            description=f"Описание книги {number}.",
            author=author,
            published_year=1900 + number,
            added_by=user_1,
        )
        item.genres.add(genre)
        created.append(item)
    return created


# --- Отзывы ---

@pytest.fixture
def review(book, user_2):
    """Отзыв user_2 на книгу user_1."""
    return Review.objects.create(
        book=book,
        reader=user_2,
        text="Отличная книга, перечитываю каждый год.",
        rating=5,
    )


@pytest.fixture
def reviews(book, user_1, user_2):
    """Несколько отзывов на одну книгу — для списка отзывов."""
    return [
        Review.objects.create(book=book, reader=reader, text=text, rating=rating)
        for reader, text, rating in (
            (user_1, "Понравилось.", 5),
            (user_2, "Тяжело читать.", 3),
        )
    ]


# --- Данные для форм ---

@pytest.fixture
def book_form_data(author, genre):
    """Корректные данные для BookForm."""
    return {
        "title": "Собачье сердце",
        "author": author.pk,
        "genres": [genre.pk],
        "published_year": 1925,
        "description": "Повесть о профессоре Преображенском.",
    }


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
