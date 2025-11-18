#!/usr/bin/env python3
"""
CRUD Packs atualizado: each pack stores full player objects in JSON lists.
- field_players, gk_players: lists of dicts:
  { "id": "<uuid>", "weight": 1, "note": "", "name": "...", "club":"...", "photo_path":"...", "overall": 0, ...attrs... }
- Includes a migration helper to migrate from old sistemas_packentry -> new JSON full objects.
"""
import sqlite3
import uuid
import random
import datetime
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BANCOS_DIR = ROOT / "bancos"
DB_PATH = BANCOS_DIR / "db.sqlite3"
IMAGES_ROOT = ROOT / "imagens" / "webmedia" / "packs"

CREATE_PACKS_SQL = """
CREATE TABLE IF NOT EXISTS sistemas_packs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    image_path TEXT,
    price INTEGER NOT NULL DEFAULT 0,
    field_players TEXT DEFAULT '[]',
    gk_players TEXT DEFAULT '[]',
    created_at TEXT NOT NULL
);
"""

def ensure_db():
    BANCOS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(CREATE_PACKS_SQL)
    conn.commit()
    return conn

def input_nonempty(prompt):
    while True:
        v = input(prompt).strip()
        if v:
            return v

def input_int(prompt, default=None):
    while True:
        s = input(prompt).strip()
        if s == "" and default is not None:
            return default
        try:
            return int(s)
        except:
            print("Digite um número inteiro válido.")

def scan_pack_images():
    imgs = []
    if not IMAGES_ROOT.exists():
        return imgs
    for p in IMAGES_ROOT.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            imgs.append(p.relative_to(IMAGES_ROOT))
    imgs.sort()
    return imgs

def choose_image_interactive():
    imgs = scan_pack_images()
    if not imgs:
        print("Nenhuma imagem encontrada em", IMAGES_ROOT)
        return None
    while True:
        for i, r in enumerate(imgs[:50], start=1):
            print(f"{i:3d}) {r}")
        opt = input("Escolha número (ou 'm' manual, 'q' cancelar): ").strip().lower()
        if opt == "q": return None
        if opt == "m":
            manual = input("Caminho relativo dentro de webmedia/packs/: ").strip()
            p = IMAGES_ROOT / manual
            if p.exists(): return str(Path("webmedia/packs") / manual).replace("\\","/")
            print("Arquivo não encontrado.")
            continue
        if opt.isdigit():
            n = int(opt)
            if 1 <= n <= min(50, len(imgs)):
                chosen = imgs[n-1]
                return str(Path("webmedia/packs") / chosen).replace("\\","/")
        print("Opção inválida.")

# JSON helpers
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

# --- Player lookup helpers (pega o objeto completo do jogador por id) ---
def fetch_field_player_object(conn, player_id):
    """Retorna dict com dados completos do jogador de campo ou None."""
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
    """Retorna dict com dados completos do goleiro ou None."""
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

# --- Packs CRUD ---

def create_pack(conn):
    print("\n--- Criar Pack ---")
    name = input_nonempty("Nome do pack: ")
    description = input("Descrição (opcional): ").strip() or None
    price = input_int("Preço em moedas: ")
    print("Escolha imagem do pack (opcional):")
    image_path = choose_image_interactive()
    created_at = datetime.datetime.utcnow().isoformat() + "Z"
    pid = str(uuid.uuid4())
    try:
        conn.execute(
            "INSERT INTO sistemas_packs (id, name, description, image_path, price, field_players, gk_players, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, name, description, image_path, price, "[]", "[]", created_at)
        )
        conn.commit()
        print("Pack criado:", pid)
    except sqlite3.IntegrityError as e:
        print("Erro ao criar pack:", e)

def list_packs(conn):
    cur = conn.execute("SELECT id, name, price, created_at FROM sistemas_packs ORDER BY created_at DESC;")
    rows = cur.fetchall()
    if not rows:
        print("Nenhum pack cadastrado.")
        return
    print("\n--- Packs ---")
    for r in rows:
        print(f"{r['id']} | {r['name']} | {r['price']} coins | criado: {r['created_at']}")

