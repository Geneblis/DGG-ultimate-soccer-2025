# views.py (atualizado)
# ===== Standard Library =====
import random
import json
import uuid
import unicodedata
import logging
logger = logging.getLogger(__name__)

# ===== Django Core =====
from django.shortcuts import render, get_object_or_404, redirect
from django.db import transaction, connection
from django.db.models import Q
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
    InventoryItem, Pack, Team
)


def _static_path_for_club_logo(player):
    slug = slugify(player.club or "")
    candidate = f"players/{slug}/logo.png"
    return candidate

def _flag_url_for_country(country_code_or_name):
    if not country_code_or_name:
        return None
    cc = str(country_code_or_name).strip().lower()
    if len(cc) == 2 and cc.isalpha():
        return f"https://flagcdn.com/h40/{cc}.png"
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
    }
    code = MAP.get(cc)
    if code:
        return f"https://flagcdn.com/h40/{code}.png"
    return None

def _get_current_user(request):
    uid = request.session.get("user_id")
    if not uid:
        return None
    try:
        return SistemasUser.objects.get(pk=uid)
    except SistemasUser.DoesNotExist:
        return None


def _normalize_position(pos):
    """
    Normaliza várias formas de posição para as constantes do modelo JogadorCampo.
    Retorna uma das constantes JogadorCampo.POSITION_* ou None.
    """
    if not pos:
        return None
    p = str(pos).strip().lower()
    offs = {"offensivezone","offensive","off","ata","ataque","ata_zone","ataquezone","ataque_zone","offensive_zone"}
    neuts = {"neutralzone","neutral","mid","midfield","meio","medio","mid_zone","meiozone","neutral_zone"}
    defs = {"defensivezone","defensive","def","defesa","zdef","def_zone","defensive_zone"}

    # se já é a constante (em lowercase)
    if p == JogadorCampo.POSITION_OFF.lower():
        return JogadorCampo.POSITION_OFF
    if p == JogadorCampo.POSITION_NEU.lower():
        return JogadorCampo.POSITION_NEU
    if p == JogadorCampo.POSITION_DEF.lower():
        return JogadorCampo.POSITION_DEF

    if p in offs:
        return JogadorCampo.POSITION_OFF
    if p in neuts:
        return JogadorCampo.POSITION_NEU
    if p in defs:
        return JogadorCampo.POSITION_DEF

    # heurística simples por substring
    if "off" in p and "def" not in p:
        return JogadorCampo.POSITION_OFF
    if "def" in p:
        return JogadorCampo.POSITION_DEF
    if "mid" in p or "neu" in p or "meio" in p:
        return JogadorCampo.POSITION_NEU

    return None

def _infer_position_from_snapshot(snapshot):
    """
    Heurística simples para inferir posição se snapshot vier sem 'position'.
    Usa diferença entre ataque e defesa.
    """
    try:
        atk = int(snapshot.get("attack") or 0)
        df = int(snapshot.get("defense") or 0)
        if atk >= df + 5:
            return JogadorCampo.POSITION_OFF
        if df >= atk + 5:
            return JogadorCampo.POSITION_DEF
    except Exception:
        pass
    return JogadorCampo.POSITION_NEU

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

## TIME ##

# ===== Helpers internos =====

def _inv_item_match_by_pid(inv_item, pid):
    if not inv_item:
        return False
    try:
        if getattr(inv_item, "object_id", None) and str(inv_item.object_id) == str(pid):
            return True
    except Exception:
        pass
    try:
        pd = getattr(inv_item, "player_data", None)
        if isinstance(pd, dict) and str(pd.get("id")) == str(pid):
            return True
    except Exception:
        pass
    try:
        co = getattr(inv_item, "content_object", None)
        if co is not None:
            if getattr(co, "id", None) and str(co.id) == str(pid):
                return True
    except Exception:
        pass
    return False

