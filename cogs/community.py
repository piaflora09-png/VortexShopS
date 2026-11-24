import re
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from moderation import staff_allowed

DEFAULT_CATEGORIES = ["General Support", "Report a User", "Billing"]
PANEL_SELECT_ID = "vortex:ticket-panel:category"
TICKET_CLOSE_ID = "vortex:ticket:close"


def parse_categories(value: str) -> list[str]:
    categories = [item.strip()[:100] for item in value.split(";") if item.strip()]
    if not categories or len(categories) > 25:
        raise ValueError("Provide between 1 and 25 categories separated by semicolons.")
    if len({category.casefold() for category in categories}) != len(categories):
        raise ValueError("Ticket categories must be unique.")
    return categories


def validate_image_url(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    value = value.strip()
    parsed = urlparse(value)
    if (
        len(value) > 2000
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or any(character.isspace() for character in value)
    ):
        raise ValueError("Image URL must be a valid public HTTPS URL.")
    return value


class TicketCategorySelect(discord.ui.Select):
    def __init__(self, bot, categories: list[str]):
        super().__init__(
            custom_id=PANEL_SELECT_ID,
            placeholder="Choose a ticket category",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=category, value=category)
                for category in categories
            ],
        )
        self.bot = bot

    async def callback(self, interaction: discord.Interaction) -> None:
        await create_ticket(interaction, self.bot, self.values[0])


class TicketPanelView(discord.ui.LayoutView):
    def __init__(
        self,
        bot,
        title: str,
        description: str,
        categories: list[str],
        image_url: str | None = None,
    ):
        super().__init__(timeout=None)
        components = [discord.ui.TextDisplay(f"# {title}\n{description}")]
        if image_url:
            components.append(discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=image_url, description=title[:100])
            ))
        components.extend([
            discord.ui.Separator(),
            discord.ui.ActionRow(TicketCategorySelect(bot, categories)),
        ])
        self.add_item(discord.ui.Container(
            *components,
            accent_color=discord.Color.from_rgb(57, 255, 136),
        ))


class VerificationPanelView(discord.ui.LayoutView):
    def __init__(
        self,
        public_url: str,
        title: str,
        description: str,
        image_url: str | None = None,
    ):
        super().__init__(timeout=None)
        components = [discord.ui.TextDisplay(f"# {title}\n{description}")]
        if image_url:
            components.append(discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=image_url, description=title[:100])
            ))
        components.extend([
            discord.ui.Separator(),
            discord.ui.ActionRow(discord.ui.Button(
                label="Verify with Discord",
                style=discord.ButtonStyle.link,
                url=f"{public_url.rstrip('/')}/auth/login",
            )),
        ])
        self.add_item(discord.ui.Container(
            *components,
            accent_color=discord.Color.from_rgb(155, 92, 255),
        ))


class TicketCloseButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Close ticket",
            style=discord.ButtonStyle.danger,
            custom_id=TICKET_CLOSE_ID,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        cog = interaction.client.get_cog("Community")
        if cog is None:
            await interaction.response.send_message(
                "Ticket controls are temporarily unavailable.", ephemeral=True
            )
            return
        await cog.close_ticket(interaction)


class TicketControlsView(discord.ui.LayoutView):
    def __init__(self, note: str, closed: bool = False):
        super().__init__(timeout=None)
        button = TicketCloseButton()
        button.disabled = closed
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(note),
            discord.ui.ActionRow(button),
        ))