def show_pack(conn):
    pid = input_nonempty("Digite o id do pack: ")
    cur = conn.execute("SELECT id, name, description, image_path, price, field_players, gk_players, created_at FROM sistemas_packs WHERE id = ?", (pid,))
    r = cur.fetchone()
    if not r:
        print("Pack não encontrado.")
        return
    print("\n=== Detalhes do Pack ===")
    print("ID:", r["id"])
    print("Nome:", r["name"])
    print("Descrição:", r["description"] or "-")
    print("Imagem (relative):", r["image_path"] or "-")
    print("Preço:", r["price"])
    print("Criado:", r["created_at"])

    field_entries = _load_json_list(r["field_players"])
    gk_entries = _load_json_list(r["gk_players"])

    if not field_entries and not gk_entries:
        print("\nNenhum jogador associado a esse pack.")
        return

    print("\nJogadores possíveis no pack (objetos completos):")
    for e in field_entries:
        print_entry_object(e, "field")
    for e in gk_entries:
        print_entry_object(e, "gk")

def print_entry_object(e, typ):
    pid_show = e.get("id")
    name = e.get("name") or pid_show
    club = e.get("club", "")
    overall = e.get("overall", "")
    weight = e.get("weight", 1)
    note = e.get("note", "")
    print(f"  type={typ} | player_id={pid_show} | weight={weight} -> {name} ({club}) overall={overall} | note: {note or '-'}")

def delete_pack(conn):
    pid = input_nonempty("Digite o id do pack a deletar: ")
    confirm = input(f"Confirma exclusão de {pid}? (s/N): ").strip().lower()
    if confirm != "s":
        print("Cancelado.")
        return
    conn.execute("DELETE FROM sistemas_packs WHERE id = ?", (pid,))
    conn.commit()
    print("Deletado (se existia).")

def update_pack(conn):
    pid = input_nonempty("Digite o id do pack a atualizar: ")
    cur = conn.execute("SELECT id, name, description, image_path, price FROM sistemas_packs WHERE id = ?", (pid,))
    r = cur.fetchone()
    if not r:
        print("Pack não encontrado.")
        return
    print("Pressione Enter para manter valor atual.")
    name = input(f"Nome [{r['name']}]: ").strip() or r["name"]
    description = input(f"Descrição [{r['description'] or ''}]: ").strip() or r["description"]
    price_input = input(f"Preço [{r['price']}]: ").strip()
    price = int(price_input) if price_input.isdigit() else r["price"]
    img_opt = input("Trocar imagem? (s/N): ").strip().lower()
    image_path = r["image_path"]
    if img_opt == "s":
        image_path = choose_image_interactive()
    conn.execute(
        "UPDATE sistemas_packs SET name=?, description=?, image_path=?, price=? WHERE id=?",
        (name, description, image_path, price, pid)
    )
    conn.commit()
    print("Atualizado.")

# --- Add / Remove players storing full object ---

