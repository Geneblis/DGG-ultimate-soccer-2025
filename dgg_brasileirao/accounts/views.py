# accounts/views.py
import uuid
import datetime
from django.shortcuts import render, redirect
from django.contrib import messages
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password

from .storage import load_users, save_users

def _get_current_user(request):
    uid = request.session.get("user_id")
    if not uid:
        return None
    users = load_users()
    for u in users:
        if u.get("id") == uid:
            return u
    return None

def register_view(request):
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
    request.session.flush()
    return redirect("login")

def home_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    return render(request, "accounts/home.html", {"user": user})
