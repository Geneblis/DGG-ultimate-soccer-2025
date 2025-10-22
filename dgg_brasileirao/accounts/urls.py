# accounts/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),

    # novas páginas
    path("my-team/", views.my_team_view, name="my_team"),
    path("store/", views.store_view, name="store"),
    path("jogos/", views.jogos_view, name="jogos"),
    path("support/", views.support_view, name="support"),
]
