#!/usr/bin/env python3
"""
crud_goleiros.py
CRUD CLI para goleiros — tabela 'jogadores_goleiros' no bancos/db.sqlite3.

Regras:
- Imagens devem estar em 'imagens/players/<team>/...'
- Ao criar: tenta listar imagens do time; se não houver dá opção (buscar global / digitar manual / cancelar)
- Campos obrigatórios: club, country, photo_path
- position será fixo como "GoalkeeperZone"
"""

import os
import sqlite3
import uuid
from pathlib import Path
from statistics import median
import datetime

ROOT = Path(__file__).resolve().parent
BANCOS_DIR = ROOT / "bancos"
DB_PATH = BANCOS_DIR / "db.sqlite3"

IMAGES_ROOT = ROOT / "imagens" / "players"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jogadores_goleiros (
    id TEXT PRIMARY KEY,
    level INTEGER NOT NULL,
    name TEXT NOT NULL,
    position TEXT NOT NULL,
    club TEXT NOT NULL,
    country TEXT NOT NULL,
    photo_path TEXT NOT NULL,
    overall INTEGER,
    handling INTEGER,
    positioning INTEGER,
    reflex INTEGER,
    speed INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def ensure_db():
    BANCOS_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_ROOT.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()
    return conn

def scan_images():
    imgs = []
    if not IMAGES_ROOT.exists():
        return imgs
    for p in IMAGES_ROOT.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            imgs.append(p.relative_to(IMAGES_ROOT))
    imgs.sort()
    return imgs

def scan_images_for_team(team):
    imgs = []
    team_dir = IMAGES_ROOT / team
    if not team_dir.exists() or not team_dir.is_dir():
        return imgs
    for p in team_dir.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            imgs.append(p.relative_to(IMAGES_ROOT))
    imgs.sort()
    return imgs

def choose_from_list(imgs):
    if not imgs:
        return None
    while True:
        to_show = imgs[:50]
        for i, rel in enumerate(to_show, start=1):
            print(f"{i:3d}) {rel}")
        if len(imgs) > 50:
            print("... (e mais {})".format(len(imgs) - 50))
        s = input("Digite número para escolher, 'a' listar tudo, 's' buscar, 'q' cancelar: ").strip().lower()
        if s == "q":
            return None
        if s == "a":
            for i, rel in enumerate(imgs, start=1):
                print(f"{i:4d}) {rel}")
            sel = input("Número (ou q): ").strip().lower()
            if sel == "q":
                continue
            if sel.isdigit() and 1 <= int(sel) <= len(imgs):
                chosen = imgs[int(sel)-1]
                return str(Path("players") / chosen).replace("\\", "/")
            else:
                print("Inválido.")
                continue
        if s == "s":
            q = input("Buscar por (parte do nome ou subpasta): ").strip().lower()
            results = [r for r in imgs if q in str(r).lower()]
            if not results:
                print("Nenhum resultado para:", q)
                continue
            for i, rel in enumerate(results, start=1):
                print(f"{i:3d}) {rel}")
            sel = input("Escolha número (ou enter para voltar): ").strip()
            if sel == "":
                continue
            if sel.isdigit() and 1 <= int(sel) <= len(results):
                chosen = results[int(sel)-1]
                return str(Path("players") / chosen).replace("\\", "/")
            else:
                print("Inválido.")
                continue
        if s.isdigit():
            n = int(s)
            if 1 <= n <= min(50, len(imgs)):
                chosen = imgs[n-1]
                return str(Path("players") / chosen).replace("\\", "/")
            else:
                print("Número fora do intervalo.")
                continue
        print("Entrada inválida.")

def choose_image_interactive():
    imgs = scan_images()
    if not imgs:
        print("Nenhuma imagem encontrada em", IMAGES_ROOT)
        return None
    return choose_from_list(imgs)

def validate_and_normalize_manual_path(user_input):
    s = user_input.strip()
    if s.startswith("players/"):
        rel = Path(s[len("players/"):])
    else:
        rel = Path(s)
    full = IMAGES_ROOT / rel
    if full.exists() and full.is_file():
        return str(Path("players") / rel).replace("\\", "/")
    return None

def input_nonempty(prompt):
    while True:
        v = input(prompt).strip()
        if v:
            return v

def input_int(prompt, min_val=None, max_val=None, allow_empty=False, default=None):
    while True:
        s = input(prompt).strip()
        if s == "" and allow_empty:
            return default
        try:
            v = int(s)
        except ValueError:
            print("Valor inválido — digite um número inteiro.")
            continue
        if min_val is not None and v < min_val:
            print(f"Valor deve ser >= {min_val}")
            continue
        if max_val is not None and v > max_val:
            print(f"Valor deve ser <= {max_val}")
            continue
        return v

def compute_overall_gk(handling, positioning, reflex, speed):
    return int(median([handling, positioning, reflex, speed]))

def create_goleiro(conn):
    print("\n--- Criar Goleiro ---")
    level = input_int("Level (0-5): ", min_val=0, max_val=5)
    name = input_nonempty("Nome do goleiro: ")
    # position fixo
    position = "GoalkeeperZone"

    club = input_nonempty("Time (obrigatório): ")
    country = input_nonempty("País de origem (obrigatório): ")

    team_imgs = scan_images_for_team(club)
    photo_rel = None
    if team_imgs:
        print(f"\nImagens encontradas para o time '{club}':")
        photo_rel = choose_from_list(team_imgs)
    else:
        print(f"\nNenhuma imagem encontrada nesse time: {club}")
        while True:
            opt = input("Deseja (g) buscar globalmente, (m) digitar manualmente, (c) cancelar criação? [g/m/c]: ").strip().lower()
            if opt == "c":
                print("Criação cancelada.")
                return
            if opt == "g":
                photo_rel = choose_image_interactive()
                break
            if opt == "m":
                manual = input("Digite caminho relativo dentro de 'players/' (ex: 'santos/img.png') ou 'players/santos/img.png': ").strip()
                normalized = validate_and_normalize_manual_path(manual)
                if normalized:
                    photo_rel = normalized
                    print("Imagem selecionada:", photo_rel)
                    break
                else:
                    print("Caminho inválido ou arquivo não encontrado dentro de imagens/players/. Tente novamente.")
                    continue
            print("Opção inválida.")

    if not photo_rel:
        print("Sem imagem selecionada — cancelando.")
        return

    handling = input_int("Manuseio (inteiro): ")
    positioning = input_int("Posicionamento (inteiro): ")
    reflex = input_int("Reflexo (inteiro): ")
    speed = input_int("Velocidade (inteiro): ")

    overall_input = input("Overall (enter para calcular pela mediana): ").strip()
    if overall_input == "":
        overall = compute_overall_gk(handling, positioning, reflex, speed)
        print(f"Overall calculado (mediana): {overall}")
    else:
        try:
            overall = int(overall_input)
        except:
            overall = compute_overall_gk(handling, positioning, reflex, speed)

    gid = str(uuid.uuid4())
    created_at = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    sql = """
    INSERT INTO jogadores_goleiros
    (id, level, name, position, club, country, photo_path, overall, handling, positioning, reflex, speed, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    conn.execute(sql, (gid, level, name, position, club, country, photo_rel,
                    overall, handling, positioning, reflex, speed, created_at))
    conn.commit()
    print("Goleiro criado com id:", gid)
    print("Imagem referenciada (path relativo para uso com static):", photo_rel)

def list_goleiros(conn):
    print("\n--- Lista de Goleiros ---")
    cur = conn.execute("SELECT id, name, club, overall FROM jogadores_goleiros ORDER BY overall DESC, name;")
    rows = cur.fetchall()
    if not rows:
        print("Nenhum goleiro cadastrado.")
        return
    for r in rows:
        print(f"{r[0]} | {r[1]} | {r[2]} | Overall: {r[3]}")
    print(f"Total: {len(rows)}")

def show_goleiro(conn):
    gid = input("Digite o id do goleiro: ").strip()
    cur = conn.execute("SELECT * FROM jogadores_goleiros WHERE id = ?", (gid,))
    r = cur.fetchone()
    if not r:
        print("Goleiro não encontrado.")
        return
    cols = [d[0] for d in conn.execute("PRAGMA table_info(jogadores_goleiros)").fetchall()]
    print("\n--- Detalhes ---")
    for name, val in zip(cols, r):
        print(f"{name}: {val}")

def update_goleiro(conn):
    gid = input("Digite o id do goleiro a atualizar: ").strip()
    cur = conn.execute("SELECT * FROM jogadores_goleiros WHERE id = ?", (gid,))
    row = cur.fetchone()
    if not row:
        print("Goleiro não encontrado.")
        return

    print("Pressione Enter para manter o valor atual.")
    cols_info = conn.execute("PRAGMA table_info(jogadores_goleiros)").fetchall()
    cols = [c[1] for c in cols_info]
    current = dict(zip(cols, row))

    def prompt_update(field, cast=str, extra_prompt=""):
        cur_val = current.get(field)
        s = input(f"{field} [{cur_val}] {extra_prompt}: ").strip()
        if s == "":
            return cur_val
        return cast(s)

    level = prompt_update("level", int, "(0-5)")
    try:
        level = int(level)
    except:
        level = current["level"]
    if level < 0 or level > 5:
        level = current["level"]

    name = prompt_update("name", str)

    # position é fixo como GoalkeeperZone (mas mostramos)
    print("Position (fixo):", current.get("position", "GoalkeeperZone"))
    position = "GoalkeeperZone"

    club = prompt_update("club", str)
    if not club:
        club = current["club"]

    country = prompt_update("country", str)
    if not country:
        country = current["country"]

    photo_path = current["photo_path"]
    if club != current["club"]:
        team_imgs = scan_images_for_team(club)
        if team_imgs:
            print(f"Imagens encontradas para o time '{club}':")
            sel = choose_from_list(team_imgs)
            if sel:
                photo_path = sel
        else:
            print(f"Nenhuma imagem encontrada nesse time: {club}")
            opt = input("Deseja buscar globalmente (g), digitar manual (m) ou manter atual (enter)? [g/m/enter]: ").strip().lower()
            if opt == "g":
                sel = choose_image_interactive()
                if sel:
                    photo_path = sel
            elif opt == "m":
                manual = input("Digite caminho relativo dentro de 'players/' (ex: 'santos/img.png') ou 'players/santos/img.png': ").strip()
                normalized = validate_and_normalize_manual_path(manual)
                if normalized:
                    photo_path = normalized
                else:
                    print("Caminho inválido; mantendo atual.")
    else:
        if input("Deseja alterar a imagem? (s/N): ").strip().lower() == "s":
            sel = choose_image_interactive()
            if sel:
                photo_path = sel

    handling = prompt_update("handling", int)
    positioning = prompt_update("positioning", int)
    reflex = prompt_update("reflex", int)
    speed = prompt_update("speed", int)

    overall_input = input(f"overall [{current.get('overall')}] (enter para recalcular/usar atual or number): ").strip()
    if overall_input == "":
        overall = compute_overall_gk(int(handling), int(positioning), int(reflex), int(speed))
    else:
        try:
            overall = int(overall_input)
        except:
            overall = current.get("overall")

    sql = """
    UPDATE jogadores_goleiros SET
      level=?, name=?, position=?, club=?, country=?, photo_path=?,
      overall=?, handling=?, positioning=?, reflex=?, speed=?
    WHERE id=?
    """
    conn.execute(sql, (level, name, position, club, country, photo_path,
                       overall, handling, positioning, reflex, speed, gid))
    conn.commit()
    print("Atualizado.")

def delete_goleiro(conn):
    gid = input("Digite o id do goleiro a deletar: ").strip()
    confirm = input(f"Confirma exclusão de {gid}? (s/N): ").strip().lower()
    if confirm != "s":
        print("Operação cancelada.")
        return
    conn.execute("DELETE FROM jogadores_goleiros WHERE id = ?", (gid,))
    conn.commit()
    print("Deletado (se existia).")

def find_goleiro_by_name(conn):
    q = input("Nome ou parte do nome para buscar: ").strip()
    cur = conn.execute("SELECT id, name, club, overall FROM jogadores_goleiros WHERE name LIKE ? ORDER BY overall DESC;", (f"%{q}%",))
    rows = cur.fetchall()
    if not rows:
        print("Nenhum resultado.")
        return
    for r in rows:
        print(f"{r[0]} | {r[1]} | {r[2]} | Overall: {r[3]}")

def menu():
    conn = ensure_db()
    try:
        while True:
            print("\n=== CRUD Goleiros ===")
            print("1) Listar goleiros")
            print("2) Ver detalhes de um goleiro (por id)")
            print("3) Criar goleiro")
            print("4) Atualizar goleiro")
            print("5) Deletar goleiro")
            print("6) Buscar por nome")
            print("0) Sair")
            opt = input("Escolha: ").strip()
            if opt == "1":
                list_goleiros(conn)
            elif opt == "2":
                show_goleiro(conn)
            elif opt == "3":
                create_goleiro(conn)
            elif opt == "4":
                update_goleiro(conn)
            elif opt == "5":
                delete_goleiro(conn)
            elif opt == "6":
                find_goleiro_by_name(conn)
            elif opt == "0":
                break
            else:
                print("Opção inválida.")
    finally:
        conn.close()
        print("Conexão fechada. Tchau!")

if __name__ == "__main__":
    menu()
