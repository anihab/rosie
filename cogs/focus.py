import discord
from discord import TextChannel
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context

class Focus(commands.Cog):
    """ Commands to manage a pomodoro-style focus session. """
    
    def __init__(self, bot) -> None:
        self.bot = bot

async def setup(bot) -> None:
    await bot.add_cog(Focus(bot))