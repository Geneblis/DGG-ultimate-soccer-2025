# DGG's Ultimate Brasileirão Team Manager — README (rápido e humano)

Projeto backend + templates para gerenciar times, abrir packs, montar escalações e jogar partidas simuladas. 

---

## Requisitos (mínimos)

* Python 3.10+ (recomendado 3.10/3.11)
* git (opcional)
* `pip` disponível
* Sistema com suporte a SQLite (vem por padrão com Python)

---

## Passo a passo — ambiente local (Linux / macOS / Windows)

1. **Clone o repositório** (se ainda não fez)

```bash
git clone <url-do-repo>
cd DGG-ultimate-soccer-2025
```

2. **Crie um virtualenv e ative**

* macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

* Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

* Windows (cmd.exe):

```cmd
python -m venv .venv
.venv\Scripts\activate
```

3. **Instale dependências**
   Se houver `requirements.txt`:

```bash
pip install -r requirements.txt
```

Se não houver, instale Django (versão usada no projeto) e outras libs que você precisar:

```bash
pip install django
```

4. **Configurações iniciais (migrations, criar superuser)**

```bash
python manage.py migrate
python manage.py createsuperuser
# siga as instruções para email/username/password
```


5. **Executar o servidor de desenvolvimento**

```bash
python manage.py runserver
# abre em http://127.0.0.1:8000
```

Para expor na rede (por ex. testar em outro dispositivo na mesma LAN):

```bash
python manage.py runserver 0.0.0.0:8000
```

--
## Comandos úteis

* `python manage.py makemigrations` — criar migrations locais (se mudar models)
* `python manage.py migrate` — aplicar migrations
* `python manage.py createsuperuser` — criar admin
* `python manage.py runserver 0.0.0.0:8000` — rodar servidor acessível na LAN
* `python manage.py shell` — console interativo do Django
* `python manage.py check` — checa problemas de configuração

---

## Executando em produção (observações rápidas)

* Não use `runserver` em produção. Use Gunicorn / uWSGI + Nginx.
* Configure `ALLOWED_HOSTS`, `DEBUG=False`, variáveis de ambiente seguras.
* Configure `STATIC_ROOT` e rode `python manage.py collectstatic`.
* Faça backup do `bancos/db.sqlite3` ou migre para um SGBD de produção (Postgres).
