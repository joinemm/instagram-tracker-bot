from discord.ext import commands
import os
import logger

logger = logger.create_logger(__name__)
TOKEN = os.environ.get('INSTAGRAM_BOT_TOKEN')
client = commands.Bot(command_prefix="%")

extensions = ['scraper']


@client.event
async def on_ready():
    logger.info("Bot is ready")

if __name__ == "__main__":
    for extension in extensions:
        try:
            client.load_extension(extension)
            logger.info(f"{extension} loaded successfully")
        except Exception as error:
            logger.error(f"{extension} loading failed [{error}]")

    client.run(TOKEN)
