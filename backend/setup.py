"""
Script de configuração inicial do backend ARKLAND-Player.
Execução: uv run setup.py

Detecta se .env existe. Se não, gera chaves seguras automaticamente
e solicita apenas os valores que não têm padrão (DB, Steam, etc.).
"""

import pathlib
import secrets
import sys

_ENV_PATH = pathlib.Path(__file__).parent / ".env"
_EXAMPLE_PATH = pathlib.Path(__file__).parent / ".env.example"


def _prompt(label: str, default: str = "", secret: bool = False) -> str:
    display_default = f" [{default}]" if default and not secret else (" [****]" if secret and default else "")
    try:
        value = input(f"  {label}{display_default}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return value or default


def _section(title: str) -> None:
    print(f"\n── {title} {'─' * (50 - len(title))}")


def main() -> None:
    print("=" * 56)
    print("  ARKLAND-Player — Setup do Backend")
    print("=" * 56)

    if _ENV_PATH.exists():
        print(f"\n✔  Arquivo .env já existe em: {_ENV_PATH}")
        try:
            answer = input("  Deseja recriar do zero? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if answer != "s":
            print("  Setup cancelado.")
            sys.exit(0)

    # ── Chaves geradas automaticamente ────────────────────────────────────────
    secret_key = secrets.token_hex(32)
    server_api_key = secrets.token_hex(16)

    print("\n  Chaves de segurança geradas automaticamente:")
    print(f"    SECRET_KEY      = {secret_key}")
    print(f"    SERVER_API_KEY  = {server_api_key}")

    # ── Banco de dados ─────────────────────────────────────────────────────────
    _section("Banco de dados MySQL")
    print("  Formato: mysql+pymysql://usuario:senha@host:3306/banco")
    db_url = _prompt(
        "DATABASE_URL",
        "mysql+pymysql://arkshop:senha@localhost:3306/arkshop",
    )

    # ── Steam ──────────────────────────────────────────────────────────────────
    _section("Steam API (https://steamcommunity.com/dev/apikey)")
    steam_key = _prompt("STEAM_API_KEY")
    if not steam_key:
        print("  [AVISO] STEAM_API_KEY vazia — login Steam não funcionará.")
    steam_return = _prompt(
        "STEAM_OPENID_RETURN_URL",
        "http://localhost:32444/auth/steam/callback",
    )

    # ── CORS ───────────────────────────────────────────────────────────────────
    _section("CORS (origens permitidas)")
    cors_raw = _prompt(
        "CORS_ORIGINS (separadas por vírgula)",
        "http://localhost,http://127.0.0.1",
    )
    # normaliza para JSON array
    origins = [o.strip() for o in cors_raw.split(",") if o.strip()]
    import json
    cors_json = json.dumps(origins)

    # ── Acesso Dev ─────────────────────────────────────────────────────────────
    _section("Usuário Dev (criado automaticamente na 1ª inicialização)")
    dev_user = _prompt("DEV_USERNAME", "dev")
    dev_pass = _prompt("DEV_PASSWORD", secrets.token_urlsafe(16), secret=True)
    master_pass = _prompt("MASTER_PASSWORD (senha para /auth/dev/elevate)", dev_pass, secret=True)

    # ── Grava .env ─────────────────────────────────────────────────────────────
    env_content = f"""# Gerado por setup.py — não comite este arquivo

# Banco de dados MySQL
DATABASE_URL={db_url}

# Chave secreta para JWTs (gerada automaticamente)
SECRET_KEY={secret_key}

# Chave de API compartilhada com o plugin ARK (gerada automaticamente)
SERVER_API_KEY={server_api_key}

# Steam
STEAM_API_KEY={steam_key}
STEAM_OPENID_RETURN_URL={steam_return}

# CORS
CORS_ORIGINS={cors_json}

# Acesso Dev
MASTER_PASSWORD={master_pass}
DEV_USERNAME={dev_user}
DEV_PASSWORD={dev_pass}
"""

    _ENV_PATH.write_text(env_content, encoding="utf-8")

    print(f"\n✔  Arquivo .env criado em: {_ENV_PATH}")
    print("   Guarde DEV_PASSWORD em local seguro:")
    print(f"   DEV_USERNAME = {dev_user}")
    print(f"   DEV_PASSWORD = {dev_pass}")
    print("\n  Para iniciar o backend: uv run main.py")
    print("=" * 56)


if __name__ == "__main__":
    main()
