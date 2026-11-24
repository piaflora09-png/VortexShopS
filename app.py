import asyncio
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import discord
from aiohttp import web
from aiohttp_session import setup as setup_session, get_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
import asyncpg

from bot import VortexBot
from config import load_settings
from database import initialize_database
from verification import exchange_code, get_discord_identity


def sign_value(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


class Application:
    def __init__(self):
        self.settings = load_settings()
        self.pool = None
        self.bot = None

    async def startup(self, app):
        self.pool = await initialize_database(self.settings.database_url)
        self.bot = VortexBot(self.settings, self.pool)
        app["pool"] = self.pool
        app["bot"] = self.bot
        asyncio.create_task(self.bot.start(self.settings.bot_token))

    async def cleanup(self, app):
        if self.bot:
            await self.bot.close()
        if self.pool:
            await self.pool.close()

    async def health(self, request):
        bot_ready = bool(request.app["bot"] and request.app["bot"].is_ready())
        return web.json_response({
            "status": "ok",
            "bot": "online" if bot_ready else "offline",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def oauth_login(self, request):
        state = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(minutes=10)
        async with self.pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO oauth_states(state,csrf_token,expires_at) VALUES($1,$2,$3)",
                state, csrf, expires,
            )
        session = await get_session(request)
        session["oauth_csrf"] = csrf
        params = urlencode({
            "client_id": self.settings.client_id,
            "redirect_uri": self.settings.redirect_uri,
            "response_type": "code",
            "scope": "identify guilds",
            "state": state,
            "prompt": "consent",
        })
        raise web.HTTPFound(f"https://discord.com/oauth2/authorize?{params}")

    async def oauth_callback(self, request):
        state = request.query.get("state")
        code = request.query.get("code")
        session = await get_session(request)
        if not state or not code:
            raise web.HTTPBadRequest(text="Missing OAuth parameters")
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT csrf_token FROM oauth_states "
                "WHERE state=$1 AND used=FALSE AND expires_at>NOW()",
                state,
            )
            if not row or not hmac.compare_digest(row["csrf_token"], session.get("oauth_csrf", "")):
                raise web.HTTPBadRequest(text="Invalid or expired OAuth state")
            await connection.execute(
                "UPDATE oauth_states SET used=TRUE WHERE state=$1", state
            )
        token_data = await exchange_code(code, self.settings)
        identity = await get_discord_identity(token_data["access_token"])
        discord_id = int(identity["id"])
        role_failure = None
        async with self.pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO users(discord_id,username,avatar) VALUES($1,$2,$3) "
                "ON CONFLICT(discord_id) DO UPDATE SET username=EXCLUDED.username,"
                "avatar=EXCLUDED.avatar,updated_at=NOW()",
                discord_id, identity["username"], identity.get("avatar"),
            )
            guild = self.bot.get_guild(self.settings.guild_id)
            member = guild.get_member(discord_id) if guild else None
            verified = member is not None
            if member:
                role = guild.get_role(self.settings.verified_role_id)
                bot_member = guild.me
                if role is None:
                    role_failure = "Configured Verified role was not found in the server."
                elif role not in member.roles:
                    if bot_member is None or not bot_member.guild_permissions.manage_roles:
                        role_failure = "The bot needs the Manage Roles permission."
                    elif role >= bot_member.top_role:
                        role_failure = "Move the bot's highest role above the Verified role."
                    else:
                        try:
                            await member.add_roles(role, reason="Discord OAuth2 verification")
                        except discord.Forbidden:
                            role_failure = (
                                "Discord denied role assignment. Check the bot's Manage Roles "
                                "permission and role hierarchy."
                            )
            await connection.execute(
                "INSERT INTO verification_records(discord_id,guild_id,status,details)"
                " VALUES($1,$2,$3,$4)",
                discord_id, self.settings.guild_id,
                "verified" if verified and role_failure is None else "failed",
                ("Membership and Verified role confirmed" if verified and role_failure is None
                 else role_failure if verified else "Membership not found"),
            )
        if not verified:
            raise web.HTTPFound("/admin.html?status=not_member")
        if role_failure:
            raise web.HTTPServiceUnavailable(
                text=f"Server membership was confirmed, but verification could not finish: "
                     f"{role_failure} Ask a server administrator to fix the bot permissions, "
                     "then start login again."
            )
        session_id = str(uuid.uuid4())
        csrf = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(hours=8)
        async with self.pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO sessions(id,discord_id,csrf_token,expires_at) VALUES($1,$2,$3,$4)",
                uuid.UUID(session_id), discord_id, csrf, expires,
            )
        session["session_id"] = session_id
        session["csrf_token"] = csrf
        raise web.HTTPFound("/admin.html?status=verified")

    async def auth_status(self, request):
        session = await get_session(request)
        session_id = session.get("session_id")
        if not session_id:
            return web.json_response({"authenticated": False})
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                "SELECT u.discord_id,u.username,u.avatar,u.is_owner,"
                "s.csrf_token,s.expires_at FROM sessions s "
                "JOIN users u ON u.discord_id=s.discord_id "
                "WHERE s.id=$1 AND s.expires_at>NOW()", uuid.UUID(session_id),
            )
        if not row:
            return web.json_response({"authenticated": False})
        return web.json_response({
            "authenticated": True,
            "user": {"id": str(row["discord_id"]), "username": row["username"],
                     "avatar": row["avatar"], "owner": row["is_owner"]},
        })

    async def logout(self, request):
        session = await get_session(request)
        session_id = session.get("session_id")
        if session_id:
            async with self.pool.acquire() as connection:
                await connection.execute("DELETE FROM sessions WHERE id=$1", uuid.UUID(session_id))
        session.invalidate()
        raise web.HTTPFound("/")

    async def require_session(self, request) -> asyncpg.Record:
        session = await get_session(request)
        session_id = session.get("session_id")
        if not session_id:
            raise web.HTTPUnauthorized()
        row = await self.pool.fetchrow(
            "SELECT u.discord_id,u.username,u.is_owner,s.csrf_token "
            "FROM sessions s JOIN users u ON u.discord_id=s.discord_id "
            "WHERE s.id=$1 AND s.expires_at>NOW()", uuid.UUID(session_id),
        )
        if not row:
            raise web.HTTPUnauthorized()
        return row

    async def require_staff(self, request) -> asyncpg.Record:
        row = await self.require_session(request)
        if row["is_owner"]:
            return row
        guild = self.bot.get_guild(self.settings.guild_id)
        member = guild.get_member(row["discord_id"]) if guild else None
        if not member or not (
            member.guild_permissions.administrator or
            any(role.id in self.settings.staff_role_ids for role in member.roles)
        ):
            raise web.HTTPForbidden(text="Staff permission required")
        return row

    async def require_admin_action(self, request) -> asyncpg.Record:
        row = await self.require_staff(request)
        try:
            data = await request.json()
        except Exception:
            data = {}
        session = await get_session(request)
        provided = request.headers.get("X-CSRF-Token", data.get("csrf_token", ""))
        if not hmac.compare_digest(provided, session.get("csrf_token", "")):
            raise web.HTTPForbidden(text="Invalid CSRF token")
        return row

    async def overview(self, request):
        await self.require_staff(request)
        async with self.pool.acquire() as connection:
            verified = await connection.fetchval(
                "SELECT COUNT(*) FROM verification_records WHERE status='verified'"
            )
            moderation = await connection.fetchval("SELECT COUNT(*) FROM moderation_cases")
            tickets = await connection.fetchval("SELECT COUNT(*) FROM tickets WHERE status='open'")
            campaigns = await connection.fetchval("SELECT COUNT(*) FROM campaigns")
            security = await connection.fetchval("SELECT COUNT(*) FROM security_events")
            recent = await connection.fetch(
                "SELECT event_type,user_id,details,created_at FROM security_events "
                "ORDER BY created_at DESC LIMIT 8"
            )
        return web.json_response({
            "bot_status": "online" if self.bot.is_ready() else "offline",
            "verified": verified,
            "moderation": moderation,
            "open_tickets": tickets,
            "campaigns": campaigns,
            "security_events": security,
            "transaction_target_cents": 5000000,
            "recent_activity": [
                {"event_type": r["event_type"], "user_id": str(r["user_id"]) if r["user_id"] else None,
                 "details": r["details"], "created_at": r["created_at"].isoformat()}
                for r in recent
            ],
        })

    async def recent_records(self, request):
        await self.require_staff(request)
        resource = request.match_info["resource"]
        queries = {
            "security": (
                "SELECT id,event_type,user_id,details,created_at FROM security_events "
                "ORDER BY created_at DESC LIMIT 50"
            ),
            "moderation": (
                "SELECT id,user_id,staff_id,action,reason,created_at FROM moderation_cases "
                "ORDER BY created_at DESC LIMIT 50"
            ),
            "tickets": (
                "SELECT id,channel_id,user_id,category,status,assigned_staff_id,created_at,closed_at "
                "FROM tickets ORDER BY created_at DESC LIMIT 50"
            ),
            "campaigns": (
                "SELECT id,name,status,channel_ids,scheduled_at,created_at FROM campaigns "
                "ORDER BY created_at DESC LIMIT 50"
            ),
            "giveaways": (
                "SELECT id,prize_type,prize,status,ends_at,winner_id,created_at FROM giveaways "
                "ORDER BY created_at DESC LIMIT 50"
            ),
        }
        query = queries.get(resource)
        if query is None:
            raise web.HTTPNotFound(text="Unknown dashboard section")
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(query)

        def serialize(row):
            item = {}
            for key, value in row.items():
                if isinstance(value, datetime):
                    value = value.isoformat()
                elif key.endswith("_id") and value is not None:
                    value = str(value)
                elif key == "channel_ids":
                    value = [str(channel_id) for channel_id in value]
                item[key] = value
            return item

        return web.json_response({"items": [serialize(row) for row in rows]})

    async def transaction_history(self, request):
        await self.require_staff(request)
        period = request.query.get("period", "daily")
        intervals = {
            "daily": timedelta(days=1),
            "weekly": timedelta(days=7),
            "monthly": timedelta(days=30),
        }
        interval = intervals.get(period)
        if interval is None:
            raise web.HTTPBadRequest(text="Invalid report period")
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(
                "SELECT id,amount_cents,currency,status,description,created_at "
                "FROM transactions WHERE created_at >= NOW() - $1 "
                "ORDER BY created_at DESC LIMIT 50",
                interval,
            )
        return web.json_response({
            "items": [{
                "id": row["id"],
                "amount_cents": row["amount_cents"],
                "currency": row["currency"],
                "status": row["status"],
                "description": row["description"],
                "created_at": row["created_at"].isoformat(),
            } for row in rows],
        })

    async def transactions(self, request):
        actor = await self.require_admin_action(request)
        data = await request.json()
        amount = int(data.get("amount_cents", 0))
        status = str(data.get("status", "recorded"))[:30]
        description = str(data.get("description", ""))[:500]
        if amount < 0:
            raise web.HTTPBadRequest(text="amount_cents must be non-negative")
        if status not in {"recorded", "completed", "pending", "disputed", "cancelled"}:
            raise web.HTTPBadRequest(text="Invalid transaction status")
        async with self.pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO transactions(guild_id,user_id,amount_cents,currency,status,"
                "description,recorded_by) VALUES($1,$2,$3,$4,$5,$6,$7)",
                self.settings.guild_id,
                int(data["user_id"]) if str(data.get("user_id", "")).isdigit() else None,
                amount, str(data.get("currency", "USD"))[:10], status, description, actor["discord_id"],
            )
        return web.json_response({"ok": True})

    async def transaction_report(self, request):
        await self.require_staff(request)
        period = request.match_info.get("period", "daily")
        intervals = {"daily": "1 day", "weekly": "7 days", "monthly": "30 days"}
        if period not in intervals:
            raise web.HTTPBadRequest(text="Invalid report period")
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(
                f"SELECT COALESCE(SUM(amount_cents),0) AS volume,"
                f"COUNT(*) AS count FROM transactions "
                f"WHERE created_at >= NOW() - INTERVAL '{intervals[period]}'"
            )
        return web.json_response({"period": period, "volume_cents": row["volume"],
                                  "count": row["count"], "target_cents": 5000000})


