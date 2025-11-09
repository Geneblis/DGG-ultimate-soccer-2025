# ===== Standard Library =====
import random
import json
import uuid
import unicodedata

# ===== Django Core =====
from django.shortcuts import render, get_object_or_404, redirect
from django.db import transaction, connection
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib.auth.hashers import make_password, check_password
from django.utils.text import slugify

# ===== Django ContentTypes =====
from django.contrib.contenttypes.models import ContentType

# ===== Local Models =====
from .models import (
    SistemasUser, JogadorCampo, JogadorGoleiro,
    InventoryItem, Pack
)

import logging

logger = logging.getLogger(__name__)


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

@require_http_methods(["GET"])
def packs_list_view(request):
    """
    Lista packs (GET).
    Se ?open=<pack_id> for passado, popula os jogadores desse pack (name + photo_path)
    buscando do DB apenas os IDs presentes no JSON do Pack.
    """
    user = _get_current_user(request)
    if not user:
        return redirect("/login/")

    open_pack_id = request.GET.get("open")
    packs_qs = Pack.objects.all().order_by("-created_at")
    packs = []

    def _ensure_list(v):
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return []
        return []

    for p in packs_qs:
        pack_dict = {
            "id": str(p.id),
            "name": p.name,
            "price": p.price,
            "description": p.description,
            "image_path": p.image_path,
            "field_players": [],
            "gk_players": [],
        }

        if open_pack_id and str(p.id) == str(open_pack_id):
            raw_field = getattr(p, "field_players", None)
            raw_gk = getattr(p, "gk_players", None)
            field_entries = _ensure_list(raw_field)
            gk_entries = _ensure_list(raw_gk)

            field_ids = [str(e.get("id")) for e in field_entries if e.get("id")]
            gk_ids = [str(e.get("id")) for e in gk_entries if e.get("id")]

            field_map = {}
            if field_ids:
                qs_field = JogadorCampo.objects.filter(id__in=field_ids).values("id", "name", "photo_path")
                for r in qs_field:
                    field_map[str(r["id"])] = {"id": str(r["id"]), "name": r["name"], "photo_path": r["photo_path"]}

            gk_map = {}
            if gk_ids:
                qs_gk = JogadorGoleiro.objects.filter(id__in=gk_ids).values("id", "name", "photo_path")
                for r in qs_gk:
                    gk_map[str(r["id"])] = {"id": str(r["id"]), "name": r["name"], "photo_path": r["photo_path"]}

            final_field = []
            for e in field_entries:
                pid = str(e.get("id", ""))
                src = field_map.get(pid)
                if src:
                    final_field.append({"id": pid, "name": src.get("name"), "photo_path": src.get("photo_path")})
                else:
                    final_field.append({"id": pid, "name": e.get("name") or pid, "photo_path": e.get("photo_path") or ""})

            final_gk = []
            for e in gk_entries:
                pid = str(e.get("id", ""))
                src = gk_map.get(pid)
                if src:
                    final_gk.append({"id": pid, "name": src.get("name"), "photo_path": src.get("photo_path")})
                else:
                    final_gk.append({"id": pid, "name": e.get("name") or pid, "photo_path": e.get("photo_path") or ""})

            pack_dict["field_players"] = final_field
            pack_dict["gk_players"] = final_gk

        packs.append(pack_dict)

    last_win = request.session.pop("last_win", None)
    return render(request, "accounts/packs_list.html", {"packs": packs, "user": user, "last_win": last_win})

