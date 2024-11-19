import re
import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context, has_permissions, MissingPermissions
from discord import TextChannel
from datetime import datetime, timedelta, timezone

# TODO: check if these permissions make sense ...
class General(commands.Cog):
    """ A collection of general, useful commands !"""
    
    def __init__(self, bot) -> None:
        self.bot = bot
      
    # Command: hello  
    @commands.hybrid_command(name="hello", description="Say hello!")
    async def status(self, context: Context) -> None:
        await context.send(f"hello there, {context.author.name}!")
        
    # Command: chirp (speak)
    @commands.hybrid_command(name="chirp", description="I'll repeat whatever you say!")
    @app_commands.describe(message="What would you like me to say?")
    @has_permissions(manage_messages=True)
    async def chirp(self, context: Context, message: str) -> None:
        await context.send(f"{message}")
        
    # Command: embed
    @commands.hybrid_command(name="embed", description="I'll say anything you want, but in an embed.")
    @app_commands.describe(
        message="What would you like me to say?",
        color="What color would you like the embed to be? Please use a hex code like `#ffffff` or `ffffff`",
    )
    @has_permissions(manage_messages=True)
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

    # Command: clean
    @commands.hybrid_command(
        name="clean",
        description="Let me tidy up! You can specify a number of messages, a phrase, a time range, or a user."
    )
    @app_commands.describe(
        amount="How many recent messages should I check? Defaults to 1.",
        word="A word or phrase to filter messages by. If not specified, all messages are considered.",
        time="Clear messages from the last X minutes. For example, '10' means the last 10 minutes.",
        user="The user whose messages you'd like me to clear. Mention them!",
        channel="The channel you want me to clean. Defaults to the current channel."
    )
    @has_permissions(manage_messages=True)
    async def clean(
        self, context: Context, amount: int = 1, word: str = None, time: int = None, user: discord.Member = None, channel: TextChannel = None
        ) -> None:
        target_channel = channel or context.channel
        if context.interaction:
            await context.interaction.response.defer(ephemeral=True)
        
        def check(message):
            if word and word not in message.content:
                return False
            if time:
                cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=time)
                if message.created_at < cutoff_time:
                    return False
            if user and message.author != user:
                return False
            return True
        
        try:
            # purge messages based on the specified filters
            deleted = await target_channel.purge(limit=amount, check=check)

            # build confirmation message
            description = f"all done! 🧹 i cleared {len(deleted)} messages"
            if word:
                description += f' containing "{word}"'
            if time:
                description += f" from the last {time} minutes"
            if user:
                description += f" from {user.mention}"
            if channel:
                description += f" in {channel.mention}"
            description += "!"

            embed = discord.Embed(description=description, color=0xf8eccf)
            await context.send(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                description="something went wrong while i was cleaning. try again?",
                color=0xf8bdb9,
            )
            await context.send(embed=embed)
            self.bot.logger.error("Error in clean command: %s", e)

async def setup(bot) -> None:
    await bot.add_cog(General(bot))