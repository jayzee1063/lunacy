from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Iterable

import disnake
from disnake.ext import commands
from mcrcon import MCRcon

import config


logger = logging.getLogger("LunacyTickets.Tickets")

MC_NICKNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
CHANNEL_SAFE_RE = re.compile(r"[^a-z0-9_-]+")


@dataclass(frozen=True)
class TicketMeta:
    ticket_type: str
    owner_id: int
    nickname: str | None = None


def is_staff(member: disnake.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(role.id in config.SUPPORT_ROLE_IDS for role in member.roles)


def sanitize_channel_part(value: str) -> str:
    value = value.lower().replace(" ", "-")
    value = CHANNEL_SAFE_RE.sub("-", value).strip("-")
    return value[:24] or "user"


def ticket_topic(meta: TicketMeta) -> str:
    parts = [
        "lunacy-ticket",
        f"type={meta.ticket_type}",
        f"owner={meta.owner_id}",
    ]
    if meta.nickname:
        parts.append(f"nick={meta.nickname}")
    return ";".join(parts)


def parse_ticket_topic(topic: str | None) -> TicketMeta | None:
    if not topic or not topic.startswith("lunacy-ticket;"):
        return None

    values: dict[str, str] = {}
    for part in topic.split(";")[1:]:
        if "=" in part:
            key, value = part.split("=", 1)
            values[key] = value

    try:
        return TicketMeta(
            ticket_type=values["type"],
            owner_id=int(values["owner"]),
            nickname=values.get("nick") or None,
        )
    except (KeyError, ValueError):
        return None


async def get_ticket_owner(interaction: disnake.MessageInteraction | disnake.ModalInteraction) -> disnake.User | disnake.Member | None:
    if not interaction.guild:
        return None

    topic = interaction.channel.topic if isinstance(interaction.channel, disnake.TextChannel) else None
    meta = parse_ticket_topic(topic)
    if not meta:
        return None

    member = interaction.guild.get_member(meta.owner_id)
    if member:
        return member

    try:
        return await interaction.client.fetch_user(meta.owner_id)
    except disnake.DiscordException:
        return None


async def send_dm(
    interaction: disnake.MessageInteraction,
    *,
    title: str,
    description: str,
    color: int,
) -> bool:
    user = await get_ticket_owner(interaction)
    if not user:
        return False

    embed = disnake.Embed(title=title, description=description, color=color)
    embed.set_footer(text=config.FOOTER_TEXT)

    try:
        await user.send(embed=embed)
        return True
    except disnake.DiscordException:
        return False


async def get_or_create_category(guild: disnake.Guild) -> disnake.CategoryChannel | None:
    if config.TICKET_CATEGORY_ID:
        category = guild.get_channel(config.TICKET_CATEGORY_ID)
        if isinstance(category, disnake.CategoryChannel):
            return category
        logger.warning("Ticket category with ID %s was not found.", config.TICKET_CATEGORY_ID)

    category = disnake.utils.get(guild.categories, name=config.TICKET_CATEGORY_NAME)
    if category:
        return category

    return await guild.create_category(config.TICKET_CATEGORY_NAME, reason="Lunacy ticket system setup")


def support_roles(guild: disnake.Guild) -> list[disnake.Role]:
    return [role for role_id in config.SUPPORT_ROLE_IDS if (role := guild.get_role(role_id))]


def support_mentions(guild: disnake.Guild) -> str:
    mentions = [role.mention for role in support_roles(guild)]
    return " ".join(mentions) if mentions else "@staff"


def build_ticket_overwrites(
    guild: disnake.Guild,
    owner: disnake.Member,
) -> dict[disnake.Role | disnake.Member, disnake.PermissionOverwrite]:
    overwrites: dict[disnake.Role | disnake.Member, disnake.PermissionOverwrite] = {
        guild.default_role: disnake.PermissionOverwrite(view_channel=False),
        owner: disnake.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
        ),
    }

    if guild.me:
        overwrites[guild.me] = disnake.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True,
        )

    for role in support_roles(guild):
        overwrites[role] = disnake.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True,
            manage_messages=True,
        )

    return overwrites


