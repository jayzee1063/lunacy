from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WhitelistLink:
    guild_id: int
    discord_user_id: int
    nickname: str


class WhitelistLinkStore:
    """Persistent Discord account to Minecraft nickname associations."""

    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS whitelist_links (
                        guild_id INTEGER NOT NULL,
                        discord_user_id INTEGER NOT NULL,
                        nickname TEXT NOT NULL,
                        nickname_key TEXT NOT NULL,
                        approved_at INTEGER NOT NULL,
                        PRIMARY KEY (guild_id, nickname_key)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS whitelist_links_member_idx
                    ON whitelist_links (guild_id, discord_user_id)
                    """
                )

    def remember(self, guild_id: int, discord_user_id: int, nickname: str) -> None:
        nickname_key = self._nickname_key(nickname)
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO whitelist_links (
                        guild_id,
                        discord_user_id,
                        nickname,
                        nickname_key,
                        approved_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (guild_id, nickname_key) DO UPDATE SET
                        discord_user_id = excluded.discord_user_id,
                        nickname = excluded.nickname,
                        approved_at = excluded.approved_at
                    """,
                    (guild_id, discord_user_id, nickname, nickname_key, int(time.time())),
                )

    def links_for_member(self, guild_id: int, discord_user_id: int) -> list[WhitelistLink]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT guild_id, discord_user_id, nickname
                FROM whitelist_links
                WHERE guild_id = ? AND discord_user_id = ?
                ORDER BY nickname_key
                """,
                (guild_id, discord_user_id),
            ).fetchall()
        return [WhitelistLink(*row) for row in rows]

    def all_links(self) -> list[WhitelistLink]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT guild_id, discord_user_id, nickname
                FROM whitelist_links
                ORDER BY guild_id, discord_user_id, nickname_key
                """
            ).fetchall()
        return [WhitelistLink(*row) for row in rows]

    def forget(self, link: WhitelistLink) -> bool:
        with closing(self._connect()) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    DELETE FROM whitelist_links
                    WHERE guild_id = ? AND discord_user_id = ? AND nickname_key = ?
                    """,
                    (link.guild_id, link.discord_user_id, self._nickname_key(link.nickname)),
                )
        return cursor.rowcount > 0

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @staticmethod
    def _nickname_key(nickname: str) -> str:
        return nickname.casefold()
