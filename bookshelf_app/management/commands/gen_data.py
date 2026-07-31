from django.core.management.base import BaseCommand
from bookshelf_app.models import Book, Author, Genre, Reader, Review
import random
from faker import Faker


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
                )
                # Случайные жанры для книги
                book.genres.set(random.sample(genres, random.randint(1, len(genres))))

                books.append(book)
                self.stdout.write(f"Создана книга {book.title}")

        # Генерация читателей
        for _ in range(random.randint(5, 10)):
            reader = Reader.objects.create(
                full_name=faker.name(),
                nickname=faker.unique.user_name(),
                about=faker.text(max_nb_chars=300),
                birth_date=faker.date(),
            )
            readers.append(reader)
            self.stdout.write(f"Создан читатель {reader.nickname}")

            # Генерация отзывов читателя на случайные книги
            for book in random.sample(books, random.randint(0, min(3, len(books)))):
                Review.objects.create(
                    book=book,
                    reader=reader,
                    text=faker.text(max_nb_chars=400),
                    rating=random.randint(1, 5),
                )
                self.stdout.write(f"Создан отзыв {reader.nickname} на «{book.title}»")

        # Кто добавил книгу в каталог
        for book in books:
            book.added_by = random.choice(readers)
            book.save()

        self.stdout.write("Закончено")
