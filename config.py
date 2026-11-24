import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def csv_ids(name: str) -> set[int]:
    return {int(value.strip()) for value in os.getenv(name, "").split(",") if value.strip().isdigit()}


@dataclass(frozen=True)
class Settings:
    client_id: str
    client_secret: str
    bot_token: str
    redirect_uri: str
    guild_id: int
    verified_role_id: int
    log_channel_id: int
    staff_role_ids: frozenset[int]
    session_secret: str
    database_url: str
    port: int
    public_url: str


def load_settings() -> Settings:
    def required(name: str) -> str:
        value = os.getenv(name, "").strip()
        if not value:
            raise RuntimeError(f"Missing required environment variable: {name}")
        return value

    def required_id(name: str) -> int:
        value = required(name)
        if not value.isdigit():
            raise RuntimeError(f"{name} must be a numeric Discord ID")
        return int(value)

    secret = required("SESSION_SECRET")
    if len(secret) < 32:
        raise RuntimeError("SESSION_SECRET must contain at least 32 characters")

    return Settings(
        client_id=required("DISCORD_CLIENT_ID"),
        client_secret=required("DISCORD_CLIENT_SECRET"),
        bot_token=required("DISCORD_BOT_TOKEN"),
        redirect_uri=required("DISCORD_REDIRECT_URI"),
        guild_id=required_id("DISCORD_GUILD_ID"),
        verified_role_id=required_id("DISCORD_VERIFIED_ROLE_ID"),
        log_channel_id=required_id("DISCORD_LOG_CHANNEL_ID"),
        staff_role_ids=frozenset(csv_ids("DISCORD_STAFF_ROLE_IDS")),
        session_secret=secret,
        database_url=required("DATABASE_URL"),
        port=int(os.getenv("PORT", "8080")),
        public_url=os.getenv("PUBLIC_URL", "http://localhost:8080").rstrip("/"),
    )
