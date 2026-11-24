import discord
from discord import app_commands
from discord.ext import commands

from moderation import staff_allowed


class Security(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="security-report", description="Create a staff security report")
    @app_commands.describe(subject="Short incident summary")
    async def security_report(self, interaction: discord.Interaction, subject: str) -> None:
        member = interaction.user
        if not staff_allowed(member, self.bot.settings.staff_role_ids):
            await interaction.response.send_message("Staff permission required.", ephemeral=True)
            return
        await self.bot.log_security("staff_report", member.id, {"subject": subject[:500]})
        await interaction.response.send_message("Security report recorded.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Security(bot))
