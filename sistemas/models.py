# sistemas/models.py
import uuid
from django.db import models

class SimpleUser(models.Model):
    """
    Substitui o users.json. Mantemos UUID como PK para compatibilidade
    com request.session['user_id'] (strings de UUID).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField("nome", max_length=150, blank=True)
    username = models.CharField("username", max_length=150, unique=True)
    email = models.EmailField("email", unique=True)
    password = models.CharField("password", max_length=128)  # hash do Django
    created_at = models.DateTimeField(auto_now_add=True)
    coins = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.username} <{self.email}>"
