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

GUILD_ID = discord.Object(os.getenv("GID"))

class Client(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.database_file = f"{os.path.realpath(os.path.dirname(__file__))}/database/database.db"
        self.reminders = []

    async def setup_hook(self):
        await self.tree.sync(guild=discord.Object(int(os.getenv("GID"))))
        await self.init_db()
        await self.load_db()

    async def on_ready(self):
        print(f'Logged on as {self.user.name}!')
        try:
            # sync commands after the bot is ready
            guild = GUILD_ID
            synced = await self.tree.sync(guild=guild)
            print(f'I synced {len(synced)} commands to guild {guild.id}')
            
            # start background task after bot is ready
            self.check_reminders.start()
        except Exception as e:
            print(f'Error syncing commands: {e}')

    async def init_db(self) -> None:
        async with aiosqlite.connect(self.database_file) as db:
            with open(f"{os.path.realpath(os.path.dirname(__file__))}/database/schema.sql") as file:
                await db.executescript(file.read())
            await db.commit()

    async def load_db(self):
        async with aiosqlite.connect(self.database_file) as db:
            async with db.execute("SELECT id, title, time, interval, channel, mention, message FROM reminders") as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    reminder_id, title, time_str, interval, channel_id, mention_id, message = row
                    reminder_datetime = datetime.fromisoformat(time_str)
                    self.reminders.append({
                        "id": reminder_id,
                        "title": title,
                        "time": reminder_datetime,
                        "interval": interval,
                        "channel": channel_id,
                        "mention": mention_id,
                        "message": message
                    })

    @tasks.loop(seconds=60)  # check every minute
    async def check_reminders(self):
        now = datetime.now()
        async with aiosqlite.connect(self.database_file) as db:
            for reminder in self.reminders[:]:  # copy of the list to modify safely
                if reminder["time"] <= now:
                    # send the reminder
                    channel = self.get_channel(reminder["channel"])
                    if channel:
                        mention_str = f"<@&{reminder['mention']}>" if reminder["mention"] else ""
                        await channel.send(f"{mention_str} **Reminder:** {reminder['message']}")

                    # handle repeating reminders
                    if reminder["interval"] == "daily":
                        reminder["time"] += timedelta(days=1)
                    elif reminder["interval"] == "weekly":
                        reminder["time"] += timedelta(weeks=1)
                    elif reminder["interval"] == "monthly":
                        reminder["time"] += timedelta(days=30)
                    else:
                        self.reminders.remove(reminder)
                        await db.execute("DELETE FROM reminders WHERE id = ?", (reminder["id"],))
                        await db.commit()
                        continue  # skip updating if it's a one-time reminder

                    # update the reminder time in the database for recurring reminders
                    await db.execute("UPDATE reminders SET time = ? WHERE id = ?", (reminder["time"].isoformat(), reminder["id"]))
                    await db.commit()

    async def on_message(self, message):
        if message.author == self.user or message.author.bot:
            return
        await self.process_commands(message)

bot = Client(command_prefix="!", intents=intents)

@bot.tree.command(name="hello", description="Say hello!", guild=GUILD_ID)
async def seyHello(interaction: discord.Interaction):
    await interaction.response.send_message(f"Hello there!")

@bot.tree.command(name="remind", description="Create a new reminder", guild=GUILD_ID)
@app_commands.describe(
    title="Title of the reminder",
    time="Time for the reminder (e.g., 10:30pm)",
    interval="Repeat interval (e.g., daily, weekly)",
    channel="Channel to send the reminder in",
    mention="Role to mention",
    message="Custom message for the reminder"
)
async def create_reminder(interaction: discord.Interaction, title: str, time: str, interval: str = None, channel: discord.TextChannel = None, mention: discord.Role = None, message: str = None):
    # parse the specified time
    try:
        reminder_time = datetime.strptime(time, "%I:%M%p").time()
    except ValueError:
        await interaction.response.send_message(
            "I'm sorry, that didn't work! Please input the time in a 12 hour format (e.g., 10:30pm)",
            ephemeral=True
            )
        return
    
    now = datetime.now()
    reminder_datetime = datetime.combine(now.date(), reminder_time)
    if reminder_datetime < now:
        reminder_datetime += timedelta(days=1)  # Schedule for the next day if time has passed
    
    # validate interval
    valid_intervals = ["daily", "weekly", "monthly", "yearly"]
    if interval and interval.lower() not in valid_intervals:
        await interaction.response.send_message(
            f"I'm sorry, that interval isn't valid! Please choose from: {', '.join(valid_intervals)}.",
            ephemeral=True
        )
        return
    
    # prepare reminder data
    reminder = {
        "title": title,
        "time": reminder_datetime,
        "interval": interval.lower() if interval else None,
        "channel": channel.id if channel else interaction.channel.id,
        "mention": mention.id if mention else None,
        "message": message if message else f"This is your reminder: **{title}**"
    }
    
    # insert into the database
    async with aiosqlite.connect(bot.database_file) as db:
        cursor = await db.execute('''
            INSERT INTO reminders (title, time, interval, channel, mention, message)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            reminder["title"],
            reminder["time"].isoformat(),
            reminder["interval"],
            reminder["channel"],
            reminder["mention"],
            reminder["message"]
        ))
        reminder_id = cursor.lastrowid
        await db.commit()
        
    # add to the in-memory list with its database ID
    reminder["id"] = reminder_id
    bot.reminders.append(reminder)
        
    await interaction.response.send_message(f"Okay! I'll make sure to remind you about '{title}' when it's '{time}'!", ephemeral=True)

bot.run(os.getenv("TOKEN"))