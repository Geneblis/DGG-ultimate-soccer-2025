# Top comments: simples e explicativos (mantenha no topo)
# Signals: ao criar um SistemasUser novo, automaticamente dá:
#  - 1 GK, 4 DEF, 3 MID, 3 OFF (total 11) no inventário do usuário
#  - cada snapshot recebe "level" aleatório entre 0 e 3
#  - garante que o usuário tenha pelo menos 100 moedas
# Proteções simples: se já existir qualquer InventoryItem para o usuário, o sinal não reatribui.

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
import random
import logging

from .models import SistemasUser, JogadorCampo, JogadorGoleiro, InventoryItem

logger = logging.getLogger(__name__)

def _snapshot_from_field(player):
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

def _snapshot_from_gk(player):
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

@receiver(post_save, sender=SistemasUser)
def grant_starter_pack_and_coins(sender, instance, created, **kwargs):
    """
    Ao criar um SistemasUser, dar um pacote inicial de 11 jogadores + garantir 100 coins.
    Se o usuário já tem InventoryItem qualquer, o sinal não atribui (proteção contra duplo).
    """
    if not created:
        return

    try:
        with transaction.atomic():
            user = SistemasUser.objects.select_for_update().get(pk=instance.pk)

            # se o usuário já tem inventário, não reatribui (evita duplicados)
            existing_any = InventoryItem.objects.filter(user=user).exists()
            if existing_any:
                logger.info("Usuário %s já tem inventário: pulando atribuição inicial.", user.pk)
            else:
                # carregar pools
                field_players = list(JogadorCampo.objects.all())
                goalkeepers = list(JogadorGoleiro.objects.all())

                if not goalkeepers or not field_players:
                    logger.warning("Sem jogadores suficientes no DB para popular inventário do usuário %s", user.pk)
                else:
                    random.shuffle(goalkeepers)
                    random.shuffle(field_players)

                    # escolher GK (primeiro diferente por nome se possível)
                    chosen_names = set()
                    chosen_ids = set()

                    gk_obj = None
                    for cand in goalkeepers:
                        name_norm = (cand.name or "").strip().lower()
                        if name_norm and name_norm not in chosen_names:
                            gk_obj = cand
                            chosen_names.add(name_norm)
                            chosen_ids.add(str(cand.id))
                            break
                    if not gk_obj:
                        gk_obj = goalkeepers[0]
                        chosen_names.add((gk_obj.name or "").strip().lower())
                        chosen_ids.add(str(gk_obj.id))

                    # pools posicionais
                    defenders_pool = [p for p in field_players if p.position == JogadorCampo.POSITION_DEF]
                    mids_pool = [p for p in field_players if p.position == JogadorCampo.POSITION_NEU]
                    offs_pool = [p for p in field_players if p.position == JogadorCampo.POSITION_OFF]

                    def _take_unique(pool, needed):
                        picked = []
                        candidates = list(pool)
                        random.shuffle(candidates)
                        for p in candidates:
                            if len(picked) >= needed:
                                break
                            name_norm = (p.name or "").strip().lower()
                            if not name_norm:
                                continue
                            if name_norm in chosen_names:
                                continue
                            pid = str(p.id)
                            if pid in chosen_ids:
                                continue
                            picked.append(p)
                            chosen_names.add(name_norm)
                            chosen_ids.add(pid)
                        return picked

                    def_list = _take_unique(defenders_pool, 4)
                    mid_list = _take_unique(mids_pool, 3)
                    off_list = _take_unique(offs_pool, 3)

                    # completar a partir de todos os field_players sem repetir nome
                    def _fill_from_all(target_list, needed):
                        if len(target_list) >= needed:
                            return target_list
                        extras = [p for p in field_players if (p.name or "").strip().lower() not in chosen_names]
                        random.shuffle(extras)
                        for p in extras:
                            if len(target_list) >= needed:
                                break
                            target_list.append(p)
                            chosen_names.add((p.name or "").strip().lower())
                            chosen_ids.add(str(p.id))
                        return target_list

                    def_list = _fill_from_all(def_list, 4)
                    mid_list = _fill_from_all(mid_list, 3)
                    off_list = _fill_from_all(off_list, 3)

                    # último recurso: preencher mesmo permitindo repetições (muito raro)
                    def _final_fill(target_list, needed, pool):
                        if len(target_list) >= needed:
                            return target_list
                        pool_copy = list(pool)
                        random.shuffle(pool_copy)
                        for p in pool_copy:
                            if len(target_list) >= needed:
                                break
                            target_list.append(p)
                        return target_list

                    def_list = _final_fill(def_list, 4, field_players)
                    mid_list = _final_fill(mid_list, 3, field_players)
                    off_list = _final_fill(off_list, 3, field_players)

                    # função para criar InventoryItem (ou incrementar qty)
                    def _add_inventory_for_player(obj, is_field):
                        if is_field:
                            snapshot = _snapshot_from_field(obj)
                        else:
                            snapshot = _snapshot_from_gk(obj)
                        # level aleatório 0..3
                        snapshot["level"] = random.randint(0, 3)

                        model_cls = JogadorCampo if is_field else JogadorGoleiro
                        ct = ContentType.objects.get_for_model(model_cls)
                        pid = str(obj.id)

                        inv = InventoryItem.objects.filter(user=user).filter(
                            Q(content_type=ct, object_id=pid) | Q(player_data__id=pid)
                        ).first()
                        if inv:
                            inv.qty = (inv.qty or 0) + 1
                            inv.player_data = snapshot
                            inv.content_type = ct
                            inv.object_id = pid
                            inv.save()
                        else:
                            InventoryItem.objects.create(
                                user=user,
                                content_type=ct,
                                object_id=pid,
                                player_data=snapshot,
                                qty=1
                            )

                    # adicionar GK + DEF/MID/OFF
                    _add_inventory_for_player(gk_obj, is_field=False)
                    for p in def_list:
                        _add_inventory_for_player(p, is_field=True)
                    for p in mid_list:
                        _add_inventory_for_player(p, is_field=True)
                    for p in off_list:
                        _add_inventory_for_player(p, is_field=True)

                    logger.info("Starter pack atribuído ao usuário %s (11 jogadores)", user.pk)

            # garantir 100 moedas mínimo
            current_coins = int(getattr(user, "coins", 0) or 0)
            if current_coins < 100:
                user.coins = 100
                user.save(update_fields=["coins"])
                logger.info("Usuário %s recebeu 100 moedas iniciais", user.pk)

    except Exception as exc:
        logger.exception("Erro ao atribuir starter pack/coins para usuário %s: %s", getattr(instance, "pk", "?"), exc)
