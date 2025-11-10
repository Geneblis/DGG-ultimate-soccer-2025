# sistemas/models.py
import uuid
from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
from django.db.models import JSONField
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.forms import ValidationError

class SistemasUser(models.Model):
    """
    Usuário principal — tabela explicitamente chamada 'sistemas_users'
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=150, unique=True)
    full_name = models.CharField("nome", max_length=150)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128)  # armazenar hash com make_password
    created_at = models.DateTimeField(auto_now_add=True)
    coins = models.IntegerField(default=0)

    class Meta:
        db_table = "sistemas_users"
        ordering = ["username"]

    def __str__(self):
        return f"{self.username} <{self.email}>"

class JogadorGoleiro(models.Model):
    """
    Tabela para goleiros: jogadores exclusivos com stats próprios.
    db_table explícito: jogadores_goleiros
    """
    LEVEL_CHOICES = [(i, str(i)) for i in range(0, 6)]  # 0..5 (raridade/nível de carta)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    level = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(5)])
    name = models.CharField(max_length=200)
    position = models.CharField(max_length=20, default="GoalkeeperZone")  # sempre GoalkeeperZone
    club = models.CharField(max_length=150)      # obrigatório
    country = models.CharField(max_length=120)   # obrigatório
    photo_path = models.CharField(max_length=500) # obrigatório — caminho relativo (players/...)
    overall = models.IntegerField(default=0)     # calculado manualmente ou pela média se preferir

    # atributos específicos de goleiro
    handling = models.IntegerField(default=0)
    positioning = models.IntegerField(default=0)
    reflex = models.IntegerField(default=0)
    speed = models.IntegerField(default=0)   # speed compartilhado com jogadores de campo

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "jogadores_goleiros"
        ordering = ["-overall", "name"]

    def __str__(self):
        return f"{self.name} ({self.club})"

# Tabela de jogadores de campo (cards)
class JogadorCampo(models.Model):
    LEVEL_CHOICES = [(i, str(i)) for i in range(0, 6)]  # 0..5

    POSITION_OFF = "OffensiveZone"
    POSITION_NEU = "NeutralZone"
    POSITION_DEF = "DefensiveZone"

    POSITION_CHOICES = [
        (POSITION_OFF, "OffensiveZone"),
        (POSITION_NEU, "NeutralZone"),
        (POSITION_DEF, "DefensiveZone"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    level = models.IntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(5)])  # 0..5
    name = models.CharField(max_length=200)
    position = models.CharField(max_length=20, choices=POSITION_CHOICES)
    club = models.CharField(max_length=150)
    country = models.CharField(max_length=120)
    photo_path = models.CharField(max_length=500)  # caminho para a foto (path/URL)
    overall = models.IntegerField(default=0)  # você disse que será calculado manualmente
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

    # mantemos a generic relation para compatibilidade, mas agora também armazenamos snapshot JSON
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True)
    object_id = models.CharField(max_length=36, blank=True, null=True)   # armazenamos UUID como string
    content_object = GenericForeignKey("content_type", "object_id")

    # novo: snapshot do jogador no inventário (copy do objeto no momento da aquisição)
    player_data = JSONField(null=True, blank=True, default=None)

    qty = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    obtained_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sistemas_inventory"
        # ainda garantimos unicidade quando content_type/object_id existirem
        unique_together = ("user", "content_type", "object_id")
        ordering = ["-obtained_at"]

    def __str__(self):
        # prefere o nome do snapshot, depois tenta content_object, senão object_id
        if self.player_data and isinstance(self.player_data, dict):
            name = self.player_data.get("name") or str(self.object_id)
        else:
            player = self.get_player()
            name = getattr(player, "name", str(self.object_id))
        return f"{self.user.username} - {name} x{self.qty}"

    def clean(self):
        # agora aceitamos: (content_type+object_id) OU player_data preenchido (snapshot)
        ct = self.content_type
        if (ct is None or not self.object_id) and not self.player_data:
            raise ValidationError("InventoryItem precisa de content_type+object_id ou player_data.")
        # se content_type presente, verifica tipo aceito (legacy)
        if ct is not None:
            key = (ct.app_label, ct.model)
            allowed = {
                ("sistemas", "jogadorcampo"),
                ("sistemas", "jogadorgoleiro"),
            }
            if key not in allowed:
                raise ValidationError("InventoryItem só aceita JogadorCampo ou JogadorGoleiro como alvo.")

    def save(self, *args, **kwargs):
        # garantir object_id salvo como string (caso usuário passe UUID)
        if hasattr(self.object_id, "hex"):
            self.object_id = str(self.object_id)
        # manter player_data como None ou dict
        if self.player_data == {}:
            self.player_data = None
        super().save(*args, **kwargs)

    def get_player(self):
        """Retorna o objeto do jogador (ou None)."""
        # primeiro tenta content_object (legacy), depois tenta player_data (snapshot não vira objeto Django).
        try:
            if self.content_object:
                return self.content_object
        except Exception:
            pass
        return None

    def get_player_snapshot(self):
        """Retorna dicionário com os dados do jogador: preferencialmente player_data, senão
        tenta buscar do DB via content_object e transformar em dict."""
        if self.player_data:
            return self.player_data
        try:
            player = self.get_player()
            if not player:
                # tentar buscar por content_type/object_id manualmente
                if self.content_type and self.object_id:
                    model = self.content_type.model_class()
                    p = model.objects.filter(pk=self.object_id).values().first()
                    if p:
                        return dict(p)
                return None
            # montar snapshot reduzido (só campos relevantes)
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

    # nova estrutura: listas de dicts, cada dict = { "id": "<uuid>", "weight": 1, "note": "" }
    field_players = JSONField(default=list, blank=True)  # jogadores de campo
    gk_players = JSONField(default=list, blank=True)     # goleiros

    class Meta:
        db_table = "sistemas_packs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} — {self.price} coins"

    # helpers que o código do app pode chamar

    def get_all_entries(self):
        """
        Retorna lista de entries combinadas: cada entry tem campos:
        { "id": "<uuid>", "weight": <int>, "note": "<str>", "type": "field"|'gk" }
        """
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
        """
        Retorna uma entry escolhida ponderada por 'weight', ou None se não houver entries.
        A entry retornada é o dicionário com 'type' já definido.
        """
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

    def add_entry(self, entry_id, type="field", weight=1, note=""):
        """
        Adiciona uma entry ao pack (type == 'field' ou 'gk').
        `entry_id` deve ser string UUID.
        """
        target = self.field_players if type == "field" else self.gk_players
        # prevenir duplicata simples (mesmo id)
        if any(str(x.get("id")) == str(entry_id) for x in (target or [])):
            return False
        new = {"id": str(entry_id), "weight": int(weight or 1), "note": note or ""}
        if type == "field":
            self.field_players = (self.field_players or []) + [new]
        else:
            self.gk_players = (self.gk_players or []) + [new]
        self.save(update_fields=["field_players", "gk_players"])
        return True

    def remove_entry(self, entry_id):
        """
        Remove entry (em qualquer lista) se encontrar e salva.
        """
        fid = str(entry_id)
        changed = False
        if self.field_players:
            new_field = [x for x in self.field_players if str(x.get("id")) != fid]
            if len(new_field) != len(self.field_players):
                self.field_players = new_field
                changed = True
        if self.gk_players:
            new_gk = [x for x in self.gk_players if str(x.get("id")) != fid]
            if len(new_gk) != len(self.gk_players):
                self.gk_players = new_gk
                changed = True
        if changed:
            self.save(update_fields=["field_players", "gk_players"])
        return changed
    
class Team(models.Model):
    ...
    def set_slot(self, slot_key, player_snapshot_or_id):
        """
        Agora aceita:
          - player_snapshot_or_id: dict (snapshot com campos) -> guarda este dicionário no slot
          - ou id/UUID string -> tenta buscar snapshot no inventário/DB e guarda o snapshot
        """
        self.ensure_structure()
        # tentar obter snapshot
        snap = None
        if isinstance(player_snapshot_or_id, dict):
            snap = player_snapshot_or_id
        else:
            pid = str(player_snapshot_or_id)
            # procurar em InventoryItem deste user por object_id ou player_data.id
            inv = InventoryItem.objects.filter(user=self.user).filter(
                models.Q(object_id=pid) | models.Q(player_data__id=pid)
            ).first()
            if inv:
                snap = inv.get_player_snapshot()
            else:
                # fallback: tentar buscar direto no DB
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

        # escrever no slot (guardar o dict)
        if slot_key == "gk":
            self.slots["gk"] = snap
        else:
            sec, idx = slot_key.split("_"); idx = int(idx)
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

