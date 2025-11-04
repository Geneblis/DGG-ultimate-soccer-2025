#!/usr/bin/env python3
"""
crud_pacotes.py (versão corrigida)

Correções:
- garante que 'note' nunca seja NULL (usa "" por padrão).
- trata sqlite3.IntegrityError ao inserir PackEntry (mensagem amigável, não crash).
- mantém UX do CLI (não fecha conexão por exceção).
"""
import sqlite3
import uuid
from pathlib import Path
import datetime
import random
import sys

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
    created_at TEXT NOT NULL
);
"""

CREATE_PACKENTRY_SQL = """
CREATE TABLE IF NOT EXISTS sistemas_packentry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id TEXT NOT NULL,
    player_type VARCHAR(8) NOT NULL,
    player_id CHAR(36) NOT NULL,
    weight INTEGER NOT NULL DEFAULT 1,
    note VARCHAR(200) DEFAULT '',
    FOREIGN KEY(pack_id) REFERENCES sistemas_packs(id) ON DELETE CASCADE
);
"""

def ensure_db():
    BANCOS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute(CREATE_PACKS_SQL)
    conn.execute(CREATE_PACKENTRY_SQL)
    conn.commit()
    return conn

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
        print("Coloque imagens em imagens/webmedia/packs/ e rode novamente, ou digite caminho manual.")
        return None
    while True:
        for i, r in enumerate(imgs[:50], start=1):
            print(f"{i:3d}) {r}")
        if len(imgs) > 50:
            print("... e mais", len(imgs)-50)
        opt = input("Escolha número para imagem, 'a' listar tudo, 'm' manual, 'q' cancelar: ").strip().lower()
        if opt == "q":
            return None
        if opt == "m":
            manual = input("Digite caminho relativo dentro de 'imagens/webmedia/packs/' (ex: event1/pack.png): ").strip()
            p = IMAGES_ROOT / manual
            if p.exists() and p.is_file():
                return str(Path("imagens/webmedia/packs") / manual).replace("\\","/")
            print("Arquivo não encontrado.")
            continue
        if opt == "a":
            for i, r in enumerate(imgs, start=1):
                print(f"{i:4d}) {r}")
            sel = input("Número (ou enter p/voltar): ").strip()
            if sel.isdigit() and 1 <= int(sel) <= len(imgs):
                chosen = imgs[int(sel)-1]
                return str(Path("imagens/webmedia/packs") / chosen).replace("\\","/")
            continue
        if opt.isdigit():
            n = int(opt)
            if 1 <= n <= min(50, len(imgs)):
                chosen = imgs[n-1]
                return str(Path("imagens/webmedia/packs") / chosen).replace("\\","/")
        print("Opção inválida.")

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

def lookup_player_name(conn, player_type, player_id):
    try:
        if player_type == "field":
            cur = conn.execute("SELECT name, club FROM jogadores_campo WHERE id = ?", (player_id,))
            r = cur.fetchone()
            if r:
                return f"{r['name']} ({r['club']})"
        elif player_type == "gk":
            cur = conn.execute("SELECT name, club FROM jogadores_goleiros WHERE id = ?", (player_id,))
            r = cur.fetchone()
            if r:
                return f"{r['name']} ({r['club']})"
    except Exception:
        pass
    return str(player_id)

# --- PACKS CRUD ---
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
            "INSERT INTO sistemas_packs (id, name, description, image_path, price, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (pid, name, description, image_path, price, created_at)
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
    cur = conn.execute("SELECT id, name, description, image_path, price, created_at FROM sistemas_packs WHERE id = ?", (pid,))
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
    cur = conn.execute("SELECT id, player_type, player_id, weight, note FROM sistemas_packentry WHERE pack_id = ? ORDER BY weight DESC, id", (pid,))
    entries = cur.fetchall()
    if not entries:
        print("Nenhum jogador associado a esse pack.")
        return
    print("\nJogadores possíveis no pack:")
    for e in entries:
        name = lookup_player_name(conn, e["player_type"], e["player_id"])
        print(f"  entry_id={e['id']} | type={e['player_type']} | player_id={e['player_id']} | weight={e['weight']} -> {name} | note: {e['note'] or '-'}")

def delete_pack(conn):
    pid = input_nonempty("Digite o id do pack a deletar: ")
    confirm = input(f"Confirma exclusão de {pid}? (s/N): ").strip().lower()
    if confirm != "s":
        print("Cancelado.")
        return
    conn.execute("DELETE FROM sistemas_packentry WHERE pack_id = ?", (pid,))
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

# --- PACKENTRY ---
def add_player_to_pack(conn):
    pid = input_nonempty("Digite o id do pack: ")
    cur = conn.execute("SELECT id FROM sistemas_packs WHERE id = ?", (pid,))
    if not cur.fetchone():
        print("Pack não encontrado.")
        return
    print("Adicionar jogador ao pack: escolha tipo e id do jogador.")
    ptype = input("Tipo ('field' para jogador de campo, 'gk' para goleiro): ").strip().lower()
    if ptype not in ("field", "gk"):
        print("Tipo inválido.")
        return
    player_id = input_nonempty("Digite o player id (UUID) (ou digite 'search' para procurar): ")
    if player_id.lower() == "search":
        q = input("Procurar por nome (parte): ").strip()
        if ptype == "field":
            cur = conn.execute("SELECT id, name, club FROM jogadores_campo WHERE name LIKE ? LIMIT 50", (f"%{q}%",))
        else:
            cur = conn.execute("SELECT id, name, club FROM jogadores_goleiros WHERE name LIKE ? LIMIT 50", (f"%{q}%",))
        rows = cur.fetchall()
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
    # nunca deixar note como NULL; usar string vazia se usuário não informou
    note = input("Observação (opcional): ").strip()
    if note == "":
        note = ""
    try:
        conn.execute(
            "INSERT INTO sistemas_packentry (pack_id, player_type, player_id, weight, note) VALUES (?, ?, ?, ?, ?)",
            (pid, ptype, str(player_id), int(weight), note)
        )
        conn.commit()
        print("Adicionado.")
    except sqlite3.IntegrityError as e:
        # caso de UNIQUE constraint (já existe) ou NOT NULL etc.
        if "UNIQUE constraint failed" in str(e):
            print("Este jogador já está associado a esse pack (entrada duplicada).")
        else:
            print("Erro de integridade ao adicionar entry:", e)

def remove_entry(conn):
    eid = input_nonempty("Digite entry id para remover: ")
    cur = conn.execute("SELECT id FROM sistemas_packentry WHERE id = ?", (eid,))
    if not cur.fetchone():
        print("Entry não encontrado.")
        return
    conn.execute("DELETE FROM sistemas_packentry WHERE id = ?", (eid,))
    conn.commit()
    print("Removido.")

# --- ABRIR PACK (simulação) ---
def open_pack_for_user(conn):
    user_id = input_nonempty("User id (UUID): ")
    pack_id = input_nonempty("Pack id (UUID): ")
    cur = conn.execute("SELECT price FROM sistemas_packs WHERE id = ?", (pack_id,))
    r = cur.fetchone()
    if not r:
        print("Pack não encontrado.")
        return
    price = r["price"]
    cur = conn.execute("SELECT coins FROM sistemas_users WHERE id = ?", (user_id,))
    ur = cur.fetchone()
    if not ur:
        print("User não encontrado.")
        return
    coins = ur["coins"]
    if coins < price:
        print("User não tem moedas suficientes:", coins, "<", price)
        return
    cur = conn.execute("SELECT player_type, player_id, weight FROM sistemas_packentry WHERE pack_id = ?", (pack_id,))
    entries = cur.fetchall()
    if not entries:
        print("Pack vazio (nenhuma entry).")
        return
    weights = [e["weight"] for e in entries]
    choice = random.choices(entries, weights=weights, k=1)[0]
    ptype, pid = choice["player_type"], choice["player_id"]
    player_name = lookup_player_name(conn, ptype, pid)
    conn.execute("UPDATE sistemas_users SET coins = coins - ? WHERE id = ?", (price, user_id))

    inserted = False
    try:
        cols_info = conn.execute("PRAGMA table_info(sistemas_inventory)").fetchall()
        cols = [c[1] for c in cols_info]
        if "content_type" in cols and "object_id" in cols:
            ctname = "sistemas.jogadorcampo" if ptype == "field" else "sistemas.jogadorgoleiro"
            cur = conn.execute("SELECT id, qty FROM sistemas_inventory WHERE user_id = ? AND content_type = ? AND object_id = ?", (user_id, ctname, str(pid)))
            ex = cur.fetchone()
            if ex:
                conn.execute("UPDATE sistemas_inventory SET qty = qty + 1 WHERE id = ?", (ex["id"],))
            else:
                conn.execute("INSERT INTO sistemas_inventory (user_id, content_type, object_id, qty, obtained_at) VALUES (?, ?, ?, ?, ?)",
                             (user_id, ctname, str(pid), 1, datetime.datetime.utcnow().isoformat() + "Z"))
            inserted = True
        elif "content_type_id" in cols and "object_id" in cols:
            print("Inventário usa content_type_id (numeric). Este script não consegue preencher content_type_id automaticamente.")
            inserted = False
        elif "player" in cols:
            if ptype != "field":
                inserted = False
            else:
                cur = conn.execute("SELECT id, qty FROM sistemas_inventory WHERE user_id = ? AND player = ?", (user_id, str(pid)))
                ex = cur.fetchone()
                if ex:
                    conn.execute("UPDATE sistemas_inventory SET qty = qty + 1 WHERE id = ?", (ex["id"],))
                else:
                    conn.execute("INSERT INTO sistemas_inventory (user_id, player, qty, obtained_at) VALUES (?, ?, ?, ?)",
                                 (user_id, str(pid), 1, datetime.datetime.utcnow().isoformat() + "Z"))
                inserted = True
        else:
            inserted = False
    except Exception as exc:
        print("Erro ao tentar inserir no inventário:", exc)
        inserted = False

    conn.commit()
    print(f"Pack aberto! Jogador recebido: {player_name} (type={ptype} id={pid})")
    if inserted:
        print("Inserido no inventário do usuário.")
    else:
        print("Não foi possível inserir automaticamente no inventário (schema custom). Verifique manualmente.")

# --- MENU ---
def menu():
    conn = ensure_db()
    try:
        while True:
            print("\n=== CRUD Packs ===")
            print("1) Listar packs")
            print("2) Ver pack (detalhes)")
            print("3) Criar pack")
            print("4) Atualizar pack")
            print("5) Deletar pack")
            print("6) Adicionar jogador ao pack")
            print("7) Remover jogador do pack (entry id)")
            print("8) Abrir pack para user (simulação)")
            print("0) Sair")
            opt = input("Escolha: ").strip()
            if opt == "1":
                list_packs(conn)
            elif opt == "2":
                show_pack(conn)
            elif opt == "3":
                create_pack(conn)
            elif opt == "4":
                update_pack(conn)
            elif opt == "5":
                delete_pack(conn)
            elif opt == "6":
                add_player_to_pack(conn)
            elif opt == "7":
                remove_entry(conn)
            elif opt == "8":
                open_pack_for_user(conn)
            elif opt == "0":
                break
            else:
                print("Inválido.")
    finally:
        conn.close()
        print("Conexão fechada.")

if __name__ == "__main__":
    menu()
