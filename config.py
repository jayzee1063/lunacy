from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _load_env_file(path: Path = BASE_DIR / ".env") -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _int_env(name: str, default: int = 0) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    return int(value)


def _int_list_env(name: str, default: str = "") -> list[int]:
    value = os.getenv(name, default).strip()
    if not value:
        return []
    return [int(item.strip()) for item in value.split(",") if item.strip()]


_load_env_file()


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
COMMAND_GUILD_IDS = _int_list_env("COMMAND_GUILD_IDS")

RCON_HOST = os.getenv("RCON_HOST", "127.0.0.1")
RCON_PORT = _int_env("RCON_PORT", 25575)
RCON_PASSWORD = os.getenv("RCON_PASSWORD", "")

SUPPORT_ROLE_IDS = _int_list_env("SUPPORT_ROLE_IDS")
ACCEPTED_ROLE_ID = _int_env("ACCEPTED_ROLE_ID")
REMOVE_ROLE_AFTER_ACCEPT_ID = _int_env("REMOVE_ROLE_AFTER_ACCEPT_ID", 1516155084948639786)
TICKET_CATEGORY_ID = _int_env("TICKET_CATEGORY_ID")
RULES_CHANNEL_ID = _int_env("RULES_CHANNEL_ID", 1516159088151761107)

WHITELIST_COMMAND_TEMPLATE = os.getenv("WHITELIST_COMMAND_TEMPLATE", "swl add {nickname}")

LUNACY_PURPLE = 0xAC26FF
LUNACY_DARK = 0x27123D
LUNACY_PINK = 0xFF75E6
LUNACY_GREEN = 0x63FCB1
LUNACY_RED = 0xFF3D6E

TICKET_CATEGORY_NAME = os.getenv("TICKET_CATEGORY_NAME", "Lunacy Tickets")
FOOTER_TEXT = os.getenv("FOOTER_TEXT", "Lunacy Tickets")

# Старые slash-команды из прежней версии бота, которые нужно удалить у Discord.
STALE_COMMAND_NAMES = {
    "coinflip",
    "bomba",
    "flip",
    "setup_tickets",
    "ticket",
    "status",
    "info",
    "playnumber",
    "accept",
    "roles",
    "create_modal",
    "start_math_game",
    "stop_math_game",
    "setup_whitelist",
    "avatar",
    "addview",
    "cog",
}