async def create_ticket(
    interaction: discord.Interaction,
    bot,
    category_name: str,
) -> None:
    guild = interaction.guild
    if guild is None or guild.id != bot.settings.guild_id:
        await interaction.response.send_message(
            "Tickets can only be opened in the configured server.", ephemeral=True
        )
        return

    async with bot.pool.acquire() as connection:
        config = await connection.fetchrow(
            "SELECT categories FROM ticket_panel_settings WHERE id=1"
        )
        open_ticket = await connection.fetchrow(
            "SELECT channel_id FROM tickets WHERE guild_id=$1 AND user_id=$2 "
            "AND status='open' LIMIT 1",
            guild.id,
            interaction.user.id,
        )
    categories = list(config["categories"]) if config else DEFAULT_CATEGORIES
    if category_name not in categories:
        await interaction.response.send_message(
            "That ticket category is no longer available. Ask staff to refresh the ticket panel.",
            ephemeral=True,
        )
        return
    if open_ticket:
        channel = guild.get_channel(open_ticket["channel_id"])
        message = f"You already have an open ticket{f': {channel.mention}' if channel else ''}."
        await interaction.response.send_message(message, ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    bot_member = guild.me
    if bot_member is None or not bot_member.guild_permissions.manage_channels:
        await interaction.followup.send(
            "The bot needs Manage Channels permission to create private tickets.",
            ephemeral=True,
        )
        return

    category = discord.utils.get(guild.categories, name="Vortex Tickets")
    if category is None:
        category = await guild.create_category("Vortex Tickets")

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        ),
        bot_member: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True,
            manage_channels=True,
        ),
    }
    for role_id in bot.settings.staff_role_ids:
        role = guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

    safe_name = re.sub(r"[^a-z0-9-]+", "-", interaction.user.name.casefold()).strip("-")
    channel = await guild.create_text_channel(
        f"ticket-{safe_name[:60] or interaction.user.id}",
        category=category,
        overwrites=overwrites,
        topic=f"Ticket for {interaction.user.id} | {category_name[:80]}",
        reason=f"Ticket opened by {interaction.user} ({interaction.user.id})",
    )
    try:
        async with bot.pool.acquire() as connection:
            ticket_id = await connection.fetchval(
                "INSERT INTO tickets(guild_id,channel_id,user_id,category) "
                "VALUES($1,$2,$3,$4) RETURNING id",
                guild.id, channel.id, interaction.user.id, category_name,
            )
        await channel.send(
            view=TicketControlsView(
                f"# Support ticket #{ticket_id}\n"
                f"Opened by {interaction.user.mention} · Category: **{category_name}**\n\n"
                "Use the button below when your support request is resolved."
            ),
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )
    except Exception:
        await channel.delete(reason="Ticket setup failed")
        raise
    await interaction.followup.send(
        f"Your private ticket is ready: {channel.mention}", ephemeral=True
    )


