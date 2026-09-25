"""Тесты админки каталога: собственные действия и массовое удаление отзывов."""

import pytest
from django.urls import reverse

from bookshelf_app.models import MAX_RATING, Review

pytestmark = pytest.mark.django_db


class TestReviewAdmin:
    """Админка отзывов."""

    @staticmethod
    def run_action(client, action, reviews):
        """Запускает действие админки над выбранными отзывами."""
        return client.post(
            reverse("admin:bookshelf_app_review_changelist"),
            {"action": action, "_selected_action": [review.pk for review in reviews], "post": "yes"},
        )

    def test_up_rating(self, admin_auth_client, reviews):
        self.run_action(admin_auth_client, "up_rating", reviews)
        assert [Review.objects.get(pk=review.pk).rating for review in reviews] == [MAX_RATING, 4]

    def test_bulk_delete_is_soft(self, admin_auth_client, reviews, superuser):
        self.run_action(admin_auth_client, "delete_selected", reviews)
        assert not Review.objects.exists()
        deleted = Review.all_objects.filter(pk__in=[review.pk for review in reviews])
        assert deleted.count() == len(reviews)
        assert all(review.deleted_by == superuser for review in deleted)