def _inv_item_snapshot(inv_item):
    """Tenta retornar snapshot (dict) representando o jogador do InventoryItem."""
    try:
        pd = getattr(inv_item, "player_data", None)
        if isinstance(pd, dict) and pd:
            # garantir position canônica se for jogador de campo
            snap = dict(pd)
            if snap.get("type") == "field":
                pos = snap.get("position") or snap.get("pos")
                pos_norm = _normalize_position(pos)
                if not pos_norm:
                    pos_norm = _infer_position_from_snapshot(snap)
                snap["position"] = pos_norm
            return snap
    except Exception:
        pass

    try:
        co = getattr(inv_item, "content_object", None)
        if co:
            if isinstance(co, JogadorCampo):
                pos_norm = _normalize_position(getattr(co, "position", None)) or getattr(co, "position", None)
                return {
                    "id": str(co.id), "type": "field", "name": co.name, "club": co.club,
                    "country": co.country, "photo_path": co.photo_path, "overall": co.overall,
                    "attack": co.attack, "passing": co.passing, "defense": co.defense,
                    "speed": co.speed, "position": pos_norm,
                }
            else:
                return {
                    "id": str(co.id), "type": "gk", "name": co.name, "club": co.club,
                    "country": co.country, "photo_path": co.photo_path, "overall": co.overall,
                    "handling": co.handling, "positioning": co.positioning, "reflex": co.reflex,
                    "speed": co.speed,
                }
    except Exception:
        pass

    try:
        ct = getattr(inv_item, "content_type", None)
        oid = getattr(inv_item, "object_id", None)
        if ct and oid:
            model = ct.model_class()
            p = model.objects.filter(pk=oid).first()
            if p:
                if isinstance(p, JogadorCampo):
                    pos_norm = _normalize_position(getattr(p, "position", None)) or getattr(p, "position", None)
                    return {
                        "id": str(p.id), "type": "field", "name": p.name, "club": p.club,
                        "country": p.country, "photo_path": p.photo_path, "overall": p.overall,
                        "attack": p.attack, "passing": p.passing, "defense": p.defense,
                        "speed": p.speed, "position": pos_norm,
                    }
                else:
                    return {
                        "id": str(p.id), "type": "gk", "name": p.name, "club": p.club,
                        "country": p.country, "photo_path": p.photo_path, "overall": p.overall,
                        "handling": p.handling, "positioning": p.positioning, "reflex": p.reflex,
                        "speed": p.speed,
                    }
    except Exception:
        pass

    return None

# ----------------------
# Views
# ----------------------

