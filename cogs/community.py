import discord
from discord import app_commands
from discord.ext import commands


class Community(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticket", description="Create a private support ticket")
    @app_commands.describe(category="Support category")
    async def ticket(self, interaction: discord.Interaction, category: str) -> None:
        guild = interaction.guild
        category_object = discord.utils.get(guild.categories, name="Vortex Tickets")
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        channel = await guild.create_text_channel(
            f"ticket-{interaction.user.id}", category=category_object, overwrites=overwrites
        )
        async with self.bot.pool.acquire() as connection:
            await connection.execute(
                "INSERT INTO tickets(guild_id,channel_id,user_id,category) VALUES($1,$2,$3,$4)",
                guild.id, channel.id, interaction.user.id, category[:40],
            )
        await interaction.response.send_message(f"Ticket created: {channel.mention}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Community(bot))
