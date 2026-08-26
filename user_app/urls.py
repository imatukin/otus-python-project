"""Маршруты приложения пользователей."""

from django.urls import path

from user_app.views import (
    ProfileView,
    RegisterView,
    UserDetailView,
    UserLoginView,
    UserLogoutView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", UserLoginView.as_view(), name="login"),
    path("logout/", UserLogoutView.as_view(), name="logout"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user_detail"),
]
