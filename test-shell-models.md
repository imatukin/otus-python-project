# Проверка моделей через shell
```shell
python manage.py shell
```

## Create — создание записей
```python
author = Author(name='Михаил Булгаков', birth_date='1891-05-15')
author.save()
genre_novel = Genre.objects.create(name='Роман')
genre_mystic = Genre.objects.create(name='Мистика')
reader = Reader.objects.create(full_name='Иванов Иван Иванович', nickname='ivan')
```

## Read — чтение
```python
Author.objects.all()
Author.objects.count()
Genre.objects.first()
Genre.objects.get(name='Роман')
Reader.objects.filter(nickname='ivan')
Reader.objects.filter(nickname__icontains='IVAN')
Reader.objects.filter(full_name__contains='Иван')
```

## ForeignKey — книга и её автор (один ко многим)
```python
book = Book.objects.create(
    title='Мастер и Маргарита',
    description='Роман о добре и зле',
    author=author,
    published_year=1967,
    added_by=reader,
)
book2 = Book.objects.create(title='Собачье сердце', author=author, published_year=1925)
book.author.name
author.books.all()
reader.added_books.all()
```

## ManyToMany — жанры книги
```python
book.genres.add(genre_novel, genre_mystic)
book.genres.all()
genre_mystic.books.all()
book.genres.remove(genre_mystic)
book.genres.count()
```

## Отзывы — связь с книгой и читателем
```python
reader2 = Reader.objects.create(full_name='Петров Пётр Петрович', nickname='petr')
review = Review.objects.create(book=book, reader=reader, text='Лучшая книга', rating=5)
Review.objects.create(book=book, reader=reader2, text='Тяжело читается', rating=3)
book.reviews.all()
reader.reviews.all()
review.book.title
review.reader.nickname
```

## Фильтрация и сортировка по связям
```python
Book.objects.filter(author__name='Михаил Булгаков')
Book.objects.filter(genres__name='Роман')
Review.objects.filter(book__title='Мастер и Маргарита', rating__gte=4)
Review.objects.filter(reader__nickname='ivan').order_by('-created_at')
Book.objects.filter(published_year__lt=1930)
Book.objects.exclude(published_year=None)
```

## Update — изменение
```python
book.published_year = 1966
book.save()
Book.objects.filter(author=author).update(description='Обновлённое описание')
```

## Delete — удаление и поведение связей
```python
review.delete()
book.delete()
author.delete()
reader.delete()
```

## Очистка тестовых данных

```python
Review.objects.all().delete()
Book.objects.all().delete()
Genre.objects.all().delete()
Reader.objects.all().delete()
Author.objects.all().delete()
```
