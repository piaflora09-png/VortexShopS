import discord


async def close_ticket(channel: discord.TextChannel, reason: str) -> list[discord.Message]:
    messages = [message async for message in channel.history(limit=500, oldest_first=True)]
    await channel.send(f"Ticket closed: {reason}")
    await channel.edit(name=f"closed-{channel.id}", reason=reason)
    return messages