@require_POST
@transaction.atomic
def buy_pack_view(request, pack_id):
    """
    Compra de pack via POST em /packs/<pack_id>/buy/
    - seleciona entry aleatória a partir do JSON do Pack (pick_random_entry)
    - encontra o jogador no DB pelo id e tipo (field|gk)
    - cria/incrementa InventoryItem (generic FK)
    - debita coins do usuário
    - salva last_win na session e redirect para /packs/#result
    """
    user = _get_current_user(request)
    if not user:
        return redirect("/login/")

    # debug: ver o pack_id recebido
    try:
        logger.debug("DBGBUY: received pack_id repr: %r type: %s", pack_id, type(pack_id))
        print("DBGBUY: received pack_id repr:", repr(pack_id), "type:", type(pack_id))
    except Exception:
        pass

    # tentar carregar pack diretamente (aceita uuid ou str)
    pack = None
    try:
        pack = get_object_or_404(Pack, pk=pack_id)
    except Exception as exc:
        logger.debug("DBGBUY: get_object_or_404 failed: %s", exc)
        print("DBGBUY: get_object_or_404 failed:", exc)
        # fallback: comparar string dos ids (útil se houver diferença de tipo)
        for ex in Pack.objects.values_list("id", flat=True)[:500]:
            try:
                if str(ex) == str(pack_id):
                    pack = Pack.objects.filter(pk=ex).first()
                    if pack:
                        logger.debug("DBGBUY: fallback matched pack id: %r", ex)
                        print("DBGBUY: fallback matched pack id:", ex)
                        break
            except Exception:
                continue

    if pack is None:
        messages.error(request, "Pack não encontrado (buy endpoint).")
        return redirect("/packs/")

    # lock do usuário para evitar double-spend
    user = SistemasUser.objects.select_for_update().get(pk=user.pk)

    if getattr(user, "coins", 0) < pack.price:
        messages.error(request, "Moedas insuficientes.")
        return redirect("/packs/")

    # sorteio ponderado a partir do JSON do pack
    try:
        chosen = pack.pick_random_entry()
    except Exception as e:
        logger.exception("DBGBUY: error picking entry: %s", e)
        chosen = None

    if not chosen:
        messages.error(request, "Pack vazio ou sem entradas ponderadas.")
        return redirect("/packs/")

    # chosen: dict com "id", "type" ("field" | "gk"), possivelmente outros campos
    player_id = str(chosen.get("id"))
    player_type = chosen.get("type")

    if player_type == "field":
        model = JogadorCampo
        p_type = "field"
    elif player_type == "gk":
        model = JogadorGoleiro
        p_type = "gk"
    else:
        messages.error(request, "Entrada inválida no pack.")
        return redirect("/packs/")

    # buscar jogador atual no DB (preferível aos dados embutidos)
    player_obj = model.objects.filter(pk=player_id).first()
    # se não existir no DB, ainda aceitamos a entry (pode ter sido migrada como snapshot)
    if player_obj is None:
        # tenta encontrar por string id comparando com os registros (fallback)
        for ex in model.objects.values_list("id", flat=True)[:1000]:
            if str(ex) == player_id:
                player_obj = model.objects.filter(pk=ex).first()
                break

    # criar/incrementar InventoryItem (usa ContentType)
    ct = ContentType.objects.get_for_model(model)
    inv, created = InventoryItem.objects.get_or_create(
        user=user,
        content_type=ct,
        object_id=player_id,
        defaults={"qty": 1}
    )
    if not created:
        inv.qty = inv.qty + 1
        inv.save()

    # debitar coins e salvar
    user.coins = user.coins - pack.price
    user.save()

    # preparar dados para modal (prefere dados atuais do DB, senão pega do chosen)
    photo_path = chosen.get("photo_path") or (getattr(player_obj, "photo_path", None) if player_obj else "")
    player_name = chosen.get("name") or (getattr(player_obj, "name", None) if player_obj else player_id)
    overall = chosen.get("overall") or (getattr(player_obj, "overall", "") if player_obj else "")

    request.session["last_win"] = {
        "id": player_id,
        "name": player_name or player_id,
        "type": p_type,
        "photo_path": photo_path or "",
        "overall": overall,
        "pack_name": pack.name,
    }

    return redirect("/packs/#result")