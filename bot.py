import asyncio
import secrets
from datetime import timedelta

import discord
from discord.ext import commands, tasks

from moderation import apply_action, staff_allowed
from security import ActivityGuard


class VortexBot(commands.Bot):
    def __init__(self, settings, pool):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings
        self.pool = pool
        self.guard = ActivityGuard()

    async def setup_hook(self) -> None:
        await self.load_extension("cogs.security")
        await self.load_extension("cogs.moderation")
        await self.load_extension("cogs.community")
        guild = discord.Object(id=self.settings.guild_id)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        print(f"Synced {len(synced)} slash commands to guild {self.settings.guild_id}")

    async def log_security(self, event_type: str, user_id: int | None, details: dict) -> None:
        async with self.pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO security_events(guild_id,event_type,user_id,details) VALUES($1,$2,$3,$4)",
                self.settings.guild_id, event_type, user_id, details,
            )
        channel = self.get_channel(self.settings.log_channel_id)
        if channel:
            await channel.send(
                f"**Security event:** `{event_type}`"
                + (f" | User: <@{user_id}>" if user_id else "")
                + f" | {details}",
                allowed_mentions=discord.AllowedMentions.none(),
            )

    async def on_ready(self) -> None:
        print(f"Vortex bot ready as {self.user}")

    async def on_member_join(self, member: discord.Member) -> None:
        if member.guild.id != self.settings.guild_id:
            return
        if self.guard.check_join():
            await self.log_security("raid_monitor", member.id, {"joined_recently": True})

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        reason = self.guard.check_message(message.author.id, len(message.raw_mentions))
        if reason:
            await self.log_security(reason, message.author.id, {
                "channel_id": message.channel.id,
                "message_id": message.id,
            })
        await self.process_commands(message)
