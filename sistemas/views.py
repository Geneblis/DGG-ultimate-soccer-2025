# sistemas/views.py
import random
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.hashers import make_password, check_password
from django.utils.text import slugify

from .models import (
    SistemasUser, JogadorCampo, JogadorGoleiro,
    InventoryItem, Pack, PackEntry
)
from .utils import add_player_to_user_inventory


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

def get_players_for_pack(pack):
    """
    Recebe uma instância Pack (ou id string/UUID) e devolve lista de dicts:
      [{ 'entry': <PackEntry>, 'player': <JogadorCampo|JogadorGoleiro|None>,
         'player_type': 'field'|'gk', 'player_id': '<uuid str>', 'photo': '<path>' }, ...]
    Busca os jogadores em batch para evitar N queries.
    """
    # aceita pack instância ou id
    if not isinstance(pack, Pack):
        pack = Pack.objects.filter(pk=pack).first()
        if not pack:
            return []

    entries_qs = list(pack.entries.all().order_by("-weight", "id"))
    # coletar ids por tipo para buscas em lote
    field_ids = [str(e.player_id) for e in entries_qs if e.player_type == "field"]
    gk_ids = [str(e.player_id) for e in entries_qs if e.player_type == "gk"]

    campos_map = {}
    if field_ids:
        qs = JogadorCampo.objects.filter(id__in=field_ids)
        campos_map = {str(x.id): x for x in qs}

    gks_map = {}
    if gk_ids:
        qs = JogadorGoleiro.objects.filter(id__in=gk_ids)
        gks_map = {str(x.id): x for x in qs}

    results = []
    for e in entries_qs:
        pid = str(e.player_id)
        player_obj = None
        if e.player_type == "field":
            player_obj = campos_map.get(pid)
        else:
            player_obj = gks_map.get(pid)

        photo = ""
        if player_obj is not None:
            photo = getattr(player_obj, "photo_path", "") or getattr(player_obj, "photo", "") or ""

        results.append({
            "entry": e,
            "player": player_obj,
            "player_type": e.player_type,
            "player_id": pid,
            "photo": photo,
        })
    return results

@transaction.atomic
def packs_list_view(request):
    """
    GET -> renderiza lista de packs com entries (cada entry traz player.photo e player.name quando existir).
    POST -> form (action=open + pack_id) -> abre pack (debita moedas, salva inventário) e redireciona.
    """
    uid = request.session.get("user_id")
    user = None
    if uid:
        try:
            user = SistemasUser.objects.get(pk=uid)
        except SistemasUser.DoesNotExist:
            user = None

    # -- POST: abrir pack --
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "open":
            pack_id = request.POST.get("pack_id")
            if not pack_id:
                messages.error(request, "Pack inválido.")
                return redirect("packs_list")
            if not user:
                messages.error(request, "Faça login para abrir packs.")
                return redirect("login")

            pack = get_object_or_404(Pack, pk=pack_id)

            if user.coins < pack.price:
                messages.error(request, "Moedas insuficientes.")
                return redirect("packs_list")

            entries = list(pack.entries.all())
            if not entries:
                messages.error(request, "Pack vazio. Contate o administrador.")
                return redirect("packs_list")

            weights = [max(1, int(getattr(e, "weight", 1) or 1)) for e in entries]
            chosen = random.choices(entries, weights=weights, k=1)[0]

            # debita moedas
            user.coins -= pack.price
            user.save()

            # tenta usar sua utilidade existente, se não existir faz fallback com ContentType/InventoryItem
            item = None
            try:
                # se você tiver add_player_to_user_inventory importada/util
                item, created = add_player_to_user_inventory(user, chosen.player_type, chosen.player_id, amount=1)
            except Exception:
                try:
                    if chosen.player_type == "field":
                        ct = ContentType.objects.get_for_model(JogadorCampo)
                    else:
                        ct = ContentType.objects.get_for_model(JogadorGoleiro)
                    inv, created = InventoryItem.objects.get_or_create(
                        user=user,
                        content_type=ct,
                        object_id=str(chosen.player_id),
                        defaults={"qty": 1}
                    )
                    if not created:
                        inv.qty += 1
                        inv.save()
                    item = inv
                except Exception:
                    # reembolsa e retorna erro
                    user.coins += pack.price
                    user.save()
                    messages.error(request, "Erro interno ao adicionar ao inventário. Tente novamente.")
                    return redirect("packs_list")

            # buscar dados do jogador sorteado para a mensagem
            if chosen.player_type == "field":
                pdata = JogadorCampo.objects.filter(pk=chosen.player_id).first()
            else:
                pdata = JogadorGoleiro.objects.filter(pk=chosen.player_id).first()

            player_name = pdata.name if pdata else "Jogador"
            messages.success(request, f"Você abriu '{pack.name}' e obteve: {player_name} — custo: {pack.price} moedas. Moedas atuais: {user.coins}")
            return redirect("packs_list")
        else:
            messages.error(request, "Ação inválida.")
            return redirect("packs_list")

    # -- GET: montar dados dos packs (com players) --
    packs_qs = Pack.objects.all().order_by("price")
    packs = []
    for p in packs_qs:
        entries = []
        for e in p.entries.all().order_by("-weight"):
            # tenta buscar objeto jogador em cada entry
            if e.player_type == "field":
                pdata = JogadorCampo.objects.filter(pk=e.player_id).first()
            else:
                pdata = JogadorGoleiro.objects.filter(pk=e.player_id).first()

            player_obj = None
            if pdata:
                player_obj = {
                    "id": str(pdata.id),
                    "name": pdata.name,
                    # normaliza caminhos de foto: photo_path ou photo
                    "photo": getattr(pdata, "photo_path", "") or getattr(pdata, "photo", "") or ""
                }

            entries.append({
                "entry_id": e.id,
                "player_type": e.player_type,
                "player_id": str(e.player_id),
                "player": player_obj,
                "weight": e.weight,
                "note": getattr(e, "note", ""),
            })

        pack_dict = {
            "obj": p,
            "image_path": getattr(p, "image_path", "") or getattr(p, "image", "") or getattr(p, "path_image", "") or "",
            "entries": entries,
        }
        packs.append(pack_dict)

    return render(request, "accounts/packs_list.html", {"packs": packs, "user": user})