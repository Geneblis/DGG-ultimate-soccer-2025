# sistemas/management/commands/fix_packentries.py
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings

import os
import shutil
import datetime
from uuid import UUID

from sistemas.models import PackEntry, Pack, JogadorCampo, JogadorGoleiro

class Command(BaseCommand):
    help = "Tenta corrigir PackEntry com IDs 'estranhos' (aspas, chaves, espaços). Faz backup do sqlite antes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--db-path",
            help="Caminho do sqlite db (por padrão settings.BASE_DIR / 'bancos/db.sqlite3')",
            default=None,
        )
        parser.add_argument(
            "--dry-run",
            help="Não escreve mudanças no DB, apenas mostra o que faria.",
            action="store_true",
        )

    def handle(self, *args, **options):
        db_path = options["db_path"]
        if not db_path:
            # caminho padrão relativo ao project root
            db_path = os.path.join(settings.BASE_DIR, "bancos", "db.sqlite3")

        self.stdout.write(self.style.NOTICE(f"Usando DB path: {db_path}"))

        if os.path.exists(db_path):
            ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
            bak_path = f"{db_path}.bak.{ts}"
            try:
                shutil.copyfile(db_path, bak_path)
                self.stdout.write(self.style.SUCCESS(f"Backup do DB criado em: {bak_path}"))
            except Exception as ex:
                self.stdout.write(self.style.WARNING(f"Falha ao criar backup automático: {ex}"))
                self.stdout.write(self.style.WARNING("Continuando sem backup automático — recomendado criar backup manualmente."))
        else:
            self.stdout.write(self.style.WARNING(f"Arquivo DB não encontrado em {db_path}. Continuando (pode ser outro DB)."))

        dry = options["dry_run"]

        def canonical_uuid_string(raw):
            """Remove aspas/braces/spaces e tenta validar como UUID; retorna string canônica ou None."""
            if raw is None:
                return None
            s = str(raw).strip()
            # tira aspas externas e chaves
            s = s.strip("'\"").strip("{} ").strip()
            # já está no formato com hífens?
            try:
                u = UUID(s)
                return str(u)
            except Exception:
                # tenta remover hífens e validar
                s2 = s.replace("-", "")
                try:
                    u = UUID(s2)
                    return str(u)
                except Exception:
                    return None

        fixed = []
        not_fixed = []

        all_entries = list(PackEntry.objects.all())
        self.stdout.write(f"PackEntry rows to inspect: {len(all_entries)}")

        # vamos agrupar em uma transação mas só salvar se não for dry-run
        with transaction.atomic():
            for e in all_entries:
                orig_pack_raw = e.pack_id
                orig_player_raw = e.player_id

                pack_can = canonical_uuid_string(orig_pack_raw)
                player_can = canonical_uuid_string(orig_player_raw)

                pack_obj = None
                if pack_can:
                    pack_obj = Pack.objects.filter(pk=pack_can).first()

                # fallback: tenta usar o raw string (sem canonical) caso pack_can fale
                if not pack_obj and str(orig_pack_raw):
                    try:
                        cand = str(orig_pack_raw).strip().strip("'\"{} ")
                        pack_obj = Pack.objects.filter(pk=cand).first()
                    except Exception:
                        pack_obj = None

                # procurar jogador
                player_field_obj = None
                player_gk_obj = None
                if player_can:
                    player_field_obj = JogadorCampo.objects.filter(pk=player_can).first()
                    player_gk_obj = JogadorGoleiro.objects.filter(pk=player_can).first()

                if not player_field_obj and not player_gk_obj and str(orig_player_raw):
                    pr = str(orig_player_raw).strip().strip("'\"{} ")
                    player_field_obj = JogadorCampo.objects.filter(pk=pr).first()
                    player_gk_obj = JogadorGoleiro.objects.filter(pk=pr).first()

                if pack_obj:
                    changed = False
                    # atualiza referência do pack (campo pack_id/pack pode ser atualizado ao setar e.pack = pack_obj)
                    # OBS: pack_id é na model UUIDField via pack FK; escrevemos apenas se diferente
                    try:
                        if getattr(e, "pack_id", None) != pack_obj.id:
                            e.pack = pack_obj
                            changed = True
                    except Exception:
                        # se não tiver pack relation, ignore
                        pass

                    # corrige player_id e player_type se encontramos o jogador
                    if player_field_obj:
                        if str(getattr(e, "player_id", "")) != str(player_field_obj.id) or getattr(e, "player_type", "") != "field":
                            e.player_id = str(player_field_obj.id)
                            e.player_type = "field"
                            changed = True
                    elif player_gk_obj:
                        if str(getattr(e, "player_id", "")) != str(player_gk_obj.id) or getattr(e, "player_type", "") != "gk":
                            e.player_id = str(player_gk_obj.id)
                            e.player_type = "gk"
                            changed = True

                    if changed:
                        if dry:
                            fixed.append((e.id, str(pack_obj.id), str(e.player_id), e.player_type, "DRY_RUN"))
                        else:
                            e.save()
                            fixed.append((e.id, str(pack_obj.id), str(e.player_id), e.player_type))
                    else:
                        fixed.append((e.id, "already-ok"))
                else:
                    not_fixed.append((e.id, str(orig_pack_raw), str(orig_player_raw)))

            if dry:
                # força rollback da transação para não salvar nada
                transaction.set_rollback(True)

        # resumo
        self.stdout.write(self.style.SUCCESS(f"Corrigidos (ou ok): {len(fixed)}"))
        for r in fixed[:200]:
            self.stdout.write(f"  FIX: {r}")
        if len(fixed) > 200:
            self.stdout.write(f"  ... mais {len(fixed)-200}")

        self.stdout.write(self.style.WARNING(f"Não corrigidos (requer revisão manual): {len(not_fixed)}"))
        for r in not_fixed[:200]:
            self.stdout.write(f"  NOK: {r}")
        if len(not_fixed) > 200:
            self.stdout.write(f"  ... mais {len(not_fixed)-200}")

        # verificação pós-fix (rápida)
        self.stdout.write("\nVerificação pós-fix (contagem entries por pack):")
        for p in Pack.objects.all():
            try:
                cnt_rel = p.entries.count()
            except Exception:
                cnt_rel = "N/A"
            cnt_filter = PackEntry.objects.filter(pack_id=str(p.id)).count()
            self.stdout.write(f" - {p.id} ({p.name}): relation={cnt_rel} filter(pack_id)={cnt_filter}")

        self.stdout.write(self.style.SUCCESS("Operação concluída."))
        if dry:
            self.stdout.write(self.style.NOTICE("Foi executado em modo --dry-run, nenhuma alteração foi salva."))