async def create_ticket_channel(
    interaction: disnake.ModalInteraction,
    ticket_type: str,
    title: str,
    description: str,
    fields: Iterable[tuple[str, str]],
    nickname: str | None = None,
) -> None:
    guild = interaction.guild
    owner = interaction.user

    if not guild or not isinstance(owner, disnake.Member):
        await interaction.response.send_message("Ошибка: тикеты доступны только на Discord-сервере.", ephemeral=True)
        return

    category = await get_or_create_category(guild)
    safe_owner = sanitize_channel_part(owner.display_name or owner.name)
    channel_prefix = {
        "pass": "pass",
        "complaint": "complaint",
        "suggestion": "suggestion",
    }.get(ticket_type, "ticket")

    channel = await guild.create_text_channel(
        name=f"{channel_prefix}-{safe_owner}",
        category=category,
        overwrites=build_ticket_overwrites(guild, owner),
        topic=ticket_topic(TicketMeta(ticket_type=ticket_type, owner_id=owner.id, nickname=nickname)),
        reason=f"Lunacy ticket created by {owner}",
    )

    embed = disnake.Embed(
        title=title,
        description=description,
        color=config.LUNACY_PURPLE,
    )
    embed.set_author(name=str(owner), icon_url=owner.display_avatar.url)
    for name, value in fields:
        embed.add_field(name=name, value=value[:1024] or "—", inline=False)
    embed.set_footer(text=config.FOOTER_TEXT)

    view: disnake.ui.View
    if ticket_type == "pass":
        view = PassTicketControlView()
    else:
        view = CommonTicketControlView(ticket_type)

    await channel.send(
        content=f"{support_mentions(guild)} {owner.mention}",
        embed=embed,
        view=view,
        allowed_mentions=disnake.AllowedMentions(users=True, roles=True),
    )
    await interaction.response.send_message(f"Тикет создан: {channel.mention}", ephemeral=True)


def run_whitelist_command(nickname: str) -> str:
    command = config.WHITELIST_COMMAND_TEMPLATE.format(nickname=nickname)
    command = command[1:] if command.startswith("/") else command
    with MCRcon(config.RCON_HOST, config.RCON_PASSWORD, port=config.RCON_PORT) as rcon:
        return rcon.command(command)


