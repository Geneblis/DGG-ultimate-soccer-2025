#!/usr/bin/env python3
import sqlite3
import uuid
from pathlib import Path
import datetime
import json

ROOT = Path(__file__).resolve().parent
BANCOS_DIR = ROOT / "bancos"
DB_PATH = BANCOS_DIR / "db.sqlite3"

IMAGES_ROOT = ROOT / "imagens" / "webmedia" / "packs"


def ensure_db():
    BANCOS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = ON;")
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
        opt = input("Escolha número para imagem, 'a' listar tudo, 'm' manual, 'q' nenhuma: ").strip().lower()
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
            print("Digite um número inteiro.")

# helpers para mostrar nome do jogador consultando o DB (se existir)
def lookup_player_name(conn, player_type, player_id):
    try:
        if player_type == "field":
            cur = conn.execute("SELECT name, club FROM jogadores_campo WHERE id = ?", (player_id,))
            r = cur.fetchone()
            if r: return f"{r[0]} ({r[1]})"
        elif player_type == "gk":
            cur = conn.execute("SELECT name, club FROM jogadores_goleiros WHERE id = ?", (player_id,))
            r = cur.fetchone()
            if r: return f"{r[0]} ({r[1]})"
    except Exception:
        pass
    return player_id

def create_pack(conn):
    print("\n--- Criar Pack ---")
    name = input_nonempty("Nome do pack: ")
    description = input("Descrição (opcional): ").strip()
    price = input_int("Preço em moedas: ")
    print("Escolha imagem do pack (opcional):")
    image = choose_image_interactive()
    created_at = datetime.datetime.utcnow().isoformat() + "Z"
    pid = str(uuid.uuid4())
    conn.execute("INSERT INTO sistemas_packs (id, name, description, image, price, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (pid, name, description, image, price, created_at))
    conn.commit()
    print("Pack criado:", pid)

def list_packs(conn):
    cur = conn.execute("SELECT id, name, price, created_at FROM sistemas_packs ORDER BY created_at DESC;")
    rows = cur.fetchall()
    if not rows:
        print("Nenhum pack cadastrado.")
        return
    print("\n--- Packs ---")
    for r in rows:
        print(f"{r[0]} | {r[1]} | {r[2]} coins | criado: {r[3]}")

def show_pack(conn):
    pid = input("Digite o id do pack: ").strip()
    cur = conn.execute("SELECT id, name, description, image, price, created_at FROM sistemas_packs WHERE id = ?", (pid,))
    r = cur.fetchone()
    if not r:
        print("Pack não encontrado.")
        return
    print("\n=== Detalhes do Pack ===")
    print("ID:", r[0])
    print("Nome:", r[1])
    print("Descrição:", r[2] or "-")
    print("Imagem (relative):", r[3] or "-")
    print("Preço:", r[4])
    print("Criado:", r[5])
    # listar entries
    cur = conn.execute("SELECT id, player_type, player_id, weight FROM sistemas_packentry WHERE pack_id = ? ORDER BY weight DESC, id", (pid,))
    entries = cur.fetchall()
    if not entries:
        print("Nenhum jogador associado a esse pack.")
        return
    print("\nJogadores possíveis no pack:")
    for e in entries:
        name = lookup_player_name(conn, e[1], e[2])
        print(f"  entry_id={e[0]} | type={e[1]} | player_id={e[2]} | weight={e[3]} -> {name}")

def delete_pack(conn):
    pid = input("Digite o id do pack a deletar: ").strip()
    confirm = input(f"Confirma exclusão de {pid}? (s/N): ").strip().lower()
    if confirm != "s":
        print("Cancelado.")
        return
    conn.execute("DELETE FROM sistemas_packentry WHERE pack_id = ?", (pid,))
    conn.execute("DELETE FROM sistemas_packs WHERE id = ?", (pid,))
    conn.commit()
    print("Deletado (se existia).")

def update_pack(conn):
    pid = input("Digite o id do pack a atualizar: ").strip()
    cur = conn.execute("SELECT id, name, description, image, price FROM sistemas_packs WHERE id = ?", (pid,))
    r = cur.fetchone()
    if not r:
        print("Pack não encontrado.")
        return
    print("Pressione Enter para manter valor atual.")
    name = input(f"Nome [{r[1]}]: ").strip() or r[1]
    description = input(f"Descrição [{r[2] or ''}]: ").strip() or r[2]
    price_input = input(f"Preço [{r[4]}]: ").strip()
    price = int(price_input) if price_input.isdigit() else r[4]
    img_opt = input("Trocar imagem? (s/N): ").strip().lower()
    image = r[3]
    if img_opt == "s":
        image = choose_image_interactive()
    conn.execute("UPDATE packs SET name=?, description=?, image=?, price=? WHERE id=?",
                 (name, description, image, price, pid))
    conn.commit()
    print("Atualizado.")

def add_player_to_pack(conn):
    pid = input("Digite o id do pack: ").strip()
    cur = conn.execute("SELECT id FROM sistemas_packs WHERE id = ?", (pid,))
    if not cur.fetchone():
        print("Pack não encontrado.")
        return
    print("Adicionar jogador ao pack: escolha tipo e id do jogador.")
    ptype = input("Tipo ('field' para jogador campo, 'gk' para goleiro): ").strip().lower()
    if ptype not in ("field", "gk"):
        print("Tipo inválido.")
        return
    player_id = input_nonempty("Digite o player id (UUID) (ou 'search' para procurar): ")
    if player_id == "search":
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
            print(f"{i}) {rr[0]} | {rr[1]} ({rr[2]})")
        sel = input("Escolha número: ").strip()
        if not sel.isdigit() or not (1 <= int(sel) <= len(rows)):
            print("Escolha inválida.")
            return
        player_id = rows[int(sel)-1][0]
    weight = input_int("Weight (probabilidade relativa, inteiro, default 1): ",)
    if weight is None:
        weight = 1
    conn.execute("INSERT INTO sistemas_packentry (pack_id, player_type, player_id, weight) VALUES (?, ?, ?, ?)",
                 (pid, ptype, str(player_id), weight))
    conn.commit()
    print("Adicionado.")

def remove_entry(conn):
    eid = input("Digite entry id para remover: ").strip()
    cur = conn.execute("SELECT id FROM sistemas_packentry WHERE id = ?", (eid,))
    if not cur.fetchone():
        print("Entry não encontrado.")
        return
    conn.execute("DELETE FROM sistemas_packentry WHERE id = ?", (eid,))
    conn.commit()
    print("Removido.")

def open_pack_for_user(conn):
    """
    Operação que representaria 'abrir' o pack:
    - checa se user tem moedas suficientes (usuário informado pelo UUID)
    - subtrai o preço das moedas do usuário (tabela sistemas_users)
    - seleciona aleatoriamente um jogador do pack com base no weight
    - adiciona item no inventory (tabela sistemas_inventory) ou incrementa qty se já existir
    OBS: essa função é básica — assume tabelas sistemas_users e sistemas_inventory existentes.
    """
    import random
    user_id = input_nonempty("User id (UUID): ")
    pack_id = input_nonempty("Pack id (UUID): ")
    # checar pack
    cur = conn.execute("SELECT price FROM sistemas_packs WHERE id = ?", (pack_id,))
    r = cur.fetchone()
    if not r:
        print("Pack não encontrado.")
        return
    price = r[0]
    # checar user coins
    try:
        cur = conn.execute("SELECT coins FROM sistemas_users WHERE id = ?", (user_id,))
        ur = cur.fetchone()
        if not ur:
            print("User não encontrado.")
            return
        coins = ur[0]
        if coins < price:
            print("User não tem moedas suficientes:", coins, "<", price)
            return
        # escolher entry
        cur = conn.execute("SELECT player_type, player_id, weight FROM sistemas_packentry WHERE pack_id = ?", (pack_id,))
        entries = cur.fetchall()
        if not entries:
            print("Pack vazio (nenhuma entry).")
            return
        weights = [e[2] for e in entries]
        choice = random.choices(entries, weights=weights, k=1)[0]
        ptype, pid = choice[0], choice[1]
        player_name = lookup_player_name(conn, ptype, pid)
        # debitar moedas
        conn.execute("UPDATE sistemas_users SET coins = coins - ? WHERE id = ?", (price, user_id))
        # inserir no inventory: tentamos inserir na sua tabela de inventory genérica se existir
        # tentaremos inserir nas colunas existentes: se houver sistemas_inventory (generic content), adaptamos; caso contrário,
        # tentamos a tabela antiga (sistemas_inventory com player FK em jogador_campo).
        inserted = False
        # caso tenha colunas content_type/object_id (generic), vamos inserir genérico
        try:
            cur = conn.execute("PRAGMA table_info(sistemas_inventory)").fetchall()
            cols = [c[1] for c in cur]
            if "content_type_id" in cols or ("content_type" in cols and "object_id" in cols):
                # tentativa simples: inserir as content_type (string) + object_id
                # NOTE: este trecho é adaptativo — ajuste conforme seu schema real.
                ct_name = "sistemas.jogadorcampo" if ptype == "field" else "sistemas.jogadorgoleiro"
                # if content_type_id present, we can't easily insert without ContentType table; skip
                if "content_type" in cols and "object_id" in cols:
                    conn.execute("INSERT OR IGNORE INTO sistemas_inventory (user_id, content_type, object_id, qty, obtained_at) VALUES (?, ?, ?, ?, ?)",
                                 (user_id, ct_name, pid, 1, datetime.datetime.utcnow().isoformat() + "Z"))
                    inserted = True
            else:
                # fallback: try sistemas_inventory with user FK and player FK (JogadorCampo)
                if ptype == "field":
                    conn.execute("INSERT INTO sistemas_inventory (user_id, player, qty, obtained_at) VALUES (?, ?, ?, ?)",
                                 (user_id, pid, 1, datetime.datetime.utcnow().isoformat() + "Z"))
                    inserted = True
                else:
                    # cannot handle GK if table expects player FK only to jogadores_campo
                    inserted = False
        except Exception:
            inserted = False

        conn.commit()
        print(f"Pack aberto! Jogador recebido: {player_name} (type={ptype} id={pid})")
        if inserted:
            print("Inserido no inventário do usuário.")
        else:
            print("Não foi possível inserir automaticamente no inventário (schema custom). Verifique e insira manualmente se precisar.")
    except Exception as ex:
        print("Erro ao abrir pack:", ex)
        conn.rollback()

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
            print("8) Abrir pack para user (demo)")
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
