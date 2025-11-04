from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from .models import InventoryItem, SistemasUser, JogadorCampo, JogadorGoleiro
from django.core.exceptions import ObjectDoesNotExist

def add_player_to_user_inventory(user: SistemasUser, player_type: str, player_id: str, amount: int = 1):
    """
    Adiciona 'amount' cópias do jogador ao inventário do user.
    Usa InventoryItem (qty). Retorna (item, created_bool).
    """
    if player_type == "field":
        model = JogadorCampo
    elif player_type == "gk":
        model = JogadorGoleiro
    else:
        raise ValueError("player_type inválido")

    # valida existência do jogador
    try:
        model.objects.get(pk=player_id)
    except ObjectDoesNotExist:
        return None, False

    ct = ContentType.objects.get_for_model(model)
    with transaction.atomic():
        item, created = InventoryItem.objects.get_or_create(
            user=user,
            content_type=ct,
            object_id=str(player_id),
            defaults={"qty": amount}
        )
        if not created:
            item.qty += amount
            item.save()
    return item, created
