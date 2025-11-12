"""
Modelos do app 'sistemas'.
Comentários e helpers top-of-file.
Novos modelos:
- AITeam: times gerados pelo site (não pertencem a usuários humanos)
- Match: armazena partida (home_team, away_team, events JSON, resultado)
"""

import uuid
from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.db.models import JSONField
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.forms import ValidationError

# --- existentes (SistemasUser, JogadorCampo, JogadorGoleiro, InventoryItem, Pack, Team) ---
# Copie aqui todo o conteúdo dos seus modelos existentes (os que você já tinha).
# Abaixo incluo apenas os novos modelos e a parte relevante do Team (assegure que não haja duplicação).

class SistemasUser(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True)
    full_name = models.CharField("nome", max_length=150)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    coins = models.IntegerField(default=0)

    class Meta:
        db_table = "sistemas_users"
        ordering = ["username"]

    def __str__(self):
        return f"{self.username} <{self.email}>"

class JogadorGoleiro(models.Model):
    LEVEL_CHOICES = [(i, str(i)) for i in range(0, 6)]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    level = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(5)])
    name = models.CharField(max_length=200)
    position = models.CharField(max_length=20, default="GoalkeeperZone")
    club = models.CharField(max_length=150)
    country = models.CharField(max_length=120)
    photo_path = models.CharField(max_length=500)
    overall = models.IntegerField(default=0)
    handling = models.IntegerField(default=0)
    positioning = models.IntegerField(default=0)
    reflex = models.IntegerField(default=0)
    speed = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "jogadores_goleiros"
        ordering = ["-overall", "name"]

    def __str__(self):
        return f"{self.name} ({self.club})"

class JogadorCampo(models.Model):
    LEVEL_CHOICES = [(i, str(i)) for i in range(0, 6)]
    POSITION_OFF = "OffensiveZone"
    POSITION_NEU = "NeutralZone"
    POSITION_DEF = "DefensiveZone"
    POSITION_CHOICES = [
        (POSITION_OFF, "OffensiveZone"),
        (POSITION_NEU, "NeutralZone"),
        (POSITION_DEF, "DefensiveZone"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    level = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(5)])
    name = models.CharField(max_length=200)
    position = models.CharField(max_length=20, choices=POSITION_CHOICES)
    club = models.CharField(max_length=150)
    country = models.CharField(max_length=120)
    photo_path = models.CharField(max_length=500)
    overall = models.IntegerField(default=0)
    attack = models.IntegerField(default=0)
    passing = models.IntegerField(default=0)
    defense = models.IntegerField(default=0)
    speed = models.IntegerField(default=0)

    class Meta:
        db_table = "jogadores_campo"
        ordering = ["-overall", "name"]

    def __str__(self):
        return f"{self.name} ({self.club})"

    def get_position_abbr(self):
        if self.position == "OffensiveZone":
            return "ATA"
        elif self.position == "NeutralZone":
            return "MID"
        elif self.position == "DefensiveZone":
            return "DEF"
        return "N/A"

class InventoryItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(SistemasUser, on_delete=models.CASCADE, related_name="inventory_items")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.CharField(max_length=36, blank=True, null=True)
    content_object = GenericForeignKey("content_type", "object_id")
    player_data = JSONField(null=True, blank=True, default=None)
    qty = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    obtained_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sistemas_inventory"
        unique_together = ("user", "content_type", "object_id")
        ordering = ["-obtained_at"]

    def __str__(self):
        if self.player_data and isinstance(self.player_data, dict):
            name = self.player_data.get("name") or str(self.object_id)
        else:
            player = self.get_player()
            name = getattr(player, "name", str(self.object_id))
        return f"{self.user.username} - {name} x{self.qty}"

    def clean(self):
        ct = self.content_type
        if (ct is None or not self.object_id) and not self.player_data:
            raise ValidationError("InventoryItem precisa de content_type+object_id ou player_data.")
        if ct is not None:
            key = (ct.app_label, ct.model)
            allowed = {("sistemas", "jogadorcampo"), ("sistemas", "jogadorgoleiro")}
            if key not in allowed:
                raise ValidationError("InventoryItem só aceita JogadorCampo ou JogadorGoleiro como alvo.")

    def save(self, *args, **kwargs):
        if hasattr(self.object_id, "hex"):
            self.object_id = str(self.object_id)
        if self.player_data == {}:
            self.player_data = None
        super().save(*args, **kwargs)

    def get_player(self):
        try:
            if self.content_object:
                return self.content_object
        except Exception:
            pass
        return None

    def get_player_snapshot(self):
        if self.player_data:
            return self.player_data
        try:
            player = self.get_player()
            if not player:
                if self.content_type and self.object_id:
                    model = self.content_type.model_class()
                    p = model.objects.filter(pk=self.object_id).values().first()
                    if p:
                        return dict(p)
                return None
            if isinstance(player, JogadorCampo):
                return {
                    "id": str(player.id),
                    "type": "field",
                    "name": player.name,
                    "club": player.club,
                    "country": player.country,
                    "photo_path": player.photo_path,
                    "overall": player.overall,
                    "attack": player.attack,
                    "passing": player.passing,
                    "defense": player.defense,
                    "speed": player.speed,
                    "position": player.position,
                }
            else:
                return {
                    "id": str(player.id),
                    "type": "gk",
                    "name": player.name,
                    "club": player.club,
                    "country": player.country,
                    "photo_path": player.photo_path,
                    "overall": player.overall,
                    "handling": player.handling,
                    "positioning": player.positioning,
                    "reflex": player.reflex,
                    "speed": player.speed,
                }
        except Exception:
            return None

