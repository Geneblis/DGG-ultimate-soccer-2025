# sistemas/models.py
import uuid
from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
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

    # generic relation -> aponta para JogadorCampo ou JogadorGoleiro
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=36)   # armazenamos UUID como string
    content_object = GenericForeignKey("content_type", "object_id")

    qty = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    obtained_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sistemas_inventory"
        unique_together = ("user", "content_type", "object_id")
        ordering = ["-obtained_at"]

    def __str__(self):
        # tenta mostrar nome do player se possível
        player = self.get_player()
        player_name = getattr(player, "name", str(self.object_id))
        return f"{self.user.username} - {player_name} x{self.qty}"

    def clean(self):
        allowed = {
            ("sistemas", "jogadorcampo"),
            ("sistemas", "jogadorgoleiro"),
        }
        ct = self.content_type
        if ct is None:
            raise ValidationError("content_type não pode ser nulo.")
        key = (ct.app_label, ct.model)
        if key not in allowed:
            raise ValidationError("InventoryItem só aceita JogadorCampo ou JogadorGoleiro como alvo.")

    def save(self, *args, **kwargs):
        # chama clean para validação simples antes de salvar
        self.clean()
        # garantir object_id salvo como string (caso usuário passe UUID)
        if hasattr(self.object_id, "hex"):
            self.object_id = str(self.object_id)
        super().save(*args, **kwargs)

    def get_player(self):
        """Retorna o objeto do jogador (ou None)."""
        try:
            return self.content_object
        except Exception:
            return None

    def get_player_type(self):
        """Retorna 'field' ou 'gk' conforme o modelo apontado."""
        ct = self.content_type
        if ct is None:
            return None
        if (ct.app_label, ct.model) == ("sistemas", "jogadorcampo"):
            return "field"
        if (ct.app_label, ct.model) == ("sistemas", "jogadorgoleiro"):
            return "gk"
        return "unknown"
    
class Pack(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=140)
    price = models.IntegerField(default=0)
    description = models.TextField(blank=True)
    image_path = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "sistemas_packs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} — {self.price} coins"

class PackEntry(models.Model):
    id = models.AutoField(primary_key=True)
    pack = models.ForeignKey(Pack, on_delete=models.CASCADE, related_name="entries")
    # duas FKs opcionais — apenas uma deve ser preenchida por entry
    player_field = models.ForeignKey(JogadorCampo, null=True, blank=True, on_delete=models.CASCADE)
    player_gk = models.ForeignKey(JogadorGoleiro, null=True, blank=True, on_delete=models.CASCADE)

    weight = models.IntegerField(default=1)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        db_table = "sistemas_packentry"
        unique_together = (("pack", "player_field"), ("pack", "player_gk"))
        ordering = ["-weight"]

    def get_player(self):
        """Retorna (obj, 'field'|'gk'|None)."""
        if self.player_field_id:
            return (self.player_field, "field")
        if self.player_gk_id:
            return (self.player_gk, "gk")
        return (None, None)

    def __str__(self):
        p, t = self.get_player()
        return f"{self.pack.name} - {p.name if p else '???'} ({t})"