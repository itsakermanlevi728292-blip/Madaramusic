"""Settings come from environment variables (or a local .env file). Nothing secret lives in the code."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


class ConfigError(SystemExit):
    """Raised with a human-friendly message when the setup is incomplete."""


def _int(env: dict, key: str, default: int) -> int:
    raw = (env.get(key) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"[config] {key} must be a number, got {raw!r}")


def _bool(env: dict, key: str, default: bool) -> bool:
    raw = (env.get(key) or "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _ids(env: dict, key: str) -> frozenset[int]:
    out = set()
    for part in re.split(r"[,\s]+", env.get(key) or ""):
        if part:
            try:
                out.add(int(part))
            except ValueError:
                raise ConfigError(f"[config] {key} must be numeric Telegram user IDs, got {part!r}")
    return frozenset(out)


def _url(env: dict, key: str, default: str = "") -> str:
    value = (env.get(key) or default).strip()
    if value and not re.match(r"^https?://", value):
        raise ConfigError(f"[config] {key} must start with https:// (got {value!r})")
    return value


@dataclass(frozen=True)
class Config:
    # Telegram
    api_id: int
    api_hash: str
    bot_token: str
    session_strings: tuple[str, ...]
    owner_ids: frozenset[int]
    # Your own API (https://github.com/dev-shubh-madara/Yt-paid-api-bot)
    api_url: str
    api_key: str
    # Look and feel
    bot_name: str = "Shubh Music"
    support_chat: str = ""
    support_channel: str = ""
    start_image_url: str = ""
    # Behaviour
    log_chat_id: int = 0
    data_dir: str = "data"
    timezone: str = "Asia/Kolkata"
    duration_limit_min: int = 600
    max_queue: int = 50
    playlist_import_limit: int = 25
    auto_leave_seconds: int = 300
    plays_per_chat_per_day: int = 0  # 0 = unlimited. Protects your API quota from one busy group.
    command_cooldown_seconds: float = 1.5
    song_max_mb: int = 100
    health_port: int = 0
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, env: dict | None = None) -> "Config":
        env = dict(os.environ if env is None else env)
        missing = [k for k in ("API_ID", "API_HASH", "BOT_TOKEN", "API_URL", "API_KEY") if not (env.get(k) or "").strip()]
        if not (env.get("STRING_SESSION") or "").strip():
            missing.append("STRING_SESSION")
        if missing:
            raise ConfigError(
                "\n[config] Missing required settings: " + ", ".join(missing) + "\n"
                "  API_ID / API_HASH  -> https://my.telegram.org\n"
                "  BOT_TOKEN          -> @BotFather\n"
                "  STRING_SESSION     -> a Pyrogram string session of the assistant account (see README)\n"
                "  API_URL / API_KEY  -> your API deployment and the key from its /portal page\n"
            )
        sessions = tuple(
            s.strip()
            for s in (env.get("STRING_SESSION"), env.get("STRING_SESSION2"), env.get("STRING_SESSION3"))
            if s and s.strip()
        )
        api_url = _url(env, "API_URL").rstrip("/")
        if not api_url:
            raise ConfigError("[config] API_URL must be set to your API address, e.g. https://yt-api.example.com")
        port = _int(env, "PORT", 0) if _bool(env, "HEALTH_SERVER", True) else 0
        return cls(
            api_id=_int(env, "API_ID", 0),
            api_hash=env["API_HASH"].strip(),
            bot_token=env["BOT_TOKEN"].strip(),
            session_strings=sessions,
            owner_ids=_ids(env, "OWNER_ID"),
            api_url=api_url,
            api_key=env["API_KEY"].strip(),
            bot_name=(env.get("BOT_NAME") or "Shubh Music").strip(),
            support_chat=_url(env, "SUPPORT_CHAT"),
            support_channel=_url(env, "SUPPORT_CHANNEL"),
            start_image_url=_url(env, "START_IMG_URL"),
            log_chat_id=_int(env, "LOG_CHAT_ID", 0),
            data_dir=(env.get("DATA_DIR") or "data").strip(),
            timezone=(env.get("TIMEZONE") or "Asia/Kolkata").strip(),
            duration_limit_min=_int(env, "DURATION_LIMIT_MIN", 600),
            max_queue=max(1, _int(env, "MAX_QUEUE", 50)),
            playlist_import_limit=max(1, min(100, _int(env, "PLAYLIST_IMPORT_LIMIT", 25))),
            auto_leave_seconds=max(30, _int(env, "AUTO_LEAVE_SECONDS", 300)),
            plays_per_chat_per_day=max(0, _int(env, "PLAYS_PER_CHAT_PER_DAY", 0)),
            command_cooldown_seconds=float(env.get("COMMAND_COOLDOWN_SECONDS") or 1.5),
            song_max_mb=max(5, _int(env, "SONG_MAX_MB", 100)),
            health_port=port,
        )

    @property
    def duration_limit_seconds(self) -> int:
        return self.duration_limit_min * 60