class PassTicketPanelView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @disnake.ui.button(
        label="Подать заявку на проходку",
        style=disnake.ButtonStyle.primary,
        emoji="🌙",
        custom_id="lunacy_ticket:create:pass",
    )
    async def open_ticket(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.send_modal(PassTicketModal())


class ComplaintTicketPanelView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @disnake.ui.button(
        label="Подать жалобу",
        style=disnake.ButtonStyle.danger,
        emoji="⚠️",
        custom_id="lunacy_ticket:create:complaint",
    )
    async def open_ticket(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.send_modal(ComplaintTicketModal())


class SuggestionTicketPanelView(disnake.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @disnake.ui.button(
        label="Оставить предложение",
        style=disnake.ButtonStyle.secondary,
        emoji="✨",
        custom_id="lunacy_ticket:create:suggestion",
    )
    async def open_ticket(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await interaction.response.send_modal(SuggestionTicketModal())


class PassTicketModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Ваш игровой ник",
                custom_id="nickname",
                style=disnake.TextInputStyle.short,
                placeholder="kinya169",
                min_length=3,
                max_length=16,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Откуда узнали о проекте",
                custom_id="source",
                style=disnake.TextInputStyle.paragraph,
                max_length=700,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Ваш возраст (14+)",
                custom_id="age",
                style=disnake.TextInputStyle.short,
                placeholder="14+",
                max_length=32,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Есть возможность играть с войсом?",
                custom_id="voice",
                style=disnake.TextInputStyle.short,
                placeholder="Да / нет / иногда",
                max_length=100,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Кодовое слово из правил",
                custom_id="codeword",
                style=disnake.TextInputStyle.short,
                max_length=100,
                required=True,
            ),
        ]
        super().__init__(title="Заявка на проходку", custom_id="lunacy_ticket:modal:pass", components=components)

    async def callback(self, interaction: disnake.ModalInteraction):
        nickname = interaction.text_values["nickname"].strip()
        if not MC_NICKNAME_RE.fullmatch(nickname):
            await interaction.response.send_message(
                "Ник должен быть Minecraft-ником: 3-16 символов, латиница, цифры и подчёркивание.",
                ephemeral=True,
            )
            return

        await create_ticket_channel(
            interaction=interaction,
            ticket_type="pass",
            title="🌙 Заявка на проходку",
            description="Новая заявка на добавление игрока в whitelist Lunacy.",
            nickname=nickname,
            fields=[
                ("1) Ваш игровой ник", nickname),
                ("2) Откуда узнали о проекте", interaction.text_values["source"]),
                ("3) Ваш возраст (14+)", interaction.text_values["age"]),
                ("4) Имеете ли возможность играть с войсом", interaction.text_values["voice"]),
                ("5) Кодовое слово из правил", interaction.text_values["codeword"]),
            ],
        )


class ComplaintTicketModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Ваш ник или ник пострадавшего",
                custom_id="victim",
                style=disnake.TextInputStyle.short,
                max_length=80,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Ник нарушителя",
                custom_id="target",
                style=disnake.TextInputStyle.short,
                max_length=80,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Время нарушения по МСК",
                custom_id="time",
                style=disnake.TextInputStyle.short,
                placeholder="Например: 21:30 МСК",
                max_length=80,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Кратко опишите ситуацию",
                custom_id="details",
                style=disnake.TextInputStyle.paragraph,
                max_length=1200,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Доказательства",
                custom_id="proof",
                style=disnake.TextInputStyle.paragraph,
                placeholder="Ссылки на фото/видео",
                max_length=1000,
                required=True,
            ),
        ]
        super().__init__(title="Жалоба", custom_id="lunacy_ticket:modal:complaint", components=components)

    async def callback(self, interaction: disnake.ModalInteraction):
        await create_ticket_channel(
            interaction=interaction,
            ticket_type="complaint",
            title="⚠️ Жалоба",
            description="Новая жалоба от игрока.",
            fields=[
                ("1) Ваш игровой ник или ник пострадавшего", interaction.text_values["victim"]),
                ("2) Ник нарушителя", interaction.text_values["target"]),
                ("3) Приблизительное время по МСК", interaction.text_values["time"]),
                ("4) Что произошло и кто что нарушил", interaction.text_values["details"]),
                ("5) Доказательства", interaction.text_values["proof"]),
            ],
        )


class SuggestionTicketModal(disnake.ui.Modal):
    def __init__(self):
        components = [
            disnake.ui.TextInput(
                label="Ваш игровой ник",
                custom_id="nickname",
                style=disnake.TextInputStyle.short,
                max_length=80,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Суть бага либо идеи",
                custom_id="details",
                style=disnake.TextInputStyle.paragraph,
                max_length=1400,
                required=True,
            ),
            disnake.ui.TextInput(
                label="Видео/фото при наличии",
                custom_id="proof",
                style=disnake.TextInputStyle.paragraph,
                placeholder="Необязательно",
                max_length=1000,
                required=False,
            ),
        ]
        super().__init__(title="Предложение", custom_id="lunacy_ticket:modal:suggestion", components=components)

    async def callback(self, interaction: disnake.ModalInteraction):
        await create_ticket_channel(
            interaction=interaction,
            ticket_type="suggestion",
            title="✨ Предложение",
            description="Новая идея или сообщение о баге для развития Lunacy.",
            fields=[
                ("1) Ваш игровой ник", interaction.text_values["nickname"]),
                ("2) Суть бага либо идеи", interaction.text_values["details"]),
                ("3) Видео/фото при наличии", interaction.text_values.get("proof") or "Не приложено"),
            ],
        )


