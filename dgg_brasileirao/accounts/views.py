# accounts/views.py
# comentários: views simples para registro/login/logout/home e páginas adicionais:
# - my_team_view, store_view, jogos_view, support_view
# Todas checam sessão com _get_current_user e redirecionam para /login/ se não autenticado.

import uuid
import datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password

from .storage import load_users, save_users

def _get_current_user(request):
    """
    Retorna o usuário (dicionário) salvo em users.json com base na session["user_id"].
    """
    uid = request.session.get("user_id")
    if not uid:
        return None
    users = load_users()
    for u in users:
        if u.get("id") == uid:
            return u
    return None

def register_view(request):
    """
    Registro simples: cria usuário e grava em users.json. Faz login automático.
    """
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""

        if not username or not email or not password:
            messages.error(request, "Preencha todos os campos.")
        else:
            users = load_users()
            if any(u["email"] == email for u in users):
                messages.error(request, "Email já cadastrado.")
            elif any(u["username"].lower() == username.lower() for u in users):
                messages.error(request, "Nome de usuário já existe.")
            else:
                uid = str(uuid.uuid4())
                hashed = make_password(password)
                new_user = {
                    "id": uid,
                    "username": username,
                    "email": email,
                    "password": hashed,
                    "created_at": datetime.datetime.utcnow().isoformat() + "Z",
                }
                users.append(new_user)
                save_users(users)
                request.session["user_id"] = uid
                return redirect("home")
    return render(request, "accounts/register.html")

def login_view(request):
    """
    Login por email+senha. Salva user_id na session se válido.
    """
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        password = request.POST.get("password") or ""
        users = load_users()
        user = next((u for u in users if u["email"] == email), None)
        if user and check_password(password, user.get("password", "")):
            request.session["user_id"] = user["id"]
            return redirect("home")
        else:
            messages.error(request, "Email ou senha inválidos.")
    return render(request, "accounts/login.html")

def logout_view(request):
    """
    Faz logout limpando a session e redireciona para login.
    """
    request.session.flush()
    return redirect("login")

def home_view(request):
    """
    Página Home — acessível apenas com sessão ativa.
    No header (Home) mostramos primeiro o link 'My Team'.
    """
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    # Passa contexto com user; template home.html exibe header personalizado
    return render(request, "accounts/home.html", {"user": user})

def my_team_view(request):
    """
    Página 'My Team' — acessível apenas com sessão ativa.
    No header mostramos primeiro o link 'Home'.
    """
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    # exemplo simples: dados fictícios do time (pode adaptar depois)
    team = {
        "name": f"{user['username']}'s Team",
        "level": 1,
        "coins": 100,
    }
    return render(request, "accounts/my_team.html", {"user": user, "team": team})

def store_view(request):
    """
    Página Loja (simples placeholder).
    """
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    # lista de itens exemplo
    itens = [
        {"id": 1, "name": "Camisa", "price": 50},
        {"id": 2, "name": "Bola", "price": 30},
    ]
    return render(request, "accounts/store.html", {"user": user, "items": itens})

def jogos_view(request):
    """
    Página Jogos (placeholder).
    """
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    matches = [
        {"opponent": "Time A", "date": "2025-10-25"},
        {"opponent": "Time B", "date": "2025-10-30"},
    ]
    return render(request, "accounts/matches.html", {"user": user, "matches": matches})

def support_view(request):
    """
    Página Suporte/Contato (placeholder).
    """
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    return render(request, "accounts/support.html", {"user": user})

def contratos_view(request):
    """Rota /contracts/ — exibe lista de contratos (placeholder)."""
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    contratos = [
        {"id": 1, "player": "Player X", "value": 1000},
        {"id": 2, "player": "Player Y", "value": 750},
    ]
    return render(request, "accounts/contracts.html", {"user": user, "contratos": contratos})

def missoes_view(request):
    """Rota /missions/ — exibe missões (placeholder)."""
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    missoes = [
        {"id": 1, "title": "Train 3x", "reward": 50},
        {"id": 2, "title": "Win a match", "reward": 100},
    ]
    return render(request, "accounts/missions.html", {"user": user, "missoes": missoes})