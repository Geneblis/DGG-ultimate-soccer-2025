#!/usr/bin/env python3
"""
Batch deposit tool para packs (SQLite).
- Interativo: cola muitos player IDs (um por linha) e adiciona ao pack.
- Linhas podem ser: "<id>" ou "<id>,<weight>" ou "<id>,<weight>,<note>"
- Tipo: 1 = jogador de campo (field); 2 = goleiro (gk). Aceita também 'field'/'gk'.
- Evita duplicatas por player.id no pack.
Comentários e explicações concentrados no topo (conforme pedido).
"""
import sqlite3
import json
import datetime
from pathlib import Path

# Ajuste este caminho se necessário (mesma convenção do CRUD)
ROOT = Path(__file__).resolve().parent.parent  # supondo scripts/.. ajuste se quiser
DB_PATH = ROOT / "DGG-ultimate-soccer-2025" / "bancos" / "db.sqlite3"

# ---------- helpers JSON ----------
def _load_json_list(text):
    try:
        if text is None or text == "":
            return []
        return json.loads(text)
    except Exception:
        return []

def _dump_json_list(lst):
    try:
        return json.dumps(lst, ensure_ascii=False)
    except Exception:
        return "[]"

# ---------- fetch players ----------
def fetch_field_player_object(conn, player_id):
    r = conn.execute(
        "SELECT id, name, club, country, photo_path, overall, attack, passing, defense, speed FROM jogadores_campo WHERE id = ? LIMIT 1",
        (player_id,)
    ).fetchone()
    if not r:
        return None
    return {
        "id": r["id"],
        "name": r["name"],
        "club": r["club"],
        "country": r["country"],
        "photo_path": r["photo_path"],
        "overall": r["overall"],
        "attack": r["attack"],
        "passing": r["passing"],
        "defense": r["defense"],
        "speed": r["speed"],
    }

def fetch_gk_player_object(conn, player_id):
    r = conn.execute(
        "SELECT id, name, club, country, photo_path, overall, handling, positioning, reflex, speed FROM jogadores_goleiros WHERE id = ? LIMIT 1",
        (player_id,)
    ).fetchone()
    if not r:
        return None
    return {
        "id": r["id"],
        "name": r["name"],
        "club": r["club"],
        "country": r["country"],
        "photo_path": r["photo_path"],
        "overall": r["overall"],
        "handling": r["handling"],
        "positioning": r["positioning"],
        "reflex": r["reflex"],
        "speed": r["speed"],
    }

# ---------- main ----------
def main():
    if not DB_PATH.exists():
        print("DB não encontrado em:", DB_PATH)
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        pack_id = input("Pack id (UUID): ").strip()
        if not pack_id:
            print("Pack id obrigatório.")
            return

        # carregar pack
        cur = conn.execute("SELECT id, field_players, gk_players FROM sistemas_packs WHERE id = ?", (pack_id,))
        pack_row = cur.fetchone()
        if not pack_row:
            print("Pack não encontrado (id):", pack_id)
            return

        type_choice = input("Tipo (1=campo, 2=goleiro) ou 'field'/'gk': ").strip().lower()
        if type_choice == "1":
            ptype = "field"
        elif type_choice == "2":
            ptype = "gk"
        elif type_choice in ("field","gk"):
            ptype = type_choice
        else:
            print("Tipo inválido.")
            return

        default_weight = input("Peso padrão (weight) [enter=1]: ").strip()
        default_weight = int(default_weight) if default_weight.isdigit() else 1
        default_note = input("Nota padrão (note) [enter='']: ").strip() or ""

        print("\nCole os player IDs (um por linha). Termine com uma linha vazia (Enter).")
        print("Formato por linha opcional: id  OR  id,weight  OR  id,weight,note")
        lines = []
        while True:
            line = input().strip()
            if line == "":
                break
            lines.append(line)

        if not lines:
            print("Nenhum ID fornecido. Abortando.")
            return

        field_list = _load_json_list(pack_row["field_players"])
        gk_list = _load_json_list(pack_row["gk_players"])
        target_list = field_list if ptype == "field" else gk_list

        added = []
        skipped_dup = []
        missing_and_added_minimal = []
        failed = []

        for raw in lines:
            # parse
            parts = [p.strip() for p in raw.split(",", 2)]
            player_id = parts[0] if parts else ""
            if not player_id:
                failed.append((raw, "id vazio"))
                continue
            try:
                weight = int(parts[1]) if len(parts) >= 2 and parts[1] != "" else default_weight
            except Exception:
                weight = default_weight
            note = parts[2] if len(parts) == 3 else default_note

            # check duplicate
            if any(str(x.get("id")) == str(player_id) for x in target_list):
                skipped_dup.append(player_id)
                continue

            # fetch object
            player_obj = fetch_field_player_object(conn, player_id) if ptype == "field" else fetch_gk_player_object(conn, player_id)
            if player_obj is None:
                # perguntar se deve criar minimal
                ans = input(f"Player {player_id} não encontrado no DB. Criar entrada minimal (id+name=id)? (s/N): ").strip().lower()
                if ans != "s":
                    failed.append((player_id, "não encontrado e não criado"))
                    continue
                player_obj = {"id": player_id, "name": player_id}

            # montar entry e adicionar
            entry = dict(player_obj)
            entry["weight"] = int(weight or 1)
            entry["note"] = note or ""
            target_list.append(entry)
            added.append(player_id)
            if player_obj and (player_obj.get("name") == player_id):
                missing_and_added_minimal.append(player_id)

        # salvar no DB
        conn.execute(
            "UPDATE sistemas_packs SET field_players = ?, gk_players = ? WHERE id = ?",
            (_dump_json_list(field_list), _dump_json_list(gk_list), pack_id)
        )
        conn.commit()

        # resumo
        print("\n=== Resultado do batch ===")
        print("Pack:", pack_id, "| tipo:", ptype)
        print("Adicionados:", len(added))
        for a in added[:50]:
            print("  +", a)
        if skipped_dup:
            print("Duplicatas ignoradas (já existiam):", len(skipped_dup))
            for d in skipped_dup[:50]:
                print("  -", d)
        if missing_and_added_minimal:
            print("Foram adicionados como minimal (não estavam no DB):", len(missing_and_added_minimal))
            for m in missing_and_added_minimal[:50]:
                print("  *", m)
        if failed:
            print("Falhas:", len(failed))
            for f in failed[:50]:
                print("  !", f[0], "-", f[1])

        print("\nGravado com sucesso.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
