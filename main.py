# main.py
import os
import asyncio

import aiosqlite
import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
from dotenv import load_dotenv

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

load_dotenv()

GUILD_ID = discord.Object(os.getenv("ID"))

class Client(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.database = None
        
    async def on_ready(self):
        print(f'Logged on as {self.user.name}!')

        try:
            guild = GUILD_ID
            synced = await self.tree.sync(guild=guild)
            print(f'Synced {len(synced)} commands to guild {guild.id}')
        except Exception as e:
            print(f'Error syncing commands: {e}')
    
    async def init_db(self) -> None:
        async with aiosqlite.connect(
            f"{os.path.realpath(os.path.dirname(__file__))}/database/database.db"
        ) as db:
            with open(
                f"{os.path.realpath(os.path.dirname(__file__))}/database/schema.sql"
            ) as file:
                await db.executescript(file.read())
            await db.commit()
            
    async def on_message(self, message):
        if message.author == self.user or message.author.bot:
            return
        await self.process_commands(message)     

bot = Client(command_prefix="!", intents=intents)

@bot.tree.command(name="hello", description="Say hello!", guild=GUILD_ID)
async def seyHello(interaction: discord.Interaction):
    await interaction.response.send_message('hello there!')
    
@bot.tree.command(name="remind", description="Set a new reminder", guild=GUILD_ID)
@app_commands.describe(
    title="Title of the reminder",
    time="Time for the reminder (e.g., 10:30pm)",
    interval="Repeat interval (e.g., daily, weekly)",
    channel="Channel to send the reminder in",
    mention="Role to mention",
    message="Custom message for the reminder"
)
async def set_reminder(interaction: discord.Interaction, title: str, time: str, interval: str = None, channel: discord.TextChannel = None, mention: discord.Role = None, message: str = None):
    # parse the specified time
    try:
        reminder_time = datetime.strptime(time, "%I:%M%p").time()
    except ValueError:
        await interaction.response.send_message("Invalid time format. Please use '10:30pm'.", ephemeral=True)
        return
    
    await interaction.response.send_message(f"Reminder '{title}' set for {time}!", ephemeral=True)
    
    async def send_reminder():
        """
        Send the Reminder
        """
        target_channel = channel if channel else interaction.channel
        mention_str = mention.mention if mention else ""
        reminder_message = message if message else f"This is your reminder: {title}"
        await target_channel.send(f"{mention_str} **Reminder:** {reminder_message}")
        
         # calculate the next reminder's datetime
        now = datetime.now()
        reminder_datetime = datetime.combine(now.date(), reminder_time)
        if reminder_datetime < now:
            reminder_datetime += timedelta(days=1)
        
        # add the reminder to the list
        bot.reminders.append({
            "title": title,
            "time": reminder_datetime,
            "interval": interval.lower() if interval else None,
            "channel": channel.id if channel else interaction.channel.id,
            "mention": mention.id if mention else None,
            "message": message if message else f"This is your reminder: {title}"
        })
        
        await interaction.response.send_message(f"Reminder '{title}' set for {time}!", ephemeral=True)

bot.run(os.getenv("TOKEN"))

# all the different types of events (for reference)
#     on_ready()
#     on_message(message)
#     on_message_edit(before, after)
#     on_message_delete(message)
#     on_member_join(member)
#     on_member_remove(member)
#     on_member_update(before, after)
#     on_guild_join(guild)
#     on_guild_remove(guild)
#     on_reaction_add(reaction, user)
#     on_reaction_remove(reaction, user)