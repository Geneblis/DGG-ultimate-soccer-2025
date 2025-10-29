# dgg_brasileirao/urls.py
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),      # opcional — pode comentar se não quiser admin
    path("", include("sistemas.urls")),   # encaminha a raiz para o app accounts
]
