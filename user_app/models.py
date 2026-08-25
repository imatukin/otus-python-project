from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.urls import reverse


class CustomUserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Почта должна быть указана!')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True')
        if extra_fields.get('is_active') is not True:
            raise ValueError('Superuser must have is_active=True')

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractUser):
    """Пользователь сайта, он же читатель."""
    username = models.CharField(
        max_length=150,
        unique=False,
        blank=True,
        null=True,
        verbose_name='Имя пользователя'
    )
    email = models.EmailField(
        unique=True,
        verbose_name='Email пользователя'
    )
    full_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='ФИО'
    )
    about = models.TextField(
        blank=True,
        verbose_name='О себе'
    )
    date_of_birth = models.DateField(
        blank=True,
        null=True,
        verbose_name='Дата рождения пользователя'
    )
    avatar = models.ImageField(
        blank=True,
        null=True,
        upload_to='avatars/',
        verbose_name='Аватар пользователя'
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    @property
    def display_name(self):
        """Как показываем читателя: ник, а если его нет — email целиком."""
        return self.username or self.email

    def __repr__(self):
        return f'{self.email} ({self.username})'

    def __str__(self):
        return self.display_name

    def get_absolute_url(self):
        """Публичная страница читателя."""
        return reverse('user_detail', args=[self.pk])
