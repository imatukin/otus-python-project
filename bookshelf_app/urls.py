from django.urls import path
from bookshelf_app.views import index, about


urlpatterns = [
    path('', index),
    path('about/', about),
]
