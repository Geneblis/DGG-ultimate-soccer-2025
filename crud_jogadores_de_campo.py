#!/usr/bin/env python3
"""
crud_jogadores_de_campo.py (atualizado)
- Posições por escolha.
- Se o usuário fornecer clube "santos", o script listará imagens em imagens/players/santos/.
  Se não houver, avisa "Nenhuma imagem encontrada nesse time" e permite buscar globalmente ou informar
  manualmente um caminho relativo dentro de players/.
- Mantém club, country e photo_path como obrigatórios.
"""

import os
import sqlite3
import uuid
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent
BANCOS_DIR = ROOT / "bancos"
DB_PATH = BANCOS_DIR / "db.sqlite3"

# A pasta onde você guarda as imagens para os players
IMAGES_ROOT = ROOT / "imagens" / "players"
POSITION_CHOICES = [
    "OffensiveZone",
    "NeutralZone",
    "DefensiveZone",
    "GoalkeeperZone",
]

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS jogadores_campo (
    id TEXT PRIMARY KEY,
    level INTEGER NOT NULL,
    name TEXT NOT NULL,
    position TEXT NOT NULL,
    club TEXT NOT NULL,
    country TEXT NOT NULL,
    photo_path TEXT NOT NULL,
    overall INTEGER,
    attack INTEGER,
    passing INTEGER,
    defense INTEGER,
    aggression INTEGER
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
    """Retorna lista de Paths relativos (a IMAGES_ROOT)."""
    imgs = []
    if not IMAGES_ROOT.exists():
        return imgs
    for p in IMAGES_ROOT.rglob("*"):
        if p.is_file() and not p.name.startswith("."):
            imgs.append(p.relative_to(IMAGES_ROOT))
    imgs.sort()
    return imgs

def scan_images_for_team(team):
    """Retorna lista de Paths relativos dentro de IMAGES_ROOT/team/..."""
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
    """
    Escolhe um item de uma lista de Paths (relativos a IMAGES_ROOT).
    Retorna string tipo 'players/<relative>' ou None.
    """
    if not imgs:
        return None
    while True:
        # mostra até 50 por vez
        to_show = imgs[:50]
        for i, rel in enumerate(to_show, start=1):
            print(f"{i:3d}) {rel}")
        if len(imgs) > 50:
            print("... (e mais {})".format(len(imgs) - 50))
        s = input("Digite número para escolher, 'a' para listar tudo, 's' para buscar, 'q' para cancelar: ").strip().lower()
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
    """Busca globalmente dentro de imagens/players e chama choose_from_list."""
    imgs = scan_images()
    if not imgs:
        print("Nenhuma imagem encontrada em", IMAGES_ROOT)
        return None
    return choose_from_list(imgs)

def validate_and_normalize_manual_path(user_input):
    """
    Aceita um caminho relativo (ex: 'players/santos/img.png') ou apenas 'santos/img.png'
    Retorna path relativo 'players/<...>' se existir dentro de IMAGES_ROOT, ou None.
    """
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

def choose_position(prompt="Position"):
    print("Posições válidas:")
    for i, p in enumerate(POSITION_CHOICES, start=1):
        print(f"  {i}) {p}")
    while True:
        sel = input(f"{prompt} (digite número ou nome): ").strip()
        if sel.isdigit():
            idx = int(sel) - 1
            if 0 <= idx < len(POSITION_CHOICES):
                return POSITION_CHOICES[idx]
        elif sel in POSITION_CHOICES:
            return sel
        print("Escolha inválida.")

def compute_overall_from_stats(attack, passing, defense, aggression):
    return int(median([attack, passing, defense, aggression]))

def create_player(conn):
    print("\n--- Criar Jogador de Campo ---")
    level = input_int("Level (0-5): ", min_val=0, max_val=5)
    name = input_nonempty("Nome do jogador: ")
    position = choose_position()

    # obrigatórios
    club = input_nonempty("Time (obrigatório): ")
    country = input_nonempty("País de origem (obrigatório): ")

    # tenta listar imagens do time
    team_imgs = scan_images_for_team(club)
    photo_rel = None
    if team_imgs:
        print(f"\nImagens encontradas para o time '{club}':")
        photo_rel = choose_from_list(team_imgs)
    else:
        print(f"\nNenhuma imagem encontrada nesse time: {club}")
        # dá opções: buscar globalmente, digitar manualmente, ou cancelar
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

    attack = input_int("Ataque (inteiro): ")
    passing = input_int("Passe (inteiro): ")
    defense = input_int("Defesa (inteiro): ")
    aggression = input_int("Agressividade (inteiro): ")

    overall_input = input("Overall (enter para calcular pela mediana): ").strip()
    if overall_input == "":
        overall = compute_overall_from_stats(attack, passing, defense, aggression)
        print(f"Overall calculado (mediana): {overall}")
    else:
        try:
            overall = int(overall_input)
        except ValueError:
            print("Overall inválido, usando cálculo automático.")
            overall = compute_overall_from_stats(attack, passing, defense, aggression)

    player_id = str(uuid.uuid4())
    sql = """
    INSERT INTO jogadores_campo
      (id, level, name, position, club, country, photo_path, overall, attack, passing, defense, aggression)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    conn.execute(sql, (player_id, level, name, position, club, country, photo_rel,
                       overall, attack, passing, defense, aggression))
    conn.commit()
    print("Criado jogador com id:", player_id)
    print("Imagem referenciada (path relativo para uso com static):", photo_rel)

def list_players(conn):
    print("\n--- Lista de Jogadores ---")
    cur = conn.execute("SELECT id, name, position, club, overall FROM jogadores_campo ORDER BY overall DESC, name;")
    rows = cur.fetchall()
    if not rows:
        print("Nenhum jogador cadastrado.")
        return
    for r in rows:
        print(f"{r[0]} | {r[1]} | {r[2]} | {r[3] or '-'} | Overall: {r[4]}")
    print(f"Total: {len(rows)}")

def show_player(conn):
    pid = input("Digite o id do jogador: ").strip()
    cur = conn.execute("SELECT * FROM jogadores_campo WHERE id = ?", (pid,))
    r = cur.fetchone()
    if not r:
        print("Jogador não encontrado.")
        return
    cols = [d[0] for d in conn.execute("PRAGMA table_info(jogadores_campo)").fetchall()]
    print("\n--- Detalhes ---")
    for name, val in zip(cols, r):
        print(f"{name}: {val}")

def update_player(conn):
    pid = input("Digite o id do jogador a atualizar: ").strip()
    cur = conn.execute("SELECT * FROM jogadores_campo WHERE id = ?", (pid,))
    row = cur.fetchone()
    if not row:
        print("Jogador não encontrado.")
        return

    print("Pressione Enter para manter o valor atual.")
    cols_info = conn.execute("PRAGMA table_info(jogadores_campo)").fetchall()
    cols = [c[1] for c in cols_info]
    current = dict(zip(cols, row))

    def prompt_update(field, cast=str, extra_prompt=""):
        cur_val = current.get(field)
        s = input(f"{field} [{cur_val}] {extra_prompt}: ").strip()
        if s == "":
            return cur_val
        return cast(s)

    level = prompt_update("level", int, "(0-5)")
    if isinstance(level, str):
        try:
            level = int(level)
        except:
            level = current["level"]
    if level < 0 or level > 5:
        print("Level inválido, mantendo atual.")
        level = current["level"]

    name = prompt_update("name", str)

    print("Posição atual:", current["position"])
    if input("Deseja alterar a posição? (s/N): ").strip().lower() == "s":
        position = choose_position()
    else:
        position = current["position"]

    club = prompt_update("club", str)
    if not club:
        club = current["club"]

    country = prompt_update("country", str)
    if not country:
        country = current["country"]

    # se o club foi alterado, tentar imagens do novo club
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
        # pedir se quer trocar a imagem
        if input("Deseja alterar a imagem? (s/N): ").strip().lower() == "s":
            sel = choose_image_interactive()
            if sel:
                photo_path = sel

    attack = prompt_update("attack", int)
    passing = prompt_update("passing", int)
    defense = prompt_update("defense", int)
    aggression = prompt_update("aggression", int)

    overall_input = input(f"overall [{current.get('overall')}] (enter para recalcular/usar atual or number): ").strip()
    if overall_input == "":
        overall = compute_overall_from_stats(attack, passing, defense, aggression)
        print(f"Overall recalculado: {overall}")
    else:
        try:
            overall = int(overall_input)
        except:
            overall = current.get("overall")

    sql = """
    UPDATE jogadores_campo SET
      level=?, name=?, position=?, club=?, country=?, photo_path=?,
      overall=?, attack=?, passing=?, defense=?, aggression=?
    WHERE id=?
    """
    conn.execute(sql, (level, name, position, club, country, photo_path,
                       overall, attack, passing, defense, aggression, pid))
    conn.commit()
    print("Atualizado.")

def delete_player(conn):
    pid = input("Digite o id do jogador a deletar: ").strip()
    confirm = input(f"Confirma exclusão de {pid}? (s/N): ").strip().lower()
    if confirm != "s":
        print("Operação cancelada.")
        return
    conn.execute("DELETE FROM jogadores_campo WHERE id = ?", (pid,))
    conn.commit()
    print("Deletado (se existia).")

def find_by_name(conn):
    q = input("Nome ou parte do nome para buscar: ").strip()
    cur = conn.execute("SELECT id, name, position, overall FROM jogadores_campo WHERE name LIKE ? ORDER BY overall DESC;", (f"%{q}%",))
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
            print("\n=== CRUD Jogadores de Campo ===")
            print("1) Listar jogadores")
            print("2) Ver detalhes de um jogador (por id)")
            print("3) Criar jogador")
            print("4) Atualizar jogador")
            print("5) Deletar jogador")
            print("6) Buscar por nome")
            print("0) Sair")
            opt = input("Escolha: ").strip()
            if opt == "1":
                list_players(conn)
            elif opt == "2":
                show_player(conn)
            elif opt == "3":
                create_player(conn)
            elif opt == "4":
                update_player(conn)
            elif opt == "5":
                delete_player(conn)
            elif opt == "6":
                find_by_name(conn)
            elif opt == "0":
                break
            else:
                print("Opção inválida.")
    finally:
        conn.close()
        print("Conexão fechada. Tchau!")

if __name__ == "__main__":
    menu()
