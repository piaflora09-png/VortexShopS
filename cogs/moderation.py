import discord
from discord import app_commands
from discord.ext import commands

from moderation import apply_action, staff_allowed


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def record(self, interaction, member: discord.Member, action: str, reason: str,
                     duration: int | None = None) -> None:
        await apply_action(interaction.guild, member, action, reason, duration)
        async with self.bot.pool.acquire() as connection:
            case_id = await connection.fetchval(
                "INSERT INTO moderation_cases(guild_id,user_id,staff_id,action,reason) "
                "VALUES($1,$2,$3,$4,$5) RETURNING id",
                interaction.guild_id, member.id, interaction.user.id, action, reason,
            )
        await interaction.response.send_message(
            f"Case #{case_id}: **{action}** recorded for {member.mention}.",
            ephemeral=True,
        )

    @app_commands.command(name="warn", description="Record a warning")
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        if not staff_allowed(interaction.user, self.bot.settings.staff_role_ids):
            await interaction.response.send_message("Staff permission required.", ephemeral=True)
            return
        await self.record(interaction, member, "warn", reason)

    @app_commands.command(name="timeout", description="Temporarily timeout a member")
    async def timeout(self, interaction: discord.Interaction, member: discord.Member,
                      minutes: app_commands.Range[int, 1, 10080], reason: str) -> None:
        if not staff_allowed(interaction.user, self.bot.settings.staff_role_ids):
            await interaction.response.send_message("Staff permission required.", ephemeral=True)
            return
        await self.record(interaction, member, "timeout", reason, minutes * 60)

    @app_commands.command(name="kick", description="Kick a member")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        if not staff_allowed(interaction.user, self.bot.settings.staff_role_ids):
            await interaction.response.send_message("Staff permission required.", ephemeral=True)
            return
        await self.record(interaction, member, "kick", reason)

    @app_commands.command(name="ban", description="Ban a member")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str) -> None:
        if not staff_allowed(interaction.user, self.bot.settings.staff_role_ids):
            await interaction.response.send_message("Staff permission required.", ephemeral=True)
            return
        await self.record(interaction, member, "ban", reason)


async def setup(bot):
    await bot.add_cog(Moderation(bot))
