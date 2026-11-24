import asyncio
import discord


async def send_authorized_campaign(channel: discord.TextChannel, template: str) -> discord.Message:
    if not channel.permissions_for(channel.guild.me).send_messages:
        raise PermissionError("Bot cannot send in the selected channel")
    await asyncio.sleep(2)
    return await channel.send(template)
