# sistemas/views.py
import random
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password
from django.utils.text import slugify
from django.db import transaction

from .models import SistemasUser, JogadorCampo, JogadorGoleiro, InventoryItem, Pack, PackEntry, SistemasUser, JogadorCampo, JogadorGoleiro
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

def packs_list_view(request):
    uid = request.session.get("user_id")
    user = None
    if uid:
        try:
            user = SistemasUser.objects.get(pk=uid)
        except SistemasUser.DoesNotExist:
            user = None
    packs = Pack.objects.all().order_by("price")
    return render(request, "accounts/packs_list.html", {"packs": packs, "user": user})

# detalhe do pack
def pack_detail_view(request, pack_id):
    uid = request.session.get("user_id")
    user = None
    if uid:
        try:
            user = SistemasUser.objects.get(pk=uid)
        except SistemasUser.DoesNotExist:
            user = None
    pack = get_object_or_404(Pack, pk=pack_id)
    entries = []
    for e in pack.entries.all():
        # tenta puxar dados do jogador para exibição
        pdata = None
        if e.player_type == "field":
            pdata = JogadorCampo.objects.filter(pk=e.player_id).first()
        else:
            pdata = JogadorGoleiro.objects.filter(pk=e.player_id).first()
        entries.append({"entry": e, "player": pdata})
    return render(request, "accounts/pack_detail.html", {"pack": pack, "entries": entries, "user": user})

# abrir (comprar) pack
@transaction.atomic
def pack_open_view(request, pack_id):
    if request.method != "POST":
        return redirect("pack_detail", pack_id=pack_id)

    uid = request.session.get("user_id")
    if not uid:
        messages.error(request, "Faça login para abrir packs.")
        return redirect("login")

    user = get_object_or_404(SistemasUser, pk=uid)
    pack = get_object_or_404(Pack, pk=pack_id)

    if user.coins < pack.price:
        messages.error(request, "Moedas insuficientes.")
        return redirect("pack_detail", pack_id=pack_id)

    entries = list(pack.entries.all())
    if not entries:
        messages.error(request, "Pack vazio, contate o administrador.")
        return redirect("pack_detail", pack_id=pack_id)

    # escolhas por peso
    weights = [max(1, int(e.weight or 1)) for e in entries]
    chosen_entry = random.choices(entries, weights=weights, k=1)[0]

    # deduzir moedas e adicionar ao inventário de forma atômica
    user.coins -= pack.price
    user.save()

    item, created = add_player_to_user_inventory(user, chosen_entry.player_type, chosen_entry.player_id, amount=1)
    if item is None:
        # jogador não encontrado — reembolsa
        user.coins += pack.price
        user.save()
        messages.error(request, "Erro ao adicionar jogador (não encontrado). Operação cancelada.")
        return redirect("pack_detail", pack_id=pack_id)

    # buscar dados do jogador para exibir
    if chosen_entry.player_type == "field":
        player_obj = JogadorCampo.objects.filter(pk=chosen_entry.player_id).first()
    else:
        player_obj = JogadorGoleiro.objects.filter(pk=chosen_entry.player_id).first()

    messages.success(request, f"Você abriu {pack.name} e obteve {player_obj.name if player_obj else 'um jogador'}!")
    return render(request, "accounts/pack_result.html", {"pack": pack, "player": player_obj, "user": user})