def add_player_to_pack(conn):
    """
    Adiciona um jogador ao pack — escolha de tipo simplificada:
    - Digite '1' para jogador de campo (field)
    - Digite '2' para goleiro (gk)
    Aceita também 'field' ou 'gk' caso prefira.
    """
    pid = input_nonempty("Digite o id do pack: ")
    cur = conn.execute("SELECT id, field_players, gk_players FROM sistemas_packs WHERE id = ?", (pid,))
    row = cur.fetchone()
    if not row:
        print("Pack não encontrado.")
        return

    print("Adicionar jogador ao pack: escolha tipo e id do jogador.")
    print("1) Jogador de campo")
    print("2) Goleiro")
    type_choice = input("Escolha (1/2) ou digite 'field'/'gk': ").strip().lower()

    if type_choice == "1":
        ptype = "field"
    elif type_choice == "2":
        ptype = "gk"
    elif type_choice in ("field", "gk"):
        ptype = type_choice
    else:
        print("Tipo inválido. Use 1 para jogador de campo ou 2 para goleiro.")
        return

    player_id = input_nonempty("Digite o player id (UUID) (ou digite 'search' para procurar): ")
    if player_id.lower() == "search":
        q = input("Procurar por nome (parte): ").strip()
        if ptype == "field":
            rows = conn.execute("SELECT id, name, club FROM jogadores_campo WHERE name LIKE ? LIMIT 50", (f"%{q}%",)).fetchall()
        else:
            rows = conn.execute("SELECT id, name, club FROM jogadores_goleiros WHERE name LIKE ? LIMIT 50", (f"%{q}%",)).fetchall()
        if not rows:
            print("Nenhum jogador encontrado.")
            return
        for i, rr in enumerate(rows, start=1):
            print(f"{i}) {rr['id']} | {rr['name']} ({rr['club']})")
        sel = input("Escolha número: ").strip()
        if not sel.isdigit() or not (1 <= int(sel) <= len(rows)):
            print("Escolha inválida.")
            return
        player_id = rows[int(sel)-1]["id"]

    weight = input_int("Weight (probabilidade relativa, inteiro, default 1): ", default=1) or 1
    note = input("Observação (opcional): ").strip() or ""

    # buscar objeto completo do jogador nas tabelas
    player_obj = None
    if ptype == "field":
        player_obj = fetch_field_player_object(conn, player_id)
    else:
        player_obj = fetch_gk_player_object(conn, player_id)

    if player_obj is None:
        print("Jogador não encontrado nas tabelas de jogadores; você ainda pode adicionar manualmente os campos.")
        if input("Adicionar manualmente com apenas ID (s/N)? ").strip().lower() != "s":
            print("Cancelado.")
            return
        player_obj = {"id": str(player_id), "name": str(player_id)}

    # anexar weight & note (sem sobrescrever campos do jogador)
    entry = dict(player_obj)
    entry["weight"] = int(weight or 1)
    entry["note"] = note or ""

    field_entries = _load_json_list(row["field_players"])
    gk_entries = _load_json_list(row["gk_players"])
    target_list = field_entries if ptype == "field" else gk_entries

    # impedir duplicata por id
    if any(str(x.get("id")) == str(entry["id"]) for x in target_list):
        print("Este jogador já está associado a esse pack (entrada duplicada).")
        return

    if ptype == "field":
        field_entries.append(entry)
    else:
        gk_entries.append(entry)

    conn.execute(
        "UPDATE sistemas_packs SET field_players = ?, gk_players = ? WHERE id = ?",
        (_dump_json_list(field_entries), _dump_json_list(gk_entries), pid)
    )
    conn.commit()
    print("Adicionado (objeto completo salvo no JSON).")



def remove_player_from_pack(conn):
    pid = input_nonempty("Digite o id do pack: ")
    cur = conn.execute("SELECT id, field_players, gk_players FROM sistemas_packs WHERE id = ?", (pid,))
    row = cur.fetchone()
    if not row:
        print("Pack não encontrado.")
        return
    player_id = input_nonempty("Digite o player id (UUID) a remover: ")
    field_entries = _load_json_list(row["field_players"])
    gk_entries = _load_json_list(row["gk_players"])

    fid = str(player_id)
    new_field = [x for x in field_entries if str(x.get("id")) != fid]
    new_gk = [x for x in gk_entries if str(x.get("id")) != fid]

    if len(new_field) == len(field_entries) and len(new_gk) == len(gk_entries):
        print("Player id não encontrado neste pack.")
        return

    conn.execute(
        "UPDATE sistemas_packs SET field_players = ?, gk_players = ? WHERE id = ?",
        (_dump_json_list(new_field), _dump_json_list(new_gk), pid)
    )
    conn.commit()
    print("Removido (se existia).")

