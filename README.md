# DGG's Ultimate Brasileirão Team Manager 2025

Projeto backend + templates para gerenciar times, abrir packs, montar escalações e jogar partidas simuladas. 

---

## Requisitos

* Python 3.10+

---

## Passo a passo — ambiente local (Linux / macOS / Windows)

1. **Clone o repositório**

```bash
git clone https://github.com/Geneblis/DGG-ultimate-soccer-2025
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
---
