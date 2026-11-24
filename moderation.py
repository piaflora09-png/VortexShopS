import discord
from datetime import timedelta


def staff_allowed(member: discord.Member, staff_role_ids: frozenset[int]) -> bool:
    return member.guild_permissions.administrator or any(role.id in staff_role_ids for role in member.roles)


async def apply_action(guild: discord.Guild, user: discord.Member, action: str, reason: str,
                       duration_seconds: int | None = None) -> None:
    if getattr(user, "top_role", None) and getattr(guild.me, "top_role", None):
        if user.top_role >= guild.me.top_role:
            raise ValueError("Target role is above or equal to the bot role")
    if action == "warn":
        return
    if action == "timeout":
        await user.timeout(discord.utils.utcnow() + timedelta(seconds=duration_seconds or 300),
                           reason=reason)
    elif action == "kick":
        await user.kick(reason=reason)
    elif action == "ban":
        await user.ban(reason=reason)
    else:
        raise ValueError("Unsupported moderation action")
