import logging

import disnake
from disnake.ext import commands

import config


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("LunacyTickets")


class LunacyTicketsBot(commands.Bot):
    def __init__(self):
        intents = disnake.Intents.default()
        intents.guilds = True
        intents.members = True
        intents.moderation = True
        intents.message_content = True

        kwargs = {"intents": intents, "command_prefix": config.COMMAND_PREFIX}
        if config.COMMAND_GUILD_IDS:
            kwargs["test_guilds"] = config.COMMAND_GUILD_IDS

        super().__init__(**kwargs)


bot = LunacyTicketsBot()
_stale_commands_cleaned = False


async def cleanup_stale_application_commands():
    if not config.STALE_COMMAND_NAMES:
        return

    stale_names = {name.lower() for name in config.STALE_COMMAND_NAMES}

    try:
        global_commands = await bot.fetch_global_commands()
        for command in global_commands:
            if command.name.lower() in stale_names:
                await bot.delete_global_command(command.id)
                logger.info("Deleted stale global command /%s", command.name)
    except Exception:
        logger.exception("Failed to clean stale global application commands")

    for guild in bot.guilds:
        try:
            guild_commands = await bot.fetch_guild_commands(guild.id)
            for command in guild_commands:
                if command.name.lower() in stale_names:
                    await bot.delete_guild_command(guild.id, command.id)
                    logger.info("Deleted stale guild command /%s in %s", command.name, guild.id)
        except Exception:
            logger.exception("Failed to clean stale guild commands in %s", guild.id)


@bot.event
async def on_ready():
    global _stale_commands_cleaned
    logger.info("Bot is ready as %s (%s)", bot.user, bot.user.id if bot.user else "unknown")
    if not _stale_commands_cleaned:
        await cleanup_stale_application_commands()
        _stale_commands_cleaned = True


def main():
    if not config.DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is empty. Fill it in .env or environment variables.")

    logger.info("Loading cogs...")
    bot.load_extension("cogs.tickets")
    logger.info("Starting bot...")
    bot.run(config.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
