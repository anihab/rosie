import os
import re
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context
from dotenv import load_dotenv

load_dotenv()
GUILD = discord.Object(os.getenv("GID"))

class Owner(commands.Cog):
    """ Commands for owner only! """

    def __init__(self, bot) -> None:
        self.bot = bot
        self.bot.blacklist = {}
      
    # Command: set prefix   
    @commands.hybrid_command(name="setprefix", description="Let's set a new prefix for you, what should it be?")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def setprefix(self, context: Context, prefix: str) -> None:
        self.bot.command_prefix = prefix
        embed = discord.Embed(
            description=f"All done! I've set the new prefix to `{prefix}`!",
            color=0xf9e5e0,
        )
        await context.send(embed=embed)
       
    # Command: status 
    @commands.hybrid_command(name="status", description="Let me tell you how I'm doing!")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def status(self, context: Context) -> None:
        uptime = datetime.now(timezone.utc) - self.bot.start_time
        embed = discord.Embed(
            description=f"rosie's doing well! \n*uptime:* `{str(uptime).split('.')[0]}`",
            color=0xf9e5e0,
        )
        await context.send(embed=embed)

    # Command: sync
    @commands.hybrid_command(name="sync", description="Sync slash commands.")
    @app_commands.describe(scope="Can be `global` or `guild`.")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def sync(self, context: Context, scope: str) -> None:
        if scope == "global":
            await context.bot.tree.sync()
            embed = discord.Embed(
                description="all set! my commands are now updated *globally* for everyone~",
                color=0xf9e5e0,
            )
            await context.send(embed=embed)
            return
        elif scope == "guild":
            context.bot.tree.copy_global_to(guild=context.guild)
            await context.bot.tree.sync(guild=context.guild)
            embed = discord.Embed(
                description="my commands are now all synced just for this guild! 🏠",
                color=0xf9e5e0,
            )
            await context.send(embed=embed)
            return
        else:
            embed = discord.Embed(
                description="oh, um... i didn't understand that. the scope can only be `global` or `guild`. could you try again, please?",
                color=0xf8bdb9,
            )
            await context.send(embed=embed)

    # Command: unsync
    @commands.hybrid_command(name="unsync", description="Unsync slash commands")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def unsync(self, context: Context, scope: str) -> None:
        if scope == "global":
            context.bot.tree.clear_commands(guild=None)
            await context.bot.tree.sync()
            embed = discord.Embed(
                description="i've cleared all my global commands!",
                color=0xf9e5e0,
            )
            await context.send(embed=embed)
            return
        elif scope == "guild":
            context.bot.tree.clear_commands(guild=context.guild)
            await context.bot.tree.sync(guild=context.guild)
            embed = discord.Embed(
                description="commands for this guild have been unsynced. call if you need me!",
                color=0xf9e5e0,
            )
            await context.send(embed=embed)
            return
        else:
            embed = discord.Embed(
                description="hmm, i don't think that's right. the scope has to be `global` or `guild`. could you try again, please? 🥕",
                color=0xf8bdb9,
            )
            await context.send(embed=embed)

    # Command: load
    @commands.hybrid_command(name="load", description="Load a new cog.")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def load(self, context: Context, cog: str) -> None:
        try:
            await self.bot.load_extension(f"cogs.{cog}")
            embed = discord.Embed(
                description=f"Yay! I've loaded the `{cog}` cog for you! 🥕",
                color=0xf9e5e0,
            )
            await context.send(embed=embed)
        except Exception as e:
            embed = discord.Embed(
                description=f"oh no, i couldn't load the `{cog}` cog... here's the error message for you: {e} 🐰💨",
                color=0xf8bdb9,
            )
            await context.send(embed=embed)
      
    # Command: load all      
    @commands.hybrid_command(name="loadall", description="I'll load up all the cogs for you!")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def loadall(self, context: Context) -> None:
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py"):
                cog = filename[:-3]
                try:
                    await self.bot.load_extension(f"cogs.{cog}")
                    await context.send(f"loaded the `{cog}` cog...")
                except Exception as e:
                    await context.send(f"oh no, i couldn't load the `{cog}` cog... here's the error message for you: {e}")
        embed = discord.Embed(
                description=f"success! i've loaded all the cogs for you.",
                color=0xf9e5e0,
            )
        await context.send(embed=embed)

    # Command: unload
    @commands.hybrid_command(name="unload", description="Unload a cog.")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def unload(self, context: Context, cog: str) -> None:
        try:
            await self.bot.unload_extension(f"cogs.{cog}")
            embed = discord.Embed(
                description=f"i unloaded the `{cog}` cog for you!",
                color=0xf9e5e0,
            )
            await context.send(embed=embed)
        except Exception:
            embed = discord.Embed(
                description=f"i'm sorry, i couldn't unload the `{cog}` cog.",
                color=0xf8bdb9,
            )
            await context.send(embed=embed)

    # Command: reload
    @commands.hybrid_command(name="reload", description="Reload a cog.")
    @app_commands.describe(cog="The cog to reload")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def reload(self, context: Context, cog: str) -> None:
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            embed = discord.Embed(
                description=f"i reloaded the `{cog}` cog for you! 🌷",
                color=0xf9e5e0,
            )
            await context.send(embed=embed)
        except Exception:
            embed = discord.Embed(
                description=f"i'm sorry, i couldn't reload the `{cog}` cog.",
                color=0xf8bdb9,
            )
            await context.send(embed=embed)

    # Command: snuggle_up (shutdown)
    @commands.hybrid_command(name="snuggle_up", description="Put me to sleep.")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def snuggle_up(self, context: Context) -> None:
        embed = discord.Embed(
            description="i'll snuggle up for a nap now. sweet dreams! 💤🐰",
            color=0xf9e5e0,
        )
        await context.send(embed=embed)
        await self.bot.close()

    # Command: chirp (speak)
    @commands.hybrid_command(name="chirp", description="I'll repeat whatever you say!")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def chirp(self, context: Context, message: str) -> None:
        await context.send(f"{message}")

    # Command: embed
    @commands.hybrid_command(
        name="embed",
        description="I'll say anything you want, but within embeds.",
    )
    @app_commands.describe(
        message="The message you'd like me to repeat.",
        color="The color you'd like the embed to be. Please use a hex code like `#ffffff` or `ffffff`",
    )
    @commands.is_owner() # TODO: DOUBLE TRIPLE CHECK THIS BY ADDING OWNERID TO CONFIG FILE
    @app_commands.guilds(GUILD)
    async def embed(self, context: Context, message: str, color: str = None) -> None:
        embed_color = 0xf9e5e0
        # validate color if provided
        if color:
            match = re.fullmatch(r"#?([a-fA-F0-9]{6})", color)
            if match:
                embed_color = int(match.group(1), 16)
            else:
                embed = discord.Embed(
                    description="i'm sorry, i only understand colors in hex code, like `#ffffff` or `ffffff`.",
                    color=0xf8bdb9,
                )
                await context.send(embed=embed)
                return
        embed = discord.Embed(description=message, color=embed_color)
        await context.send(embed=embed) 
        
    # Command: clear
    @commands.hybrid_command(name="clear", description="Let me tidy up for you, how many messages should I clear?")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def clear(self, context: Context, amount: int) -> None:
        await context.channel.purge(limit=amount)
        embed = discord.Embed(
            description=f"all done! i cleared {amount} messages! 🧹",
            color=0xf9e5e0,
        )
        await context.send(embed=embed)
      
    # Command: set status  
    @commands.hybrid_command(name="setstatus", description="Let's set my status! What would you like me to do today?")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def setstatus(self, context: Context, activity_type: str, *, message: str) -> None:
        activity_types = {
            "playing": discord.Game,
            "watching": discord.Activity,
            "listening": discord.Activity,
        }

        if activity_type.lower() not in activity_types:
            await context.send("sorry! i only know 'playing', 'watching', or 'listening'. can we try again?")
            return

        activity = activity_types[activity_type.lower()](name=message)
        await self.bot.change_presence(activity=activity)
        embed = discord.Embed(
            description=f"yay! i'm now {activity_type} {message}. let's go!",
            color=0xf9e5e0,
        )
        await context.send(embed=embed)
        
    # Command: eval
    @commands.hybrid_command(name="eval", description="I'll give it a try! Show me your code!")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def _eval(self, context: Context, *, code: str) -> None:
        try:
            result = eval(code)
            await context.send(f"here's the result: {result}")
        except Exception as e:
            await context.send(f"oh no! something went wrong... {e} 🐰💦")
        
    # Command: debug    
    @commands.hybrid_command(name="debug", description="Let's check things out! Should I turn on debug mode?")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def debug(self, context: Context, enable: bool) -> None:
        if enable:
            self.bot.debug_mode = True
            embed = discord.Embed(
                description="debugging mode is now ON! i'll give you all the details you need! 🐇🔧",
                color=0xf9e5e0,
            )
        else:
            self.bot.debug_mode = False
            embed = discord.Embed(
                description="i've turned off debugging mode! all is peaceful now~",
                color=0xf9e5e0,
            )
        await context.send(embed=embed)
       
    # Command: blacklist     
    @commands.hybrid_command(name="blacklist", description="Let me help you keep things safe. I'll make sure this user can't interact with me.")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def blacklist(self, context: Context, user: discord.User) -> None:
        self.bot.blacklist.add(user.id)
        embed = discord.Embed(
            description=f"{user.name} is now blacklisted and can't interact with me anymore.",
            color=0xf9e5e0,
        )
        await context.send(embed=embed)
      
    # Command: whitelist  
    @commands.hybrid_command(name="whitelist", description="Oh, this person gets another chance to play with me!")
    @commands.is_owner()
    @app_commands.guilds(GUILD)
    async def whitelist(self, context: Context, user: discord.User) -> None:
        self.bot.blacklist.discard(user.id)
        embed = discord.Embed(
            description=f"all set! {user.name} is now whitelisted!",
            color=0xf9e5e0,
        )
        await context.send(embed=embed)

async def setup(bot) -> None:
    await bot.add_cog(Owner(bot))