@require_http_methods(["GET"])
def my_team_view(request):
    """
    Mostra 'My Team' com slots resolvidos e lista de jogadores elegíveis
    quando ?select_slot=<slot_key> é passado.
    """
    user = _get_current_user(request)
    if not user:
        return redirect("/login/")

    team, created = Team.objects.get_or_create(user=user)
    # garantir estrutura mínima
    try:
        team.ensure_structure()
    except Exception:
        s = team.slots or {}
        if "gk" not in s:
            s["gk"] = ""
        if "def" not in s:
            s["def"] = ["", "", "", ""]
        if "mid" not in s:
            s["mid"] = ["", "", ""]
        if "off" not in s:
            s["off"] = ["", "", ""]
        team.slots = s
        team.save(update_fields=["slots"])

    inv_rows = list(InventoryItem.objects.filter(user=user).select_related("content_type"))
    inventory_players = []
    inv_map = {}

    for it in inv_rows:
        snap = _inv_item_snapshot(it)
        if not snap:
            continue
        pid = str(snap.get("id") or it.object_id or "")
        snap_norm = dict(snap)
        snap_norm["id"] = pid
        # inferir tipo se não existir
        if "type" not in snap_norm:
            if any(k in snap_norm for k in ("handling", "reflex", "positioning")):
                snap_norm["type"] = "gk"
            else:
                snap_norm["type"] = "field"

        # normaliza posição para jogadores de campo
        if snap_norm.get("type") == "field":
            pos_curr = snap_norm.get("position")
            pos_norm = _normalize_position(pos_curr)
            if not pos_norm:
                pos_norm = _infer_position_from_snapshot(snap_norm)
            snap_norm["position"] = pos_norm

        snap_norm["qty"] = int(getattr(it, "qty", 1) or 1)
        inventory_players.append(snap_norm)
        inv_map[pid] = snap_norm

    # montar slots prontos
    slots = {"gk": None, "def": [], "mid": [], "off": []}

    def _resolve_slot_value(val):
        if not val:
            return ("", None)
        if isinstance(val, dict):
            pid = str(val.get("id") or "")
            snap = dict(val)
            snap["qty"] = inv_map.get(pid, {}).get("qty", 0)
            # garantir posição canônica pra snapshot guardado no time
            if snap.get("type") == "field":
                p = snap.get("position")
                snap["position"] = _normalize_position(p) or snap.get("position")
            return (pid, snap)
        pid = str(val)
        if pid in inv_map:
            return (pid, inv_map[pid])
        pobj_gk = JogadorGoleiro.objects.filter(pk=pid).first()
        if pobj_gk:
            return (pid, {
                "id": pid, "type": "gk", "name": pobj_gk.name, "club": pobj_gk.club,
                "country": pobj_gk.country, "photo_path": pobj_gk.photo_path, "overall": pobj_gk.overall,
                "handling": pobj_gk.handling, "positioning": pobj_gk.positioning, "reflex": pobj_gk.reflex,
                "speed": pobj_gk.speed, "qty": 0
            })
        pobj = JogadorCampo.objects.filter(pk=pid).first()
        if pobj:
            pos_norm = _normalize_position(getattr(pobj, "position", None)) or getattr(pobj, "position", None)
            return (pid, {
                "id": pid, "type": "field", "name": pobj.name, "club": pobj.club,
                "country": pobj.country, "photo_path": pobj.photo_path, "overall": pobj.overall,
                "attack": pobj.attack, "passing": pobj.passing, "defense": pobj.defense,
                "speed": pobj.speed, "position": pos_norm, "qty": 0
            })
        return (pid, None)

    raw_gk = (team.slots.get("gk") if getattr(team, "slots", None) else "") or ""
    pid, player_detail = _resolve_slot_value(raw_gk)
    slots["gk"] = {"key": "gk", "assigned": pid or "", "player": player_detail}

    def_list = (team.slots.get("def") if getattr(team, "slots", None) else []) or ["", "", "", ""]
    for i in range(4):
        v = def_list[i] if i < len(def_list) else ""
        pid, player_detail = _resolve_slot_value(v)
        slots["def"].append({"key": f"def_{i}", "assigned": pid or "", "player": player_detail})

    mid_list = (team.slots.get("mid") if getattr(team, "slots", None) else []) or ["", "", ""]
    for i in range(3):
        v = mid_list[i] if i < len(mid_list) else ""
        pid, player_detail = _resolve_slot_value(v)
        slots["mid"].append({"key": f"mid_{i}", "assigned": pid or "", "player": player_detail})

    off_list = (team.slots.get("off") if getattr(team, "slots", None) else []) or ["", "", ""]
    for i in range(3):
        v = off_list[i] if i < len(off_list) else ""
        pid, player_detail = _resolve_slot_value(v)
        slots["off"].append({"key": f"off_{i}", "assigned": pid or "", "player": player_detail})

    # eligíveis
    selected_slot = request.GET.get("select_slot")
    eligible_players = []
    if selected_slot:
        if selected_slot == "gk":
            eligible_players = [p for p in inventory_players if p.get("type") == "gk" and p.get("qty", 0) > 0]
        else:
            sec = selected_slot.split("_")[0]
            if sec == "def":
                eligible_players = [p for p in inventory_players if p.get("type") == "field" and p.get("position") == JogadorCampo.POSITION_DEF and p.get("qty", 0) > 0]
            elif sec == "mid":
                eligible_players = [p for p in inventory_players if p.get("type") == "field" and p.get("position") == JogadorCampo.POSITION_NEU and p.get("qty", 0) > 0]
            elif sec == "off":
                eligible_players = [p for p in inventory_players if p.get("type") == "field" and p.get("position") == JogadorCampo.POSITION_OFF and p.get("qty", 0) > 0]

    logger.debug("my_team_view: user=%s inventory_count=%d team_slots=%s selected_slot=%s eligible=%d",
                 user.username, len(inventory_players), team.slots, selected_slot, len(eligible_players))

    return render(request, "accounts/my_team.html", {
        "user": user,
        "team": {"name": f"{user.username}'s Team", "level": 1, "coins": user.coins},
        "team_obj": team,
        "inventory_players": inventory_players,
        "inv_map": inv_map,
        "slots": slots,
        "selected_slot": selected_slot,
        "eligible_players": eligible_players,
    })

