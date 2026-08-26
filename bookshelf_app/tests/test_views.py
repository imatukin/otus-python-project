import pytest
from django.urls import reverse


# Это дневник, прочитанных книг.

def test_index_view(client):
    """Тест главной страницы"""
    url = reverse('index')
    response = client.get(url)
    assert response.status_code == 200
    assert "Это дневник, прочитанных книг." in response.content.decode()