class BaseTicketControlView(disnake.ui.View):
    def __init__(self, *, ticket_type: str):
        super().__init__(timeout=None)
        self.ticket_type = ticket_type

    async def ensure_staff(self, interaction: disnake.MessageInteraction) -> bool:
        if isinstance(interaction.user, disnake.Member) and is_staff(interaction.user):
            return True
        await interaction.response.send_message("Это действие доступно только команде сервера.", ephemeral=True)
        return False

    async def approve_common_ticket(self, interaction: disnake.MessageInteraction, label: str):
        if not await self.ensure_staff(interaction):
            return

        dm_sent = await send_dm(
            interaction,
            title=f"Lunacy | {label} принят",
            description=f"Ваш тикет был принят командой сервера.\nОтветственный: {interaction.user.mention}",
            color=config.LUNACY_GREEN,
        )

        embed = disnake.Embed(
            title=f"{label} принят",
            description=f"Ответственный: {interaction.user.mention}",
            color=config.LUNACY_GREEN,
        )
        if not dm_sent:
            embed.add_field(name="ЛС", value="Не удалось отправить сообщение автору тикета.", inline=False)
        await interaction.response.send_message(embed=embed)

    async def reject_ticket(self, interaction: disnake.MessageInteraction, label: str):
        if not await self.ensure_staff(interaction):
            return

        dm_sent = await send_dm(
            interaction,
            title=f"Lunacy | {label} отклонён",
            description="Ваш тикет был отклонён командой сервера.",
            color=config.LUNACY_RED,
        )

        embed = disnake.Embed(
            title=f"{label} отклонён",
            description=f"Отклонил: {interaction.user.mention}",
            color=config.LUNACY_RED,
        )
        if not dm_sent:
            embed.add_field(name="ЛС", value="Не удалось отправить сообщение автору тикета.", inline=False)
        await interaction.response.send_message(embed=embed)

    async def close_ticket(self, interaction: disnake.MessageInteraction):
        meta = parse_ticket_topic(interaction.channel.topic if isinstance(interaction.channel, disnake.TextChannel) else None)
        is_owner = meta and interaction.user.id == meta.owner_id
        is_allowed_staff = isinstance(interaction.user, disnake.Member) and is_staff(interaction.user)

        if not is_owner and not is_allowed_staff:
            await interaction.response.send_message("Закрыть тикет может автор тикета или команда сервера.", ephemeral=True)
            return

        await interaction.response.send_message("Тикет будет закрыт и удалён через 5 секунд.", ephemeral=True)
        await interaction.channel.send("🌙 Тикет закрывается...")
        await asyncio.sleep(5)
        await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")


