# ===== Standard Library =====
import random
import json
import uuid
import logging
logger = logging.getLogger(__name__)

# ===== Django Core =====
from django.shortcuts import render, get_object_or_404, redirect
from django.db import transaction
from django.db.models import Q
from django.contrib import messages
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib.auth.hashers import make_password, check_password
from django.utils.text import slugify

# ===== Django ContentTypes =====
from django.contrib.contenttypes.models import ContentType

# ===== Local Models =====
from .models import (
    SistemasUser, JogadorCampo, JogadorGoleiro,
    InventoryItem, Pack, Team, AITeam, Match
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
        "venezuela": "ve",
        "denmark": "dk",
        "ecuador": "ec",
        "italy": "it",
        "netherlands": "nl",
        "brazil": "br",
        "argentina": "ar",
        "uruguay": "uy",
        "chile": "cl",
        "portugal": "pt",
        "spain": "es",
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

    # tipo do jogador
    p_type = snapshot.get("type")

    # validação por slot
    if slot_key == "gk":
        if p_type != "gk":
            messages.error(request, "Somente goleiros podem ser colocados neste slot.")
            return redirect("my_team")
    else:
        sec = slot_key.split("_")[0]

        if p_type != "field":
            messages.error(request, "Apenas jogadores de linha podem ocupar este slot.")
            return redirect("my_team")

        pos_norm = _normalize_position(snapshot.get("position"))
        if sec == "def" and pos_norm != JogadorCampo.POSITION_DEF:
            messages.error(request, "Jogador não é defensor.")
            return redirect("my_team")
        if sec == "mid" and pos_norm != JogadorCampo.POSITION_NEU:
            messages.error(request, "Jogador não é meio-campista.")
            return redirect("my_team")
        if sec == "off" and pos_norm != JogadorCampo.POSITION_OFF:
            messages.error(request, "Jogador não é atacante.")
            return redirect("my_team")

    # ------------------------------------------
    # --- duplicate-name check (NOVO)
    # ------------------------------------------
    try:
        new_name = (snapshot.get("name") or "").strip().lower()
        existing_names = set()

        raw_slots = team.slots or {}

        # gk
        gk = raw_slots.get("gk")
        if gk and not (slot_key == "gk"):  # não checar o slot que está sendo trocado
            if isinstance(gk, dict):
                nm = gk.get("name")
            else:
                pobj = JogadorGoleiro.objects.filter(pk=str(gk)).first()
                nm = pobj.name if pobj else None
            if nm:
                existing_names.add(nm.strip().lower())

        # def/mid/off
        for zone in ("def", "mid", "off"):
            zone_list = raw_slots.get(zone) or []
            for i, z in enumerate(zone_list):
                # pular o slot atual
                if zone + "_" + str(i) == slot_key:
                    continue
                if not z:
                    continue
                if isinstance(z, dict):
                    nm = z.get("name")
                else:
                    pobj = JogadorCampo.objects.filter(pk=str(z)).first()
                    nm = pobj.name if pobj else None
                if nm:
                    existing_names.add(nm.strip().lower())

        if new_name in existing_names:
            messages.error(request, "Já existe este jogador no time!")
            return redirect("my_team")
    except Exception:
        pass
    # ------------------------------------------

    # recuperar valor antigo do slot
    old_val = ""
    if slot_key == "gk":
        old_val = team.slots.get("gk")
    else:
        sec, idx = slot_key.split("_"); idx = int(idx)
        old_lst = team.slots.get(sec) or []
        old_val = old_lst[idx] if idx < len(old_lst) else ""

    # devolver jogador antigo ao inventário
    old_pid = ""
    if isinstance(old_val, dict):
        old_pid = str(old_val.get("id"))
    else:
        old_pid = str(old_val)

    if old_pid:
        old_item = None
        for it in inv_items:
            if _inv_item_match_by_pid(it, old_pid):
                old_item = it
                break
        if old_item:
            old_item.qty += 1
            old_item.save()

    # remover do inventário
    inv_new.qty -= 1
    if inv_new.qty <= 0:
        inv_new.delete()
    else:
        inv_new.save()

    # salvar novo jogador no time
    team.set_slot(slot_key, snapshot)

    messages.success(request, "Jogador colocado no slot!")
    return redirect("my_team")


# ---------- NOVA VIEW: vender item do inventário ----------
@require_POST
@transaction.atomic
def sell_inventory_item_view(request):
    """
    Vende uma carta do inventário do usuário (player_id).
    - Procura um InventoryItem do usuário que corresponda ao player_id.
    - Credita 100 moedas ao usuário (fixo).
    - Decrementa qty ou deleta o InventoryItem.
    """
    user = _get_current_user(request)
    if not user:
        return redirect("/login/")

    player_id = request.POST.get("player_id")
    if not player_id:
        messages.error(request, "Jogador inválido para venda.")
        return redirect("my_team")

    # lock user and work inside transaction
    try:
        user_locked = SistemasUser.objects.select_for_update().get(pk=user.pk)
    except SistemasUser.DoesNotExist:
        return redirect("my_team")

    # localizar InventoryItem correspondente (tolerante)
    inv_items = list(InventoryItem.objects.filter(user=user_locked).select_related("content_type"))
    found_item = None
    for it in inv_items:
        if _inv_item_match_by_pid(it, player_id):
            found_item = it
            break

    if not found_item:
        messages.error(request, "Carta não encontrada no inventário.")
        return redirect("my_team")

    SALE_PRICE = 100  # preço fixo por sua solicitação

    # creditar moedas
    user_locked.coins = (user_locked.coins or 0) + SALE_PRICE
    user_locked.save(update_fields=["coins"])

    # decrementar ou deletar InventoryItem
    try:
        current_qty = int(getattr(found_item, "qty", 1) or 1)
        if current_qty > 1:
            found_item.qty = current_qty - 1
            found_item.save(update_fields=["qty"])
        else:
            # qty == 1 -> remove registro
            found_item.delete()
    except Exception:
        # fallback: tenta deletar
        try:
            found_item.delete()
        except Exception:
            logger.exception("Erro ao remover InventoryItem durante venda (ignorado).")

    messages.success(request, f"Carta vendida por {SALE_PRICE} moedas.")
    return redirect("my_team")
# ---------- fim da nova view ----------

@require_POST
@transaction.atomic
def clear_team_slot_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("/login/")

    slot_key = request.POST.get("slot_key")
    if not slot_key:
        #messages.error(request, "Slot inválido.")
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
        #messages.info(request, "Slot já está vazio.")
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
        #messages.error(request, f"Erro ao limpar slot: {e}")
        return redirect("my_team")

    #messages.success(request, "Slot liberado e inventário atualizado.")
    return redirect("my_team")

def store_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    return render(request, "accounts/store.html", {"user": user})

def jogos_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    return render(request, "accounts/matches.html", {"user": user,})

def support_view(request):
    user = _get_current_user(request)
    if not user:
        return redirect("login")
    return render(request, "accounts/support.html", {"user": user})

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

#Modo de jogo random

def _sample_random_players_for_ai():
    """
    Retorna slots para AI: dict com 'gk', 'def'(list4), 'mid'(list3), 'off'(list3).
    Garante que não haja jogadores com o mesmo nome (checagem por nome em lowercase).
    Se não houver jogadores distintos suficientes para preencher todas as posições,
    lança RuntimeError.
    """
    # buscar pools
    field_players = list(JogadorCampo.objects.all())
    goalkeepers = list(JogadorGoleiro.objects.all())

    if not goalkeepers:
        raise RuntimeError("Não há goleiros no banco de dados para gerar o time AI.")
    if len(field_players) < 3:
        raise RuntimeError("Não há jogadores de campo suficientes no banco para gerar o time AI.")

    random.shuffle(goalkeepers)
    random.shuffle(field_players)

    # preparar pools por posição
    defenders_pool = [p for p in field_players if p.position == JogadorCampo.POSITION_DEF]
    mids_pool = [p for p in field_players if p.position == JogadorCampo.POSITION_NEU]
    offs_pool = [p for p in field_players if p.position == JogadorCampo.POSITION_OFF]

    # helper para escolher N jogadores de uma pool garantindo nomes únicos (lowercase)
    def _take_unique(pool, needed, chosen_names, chosen_ids):
        chosen = []
        ppool = list(pool)
        random.shuffle(ppool)
        for p in ppool:
            if len(chosen) >= needed:
                break
            name_norm = (p.name or "").strip().lower()
            if not name_norm:
                continue
            if name_norm in chosen_names:
                continue
            if str(p.id) in chosen_ids:
                continue
            chosen.append(p)
            chosen_names.add(name_norm)
            chosen_ids.add(str(p.id))
        return chosen

    chosen_names = set()
    chosen_ids = set()

    # escolher goleiro (tentar garantir nome único)
    gk_obj = None
    for g in goalkeepers:
        name_norm = (g.name or "").strip().lower()
        if name_norm and name_norm not in chosen_names:
            gk_obj = g
            chosen_names.add(name_norm)
            chosen_ids.add(str(g.id))
            break
    if not gk_obj:
        # fallback se todos os goleiros tiverem nomes duplicados (muito raro)
        gk_obj = goalkeepers[0]
        chosen_names.add((gk_obj.name or "").strip().lower())
        chosen_ids.add(str(gk_obj.id))

    # tentar escolher defenders, mids e offs garantindo nomes únicos
    def_list = _take_unique(defenders_pool, 4, chosen_names, chosen_ids)
    mid_list = _take_unique(mids_pool, 3, chosen_names, chosen_ids)
    off_list = _take_unique(offs_pool, 3, chosen_names, chosen_ids)

    # Se alguma posição não foi completamente preenchida, tentar preencher a partir de field_players
    def _fill_from_field(needed, current_list):
        if len(current_list) >= needed:
            return current_list
        extras = list(field_players)
        random.shuffle(extras)
        for p in extras:
            if len(current_list) >= needed:
                break
            pid = str(p.id)
            name_norm = (p.name or "").strip().lower()
            if not name_norm:
                continue
            if name_norm in chosen_names:
                continue
            if pid in chosen_ids:
                continue
            current_list.append(p)
            chosen_names.add(name_norm)
            chosen_ids.add(pid)
        return current_list

    def_list = _fill_from_field(4, def_list)
    mid_list = _fill_from_field(3, mid_list)
    off_list = _fill_from_field(3, off_list)

    # se ainda faltar itens, significa que não há jogadores distintos suficientes
    if len(def_list) < 4 or len(mid_list) < 3 or len(off_list) < 3:
        raise RuntimeError("Não há jogadores distintos suficientes no banco para gerar um time AI sem repetições por nome.")

    # construir snapshots (mesma forma anterior)
    def snap_from_field(p):
        return {
            "id": str(p.id),
            "type": "field",
            "name": p.name,
            "club": p.club,
            "country": p.country,
            "photo_path": p.photo_path,
            "overall": p.overall,
            "attack": p.attack,
            "passing": p.passing,
            "defense": p.defense,
            "speed": p.speed,
            "position": p.position,
        }

    def snap_from_gk(g):
        return {
            "id": str(g.id),
            "type": "gk",
            "name": g.name,
            "club": g.club,
            "country": g.country,
            "photo_path": g.photo_path,
            "overall": g.overall,
            "handling": g.handling,
            "positioning": g.positioning,
            "reflex": g.reflex,
            "speed": g.speed,
        }

    ai_slots = {
        "gk": snap_from_gk(gk_obj),
        "def": [snap_from_field(p) for p in def_list],
        "mid": [snap_from_field(p) for p in mid_list],
        "off": [snap_from_field(p) for p in off_list],
    }
    return ai_slots

#Modo de jogo autentico

def _sample_authentic_players_for_ai(club_name):
    """
    Gera um time AI composto APENAS por jogadores cujo campo 'club' bate exatamente (case-insensitive)
    com `club_name`. Retorna dict com slots 'gk','def','mid','off' contendo snapshots.
    Se não houver jogadores suficientes (1 GK + 10 field players com posições adequadas),
    retorna None para sinalizar falha.
    """
    if not club_name:
        return None
    club_query = str(club_name).strip()
    if not club_query:
        return None

    # buscar jogadores EXATOS (case-insensitive)
    gk_qs = list(JogadorGoleiro.objects.filter(club__iexact=club_query))
    field_qs = list(JogadorCampo.objects.filter(club__iexact=club_query))

    # precisamos de ao menos 1 goleiro e 10 jogadores de campo
    if not gk_qs or len(field_qs) < 10:
        return None

    # separar por posição dentro do mesmo clube
    defenders_pool = [p for p in field_qs if p.position == JogadorCampo.POSITION_DEF]
    mids_pool = [p for p in field_qs if p.position == JogadorCampo.POSITION_NEU]
    offs_pool = [p for p in field_qs if p.position == JogadorCampo.POSITION_OFF]

    # se houver pools suficientes conforme posição, vamos usá-las.
    # caso alguma pool seja menor que o necessário, tentamos preencher a partir de field_qs sem repetir.
    def pick_unique_from_pool(pool, needed, taken_ids):
        chosen = []
        random.shuffle(pool)
        for p in pool:
            if len(chosen) >= needed:
                break
            pid = str(p.id)
            if pid in taken_ids:
                continue
            chosen.append(p)
            taken_ids.add(pid)
        return chosen

    taken_ids = set()
    random.shuffle(gk_qs)
    gk_obj = gk_qs[0]
    taken_ids.add(str(gk_obj.id))

    def_list = pick_unique_from_pool(defenders_pool, 4, taken_ids)
    mid_list = pick_unique_from_pool(mids_pool, 3, taken_ids)
    off_list = pick_unique_from_pool(offs_pool, 3, taken_ids)

    # preencher a partir de todos os field_qs (mesmo clube) se alguma posição ficou faltando
    def fill_from_all(current_list, needed):
        if len(current_list) >= needed:
            return current_list
        candidates = [p for p in field_qs if str(p.id) not in taken_ids]
        random.shuffle(candidates)
        for p in candidates:
            if len(current_list) >= needed:
                break
            current_list.append(p)
            taken_ids.add(str(p.id))
        return current_list

    def_list = fill_from_all(def_list, 4)
    mid_list = fill_from_all(mid_list, 3)
    off_list = fill_from_all(off_list, 3)

    # após tentativas, se ainda faltar jogadores (por posições) -> falha (None)
    if len(def_list) < 4 or len(mid_list) < 3 or len(off_list) < 3:
        return None

    # snapshots (simples)
    def snap_from_field(p):
        return {
            "id": str(p.id),
            "type": "field",
            "name": p.name,
            "club": p.club,
            "country": p.country,
            "photo_path": p.photo_path,
            "overall": p.overall,
            "attack": p.attack,
            "passing": p.passing,
            "defense": p.defense,
            "speed": p.speed,
            "position": p.position,
        }
    def snap_from_gk(g):
        return {
            "id": str(g.id),
            "type": "gk",
            "name": g.name,
            "club": g.club,
            "country": g.country,
            "photo_path": g.photo_path,
            "overall": g.overall,
            "handling": g.handling,
            "positioning": g.positioning,
            "reflex": g.reflex,
            "speed": g.speed,
        }

    ai_slots = {
        "gk": snap_from_gk(gk_obj),
        "def": [snap_from_field(p) for p in def_list[:4]],
        "mid": [snap_from_field(p) for p in mid_list[:3]],
        "off": [snap_from_field(p) for p in off_list[:3]],
    }
    return ai_slots

def _pick_random_club_with_enough_players(min_field_players=10, min_goalkeepers=1):
    """
    Retorna o nome (string) de um clube aleatório do DB que possua ao menos
    `min_goalkeepers` goleiros e `min_field_players` jogadores de campo.
    Retorna None se não houver clube suficiente.
    """
    # coletar valores brutos
    field_clubs = JogadorCampo.objects.values_list("club", flat=True)
    gk_clubs = JogadorGoleiro.objects.values_list("club", flat=True)

    counts_field = {}
    counts_gk = {}
    # mapa para retornar um nome representativo com case original
    representative_name = {}

    for raw in field_clubs:
        if not raw:
            continue
        key = str(raw).strip().lower()
        counts_field[key] = counts_field.get(key, 0) + 1
        if key not in representative_name:
            representative_name[key] = str(raw).strip()

    for raw in gk_clubs:
        if not raw:
            continue
        key = str(raw).strip().lower()
        counts_gk[key] = counts_gk.get(key, 0) + 1
        if key not in representative_name:
            representative_name[key] = str(raw).strip()

    # encontrar candidatos que satisfaçam os requisitos
    candidates = []
    for key, field_count in counts_field.items():
        gk_count = counts_gk.get(key, 0)
        if field_count >= min_field_players and gk_count >= min_goalkeepers:
            candidates.append(representative_name.get(key, key))

    if not candidates:
        return None

    random.shuffle(candidates)
    return candidates[0]

@require_POST
@transaction.atomic
def start_authentic_match_view(request):
    """
    Inicia uma partida 'Authentic Teams' escolhendo ALEATÓRIO um clube do DB
    que tenha pelo menos 1 GK e 10 jogadores de campo. O AI team será composto
    exclusivamente por jogadores desse clube.
    """
    user = _get_current_user(request)
    if not user:
        return redirect("/login/")

    # garantir time do usuário
    team_obj, _ = Team.objects.get_or_create(user=user)
    try:
        team_obj.ensure_structure()
    except Exception:
        pass

    # montar snapshot do time do usuário (igual aos outros modos, usado só como referência)
    def _slot_to_snapshot(value):
        if not value:
            return ""
        if isinstance(value, dict):
            if value.get("type") == "field":
                value["position"] = _normalize_position(value.get("position")) or value.get("position")
            return value
        pid = str(value)
        inv = InventoryItem.objects.filter(user=user).filter(Q(object_id=pid) | Q(player_data__id=pid)).first()
        if inv:
            snap = _inv_item_snapshot(inv)
            if snap and snap.get("type") == "field":
                snap["position"] = _normalize_position(snap.get("position")) or snap.get("position")
            return snap or ""
        g = JogadorGoleiro.objects.filter(pk=pid).first()
        if g:
            return {
                "id": str(g.id), "type": "gk", "name": g.name, "club": g.club,
                "country": g.country, "photo_path": g.photo_path, "overall": g.overall,
                "handling": g.handling, "positioning": g.positioning, "reflex": g.reflex, "speed": g.speed
            }
        f = JogadorCampo.objects.filter(pk=pid).first()
        if f:
            return {
                "id": str(f.id), "type": "field", "name": f.name, "club": f.club,
                "country": f.country, "photo_path": f.photo_path, "overall": f.overall,
                "attack": f.attack, "passing": f.passing, "defense": f.defense, "speed": f.speed,
                "position": f.position
            }
        return ""

    user_slots = {
        "gk": _slot_to_snapshot(team_obj.slots.get("gk")),
        "def": [_slot_to_snapshot(v) for v in (team_obj.slots.get("def") or [])],
        "mid": [_slot_to_snapshot(v) for v in (team_obj.slots.get("mid") or [])],
        "off": [_slot_to_snapshot(v) for v in (team_obj.slots.get("off") or [])],
    }

    # escolher um clube aleatório do banco com jogadores suficientes
    chosen_club = _pick_random_club_with_enough_players(min_field_players=10, min_goalkeepers=1)
    if not chosen_club:
        messages.error(request, "Não há clubes suficientes no banco para formar um 'Authentic Team' (é preciso pelo menos 1 GK + 10 jogadores de campo num mesmo clube).")
        return redirect("matches")

    # gerar slots exclusivamente do clube escolhido
    ai_slots = _sample_authentic_players_for_ai(chosen_club)
    if not ai_slots:
        messages.error(request, f"Falha ao montar time autêntico para o clube '{chosen_club}'.")
        return redirect("matches")

    # criar AITeam, simular e criar Match (mesma lógica do random)
    ai_team = AITeam.objects.create(name=f"AUTH {chosen_club[:12]} {uuid.uuid4().hex[:6]}", slots=ai_slots)
    sim = _simulate_match(user_slots, ai_slots)

    match = Match.objects.create(
        user_team=team_obj,
        ai_team=ai_team,
        home_is_user=sim["meta"]["home_is_user"],
        events=sim["events"],
        score_home=sim["score_home"],
        score_away=sim["score_away"],
        meta=sim["meta"]
    )

    return redirect("match_play", match_id=str(match.id))

##sistema de gameplay
def _simulate_match(user_team_slots, ai_team_slots, seed=None):
    """
    Simula 90 minutos e retorna um dict com:
      - events: lista de eventos com fields (minute, half, text, animations, possession_home, event_type, score_home, score_away)
      - score_home, score_away, winner, meta

    Entradas:
      - user_team_slots / ai_team_slots: dicionários com chaves 'gk', 'def'(list), 'mid'(list), 'off'(list)
        cada jogador é um snapshot dict que idealmente contém: id (string), name, (opcional) pos_x,pos_y.
      - seed (opcional): para reprodutibilidade.

    Observações:
      - O texto dos eventos usa sempre nomes dos jogadores quando disponíveis.
      - O campo `animations` contém ações com coordenadas normalizadas [0..1] para o cliente animar.
      - As posições iniciais dos jogadores são atribuídas com base em formação 4-3-3 (similar ao front-end).
    """

    rnd = random.Random(seed or uuid.uuid4().hex)

    # decide quem é "casa"
    home_is_user = rnd.choice([True, False])

    # mapear home/away slots
    if home_is_user:
        home_slots = user_team_slots or {"gk": "", "def": [], "mid": [], "off": []}
        away_slots = ai_team_slots or {"gk": "", "def": [], "mid": [], "off": []}
    else:
        home_slots = ai_team_slots or {"gk": "", "def": [], "mid": [], "off": []}
        away_slots = user_team_slots or {"gk": "", "def": [], "mid": [], "off": []}

    meta = {"seed": str(seed or ""), "home_is_user": home_is_user}

    # ---------- helpers de posição (coerente com o template JS) ----------
    def formation_position_from_token(pos_token, is_home):
        """
        Retorna (x,y) normalizados para um token de posição (ex: 'GOL','DEF1','MID2','ATA3').
        is_home=True => lado esquerdo é o time.
        """
        token = (pos_token or "").upper()
        flip_x = (lambda x: x) if is_home else (lambda x: 1.0 - x)

        if token.startswith("GOL") or token.startswith("GK"):
            return flip_x(0.06), 0.50

        if token.startswith("DEF"):
            num = 1
            try:
                num = int((token.replace("DEF", "") or "1"))
            except Exception:
                num = 1
            ys = [0.18, 0.37, 0.63, 0.82]
            x = 0.22
            idx = max(0, min(3, num - 1))
            return flip_x(x), ys[idx]

        if token.startswith("MID"):
            num = 1
            try:
                num = int((token.replace("MID", "") or "1"))
            except Exception:
                num = 1
            xs = [0.44, 0.50, 0.44]
            ys = [0.42, 0.50, 0.58]
            idx = max(0, min(2, num - 1))
            return flip_x(xs[idx]), ys[idx]

        if token.startswith("ATA") or token.startswith("FWD") or token.startswith("ST") or token.startswith("ATT"):
            num = 1
            try:
                num = int(''.join(ch for ch in token if ch.isdigit()) or "1")
            except Exception:
                num = 1
            xs = [0.68, 0.72, 0.68]
            ys = [0.30, 0.50, 0.70]
            idx = max(0, min(2, num - 1))
            return flip_x(xs[idx]), ys[idx]

        # fallback baseado em hash do token
        s = (pos_token or "")[:32]
        h = 0
        for ch in s:
            h = (h * 31 + ord(ch)) & 0xFFFFFFFF
        slotYs = [0.18, 0.32, 0.46, 0.58, 0.72, 0.86]
        return flip_x(0.5), slotYs[h % len(slotYs)]

    # cria uma lista ordenada de snapshots e atribui tokens (DEF1.., MID1.., ATA1..)
    def build_lineup_slots_from_slotdict(slotdict, is_home):
        """
        Recebe slotdict {'gk','def','mid','off'} onde cada item pode ser dict snapshot ou id string.
        Retorna lista de snapshots com campos normalizados (id,name,pos_x,pos_y,pos_token,_team_is_home).
        """
        out = []
        # GK
        gk_snap = slotdict.get("gk")
        if isinstance(gk_snap, dict) and gk_snap:
            snap = dict(gk_snap)
            snap["id"] = str(snap.get("id") or snap.get("object_id") or uuid.uuid4().hex)
            snap["pos_token"] = "GOL"
            snap["pos_x"], snap["pos_y"] = formation_position_from_token("GOL", is_home)
            snap["_team_is_home"] = is_home
            out.append(snap)

        # DEFs
        for idx, p in enumerate(slotdict.get("def") or []):
            if not p:
                continue
            snap = dict(p) if isinstance(p, dict) else {"id": str(p), "name": str(p)}
            snap["id"] = str(snap.get("id") or uuid.uuid4().hex)
            token = f"DEF{idx+1}"
            snap["pos_token"] = token
            snap["pos_x"], snap["pos_y"] = formation_position_from_token(token, is_home)
            snap["_team_is_home"] = is_home
            out.append(snap)

        # MIDs
        for idx, p in enumerate(slotdict.get("mid") or []):
            if not p:
                continue
            snap = dict(p) if isinstance(p, dict) else {"id": str(p), "name": str(p)}
            snap["id"] = str(snap.get("id") or uuid.uuid4().hex)
            token = f"MID{idx+1}"
            snap["pos_token"] = token
            snap["pos_x"], snap["pos_y"] = formation_position_from_token(token, is_home)
            snap["_team_is_home"] = is_home
            out.append(snap)

        # OFFs / ATAs
        for idx, p in enumerate(slotdict.get("off") or []):
            if not p:
                continue
            snap = dict(p) if isinstance(p, dict) else {"id": str(p), "name": str(p)}
            snap["id"] = str(snap.get("id") or uuid.uuid4().hex)
            token = f"ATA{idx+1}"
            snap["pos_token"] = token
            snap["pos_x"], snap["pos_y"] = formation_position_from_token(token, is_home)
            snap["_team_is_home"] = is_home
            out.append(snap)

        return out

    home_lineup = build_lineup_slots_from_slotdict(home_slots, is_home=True)
    away_lineup = build_lineup_slots_from_slotdict(away_slots, is_home=False)

    # criar mapeamento id -> snapshot (usado para gerar textos coerentes)
    id_to_snapshot = {}
    for snap in (home_lineup + away_lineup):
        sid = str(snap.get("id"))
        # garantir nome legível
        if not snap.get("name"):
            snap["name"] = f"Jogador {sid[-4:]}"
        id_to_snapshot[sid] = snap

    # helpers de seleção (com variedade, evitando escolher sempre o primeiro)
    def flatten_lineup(lineup):
        return [p for p in lineup if isinstance(p, dict)]

    def random_choice_player_from_zone(lineup, prefer_zone=None):
        """
        prefer_zone: a string 'off','mid','def','gk' indica preferência.
        lineup é a lista com pos_token setado para cada snap.
        Retorna snapshot ou None.
        """
        if not lineup:
            return None
        # filtrar por zone token
        zone_map = {
            "gk": lambda s: s.get("pos_token", "").startswith("GOL"),
            "def": lambda s: s.get("pos_token", "").startswith("DEF"),
            "mid": lambda s: s.get("pos_token", "").startswith("MID"),
            "off": lambda s: s.get("pos_token", "").startswith("ATA"),
        }
        if prefer_zone in zone_map:
            candidates = [s for s in lineup if zone_map[prefer_zone](s)]
            if candidates:
                return rnd.choice(candidates)
        # fallback qualquer jogador
        return rnd.choice(lineup)

    def sample_two_distinct(lineup, prefer_primary="off"):
        """Retorna até 2 snapshots distintos: [primary, secondary_or_None]"""
        if not lineup:
            return []
        primary = random_choice_player_from_zone(lineup, prefer_primary)
        secondary_candidates = [p for p in lineup if p["id"] != primary["id"]]
        secondary = rnd.choice(secondary_candidates) if secondary_candidates else None
        return [primary, secondary]

    # ---------- templates de texto ----------
    TEMPLATES = {
        "start_possession": ["{team} em posse — {attacker} conduz a bola.", "{attacker} começa a articular a jogada."],
        "advance": ["{team} empurra o jogo — {attacker} avança.", "{attacker} progride pelo corredor."],
        "pass": ["{attack_marker}Passe de {from_name} para {to_name}.", "{attack_marker}{from_name} encontra {to_name} com passe."],
        "shot": ["{attack_marker}{attacker} finaliza com perigo!", "{attack_marker}{attacker} arrisca o chute!"],
        "goal": ["{attack_marker}GOL! {scorer} balança as redes! ({team})", "{attack_marker}GOL de {scorer}! Assistência de {assister}."],
        "miss": ["{attacker} erra por pouco.", "Na trave! {attacker} lamenta."],
        "keeper_save": ["{keeper} faz uma grande defesa!", "Defesa espetacular de {keeper}!"],
        "intercepted": ["{defender} intercepta e rouba a bola.", "{defender} corta a jogada."],
        "foul": ["Falta em {attacker} — jogo parado.", "Falta marcada, bola parada para {team}."],
        "cross": ["{attack_marker}{attacker} cruza na área.", "{attack_marker}Cruzamento perigoso de {attacker}."],
        "dribble": ["{mid} tenta drible no meio.", "Troca de passes no meio-campo."]
    }

    # ---------- simulação dos 90 minutos com animações ----------
    events = []
    score_home = 0
    score_away = 0

    flat_home = flatten_lineup(home_lineup)
    flat_away = flatten_lineup(away_lineup)

    # função utilitária: cria animação de passe entre dois players (com pequenos timelines)
    def make_pass_animation(from_snap, to_snap):
        if not from_snap or not to_snap:
            return None
        return {
            "type": "pass",
            "player_from_id": str(from_snap["id"]),
            "player_to_id": str(to_snap["id"]),
            "from_pos": [float(from_snap["pos_x"]), float(from_snap["pos_y"])],
            "to_pos": [float(to_snap["pos_x"]), float(to_snap["pos_y"])],
            "duration_ms": rnd.randint(220, 420)
        }

    def make_run_animation(player_snap, to_pos=None):
        if not player_snap:
            return None
        dest = to_pos or [player_snap["pos_x"], player_snap["pos_y"]]
        return {
            "type": "run",
            "player_from_id": str(player_snap["id"]),
            "to_pos": [float(dest[0]), float(dest[1])],
            "duration_ms": rnd.randint(200, 480)
        }

    def make_shot_animation(shooter_snap, target_pos=None):
        if not shooter_snap:
            return None
        # target_pos default: gol adversário
        shooter_is_home = bool(shooter_snap.get("_team_is_home"))
        target_default = [0.98, 0.5] if shooter_is_home else [0.02, 0.5]
        target = target_pos or target_default
        return {
            "type": "shot",
            "player_from_id": str(shooter_snap["id"]),
            "from_pos": [float(shooter_snap["pos_x"]), float(shooter_snap["pos_y"])],
            "to_pos": [float(target[0]), float(target[1])],
            "duration_ms": rnd.randint(280, 500)
        }

    # loop principal de minutos
    for minute in range(1, 91):
        half = 1 if minute <= 45 else 2

        # recalcula forças simplificadas (aleatoriza um pouco para variedade)
        def strength_of_lineup(lineup):
            # soma de overalls se presente, fallback random
            total_attack = 0.0
            total_def = 0.0
            total_gk = 0.0
            neutral = 0.0
            for p in lineup:
                if not isinstance(p, dict):
                    continue
                total_attack += float(p.get("attack", rnd.uniform(0.5, 1.5)))
                total_def += float(p.get("defense", rnd.uniform(0.5, 1.5)))
                neutral += float(p.get("passing", 1.0))
                if p.get("pos_token", "").startswith("GOL"):
                    total_gk += float(p.get("handling", rnd.uniform(0.8, 1.2)))
            # normalize with small epsilon
            return {"attack": max(0.1, total_attack), "defense": max(0.1, total_def), "gk": max(0.1, total_gk or 1.0), "neutral": max(0.1, neutral)}

        home_strength = strength_of_lineup(flat_home)
        away_strength = strength_of_lineup(flat_away)

        # probabilidade de posse para home
        home_attack_metric = home_strength["attack"] + 1e-6
        away_defense_metric = away_strength["defense"] + 1e-6
        prob_home_possession = home_attack_metric / (home_attack_metric + away_defense_metric)
        possession_is_home = rnd.random() < prob_home_possession

        attacking_lineup = flat_home if possession_is_home else flat_away
        defending_lineup = flat_away if possession_is_home else flat_home
        attacking_label = "Seu Time" if (possession_is_home and home_is_user) or (not possession_is_home and not home_is_user) else "Adversário"

        # primeiras micro-frases
        first_action = "start_possession" if rnd.random() < 0.65 else "advance"
        sentences = []
        animations = []

        # start possession sentence
        attacker_choice = random_choice_player_from_zone(attacking_lineup, prefer_zone="off")
        attacker_name = attacker_choice.get("name") if attacker_choice else "Um jogador"
        sentences.append(TEMPLATES.get(first_action)[rnd.randint(0, len(TEMPLATES.get(first_action))-1)].format(team=attacking_label, attacker=attacker_name))

        # decidir se teremos finalização
        shot_chance_denom = ( (home_strength if possession_is_home else away_strength)["attack"]
                              + (home_strength if possession_is_home else away_strength)["neutral"] * 0.5
                              + (away_strength if possession_is_home else home_strength)["defense"] * 0.5 + 1e-6 )
        shot_probability = ((home_strength if possession_is_home else away_strength)["attack"] / shot_chance_denom) * 0.25
        shot_probability *= rnd.uniform(0.8, 1.2)
        did_shot = rnd.random() < shot_probability

        event_type = None

        if did_shot:
            # escolhe shooter e possivel assister
            shooters = sample_two_distinct(attacking_lineup, prefer_primary="off")
            shooter = shooters[0] if shooters else (attacking_lineup[0] if attacking_lineup else None)
            assister = shooters[1] if len(shooters) >= 2 else None

            # animação de aproximação e chute
            shot_anim = make_shot_animation(shooter)
            if shot_anim:
                animations.append(shot_anim)
                sentences.append(TEMPLATES["shot"][rnd.randint(0, len(TEMPLATES["shot"])-1)].format(attack_marker="[ATAQUE " + attacking_label + "] ", attacker=shooter.get("name")))
            # resolver resultado
            shot_power = ( (shooter.get("attack") if shooter.get("attack") is not None else rnd.uniform(0.6,1.4)) * rnd.uniform(0.6, 1.4) )
            keeper_power = ( (defending_lineup[0].get("handling") if defending_lineup and defending_lineup[0].get("pos_token","").startswith("GOL") else (away_strength["gk"] if possession_is_home else home_strength["gk"])) * 1.8 ) \
                           + ( (away_strength if possession_is_home else home_strength)["defense"] * 0.6 )
            goal_probability = shot_power / (shot_power + keeper_power + 1e-6)
            goal_probability = max(0.02, min(0.85, goal_probability * 0.7))

            if rnd.random() < goal_probability:
                # gol
                scorer_name = shooter.get("name")
                assister_name = assister.get("name") if assister else ""
                sentences.append(TEMPLATES["goal"][rnd.randint(0, len(TEMPLATES["goal"])-1)].format(attack_marker="[ATAQUE " + attacking_label + "] ", scorer=scorer_name, team=attacking_label, assister=assister_name or ""))
                # adicionar efeito de gol para animação se quisermos
                animations.append({"type": "goal_effect", "player_id": str(shooter["id"]), "duration_ms": 700})
                if possession_is_home:
                    score_home += 1
                else:
                    score_away += 1
                event_type = "goal"
            else:
                # salva ou erra
                saved_chance = keeper_power / (shot_power + keeper_power + 1e-6)
                if rnd.random() < saved_chance:
                    sentences.append(TEMPLATES["keeper_save"][rnd.randint(0, len(TEMPLATES["keeper_save"])-1)].format(keeper=(defending_lineup[0].get("name") if defending_lineup else "Goleiro")))
                    animations.append({"type": "keeper_save", "duration_ms": 420})
                    event_type = "keeper_save"
                else:
                    sentences.append(TEMPLATES["miss"][rnd.randint(0, len(TEMPLATES["miss"])-1)].format(attacker=shooter.get("name")))
                    animations.append({"type": "miss", "duration_ms": 420})
                    event_type = "miss"
        else:
            # follow-up sem chute: decide pass / intercepted / cross / foul / dribble
            r = rnd.random()
            if r < 0.12:
                # intercepted
                defender = random_choice_player_from_zone(defending_lineup, prefer_zone="def")
                defender_name = defender.get("name") if defender else "zagueiro"
                sentences.append(TEMPLATES["intercepted"][rnd.randint(0, len(TEMPLATES["intercepted"])-1)].format(defender=defender_name))
                animations.append({"type": "intercepted", "player_id": str(defender["id"]) if defender else None, "duration_ms": 300})
                event_type = "intercepted"
            elif r < 0.20:
                # offside
                attacker = random_choice_player_from_zone(attacking_lineup, prefer_zone="off")
                attacker_name = attacker.get("name") if attacker else "atacante"
                sentences.append(TEMPLATES["offside"][0].format(scorer=attacker_name) if "offside" in TEMPLATES else f"{attacker_name} em impedimento.")
                animations.append({"type": "offside", "player_id": str(attacker["id"]) if attacker else None, "duration_ms": 300})
                event_type = "offside"
            elif r < 0.35:
                # cross -> simulamos passe cruzado para um atacante na área
                passer, receiver = sample_two_distinct(attacking_lineup, prefer_primary="mid"), None
                # sample_two_distinct retorna lista; ajustar
                passer_snap = passer[0] if passer else None
                # try to prefer an off target
                possible_receivers = [p for p in attacking_lineup if p.get("pos_token","").startswith("ATA") and p.get("id") != (passer_snap["id"] if passer_snap else None)]
                receiver_snap = rnd.choice(possible_receivers) if possible_receivers else (passer[1] if len(passer) > 1 else None)
                if passer_snap and receiver_snap:
                    sentences.append(TEMPLATES["cross"][rnd.randint(0, len(TEMPLATES["cross"])-1)].format(attack_marker="[ATAQUE " + attacking_label + "] ", attacker=passer_snap.get("name")))
                    pass_anim = make_pass_animation(passer_snap, receiver_snap)
                    if pass_anim:
                        animations.append(pass_anim)
                else:
                    # fallback para dribble
                    runner = random_choice_player_from_zone(attacking_lineup, prefer_zone="mid")
                    sentences.append(TEMPLATES["dribble"][rnd.randint(0, len(TEMPLATES["dribble"])-1)].format(mid=(runner.get("name") if runner else "meio"), defender=(random_choice_player_from_zone(defending_lineup, "def") or {}).get("name", "zagueiro")))
                    animations.append(make_run_animation(runner))
                event_type = "cross"
            elif r < 0.45:
                # foul
                attacker = random_choice_player_from_zone(attacking_lineup, prefer_zone="off")
                sentences.append(TEMPLATES["foul"][rnd.randint(0, len(TEMPLATES["foul"])-1)].format(attacker=(attacker.get("name") if attacker else "jogador"), team=attacking_label))
                animations.append({"type": "foul", "duration_ms": 260})
                event_type = "foul"
            else:
                # dribble/pass: escolhe um passe simples entre dois jogadores
                from_snap, to_snap = None, None
                candidates = attacking_lineup[:]
                if candidates:
                    from_snap = rnd.choice(candidates)
                    possible_receivers = [p for p in candidates if p["id"] != from_snap["id"]]
                    if possible_receivers:
                        to_snap = rnd.choice(possible_receivers)
                if from_snap and to_snap:
                    sentences.append(TEMPLATES["pass"][rnd.randint(0, len(TEMPLATES["pass"])-1)].format(attack_marker="[ATAQUE " + attacking_label + "] ", from_name=from_snap.get("name"), to_name=to_snap.get("name")))
                    pass_anim = make_pass_animation(from_snap, to_snap)
                    if pass_anim:
                        animations.append(pass_anim)
                    event_type = "pass"
                else:
                    # fallback dribble
                    runner = random_choice_player_from_zone(attacking_lineup, prefer_zone="mid")
                    sentences.append(TEMPLATES["dribble"][rnd.randint(0, len(TEMPLATES["dribble"])-1)].format(mid=(runner.get("name") if runner else "meio"), defender=(random_choice_player_from_zone(defending_lineup, "def") or {}).get("name", "zagueiro")))
                    animations.append(make_run_animation(runner))
                    event_type = "dribble"

        # montar texto final (concatenar frases)
        full_text = " ".join([s for s in sentences if s])
        # gravar event
        events.append({
            "minute": minute,
            "half": half,
            "text": full_text,
            "animations": [a for a in animations if a],
            "possession_home": bool(possession_is_home),
            "event_type": event_type or "play",
            "score_home": score_home,
            "score_away": score_away
        })

    # determinar vencedor
    if score_home > score_away:
        winner = "home"
    elif score_away > score_home:
        winner = "away"
    else:
        winner = "draw"

    return {
        "events": events,
        "score_home": score_home,
        "score_away": score_away,
        "winner": winner,
        "meta": meta,
        # também retornamos lineups (útil para salvar/inspecionar)
        "home_lineup": home_lineup,
        "away_lineup": away_lineup
    }

# ----------------- Views expostas -----------------

@require_http_methods(["GET"])
def game_view(request):
    """
    Página com modos de jogo. Por agora apenas 'Random Team'.
    """
    user = _get_current_user(request)
    if not user:
        return redirect("/login/")
    return render(request, "accounts/game.html", {"user": user})

@require_POST
@transaction.atomic
def start_random_match_view(request):
    """
    Endpoint que cria um AITeam aleatório, simula a partida inteira e grava um Match.
    Depois redireciona para a página de reprodução (match_play).
    """
    user = _get_current_user(request)
    if not user:
        return redirect("/login/")

    # pegar team do usuário (cria se não existir)
    team_obj, _ = Team.objects.get_or_create(user=user)
    team_obj.ensure_structure()

    # montar snapshot do team do usuário (prefer snapshots se já tiverem dicts)
    def _slot_to_snapshot(value):
        if not value:
            return ""
        if isinstance(value, dict):
            return value
        # caso seja id string, tentar resolver em InventoryItem ou DB
        pid = str(value)
        inv = InventoryItem.objects.filter(user=user).filter(Q(object_id=pid) | Q(player_data__id=pid)).first()
        if inv:
            snap = inv.get_player_snapshot()
            if snap:
                # normalize position for field players
                if snap.get("type") == "field":
                    snap["position"] = _normalize_position(snap.get("position")) or snap.get("position")
                return snap
        # tentar buscar no DB
        g = JogadorGoleiro.objects.filter(pk=pid).first()
        if g:
            return {
                "id": str(g.id), "type": "gk", "name": g.name, "club": g.club,
                "country": g.country, "photo_path": g.photo_path, "overall": g.overall,
                "handling": g.handling, "positioning": g.positioning, "reflex": g.reflex, "speed": g.speed
            }
        f = JogadorCampo.objects.filter(pk=pid).first()
        if f:
            return {
                "id": str(f.id), "type": "field", "name": f.name, "club": f.club,
                "country": f.country, "photo_path": f.photo_path, "overall": f.overall,
                "attack": f.attack, "passing": f.passing, "defense": f.defense, "speed": f.speed,
                "position": f.position
            }
        return ""

    user_slots = {
        "gk": _slot_to_snapshot(team_obj.slots.get("gk")),
        "def": [ _slot_to_snapshot(v) for v in (team_obj.slots.get("def") or []) ],
        "mid": [ _slot_to_snapshot(v) for v in (team_obj.slots.get("mid") or []) ],
        "off": [ _slot_to_snapshot(v) for v in (team_obj.slots.get("off") or []) ],
    }

    # gerar AI team slots
    ai_slots = _sample_random_players_for_ai()

    # criar registro AITeam
    ai_team = AITeam.objects.create(name=f"AI Team {uuid.uuid4().hex[:6]}", slots=ai_slots)
    # simular partida
    sim = _simulate_match(user_slots, ai_slots)

    # criar Match
    match = Match.objects.create(
        user_team=team_obj,
        ai_team=ai_team,
        home_is_user=sim["meta"]["home_is_user"],
        events=sim["events"],
        score_home=sim["score_home"],
        score_away=sim["score_away"],
        meta=sim["meta"]
    )

    return redirect("match_play", match_id=str(match.id))

@require_http_methods(["GET"])
def match_play_view(request, match_id):
    """
    Prepara a página de reprodução da partida:
     - carrega Match, copia os events, placar e escalações;
     - garante que cada snapshot tenha pos_x/pos_y e id coerentes para o cliente;
     - confere o resultado e credita moedas (vitória +100, empate +50);
     - deleta registros temporários (Match e AITeam) em transação.
    Retorna render com context contendo:
     - events_json, user_lineup (lista), ai_lineup (lista), home_is_user, score_home, score_away, coins_awarded
    """

    user = _get_current_user(request)
    if not user:
        return redirect("/login/")

    match = get_object_or_404(Match, pk=match_id)

    # copiar dados antes de qualquer exclusão
    events = list(match.events or [])
    score_home = int(getattr(match, "score_home", 0) or 0)
    score_away = int(getattr(match, "score_away", 0) or 0)
    home_is_user = bool(getattr(match, "home_is_user", True))
    ai_team = match.ai_team
    user_team = match.user_team

    # função interna para resolver uma slot entry (pode ser snapshot dict, id string ou "")
    def _resolve_slot_snapshot_for_team(slot_value, user_context=None):
        if not slot_value:
            return ""
        if isinstance(slot_value, dict):
            return slot_value
        pid = str(slot_value)
        # tentar InventoryItem se usuário conhecido
        if user_context:
            inv = InventoryItem.objects.filter(user=user_context).filter(Q(object_id=pid) | Q(player_data__id=pid)).first()
            if inv:
                snap = inv.get_player_snapshot()
                if snap:
                    if snap.get("type") == "field":
                        snap["position"] = snap.get("position")
                    return snap
        # fallback DB
        g = JogadorGoleiro.objects.filter(pk=pid).first()
        if g:
            return {
                "id": str(g.id), "type": "gk", "name": g.name, "club": g.club,
                "country": g.country, "photo_path": g.photo_path, "overall": g.overall,
                "handling": g.handling, "positioning": g.positioning, "reflex": g.reflex, "speed": g.speed
            }
        f = JogadorCampo.objects.filter(pk=pid).first()
        if f:
            return {
                "id": str(f.id), "type": "field", "name": f.name, "club": f.club,
                "country": f.country, "photo_path": f.photo_path, "overall": f.overall,
                "attack": f.attack, "passing": f.passing, "defense": f.defense, "speed": f.speed,
                "position": f.position
            }
        return ""

    # montar slots como no seu código original
    if user_team:
        raw_user_slots = user_team.slots or {}
        user_slots_resolved = {
            "gk": _resolve_slot_snapshot_for_team(raw_user_slots.get("gk"), user),
            "def": [_resolve_slot_snapshot_for_team(v, user) for v in (raw_user_slots.get("def") or [])],
            "mid": [_resolve_slot_snapshot_for_team(v, user) for v in (raw_user_slots.get("mid") or [])],
            "off": [_resolve_slot_snapshot_for_team(v, user) for v in (raw_user_slots.get("off") or [])],
        }
    else:
        user_slots_resolved = {"gk": "", "def": [], "mid": [], "off": []}

    if ai_team:
        raw_ai_slots = ai_team.slots or {}
        ai_slots_resolved = {
            "gk": raw_ai_slots.get("gk") or "",
            "def": raw_ai_slots.get("def") or [],
            "mid": raw_ai_slots.get("mid") or [],
            "off": raw_ai_slots.get("off") or []
        }
    else:
        ai_slots_resolved = {"gk": "", "def": [], "mid": [], "off": []}

    # montar lineups (com pos tokens) - lista para template
    user_lineup = []
    if user_slots_resolved.get("gk"):
        user_lineup.append({"pos": "GOL", "player": user_slots_resolved["gk"]})
    for idx, p in enumerate(user_slots_resolved.get("def") or []):
        if p:
            p_snap = p
            user_lineup.append({"pos": f"DEF{idx+1}", "player": p_snap})
    for idx, p in enumerate(user_slots_resolved.get("mid") or []):
        if p:
            user_lineup.append({"pos": f"MID{idx+1}", "player": p})
    for idx, p in enumerate(user_slots_resolved.get("off") or []):
        if p:
            user_lineup.append({"pos": f"ATA{idx+1}", "player": p})

    ai_lineup = []
    if ai_slots_resolved.get("gk"):
        ai_lineup.append({"pos": "GOL", "player": ai_slots_resolved["gk"]})
    for idx, p in enumerate(ai_slots_resolved.get("def") or []):
        if p:
            ai_lineup.append({"pos": f"DEF{idx+1}", "player": p})
    for idx, p in enumerate(ai_slots_resolved.get("mid") or []):
        if p:
            ai_lineup.append({"pos": f"MID{idx+1}", "player": p})
    for idx, p in enumerate(ai_slots_resolved.get("off") or []):
        if p:
            ai_lineup.append({"pos": f"ATA{idx+1}", "player": p})

    # garantir que cada snapshot tem id e pos_x/pos_y (se não tiver, delegamos a formation simple)
    def ensure_positions_on_lineup(lineup_list, is_home):
        for entry in lineup_list:
            snap = entry.get("player") or {}
            if not isinstance(snap, dict):
                continue
            if not snap.get("id"):
                snap["id"] = str(snap.get("object_id") or uuid.uuid4().hex)
            # se backend já gerou pos_x/pos_y (ex: quando simulamos), mantemos; senão calculamos (same tokens used no JS)
            if snap.get("pos_x") is None or snap.get("pos_y") is None:
                # uso a mesma lógica breve do front (coordenadas normalizadas)
                token = entry.get("pos") or snap.get("pos_token") or snap.get("position") or ""
                

                # [NAO SEI, FRENTE,]
                def _formation_pos(token_inner, is_home_inner):
                    token_up = (token_inner or "").upper()
                    flip = (lambda x: x) if is_home_inner else (lambda x: 1.0 - x)
                    if token_up.startswith("GOL"):
                        return flip(0.06), 0.5
                    if token_up.startswith("DEF"):
                        n = int(''.join(ch for ch in token_up if ch.isdigit()) or "1")
                        ys = [0.18, 0.37, 0.63, 0.82]; x = 0.22; idx = max(0, min(3, n-1)); return flip(x), ys[idx]
                    if token_up.startswith("MID"):
                        n = int(''.join(ch for ch in token_up if ch.isdigit()) or "1")
                        xs = [0.44, 0.47, 0.44]; ys = [0.42, 0.5, 0.58]; idx = max(0, min(2, n-1)); return flip(xs[idx]), ys[idx]
                    if token_up.startswith("ATA") or token_up.startswith("FWD") or token_up.startswith("ST"):
                        n = int(''.join(ch for ch in token_up if ch.isdigit()) or "1")
                        xs = [0.68, 0.72, 0.68]; ys = [0.3, 0.5, 0.7]; idx = max(0, min(2, n-1)); return flip(xs[idx]), ys[idx]
                    return flip(0.5), 0.5
                xnorm, ynorm = _formation_pos(token, is_home)
                snap["pos_x"] = float(xnorm)
                snap["pos_y"] = float(ynorm)

    ensure_positions_on_lineup(user_lineup, is_home=True if home_is_user else False)
    ensure_positions_on_lineup(ai_lineup, is_home=False if home_is_user else True)

    # agora: credit coins conforme resultado (vitória +100, empate +50)
    if home_is_user:
        user_goal = score_home
        opp_goal = score_away
    else:
        user_goal = score_away
        opp_goal = score_home

    coins_awarded = 0
    try:
        with transaction.atomic():
            user_locked = SistemasUser.objects.select_for_update().get(pk=user.pk)
            if user_goal > opp_goal:
                user_locked.coins = (user_locked.coins or 0) + 100
                user_locked.save(update_fields=["coins"])
                coins_awarded = 100
            elif user_goal == opp_goal:
                user_locked.coins = (user_locked.coins or 0) + 50
                user_locked.save(update_fields=["coins"])
                coins_awarded = 50
            else:
                coins_awarded = 0

            # deletar ai_team e match (dentro da transação)
            try:
                if ai_team:
                    ai_team.delete()
            except Exception:
                logger.exception("Erro ao deletar ai_team (ignorado)")
            try:
                match.delete()
            except Exception:
                logger.exception("Erro ao deletar match (ignorado)")
    except Exception:
        logger.exception("Erro durante transação de final de partida (award + delete)")

    # inserir evento inicial com escalações (minute = 0)
    def lineup_text_builder(user_lineup_local, ai_lineup_local):
        seg = []
        seg.append("Escalações:")
        seg.append("Seu Time -> " + ", ".join([f"{it['pos']}:{it['player'].get('name') or ''}" for it in user_lineup_local]) if user_lineup_local else "Seu Time sem jogadores")
        seg.append("Adversário -> " + ", ".join([f"{it['pos']}:{it['player'].get('name') or ''}" for it in ai_lineup_local]) if ai_lineup_local else "Adversário sem jogadores")
        return " | ".join(seg)

    lineup_event = {
        "minute": 0,
        "half": 0,
        "text": lineup_text_builder(user_lineup, ai_lineup),
        "possession_home": None,
        "event_type": "lineup",
        "score_home": 0,
        "score_away": 0,
        "animations": []
    }

    events_with_lineup = [lineup_event] + (events or [])

    events_json = json.dumps(events_with_lineup, ensure_ascii=False)
    user_lineup_json = json.dumps(user_lineup, ensure_ascii=False)
    ai_lineup_json = json.dumps(ai_lineup, ensure_ascii=False)

    return render(request, "accounts/match_play.html", {
        "user": user,
        "events_json": events_json,
        "user_lineup_json": user_lineup_json,
        "ai_lineup_json": ai_lineup_json,
        "user_lineup": user_lineup,
        "ai_lineup": ai_lineup,
        "home_is_user": home_is_user,
        "score_home": score_home,
        "score_away": score_away,
        "coins_awarded": coins_awarded,
    })