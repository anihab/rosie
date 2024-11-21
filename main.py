#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Main file for Rosie, a Discord bot dedicated to helping user's manage their time.

This file serves as the entry point for the bot's functionality. It initializes the bot,
loads extensions (cogs) for various features, and sets up global configurations.

For more information, please refer to my github repo https://github.com/anihab/rosie
or the discord.py documentation https://discordpy.readthedocs.io/en/stable/index.html.

Author: anisa
Version: 1.0
"""
import asyncio
import json
import logging
import os
import sys

from datetime import datetime, timezone
from dotenv import load_dotenv

import aiosqlite
import discord
from discord.ext import commands, tasks
from discord.ext.commands import Context

# Load configurations and set up logging
config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.json")
if not os.path.isfile(config_path ):
    sys.exit("Error:  'config.json' not found!")
else:
    with open(config_path, "r") as config_file:
        config = json.load(config_file)
        
if not os.path.exists("logs"):
    os.makedirs("logs")

log_file = os.path.join("logs", "rosie.log")
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
    datefmt="%d/%b/%Y %H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8", mode="w"),
        logging.StreamHandler(),  # log to console as well
    ],
)
logger = logging.getLogger(__name__)

# Define intents
intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True
intents.emojis_and_stickers = True

class Rosie(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned_or(config["prefix"]),
            intents=intents,
            help_command=None,
        )
        self.db_path= os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "database", "database.db"
        )
        self.logger = logger
        self.config = config
        self.db = None
       
    async def setup_hook(self) -> None:  
        await self.init_db()
        await self.load_cogs()
        
    async def on_ready(self)  -> None:
        logger.info("Logged on as %s!", self.user.name)
        try:
            # start background tasks after bot is ready
            self.set_status.start()
            self.start_time = datetime.now(timezone.utc)
        except Exception as e:
            logger.error("Error on startup: %s", e)

    async def shutdown(self) -> None:
        await self.db.close()
        await self.close()

        for task in asyncio.all_tasks():
            if task is not asyncio.current_task():
                task.cancel()
                
        loop = asyncio.get_event_loop()
        loop.stop()

    async def init_db(self) -> None:
        self.db = await aiosqlite.connect(self.db_path)
        schema_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "database", "schema.sql"
        )
        with open(schema_path, "r") as schema_file:
            await self.db.executescript(schema_file.read())
        await self.db.commit()
            
    async def load_cogs(self) -> None:
        cogs_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "cogs")
        for file in os.listdir(cogs_dir):
            if file.endswith(".py"):
                cog = file[:-3]
                try:
                    await self.load_extension(f"cogs.{cog}")
                    logger.info("Loaded the %s cog", cog)
                except Exception as e:
                    logger.error("Error loading the %s cog: %s", cog, e)
                    
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
        self.logger.info("%s executed %s command", context.author, context.command.qualified_name)
        
    async def on_command_error(self, context, exception):
        embed = None
        if isinstance(exception, commands.CommandOnCooldown):
            embed = discord.Embed(
                description="this command is currently on cooldown. you can try again in a little bit!",
                color=0xf8eccf
            )
        elif isinstance(exception, commands.NotOwner):
            self.logger.warning("%s tried to execute an owner only command.", context.author)
            embed = discord.Embed(
                description="sorry, only the owner can execute this command!",
                color=0xf8bdb9
            )
        elif isinstance(exception, commands.MissingPermissions):
            embed = discord.Embed(
                description="i'm sorry, you do not have the permissions to use this command.",
                color=0xf8bdb9,
            )
        elif isinstance(exception, commands.ChannelNotFound):
            embed = discord.Embed(
                description="oh no! i couldn't find that channel. please make sure it exists and mention i correctly!",
                color=0xf8bdb9,
            )
        
        if embed:
            await context.send(embed=embed, ephemeral=True)
        else:
            await super().on_command_error(context, exception)       

load_dotenv()

rosie = Rosie()
rosie.run(os.getenv("TOKEN"))