# --- Open pack for user (uses stored full object) ---
def open_pack_for_user(conn):
    user_id = input_nonempty("User id (UUID): ")
    pack_id = input_nonempty("Pack id (UUID): ")
    r = conn.execute("SELECT price, field_players, gk_players FROM sistemas_packs WHERE id = ?", (pack_id,)).fetchone()
    if not r:
        print("Pack não encontrado."); return
    price = r["price"]
    ur = conn.execute("SELECT coins FROM sistemas_users WHERE id = ?", (user_id,)).fetchone()
    if not ur:
        print("User não encontrado."); return
    coins = ur["coins"]
    if coins < price:
        print("User não tem moedas suficientes:", coins, "<", price); return

    field_entries = _load_json_list(r["field_players"])
    gk_entries = _load_json_list(r["gk_players"])
    entries = []
    for e in field_entries:
        item = dict(e); item["type"] = "field"; entries.append(item)
    for e in gk_entries:
        item = dict(e); item["type"] = "gk"; entries.append(item)

    if not entries:
        print("Pack vazio (nenhuma entry)."); return

    weights = [max(0, int(e.get("weight", 0) or 0)) for e in entries]
    if sum(weights) == 0:
        print("Pack sem entradas ponderadas (weights = 0)."); return

    chosen = random.choices(entries, weights=weights, k=1)[0]
    pid_used = chosen.get("id")
    ptype = chosen.get("type")
    player_name = chosen.get("name") or str(pid_used)
    # debitar moedas
    conn.execute("UPDATE sistemas_users SET coins = coins - ? WHERE id = ?", (price, user_id))

    # inserir no inventário: temos ID e tipo; o objeto completo também é armazenado
    inserted = False
    try:
        cols_info = conn.execute("PRAGMA table_info(sistemas_inventory)").fetchall()
        cols = [c[1] for c in cols_info]
        if "content_type" in cols and "object_id" in cols:
            ctname = "sistemas.jogadorcampo" if ptype == "field" else "sistemas.jogadorgoleiro"
            ex = conn.execute("SELECT id, qty FROM sistemas_inventory WHERE user_id = ? AND content_type = ? AND object_id = ?", (user_id, ctname, str(pid_used))).fetchone()
            if ex:
                conn.execute("UPDATE sistemas_inventory SET qty = qty + 1 WHERE id = ?", (ex["id"],))
            else:
                conn.execute("INSERT INTO sistemas_inventory (user_id, content_type, object_id, qty, obtained_at) VALUES (?, ?, ?, ?, ?)",
                             (user_id, ctname, str(pid_used), 1, datetime.datetime.utcnow().isoformat() + "Z"))
            inserted = True
        elif "content_type_id" in cols and "object_id" in cols:
            print("Inventário usa content_type_id (numeric). Este script não popula automaticamente essa forma.")
            inserted = False
        elif "player" in cols:
            if ptype != "field":
                inserted = False
            else:
                ex = conn.execute("SELECT id, qty FROM sistemas_inventory WHERE user_id = ? AND player = ?", (user_id, str(pid_used))).fetchone()
                if ex:
                    conn.execute("UPDATE sistemas_inventory SET qty = qty + 1 WHERE id = ?", (ex["id"],))
                else:
                    conn.execute("INSERT INTO sistemas_inventory (user_id, player, qty, obtained_at) VALUES (?, ?, ?, ?)",
                                 (user_id, str(pid_used), 1, datetime.datetime.utcnow().isoformat() + "Z"))
                inserted = True
        else:
            inserted = False
    except Exception as exc:
        print("Erro ao tentar inserir no inventário:", exc)
        inserted = False

    conn.commit()
    print(f"Pack aberto! Jogador recebido: {player_name} (type={ptype} id={pid_used})")
    print("Inserido no inventário do usuário." if inserted else "Não foi possível inserir automaticamente no inventário (verificar esquema).")