class Pack(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=140)
    price = models.IntegerField(default=0)
    description = models.TextField(blank=True)
    image_path = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    field_players = JSONField(default=list, blank=True)
    gk_players = JSONField(default=list, blank=True)

    class Meta:
        db_table = "sistemas_packs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} — {self.price} coins"

    def get_all_entries(self):
        entries = []
        for e in (self.field_players or []):
            item = dict(e)
            item.setdefault("weight", 1)
            item.setdefault("note", "")
            item["type"] = "field"
            entries.append(item)
        for e in (self.gk_players or []):
            item = dict(e)
            item.setdefault("weight", 1)
            item.setdefault("note", "")
            item["type"] = "gk"
            entries.append(item)
        return entries

    def pick_random_entry(self):
        entries = self.get_all_entries()
        weighted = []
        total = 0
        for e in entries:
            w = int(e.get("weight", 0) or 0)
            if w <= 0:
                continue
            total += w
            weighted.append((e, total))
        if total == 0:
            return None
        import random
        r = random.randint(1, total)
        for e, cum in weighted:
            if r <= cum:
                return e
        return None

class Team(models.Model):
    user = models.OneToOneField("SistemasUser", on_delete=models.CASCADE, related_name="team")
    slots = JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sistemas_team"

    def __str__(self):
        return f"Team of {self.user.username}"

    def ensure_structure(self):
        s = self.slots or {}
        if "gk" not in s:
            s["gk"] = ""
        if "def" not in s:
            s["def"] = ["", "", "", ""]
        if "mid" not in s:
            s["mid"] = ["", "", ""]
        if "off" not in s:
            s["off"] = ["", "", ""]
        if s != self.slots:
            self.slots = s

    def set_slot(self, slot_key, player_snapshot_or_id):
        self.ensure_structure()
        snap = None
        if isinstance(player_snapshot_or_id, dict):
            snap = player_snapshot_or_id
        else:
            pid = str(player_snapshot_or_id)
            inv = InventoryItem.objects.filter(user=self.user).filter(
                models.Q(object_id=pid) | models.Q(player_data__id=pid)
            ).first()
            if inv and getattr(inv, "player_data", None):
                snap = dict(inv.player_data)
            else:
                f = JogadorCampo.objects.filter(pk=pid).first()
                if f:
                    snap = {
                        "id": str(f.id), "type": "field", "name": f.name, "club": f.club,
                        "country": f.country, "photo_path": f.photo_path, "overall": f.overall,
                        "attack": f.attack, "passing": f.passing, "defense": f.defense,
                        "speed": f.speed, "position": f.position,
                    }
                else:
                    g = JogadorGoleiro.objects.filter(pk=pid).first()
                    if g:
                        snap = {
                            "id": str(g.id), "type": "gk", "name": g.name, "club": g.club,
                            "country": g.country, "photo_path": g.photo_path, "overall": g.overall,
                            "handling": g.handling, "positioning": g.positioning,
                            "reflex": g.reflex, "speed": g.speed,
                        }
        if not snap:
            raise ValueError("Não foi possível obter snapshot do jogador para salvar no slot.")
        if slot_key == "gk":
            self.slots["gk"] = snap
        else:
            sec, idx = slot_key.split("_"); idx = int(idx)
            while len(self.slots.get(sec, [])) <= idx:
                self.slots[sec].append("")
            self.slots[sec][idx] = snap
        self.save(update_fields=["slots", "updated_at"])

    def clear_slot(self, slot_key):
        self.ensure_structure()
        if slot_key == "gk":
            self.slots["gk"] = ""
        else:
            sec, idx = slot_key.split("_"); idx = int(idx)
            self.slots[sec][idx] = ""
        self.save(update_fields=["slots", "updated_at"])


# ----------------- NOVOS MODELOS PARA JOGO -----------------

class AITeam(models.Model):
    """
    Time criado automaticamente pelo sistema (IA).
    slots: JSON -> formato id's ou snapshots, preferencialmente snapshots.
    name: nome amigável (ex: "AI Team #123")
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, default="AI Team")
    slots = JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sistemas_ai_team"

    def __str__(self):
        return f"{self.name}"

    def ensure_structure(self):
        s = self.slots or {}
        if "gk" not in s:
            s["gk"] = ""
        if "def" not in s:
            s["def"] = ["", "", "", ""]
        if "mid" not in s:
            s["mid"] = ["", "", ""]
        if "off" not in s:
            s["off"] = ["", "", ""]
        if s != self.slots:
            self.slots = s
            self.save(update_fields=["slots"])


class Match(models.Model):
    """
    Partida entre um Team (usuario) e um AITeam (ou outro Team no futuro).
    - home_is_user: bool para saber quem é casa
    - events: lista de eventos (cada evento = dict { minute, text, team_in_possession, ... })
    - score: {"home": int, "away": int}
    - meta: info extra (seed, duration, etc)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)
    ai_team = models.ForeignKey(AITeam, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    home_is_user = models.BooleanField(default=True)
    events = JSONField(default=list, blank=True)
    score_home = models.IntegerField(default=0)
    score_away = models.IntegerField(default=0)
    meta = JSONField(default=dict, blank=True)

    class Meta:
        db_table = "sistemas_match"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Match {self.id} ({'user home' if self.home_is_user else 'user away'})"