def create_app() -> web.Application:
    application = Application()
    secret = application.settings.session_secret
    # EncryptedCookieStorage signs and AES-encrypts the session payload.
    # aiohttp-session package supplies Fernet-compatible 32-byte keys.
    derived = secret.encode()[:32].ljust(32, b"_")
    storage = EncryptedCookieStorage(
        derived,
        cookie_name="vortex_session",
        domain=None,
        httponly=True,
        secure=application.settings.public_url.startswith("https://"),
        samesite="Lax",
        max_age=28800,
    )
    app = web.Application()
    setup_session(app, storage)
    app["settings"] = application.settings
    app.on_startup.append(application.startup)
    app.on_cleanup.append(application.cleanup)

    dashboard = Path(__file__).resolve().parent / "dashboard"
    app.router.add_get("/", lambda request: web.FileResponse(dashboard / "index.html"))
    app.router.add_get("/admin.html", lambda request: web.FileResponse(dashboard / "admin.html"))
    app.router.add_get("/style.css", lambda request: web.FileResponse(dashboard / "style.css"))
    app.router.add_get("/dashboard.js", lambda request: web.FileResponse(dashboard / "dashboard.js"))
    app.router.add_get("/health", application.health)
    app.router.add_get("/auth/login", application.oauth_login)
    app.router.add_get("/auth/callback", application.oauth_callback)
    app.router.add_get("/auth/status", application.auth_status)
    app.router.add_post("/auth/logout", application.logout)
    app.router.add_get("/api/overview", application.overview)
    app.router.add_get("/api/records/{resource}", application.recent_records)
    app.router.add_get("/api/transaction-history", application.transaction_history)
    app.router.add_post("/api/transactions", application.transactions)
    app.router.add_get("/api/transactions/{period}", application.transaction_report)
    return app


if __name__ == "__main__":
    app = create_app()
    settings = app["settings"]
    web.run_app(app, host="0.0.0.0", port=settings.port)
