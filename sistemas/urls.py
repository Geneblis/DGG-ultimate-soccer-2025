# accounts/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),

    # meu time
    path('my-team/', views.my_team_view, name='my_team'),
    path('my-team/set-slot/', views.set_team_slot_view, name='set_team_slot'),
    path('my-team/clear-slot/', views.clear_team_slot_view, name='clear_team_slot'),
    

    #outros
    path("store/", views.store_view, name="store"),
    path("matches/", views.jogos_view, name="matches"),    # maps to jogos_view
    path('inventory/sell/', views.sell_inventory_item_view, name='sell_inventory'),

    path("store-players/", views.store_players_view, name="store_players"),

    #packs
    path("packs/", views.packs_list_view, name="packs_list"),
    path('packs/<uuid:pack_id>/buy/', views.buy_pack_view, name='buy_pack'),

    path("game/", views.game_view, name="game"),
    path("game/start-random/", views.start_random_match_view, name="start_random_match"),
    path("game/match/<uuid:match_id>/", views.match_play_view, name="match_play"),
]