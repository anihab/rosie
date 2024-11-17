import json
import os
import logging
import sys

import aiosqlite
import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context
from dotenv import load_dotenv

load_dotenv()

config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.json")
if not os.path.isfile(config_path ):
    sys.exit("Error:  'config.json' not found!")
else:
    with open(config_path, "r") as config_file:
        config = json.load(config_file)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

intents = discord.Intents.default()

class Rosie(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned_or(config["prefix"]),
            intents=intents,
            help_command=None,
        )
        self.database_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), "database", "database.db")
        self.logger = logger
        self.config = config
       
    async def setup_hook(self) -> None:
        logger.info("Logged on as %s!", self.user.name)
        # TODO: change this to an owner-only message command !!
        try:
            await self.tree.sync(guild=discord.Object(id=os.getenv("GID")))
            self.logger.info("Commands synced successfully.")
        except Exception as e:
            self.logger.error("Error syncing commands: %s", e)
            
        await self.init_db()
        await self.load_cogs()
        self.set_status.start()
        
    async def init_db(self) -> None:
        async with aiosqlite.connect(self.database_file) as db:
            schema_path = os.path.join(
                os.path.dirname(os.path.realpath(__file__)), "database", "schema.sql"
            )
            with open(schema_path, "r") as schema_file:
                await db.executescript(schema_file.read())
            await db.commit()
            
    async def load_cogs(self) -> None:
        cogs_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "cogs")
        for file in os.listdir(cogs_dir):
            if file.endswith(".py"):
                cog = file[:-3]
                try:
                    await self.load_extension(f"cogs.{cog}")
                    logger.info("Successfully loaded cog %s", cog)
                except Exception as e:
                    logger.error("Failed to load cog %s: %s", cog, e)

    @tasks.loop(minutes=1.0)
    async def set_status(self) -> None:
        await self.change_presence(activity=discord.Game("with you!"))

    @set_status.before_loop
    async def before_set_status(self) -> None:
        await self.wait_until_ready()

    async def on_message(self, message: discord.Message) -> None:
        if message.author == self.user or message.author.bot:
            return
        await self.process_commands(message)

    async def on_command_completion(self, context: Context) -> None:
        command_name = context.command.qualified_name
        if context.guild is not None:
            self.logger.info(
                f"Successfully executed {command_name} command in {context.guild.name} by {context.author}"
            )
        else:
            self.logger.info(
                f"Successfully executed {command_name} command by {context.author} via DM"
            )

rosie = Rosie()
rosie.run(os.getenv("TOKEN"))