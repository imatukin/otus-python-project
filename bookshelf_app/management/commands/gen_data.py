import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from faker import Faker

from bookshelf_app.models import Author, Book, Genre, Review

User = get_user_model()

# Пароль у всех сгенерированных читателей одинаковый — чтобы можно было войти.
DEMO_PASSWORD = "12345"


class Command(BaseCommand):
    help = "Генерация данных для БД"

    def handle(self, *args, **options):
        """Вызов генерации данных для БД"""
        self.stdout.write("Генерация данных для БД")
        faker = Faker()

        genres = []
        authors = []
        books = []
        readers = []

        # Генерация жанров
        for _ in range(5):
            genre = Genre.objects.create(name=faker.unique.word())
            genres.append(genre)

        # Генерация читателей — они нужны раньше книг, чтобы указать, кто добавил
        for _ in range(random.randint(5, 10)):
            reader = User.objects.create_user(
                email=faker.unique.email(),
                password=DEMO_PASSWORD,
                username=faker.unique.user_name(),
                full_name=faker.name(),
                about=faker.text(max_nb_chars=300),
                date_of_birth=faker.date(),
            )
            readers.append(reader)
            self.stdout.write(f"Создан читатель {reader.display_name}")

        # Генерация авторов
        for _ in range(random.randint(3, 7)):
            author = Author.objects.create(
                name=faker.name(),
                bio=faker.text(max_nb_chars=500),
                birth_date=faker.date(),
            )
            authors.append(author)
            self.stdout.write(f"Создан автор {author.name}")

            # Генерация книг для автора
            for _ in range(random.randint(1, 3)):
                book = Book.objects.create(
                    title=faker.sentence(),
                    author=author,
                    description=faker.text(max_nb_chars=200),
                    published_year=int(faker.year()),
                    added_by=random.choice(readers),
                )
                # Случайные жанры для книги
                book.genres.set(random.sample(genres, random.randint(1, len(genres))))

                books.append(book)
                self.stdout.write(f"Создана книга {book.title}")

        # Генерация отзывов читателей на случайные книги
        for reader in readers:
            for book in random.sample(books, random.randint(0, min(3, len(books)))):
                Review.objects.create(
                    book=book,
                    reader=reader,
                    text=faker.text(max_nb_chars=400),
                    rating=random.randint(1, 5),
                )
                self.stdout.write(
                    f"Создан отзыв {reader.display_name} на «{book.title}»"
                )

        self.stdout.write(f"Пароль всех читателей: {DEMO_PASSWORD}")
        self.stdout.write("Закончено")