class Community(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self) -> None:
        async with self.bot.pool.acquire() as connection:
            config = await connection.fetchrow(
                "SELECT title,description,categories,image_url FROM ticket_panel_settings WHERE id=1"
            )
            verification = await connection.fetchrow(
                "SELECT title,description,image_url FROM verification_panel_settings WHERE id=1"
            )
        if config:
            self.bot.add_view(TicketPanelView(
                self.bot,
                config["title"],
                config["description"],
                list(config["categories"]),
                config["image_url"],
            ))
        else:
            self.bot.add_view(TicketPanelView(
                self.bot, "Vortex Support", "Choose a category below.", DEFAULT_CATEGORIES
            ))
        self.bot.add_view(TicketControlsView("Use the button below when your support request is resolved."))
        if verification:
            self.bot.add_view(VerificationPanelView(
                self.bot.settings.public_url,
                verification["title"],
                verification["description"],
                verification["image_url"],
            ))

    async def publish_panel(
        self,
        channel: discord.TextChannel,
        title: str,
        description: str,
        categories: list[str],
        actor_id: int,
        image_url: str | None = None,
    ) -> discord.Message:
        image_url = validate_image_url(image_url)
        view = TicketPanelView(self.bot, title, description, categories, image_url)
        async with self.bot.pool.acquire() as connection:
            saved = await connection.fetchrow(
                "SELECT panel_channel_id,panel_message_id FROM ticket_panel_settings WHERE id=1"
            )
        if saved and saved["panel_channel_id"] == channel.id and saved["panel_message_id"]:
            try:
                message = await channel.fetch_message(saved["panel_message_id"])
                await message.edit(view=view)
            except discord.NotFound:
                message = await channel.send(view=view)
        else:
            message = await channel.send(view=view)
        async with self.bot.pool.acquire() as connection:
            await connection.execute(
                "UPDATE ticket_panel_settings SET title=$1,description=$2,categories=$3,image_url=$4,"
                "panel_channel_id=$5,panel_message_id=$6,updated_by=$7,updated_at=NOW() "
                "WHERE id=1",
                title, description, categories, image_url, channel.id, message.id, actor_id,
            )

        self.bot.add_view(TicketPanelView(self.bot, title, description, categories, image_url))
        return message

    async def publish_verification_panel(
        self,
        channel: discord.TextChannel,
        title: str,
        description: str,
        image_url: str | None,
        actor_id: int,
    ) -> discord.Message:
        image_url = validate_image_url(image_url)
        view = VerificationPanelView(
            self.bot.settings.public_url, title, description, image_url
        )
        async with self.bot.pool.acquire() as connection:
            saved = await connection.fetchrow(
                "SELECT panel_channel_id,panel_message_id FROM verification_panel_settings WHERE id=1"
            )
        if saved and saved["panel_channel_id"] == channel.id and saved["panel_message_id"]:
            try:
                message = await channel.fetch_message(saved["panel_message_id"])
                await message.edit(view=view)
            except discord.NotFound:
                message = await channel.send(view=view)
        else:
            message = await channel.send(view=view)
        async with self.bot.pool.acquire() as connection:
            await connection.execute(
                "UPDATE verification_panel_settings SET title=$1,description=$2,image_url=$3,"
                "panel_channel_id=$4,panel_message_id=$5,updated_by=$6,updated_at=NOW() WHERE id=1",
                title, description, image_url, channel.id, message.id, actor_id,
            )
        self.bot.add_view(view)
        return message

    @app_commands.command(name="ticket", description="Create a private support ticket")
    @app_commands.describe(category="Exact category name configured by staff")
    async def ticket(self, interaction: discord.Interaction, category: str) -> None:
        await create_ticket(interaction, self.bot, category)

    @app_commands.command(name="ticket-panel", description="Create or update the Components V2 ticket panel")
    @app_commands.describe(
        channel="Channel where the ticket panel should be posted",
        title="Panel heading",
        description="Short explanation shown on the panel",
        categories="Ticket categories separated by semicolons",
    )
    async def ticket_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: app_commands.Range[str, 1, 100],
        description: app_commands.Range[str, 1, 1500],
        categories: app_commands.Range[str, 1, 1000],
        image_url: app_commands.Range[str, 1, 2000] | None = None,
    ) -> None:
        if not interaction.guild or interaction.guild.id != self.bot.settings.guild_id:
            await interaction.response.send_message(
                "This command is only available in the configured server.", ephemeral=True
            )
            return
        if not staff_allowed(interaction.user, self.bot.settings.staff_role_ids):
            await interaction.response.send_message("Staff permission required.", ephemeral=True)
            return
        try:
            parsed_categories = parse_categories(categories)
            image_url = validate_image_url(image_url)
            message = await self.publish_panel(
                channel, title, description, parsed_categories, interaction.user.id, image_url
            )
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                "The bot needs View Channel and Send Messages permission in that channel.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"Ticket panel published or updated in {channel.mention}: {message.jump_url}",
            ephemeral=True,
        )

    @app_commands.command(
        name="verification-panel",
        description="Create or update a Discord verification panel",
    )
    @app_commands.describe(
        channel="Channel where members should see the panel",
        title="Panel heading",
        description="Explain that verification happens on the Vortex website",
        image_url="Optional public HTTPS image URL",
    )
    async def verification_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: app_commands.Range[str, 1, 100],
        description: app_commands.Range[str, 1, 1500],
        image_url: app_commands.Range[str, 1, 2000] | None = None,
    ) -> None:
        if not interaction.guild or interaction.guild.id != self.bot.settings.guild_id:
            await interaction.response.send_message(
                "This command is only available in the configured server.", ephemeral=True
            )
            return
        if not staff_allowed(interaction.user, self.bot.settings.staff_role_ids):
            await interaction.response.send_message("Staff permission required.", ephemeral=True)
            return
        try:
            image_url = validate_image_url(image_url)
            message = await self.publish_verification_panel(
                channel, title, description, image_url, interaction.user.id
            )
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                "The bot needs View Channel and Send Messages permission there.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"Verification panel published or updated in {channel.mention}: {message.jump_url}",
            ephemeral=True,
        )

    async def close_ticket(self, interaction: discord.Interaction) -> None:
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("This is not a ticket channel.", ephemeral=True)
            return
        async with self.bot.pool.acquire() as connection:
            ticket = await connection.fetchrow(
                "SELECT id,user_id,status FROM tickets WHERE channel_id=$1 AND guild_id=$2",
                channel.id, interaction.guild_id,
            )
            if not ticket or ticket["status"] != "open":
                await interaction.response.send_message(
                    "This ticket is already closed or was not found.", ephemeral=True
                )
                return
            if interaction.user.id != ticket["user_id"] and not staff_allowed(
                interaction.user, self.bot.settings.staff_role_ids
            ):
                await interaction.response.send_message(
                    "Only the ticket owner or staff can close this ticket.", ephemeral=True
                )
                return
            await connection.execute(
                "UPDATE tickets SET status='closed',closed_at=NOW(),updated_at=NOW() WHERE id=$1",
                ticket["id"],
            )
        owner = channel.guild.get_member(ticket["user_id"])
        if owner:
            await channel.set_permissions(
                owner, overwrite=discord.PermissionOverwrite(
                    view_channel=True, send_messages=False, read_message_history=True
                ),
                reason="Ticket closed",
            )
        await channel.edit(name=f"closed-{channel.name}"[:100], reason="Ticket closed")
        await interaction.response.edit_message(
            view=TicketControlsView("This ticket is closed.", closed=True)
        )


async def setup(bot):
    await bot.add_cog(Community(bot))
