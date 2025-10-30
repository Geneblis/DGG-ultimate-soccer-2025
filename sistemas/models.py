# sistemas/models.py
import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

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

# Tabela de jogadores de campo (cards)
class JogadorCampo(models.Model):
    LEVEL_CHOICES = [(i, str(i)) for i in range(0, 6)]  # 0..5

    POSITION_OFF = "OffensiveZone"
    POSITION_NEU = "NeutralZone"
    POSITION_DEF = "DefensiveZone"
    POSITION_GK  = "GoalkeeperZone"

    POSITION_CHOICES = [
        (POSITION_OFF, "OffensiveZone"),
        (POSITION_NEU, "NeutralZone"),
        (POSITION_DEF, "DefensiveZone"),
        (POSITION_GK,  "GoalkeeperZone"),
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
    aggression = models.IntegerField(default=0)

    class Meta:
        db_table = "jogadores_campo"
        ordering = ["-overall", "name"]

    def __str__(self):
        return f"{self.name} ({self.club})"

# Inventário / Ownership: quantas cópias do jogador o user possui
class InventoryItem(models.Model):
    """
    Tabela que liga usuários e jogadores: armazena quantidades e metadados.
    """
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(SistemasUser, on_delete=models.CASCADE, related_name="inventory_items")
    player = models.ForeignKey(JogadorCampo, on_delete=models.CASCADE, related_name="owned_by")
    qty = models.IntegerField(default=1, validators=[MinValueValidator(1)])
    obtained_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sistemas_inventory"
        unique_together = ("user", "player")
        ordering = ["-obtained_at"]

    def __str__(self):
        return f"{self.user.username} - {self.player.name} x{self.qty}"