@require_POST
@transaction.atomic
def set_team_slot_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("/login/")

    slot_key = request.POST.get("slot_key")
    player_id = request.POST.get("player_id")
    if not slot_key or not player_id:
        messages.error(request, "Slot ou jogador inválido.")
        return redirect("my_team")

    user = SistemasUser.objects.select_for_update().get(pk=user.pk)
    team, _ = Team.objects.get_or_create(user=user)
    try:
        team.ensure_structure()
    except Exception:
        if not getattr(team, "slots", None):
            team.slots = {"gk": "", "def": ["","","",""], "mid": ["","",""], "off": ["","",""]}
            team.save(update_fields=["slots"])

    inv_items = list(InventoryItem.objects.filter(user=user).select_related("content_type"))
    inv_new = None
    for it in inv_items:
        if _inv_item_match_by_pid(it, player_id):
            inv_new = it
            break

    if not inv_new:
        messages.error(request, "Você não possui esse jogador no inventário.")
        return redirect("my_team")

    snapshot = _inv_item_snapshot(inv_new)
    if not snapshot:
        messages.error(request, "Não foi possível obter os dados do jogador.")
        return redirect("my_team")

    p_type = snapshot.get("type") or ("gk" if any(k in snapshot for k in ("handling","reflex")) else "field")

    if slot_key == "gk":
        if p_type != "gk":
            messages.error(request, "Somente goleiros podem ser colocados neste slot.")
            return redirect("my_team")
    else:
        sec = slot_key.split("_")[0]
        if p_type != "field":
            messages.error(request, "Apenas jogadores de campo podem ser colocados neste slot.")
            return redirect("my_team")
        # normalizar posição antes da checagem
        pos_norm = _normalize_position(snapshot.get("position")) or snapshot.get("position")
        if sec == "def" and pos_norm != JogadorCampo.POSITION_DEF:
            messages.error(request, "Jogador não tem posição de defesa.")
            return redirect("my_team")
        if sec == "mid" and pos_norm != JogadorCampo.POSITION_NEU:
            messages.error(request, "Jogador não tem posição de meio-campo.")
            return redirect("my_team")
        if sec == "off" and pos_norm != JogadorCampo.POSITION_OFF:
            messages.error(request, "Jogador não tem posição de ataque.")
            return redirect("my_team")

    # recuperar valor antigo do slot
    old_val = ""
    if slot_key == "gk":
        old_val = team.slots.get("gk") if getattr(team, "slots", None) else ""
    else:
        sec, idx = slot_key.split("_"); idx = int(idx)
        old_list = (team.slots.get(sec) if getattr(team, "slots", None) else []) or []
        old_val = old_list[idx] if idx < len(old_list) else ""

    old_pid = ""
    if isinstance(old_val, dict):
        old_pid = str(old_val.get("id") or "")
    else:
        old_pid = str(old_val or "")

    new_pid = str(snapshot.get("id"))

    if old_pid and old_pid == new_pid:
        messages.info(request, "Jogador já está neste slot.")
        return redirect("my_team")

    # devolver qty do antigo (se houver)
    if old_pid:
        found_old = None
        for it in inv_items:
            if _inv_item_match_by_pid(it, old_pid):
                found_old = it
                break
        if found_old:
            found_old.qty = (found_old.qty or 0) + 1
            found_old.save()
        else:
            if isinstance(old_val, dict):
                try:
                    ct = ContentType.objects.get_for_model(JogadorCampo) if old_val.get("type") == "field" else ContentType.objects.get_for_model(JogadorGoleiro)
                    InventoryItem.objects.create(user=user, content_type=ct, object_id=str(old_val.get("id") or ""), player_data=old_val, qty=1)
                except Exception:
                    try:
                        InventoryItem.objects.create(user=user, content_type=None, object_id=str(old_val.get("id") or ""), player_data=old_val, qty=1)
                    except Exception:
                        pass

    # decrementar qty do novo
    inv_new.qty = (inv_new.qty or 1) - 1
    if inv_new.qty <= 0:
        inv_new.delete()
    else:
        inv_new.save()

    # salvar no team (usando snapshot para persistir objeto no slots)
    try:
        if hasattr(team, "set_slot"):
            team.set_slot(slot_key, snapshot)
        else:
            s = team.slots or {"gk": "", "def": ["","","",""], "mid": ["","",""], "off": ["","",""]}
            if slot_key == "gk":
                s["gk"] = str(new_pid)
            else:
                sec, idx = slot_key.split("_"); idx = int(idx)
                while len(s.get(sec, [])) <= idx:
                    s[sec].append("")
                s[sec][idx] = str(new_pid)
            team.slots = s
            team.save(update_fields=["slots", "updated_at"])
    except Exception as e:
        messages.error(request, f"Erro ao salvar o time: {e}")
        return redirect("my_team")

    messages.success(request, "Jogador colocado no slot.")
    return redirect("my_team")