# --- Migration helper from old sistemas_packentry to full objects ---
def migrate_packentries_to_full_objects(conn, dry_run=False):
    """
    Se existir a tabela sistemas_packentry, converte os registros para os novos campos JSON.
    - dry_run=True apenas mostra o que seria feito.
    """
    # verifica se tabela antiga existe
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sistemas_packentry'").fetchone()
        if not cur:
            print("Tabela sistemas_packentry não existe — nada a migrar.")
            return
    except Exception as exc:
        print("Erro ao checar tabelas:", exc)
        return

    packs = conn.execute("SELECT id FROM sistemas_packs").fetchall()
    if not packs:
        print("Nenhum pack cadastrado para migrar.")
        return

    for p in packs:
        pid = p["id"]
        entries = conn.execute(
            "SELECT id, weight, note, player_field_id, player_gk_id FROM sistemas_packentry WHERE pack_id = ? ORDER BY weight DESC, id",
            (pid,)
        ).fetchall()
        if not entries:
            continue
        new_field = _load_json_list(conn.execute("SELECT field_players FROM sistemas_packs WHERE id = ?", (pid,)).fetchone()["field_players"])
        new_gk = _load_json_list(conn.execute("SELECT gk_players FROM sistemas_packs WHERE id = ?", (pid,)).fetchone()["gk_players"])
        changed = False
        for e in entries:
            pfid = e["player_field_id"]
            pgid = e["player_gk_id"]
            weight = int(e["weight"] or 1)
            note = e["note"] or ""
            if pfid:
                obj = fetch_field_player_object(conn, pfid) or {"id": str(pfid)}
                obj["weight"] = weight
                obj["note"] = note
                # prevent dup
                if not any(str(x.get("id")) == str(obj["id"]) for x in new_field):
                    new_field.append(obj)
                    changed = True
            elif pgid:
                obj = fetch_gk_player_object(conn, pgid) or {"id": str(pgid)}
                obj["weight"] = weight
                obj["note"] = note
                if not any(str(x.get("id")) == str(obj["id"]) for x in new_gk):
                    new_gk.append(obj)
                    changed = True
        if changed:
            print(f"Migrando pack {pid}: adicionando {len(new_field)} field + {len(new_gk)} gk entries (commit={not dry_run})")
            if not dry_run:
                conn.execute("UPDATE sistemas_packs SET field_players = ?, gk_players = ? WHERE id = ?",
                             (_dump_json_list(new_field), _dump_json_list(new_gk), pid))
    if not dry_run:
        conn.commit()
        print("Migração concluída e gravada.")
    else:
        print("Dry run concluído. Nenhuma alteração gravada.")

def menu():
    conn = ensure_db()
    try:
        while True:
            print("\n=== CRUD Packs (full object JSON) ===")
            print("1) Listar packs")
            print("2) Ver pack (detalhes)")
            print("3) Criar pack")
            print("4) Atualizar pack")
            print("5) Deletar pack")
            print("6) Adicionar jogador ao pack (guarda objeto completo)")
            print("7) Remover jogador do pack (por player id)")
            print("8) Abrir pack para user (simulação)")
            print("9) Migrar sistemas_packentry -> JSON full objects (dry-run primeiro!)")
            print("0) Sair")
            opt = input("Escolha: ").strip()
            if opt == "1": list_packs(conn)
            elif opt == "2": show_pack(conn)
            elif opt == "3": create_pack(conn)
            elif opt == "4": update_pack(conn)
            elif opt == "5": delete_pack(conn)
            elif opt == "6": add_player_to_pack(conn)
            elif opt == "7": remove_player_from_pack(conn)
            elif opt == "8": open_pack_for_user(conn)
            elif opt == "9":
                if input("Dry run? (s/N): ").strip().lower() == "s":
                    migrate_packentries_to_full_objects(conn, dry_run=True)
                else:
                    migrate_packentries_to_full_objects(conn, dry_run=False)
            elif opt == "0": break
            else: print("Inválido.")
    finally:
        conn.close()
        print("Conexão fechada.")

if __name__ == "__main__":
    menu()
