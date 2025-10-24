# accounts/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),

    # English paths / names
    path("my-team/", views.my_team_view, name="my_team"),
    path("store/", views.store_view, name="store"),
    path("matches/", views.jogos_view, name="matches"),    # maps to jogos_view
    path("support/", views.support_view, name="support"),

    # extras
    path("contracts/", views.contratos_view, name="contracts"),
    path("missions/", views.missoes_view, name="missions"),
]
