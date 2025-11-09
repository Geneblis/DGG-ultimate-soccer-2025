# sistemas/views.py
import random
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.hashers import make_password, check_password
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from .models import (
    SistemasUser, JogadorCampo, JogadorGoleiro,
    InventoryItem, Pack, PackEntry
)

# colocar no topo do arquivo, se ainda não tiver
import uuid
import unicodedata

# ... outros imports já existentes ...
from django.shortcuts import render, redirect
from django.db import transaction
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.contrib.contenttypes.models import ContentType

import uuid
import unicodedata
from django.db import connection

from .models import Pack, PackEntry, JogadorCampo, JogadorGoleiro, InventoryItem, SistemasUser



def _static_path_for_club_logo(player):
    """
    Retorna um caminho relativo para o logo do clube que existe - exemplo:
    'players/santos/logo.png' (para usar com {% static %}).
    Retorna None se não existir.
    """
    # normaliza o nome do clube para slug (ex: "Santos FC" -> "santos-fc")
    slug = slugify(player.club or "")
    candidate = f"players/{slug}/logo.png"
    # se suas imagens estão em STATICFILES_DIRS (ex: imagens/players/...), então
    # {% static candidate %} deve resolver. Aqui só retornamos o path relativo.
    return candidate

def _flag_url_for_country(country_code_or_name):
    """
    Espera que country seja o ISO alpha-2 (ex: 'br'). Se for nome longo, tenta
    fazer um mapeamento básico; ideal é já salvar ISO no DB.
    Retorna URL absoluta da CDN (FlagCDN) ou None.
    """
    if not country_code_or_name:
        return None
    cc = str(country_code_or_name).strip().lower()
    # se já é 2 letras, usa direto
    if len(cc) == 2 and cc.isalpha():
        return f"https://flagcdn.com/h40/{cc}.png"
    # mapeamento simples (adicione os que precisar)
    MAP = {
        "brazil": "br",
        "argentina": "ar",
        "uruguay": "uy",
        "chile": "cl",
        "portugal": "pt",
        "spain": "es",
        "espanha": "es",
        "colombia": "co",
        "paraguay": "py",
        "bolivia": "bo",
        "peru": "pe",
        "france": "fr",
        "england": "gb",
        "unitedstates": "us",
        # adicione conforme sua necessidade...
    }
    key = cc.lower()
    code = MAP.get(key)
    if code:
        return f"https://flagcdn.com/h40/{code}.png"
    return None  # se não souber, devolve None

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

def store_players_view(request):
    #use de exemplo para listar jogadores disponiveis no pack:

    user = _get_current_user(request)
    if not user:
        return redirect("login")

    field_players = list(JogadorCampo.objects.all().order_by("-overall", "name"))
    goalkeepers = list(JogadorGoleiro.objects.all().order_by("-overall", "name"))

    for p in field_players + goalkeepers:
        p.flag_url = _flag_url_for_country(p.country)
        p.club_logo = _static_path_for_club_logo(p)

    return render(request, "accounts/store_players.html", {
        "user": user,
        "field_players": field_players,
        "goalkeepers": goalkeepers,
    })

@require_http_methods(["GET", "POST"])
@transaction.atomic
def packs_list_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("/login/")

    if request.method == "POST":
        raw = request.POST.get("pack_id")
        if raw is None:
            messages.error(request, "Pack inválido (id ausente).")
            return redirect("/packs/")

        # normalizar e sanitizar input
        normalized = unicodedata.normalize("NFKC", str(raw))
        sanitized = normalized.strip().strip("'\"")
        for z in ["\u200b", "\u200c", "\u200d", "\ufeff", "\u200e", "\u200f"]:
            sanitized = sanitized.replace(z, "")
        sanitized = sanitized.strip()

        # tentar converter pra UUID canônico
        uuid_obj = None
        try:
            uuid_obj = uuid.UUID(sanitized)
            sanitized = str(uuid_obj)
        except Exception:
            uuid_obj = None

        # tentativa direta pelo ORM
        pack = None
        if uuid_obj is not None:
            pack = Pack.objects.filter(pk=uuid_obj).first()
        if pack is None:
            pack = Pack.objects.filter(pk=sanitized).first()

        # fallback robusto: comparar str(ex) com sanitized e depois buscar com o UUID existente
        if pack is None:
            for ex in Pack.objects.values_list("id", flat=True)[:200]:
                try:
                    if str(ex) == sanitized:
                        pack = Pack.objects.filter(pk=ex).first()
                        if pack:
                            break
                except Exception:
                    continue

        if pack is None:
            messages.error(request, "Pack não encontrado. Recarregue a página ou verifique o template.")
            return redirect("/packs/")

        # lock do usuário
        user = SistemasUser.objects.select_for_update().get(pk=user.pk)
        if getattr(user, "coins", 0) < pack.price:
            messages.error(request, "Moedas insuficientes.")
            return redirect("/packs/")

        entries = list(PackEntry.objects.filter(pack=pack).select_related("player_field", "player_gk"))
        if not entries:
            messages.error(request, "Pack vazio.")
            return redirect("/packs/")

        # construir ponderação
        weighted = []
        tot = 0
        for e in entries:
            w = max(0, int(e.weight or 0))
            if w <= 0:
                continue
            tot += w
            weighted.append((e, tot))
        if tot == 0:
            messages.error(request, "Pack sem entradas ponderadas.")
            return redirect("/packs/")

        r = random.randint(1, tot)
        chosen = None
        for e, cum in weighted:
            if r <= cum:
                chosen = e
                break
        if chosen is None:
            messages.error(request, "Erro ao selecionar jogador.")
            return redirect("/packs/")

        if chosen.player_field_id:
            player_obj = chosen.player_field
            ct = ContentType.objects.get_for_model(JogadorCampo)
            p_type = "field"
        elif chosen.player_gk_id:
            player_obj = chosen.player_gk
            ct = ContentType.objects.get_for_model(JogadorGoleiro)
            p_type = "gk"
        else:
            messages.error(request, "Entrada inválida.")
            return redirect("/packs/")

        obj_id = str(player_obj.id)
        inv, created = InventoryItem.objects.get_or_create(
            user=user, content_type=ct, object_id=obj_id, defaults={"qty": 1}
        )
        if not created:
            inv.qty = inv.qty + 1
            inv.save()

        user.coins = user.coins - pack.price
        user.save()

        request.session["last_win"] = {
            "id": obj_id,
            "name": player_obj.name,
            "type": p_type,
            "photo_path": player_obj.photo_path,
            "overall": getattr(player_obj, "overall", 0),
            "pack_name": pack.name,
        }
        return redirect("/packs/#result")

    # GET: listar packs (sem revelar entries)
    packs_qs = Pack.objects.all().order_by("-created_at")
    packs = []
    for p in packs_qs:
        packs.append({
            "id": str(p.id),
            "name": p.name,
            "price": p.price,
            "description": p.description,
            "image_path": p.image_path,
        })

    last_win = request.session.pop("last_win", None)
    return render(request, "accounts/packs_list.html", {"packs": packs, "user": user, "last_win": last_win})