@require_POST
@transaction.atomic
def clear_team_slot_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("/login/")

    slot_key = request.POST.get("slot_key")
    if not slot_key:
        messages.error(request, "Slot inválido.")
        return redirect("my_team")

    user = SistemasUser.objects.select_for_update().get(pk=user.pk)
    team, _ = Team.objects.get_or_create(user=user)
    try:
        team.ensure_structure()
    except Exception:
        if not getattr(team, "slots", None):
            team.slots = {"gk": "", "def": ["","","",""], "mid": ["","",""], "off": ["","",""]}
            team.save(update_fields=["slots"])

    old_val = ""
    if slot_key == "gk":
        old_val = team.slots.get("gk")
    else:
        sec, idx = slot_key.split("_"); idx = int(idx)
        old_list = team.slots.get(sec) or []
        old_val = old_list[idx] if idx < len(old_list) else ""

    if not old_val:
        messages.info(request, "Slot já está vazio.")
        return redirect("my_team")

    inv_items = list(InventoryItem.objects.filter(user=user).select_related("content_type"))
    old_pid = ""
    old_snapshot = None
    if isinstance(old_val, dict):
        old_snapshot = old_val
        old_pid = str(old_snapshot.get("id") or "")
    else:
        old_pid = str(old_val or "")

    found_old = None
    for it in inv_items:
        if _inv_item_match_by_pid(it, old_pid):
            found_old = it
            break

    if found_old:
        found_old.qty = (found_old.qty or 0) + 1
        found_old.save()
    else:
        try:
            if old_snapshot:
                ct = ContentType.objects.get_for_model(JogadorCampo) if old_snapshot.get("type") == "field" else ContentType.objects.get_for_model(JogadorGoleiro)
                InventoryItem.objects.create(user=user, content_type=ct, object_id=str(old_snapshot.get("id") or ""), player_data=old_snapshot, qty=1)
            else:
                InventoryItem.objects.create(user=user, content_type=None, object_id=str(old_pid), player_data=None, qty=1)
        except Exception:
            pass

    try:
        if hasattr(team, "clear_slot"):
            team.clear_slot(slot_key)
        else:
            s = team.slots or {"gk": "", "def": ["","","",""], "mid": ["","",""], "off": ["","",""]}
            if slot_key == "gk":
                s["gk"] = ""
            else:
                sec, idx = slot_key.split("_"); idx = int(idx)
                if s.get(sec) and idx < len(s[sec]):
                    s[sec][idx] = ""
            team.slots = s
            team.save(update_fields=["slots", "updated_at"])
    except Exception as e:
        messages.error(request, f"Erro ao limpar slot: {e}")
        return redirect("my_team")

    messages.success(request, "Slot liberado e inventário atualizado.")
    return redirect("my_team")

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
    Compra de pack via POST /packs/<pack_id>/buy/
    Agora armazena snapshot (player_data) no InventoryItem para evitar problemas ao exibir inventário.
    """
    user = _get_current_user(request)
    if not user:
        return redirect("/login/")

    try:
        print("DBGBUY: attempt buy, raw pack_id:", repr(pack_id), "type:", type(pack_id))
    except Exception:
        pass

    pid_str = str(pack_id)

    pack = Pack.objects.filter(id=pid_str).first()
    if not pack:
        pid_nodash = pid_str.replace("-", "")
        pack = Pack.objects.filter(id__in=[pid_str, pid_nodash]).first()
    if not pack:
        for p in Pack.objects.all():
            try:
                if str(p.id) == pid_str or str(p.id).replace("-", "") == pid_str.replace("-", ""):
                    pack = p
                    break
            except Exception:
                continue

    if not pack:
        sample = list(Pack.objects.values_list("id", flat=True)[:20])
        print("DBGBUY: pack NOT FOUND. pid_str:", pid_str)
        print("DBGBUY: sample existing pack ids (first 20):", sample)
        messages.error(request, "Pack não encontrado (buy endpoint).")
        return redirect("/packs/")

    print("DBGBUY: using pack:", str(pack.id), pack.name)

    user = SistemasUser.objects.select_for_update().get(pk=user.pk)
    if getattr(user, "coins", 0) < pack.price:
        messages.error(request, "Moedas insuficientes.")
        print("DBGBUY: insufficient coins:", user.coins, "price:", pack.price)
        return redirect("/packs/")

    try:
        chosen = pack.pick_random_entry()
    except Exception as e:
        print("DBGBUY: pick_random_entry error:", e)
        chosen = None

    if not chosen:
        messages.error(request, "Pack vazio ou sem entradas ponderadas.")
        print("DBGBUY: no chosen entry.")
        return redirect("/packs/")

    chosen_id = str(chosen.get("id"))
    chosen_type = chosen.get("type")
    print("DBGBUY: chosen entry:", chosen)

    if chosen_type == "field":
        player_model = JogadorCampo
        p_type = "field"
    elif chosen_type == "gk":
        player_model = JogadorGoleiro
        p_type = "gk"
    else:
        messages.error(request, "Entrada inválida no pack.")
        print("DBGBUY: invalid chosen_type:", chosen_type)
        return redirect("/packs/")

    # buscar player no DB (preferência)
    player_obj = player_model.objects.filter(id=chosen_id).first()
    if not player_obj:
        for ex in player_model.objects.values_list("id", flat=True)[:2000]:
            try:
                if str(ex) == chosen_id or str(ex).replace("-", "") == chosen_id.replace("-", ""):
                    player_obj = player_model.objects.filter(pk=ex).first()
                    if player_obj:
                        print("DBGBUY: matched player by fallback id:", ex)
                        break
            except Exception:
                continue

    # montar snapshot (prefer dados do DB, senão a entry JSON)
    snapshot = {}
    if player_obj:
        if isinstance(player_obj, JogadorCampo):
            snapshot = {
                "id": str(player_obj.id), "type": "field", "name": player_obj.name, "club": player_obj.club,
                "country": player_obj.country, "photo_path": player_obj.photo_path, "overall": player_obj.overall,
                "attack": player_obj.attack, "passing": player_obj.passing, "defense": player_obj.defense,
                "speed": player_obj.speed, "position": player_obj.position,
            }
        else:
            snapshot = {
                "id": str(player_obj.id), "type": "gk", "name": player_obj.name, "club": player_obj.club,
                "country": player_obj.country, "photo_path": player_obj.photo_path, "overall": player_obj.overall,
                "handling": player_obj.handling, "positioning": player_obj.positioning,
                "reflex": player_obj.reflex, "speed": player_obj.speed,
            }
    else:
        # use chosen JSON (entry) as fallback
        snapshot = dict(chosen)
        snapshot["id"] = chosen_id
        snapshot.setdefault("type", chosen_type)

    # localizar InventoryItem existente (tolerante)
    ct = ContentType.objects.get_for_model(player_model)
    inv = InventoryItem.objects.filter(user=user).filter(
        Q(content_type=ct, object_id=chosen_id) | Q(player_data__id=chosen_id)
    ).first()

    if inv:
        inv.qty = (inv.qty or 0) + 1
        # garantir que snapshot esteja salvo no registro
        if not inv.player_data or not isinstance(inv.player_data, dict):
            inv.player_data = snapshot
        inv.content_type = ct
        inv.object_id = chosen_id
        inv.save()
    else:
        # criar com snapshot completo
        InventoryItem.objects.create(
            user=user,
            content_type=ct,
            object_id=chosen_id,
            player_data=snapshot,
            qty=1
        )

    # debitar coins
    user.coins -= pack.price
    user.save()
    print("DBGBUY: purchase completed. new coins:", user.coins)

    photo_path = snapshot.get("photo_path", "")
    player_name = snapshot.get("name", chosen_id)
    overall = snapshot.get("overall", "")

    request.session["last_win"] = {
        "id": chosen_id,
        "name": player_name or chosen_id,
        "type": p_type,
        "photo_path": photo_path or "",
        "overall": overall,
        "pack_name": pack.name,
    }

    return redirect("/packs/#result")