class PassTicketControlView(BaseTicketControlView):
    def __init__(self):
        super().__init__(ticket_type="pass")

    @disnake.ui.button(
        label="Одобрить",
        style=disnake.ButtonStyle.success,
        emoji="✅",
        custom_id="lunacy_ticket:pass:approve",
    )
    async def approve(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        if not await self.ensure_staff(interaction):
            return

        meta = parse_ticket_topic(interaction.channel.topic if isinstance(interaction.channel, disnake.TextChannel) else None)
        if not meta or meta.ticket_type != "pass" or not meta.nickname:
            await interaction.response.send_message("Не удалось определить ник из тикета проходки.", ephemeral=True)
            return

        if not MC_NICKNAME_RE.fullmatch(meta.nickname):
            await interaction.response.send_message("Ник в тикете некорректный, whitelist-команда отменена.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        try:
            response = await asyncio.to_thread(run_whitelist_command, meta.nickname)
        except Exception as error:
            logger.exception("RCON whitelist command failed")
            await interaction.followup.send(f"RCON не выполнил whitelist-команду: `{error}`", ephemeral=True)
            return

        guild = interaction.guild
        member = guild.get_member(meta.owner_id) if guild else None
        role = guild.get_role(config.ACCEPTED_ROLE_ID) if guild and config.ACCEPTED_ROLE_ID else None

        role_granted = False
        role_status = "Роль выдана."
        if member and role:
            try:
                await member.add_roles(role, reason=f"Whitelist ticket approved by {interaction.user}")
                role_granted = True
            except disnake.Forbidden:
                logger.warning(
                    "Cannot grant role %s to %s: missing Discord permissions or role hierarchy.",
                    role.id,
                    member.id,
                )
                role_status = (
                    "Роль не выдана: у бота нет прав или его роль ниже выдаваемой роли "
                    "в иерархии Discord."
                )
            except disnake.HTTPException as error:
                logger.exception("Cannot grant role %s to %s", role.id, member.id)
                role_status = f"Роль не выдана: Discord API вернул ошибку `{error}`."
            except Exception as error:
                logger.exception("Unexpected role grant error")
                role_status = f"Роль не выдана: `{error}`."
        elif not role:
            role_status = "Роль не выдана: роль после одобрения не найдена."
        elif not member:
            role_status = "Роль не выдана: автор тикета не найден на Discord-сервере."

        dm_sent = await send_dm(
            interaction,
            title="Lunacy | Заявка одобрена",
            description=f"Ваша заявка на проходку одобрена. Ник `{meta.nickname}` добавлен в whitelist.",
            color=config.LUNACY_GREEN,
        )

        embed = disnake.Embed(
            title="Проходка одобрена",
            description=(
                f"Игрок `{meta.nickname}` добавлен в whitelist.\n"
                f"Одобрил: {interaction.user.mention}"
            ),
            color=config.LUNACY_GREEN,
        )
        if not role_granted:
            embed.add_field(name="Роль", value=role_status, inline=False)
        if not dm_sent:
            embed.add_field(name="ЛС", value="Не удалось отправить сообщение автору тикета.", inline=False)

        await interaction.channel.send(embed=embed)
        if role_granted:
            await interaction.followup.send("Готово: игрок добавлен в whitelist и получил роль.", ephemeral=True)
        else:
            await interaction.followup.send(
                "Whitelist выполнен, ЛС отправлено при возможности, но роль не удалось выдать. Подробности в тикете.",
                ephemeral=True,
            )

    @disnake.ui.button(
        label="Отказать",
        style=disnake.ButtonStyle.danger,
        emoji="❌",
        custom_id="lunacy_ticket:pass:reject",
    )
    async def reject(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await self.reject_ticket(interaction, "Заявка на проходку")

    @disnake.ui.button(
        label="Закрыть",
        style=disnake.ButtonStyle.secondary,
        emoji="🔒",
        custom_id="lunacy_ticket:pass:close",
    )
    async def close(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await self.close_ticket(interaction)


class CommonTicketControlView(BaseTicketControlView):
    def __init__(self, ticket_type: str = "common"):
        super().__init__(ticket_type=ticket_type)

    def label_for_interaction(self, interaction: disnake.MessageInteraction) -> str:
        meta = parse_ticket_topic(interaction.channel.topic if isinstance(interaction.channel, disnake.TextChannel) else None)
        ticket_type = meta.ticket_type if meta else self.ticket_type

        if ticket_type == "complaint":
            return "Жалоба"
        if ticket_type == "suggestion":
            return "Предложение"
        return "Тикет"

    @disnake.ui.button(
        label="Одобрить",
        style=disnake.ButtonStyle.success,
        emoji="✅",
        custom_id="lunacy_ticket:common:approve",
    )
    async def approve(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await self.approve_common_ticket(interaction, self.label_for_interaction(interaction))

    @disnake.ui.button(
        label="Отказать",
        style=disnake.ButtonStyle.danger,
        emoji="❌",
        custom_id="lunacy_ticket:common:reject",
    )
    async def reject(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await self.reject_ticket(interaction, self.label_for_interaction(interaction))

    @disnake.ui.button(
        label="Закрыть",
        style=disnake.ButtonStyle.secondary,
        emoji="🔒",
        custom_id="lunacy_ticket:common:close",
    )
    async def close(self, button: disnake.ui.Button, interaction: disnake.MessageInteraction):
        await self.close_ticket(interaction)


class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._persistent_views_registered = False

    @commands.Cog.listener()
    async def on_ready(self):
        if self._persistent_views_registered:
            return

        self.bot.add_view(PassTicketPanelView())
        self.bot.add_view(ComplaintTicketPanelView())
        self.bot.add_view(SuggestionTicketPanelView())
        self.bot.add_view(PassTicketControlView())
        self.bot.add_view(CommonTicketControlView())
        self._persistent_views_registered = True
        logger.info("Persistent ticket views registered.")

    def panel_embed(self, ticket_type: str) -> disnake.Embed:
        if ticket_type == "pass":
            title = "🌙 Lunacy | Проходка"
            description = (
                f"Перед заполнением заявки ознакомьтесь с правилами: <#{config.RULES_CHANNEL_ID}>\n\n"
                "Нажмите кнопку ниже, чтобы подать заявку на проходку и попасть в whitelist."
            )
        elif ticket_type == "complaint":
            title = "⚠️ Lunacy | Жалобы"
            description = "Нажмите кнопку ниже, чтобы сообщить о нарушении."
        elif ticket_type == "suggestion":
            title = "✨ Lunacy | Предложения"
            description = "Нажмите кнопку ниже, чтобы предложить идею или сообщить о баге."
        else:
            title = "🌙 Lunacy | Тикеты"
            description = "Нажмите кнопку ниже, чтобы открыть тикет."

        embed = disnake.Embed(title=title, description=description, color=config.LUNACY_PURPLE)
        embed.set_footer(text=config.FOOTER_TEXT)
        return embed

    @commands.slash_command(name="setup_pass_tickets", description="Создать сообщение для заявок на проходку")
    @commands.has_permissions(administrator=True)
    async def setup_pass_tickets(self, interaction: disnake.ApplicationCommandInteraction):
        await interaction.response.send_message(embed=self.panel_embed("pass"), view=PassTicketPanelView())

    @commands.slash_command(name="setup_complaint_tickets", description="Создать сообщение для жалоб")
    @commands.has_permissions(administrator=True)
    async def setup_complaint_tickets(self, interaction: disnake.ApplicationCommandInteraction):
        await interaction.response.send_message(embed=self.panel_embed("complaint"), view=ComplaintTicketPanelView())

    @commands.slash_command(name="setup_suggestion_tickets", description="Создать сообщение для предложений")
    @commands.has_permissions(administrator=True)
    async def setup_suggestion_tickets(self, interaction: disnake.ApplicationCommandInteraction):
        await interaction.response.send_message(embed=self.panel_embed("suggestion"), view=SuggestionTicketPanelView())

    @commands.command(name="setup_pass_tickets")
    @commands.has_permissions(administrator=True)
    async def setup_pass_tickets_prefix(self, ctx: commands.Context):
        await ctx.send(embed=self.panel_embed("pass"), view=PassTicketPanelView())

    @commands.command(name="setup_complaint_tickets")
    @commands.has_permissions(administrator=True)
    async def setup_complaint_tickets_prefix(self, ctx: commands.Context):
        await ctx.send(embed=self.panel_embed("complaint"), view=ComplaintTicketPanelView())

    @commands.command(name="setup_suggestion_tickets")
    @commands.has_permissions(administrator=True)
    async def setup_suggestion_tickets_prefix(self, ctx: commands.Context):
        await ctx.send(embed=self.panel_embed("suggestion"), view=SuggestionTicketPanelView())


def setup(bot: commands.Bot):
    bot.add_cog(TicketsCog(bot))
