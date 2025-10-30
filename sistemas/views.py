# sistemas/views.py
import datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from .models import SistemasUser, JogadorCampo, InventoryItem

def _get_current_user(request):
    uid = request.session.get("user_id")
    if not uid:
        return None
    try:
        return SistemasUser.objects.get(pk=uid)
    except SistemasUser.DoesNotExist:
        return None

def register_view(request):
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        full_name = (request.POST.get("name") or "").strip() or ""

        if not username or not email or not password:
            messages.error(request, "Preencha todos os campos.")
        else:
            if SistemasUser.objects.filter(email=email).exists():
                messages.error(request, "Email já cadastrado.")
            elif SistemasUser.objects.filter(username__iexact=username).exists():
                messages.error(request, "Nome de usuário já existe.")
            else:
                hashed = make_password(password)
                new_user = SistemasUser.objects.create(
                    full_name=full_name,
                    username=username,
                    email=email,
                    password=hashed,
                    coins=100,
                )
                request.session["user_id"] = str(new_user.id)
                return redirect("home")
    return render(request, "accounts/register.html")


def login_view(request):
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        try:
            user = SistemasUser.objects.get(email=email)
        except SistemasUser.DoesNotExist:
            user = None

        if user and check_password(password, user.password):
            request.session["user_id"] = str(user.id)
            return redirect("home")
        else:
            messages.error(request, "Email ou senha inválidos.")
    return render(request, "accounts/login.html")

def logout_view(request):
    request.session.flush()
    return redirect("login")

def home_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    return render(request, "accounts/home.html", {"user": user})

def my_team_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    team = {"name": f"{user.username}'s Team", "level": 1, "coins": user.coins}
    return render(request, "accounts/my_team.html", {"user": user, "team": team})

def store_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    items = [{"id": 1, "name": "Camisa", "price": 50}, {"id": 2, "name": "Bola", "price": 30}]
    return render(request, "accounts/store.html", {"user": user, "items": items})

def jogos_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    matches = [{"opponent": "Time A", "date": "2025-10-25"}, {"opponent": "Time B", "date": "2025-10-30"}]
    return render(request, "accounts/matches.html", {"user": user, "matches": matches})

def support_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    return render(request, "accounts/support.html", {"user": user})

def contratos_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    contratos = [{"id": 1, "player": "Player X", "value": 1000}, {"id": 2, "player": "Player Y", "value": 750}]
    return render(request, "accounts/contracts.html", {"user": user, "contratos": contratos})

def missoes_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    missoes = [{"id": 1, "title": "Train 3x", "reward": 50}, {"id": 2, "title": "Win a match", "reward": 100}]
    return render(request, "accounts/missions.html", {"user": user, "missoes": missoes})
