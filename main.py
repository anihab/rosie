import os
import asyncio

import aiosqlite
import dateparser
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
            print(f'I synced {len(synced)} commands to guild {guild.id}.')
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
                    try:
                        if reminder["channel"]:  # send to a specified channel
                            channel = self.get_channel(reminder["channel"])
                            if channel:
                                mention_str = f"<@&{reminder['mention']}>" if reminder["mention"] else ""
                                await channel.send(f"{mention_str} **Reminder:** {reminder['message']}")
                        else:  # send as a DM
                            user = await self.fetch_user(reminder["user_id"])
                            if user:
                                await user.send(f"**Reminder:** {reminder['message']}")
                    except Exception as e:
                        print(f"Failed to send reminder: {e}")

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
                    await db.execute(
                        "UPDATE reminders SET time = ? WHERE id = ?",
                        (reminder["time"].isoformat(), reminder["id"])
                    )
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
    time="Time for the reminder (e.g., Monday at 8am)",
    interval="Repeat interval (e.g., daily, weekly)",
    channel="Channel to send the reminder in",
    mention="Role to mention",
    message="Custom message for the reminder"
)
async def create_reminder(interaction: discord.Interaction, title: str, time: str, interval: str = None, channel: discord.TextChannel = None, mention: discord.Role = None, message: str = None):
    # parse with dateparser
    try:
        reminder_datetime = dateparser.parse(time)
        if not reminder_datetime:
            raise ValueError("Invalid time format.")
        if reminder_datetime < datetime.now():
            reminder_datetime += timedelta(days=1)
    except ValueError:
        await interaction.response.send_message(
            "I'm sorry, I couldn't understand that time. Try something like 'tomorrow at 9pm' or 'next Monday at 8am'.",
            ephemeral=True
        )
        return
    
    # check if the provided datetime is in the past
    now = datetime.now()
    if reminder_datetime <= now:
        await interaction.response.send_message(
            "I'm sorry, but the specified time is in the past! Please provide a future date and time.",
            ephemeral=True,
        )
        return
    
    # validate interval
    valid_intervals = ["daily", "weekly", "monthly"]
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
        "channel": channel.id if channel else None, # use None for DM
        "mention": mention.id if mention else None,
        "user_id": interaction.user.id,  # save the user ID for DM
        "message": message if message else f"This is your reminder: **{title}**"
    }
    
    try:
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
                reminder["user_id"],
                reminder["message"]
            ))
            reminder_id = cursor.lastrowid
            await db.commit()

            # add to the in-memory list with its database ID
            reminder["id"] = reminder_id
            bot.reminders.append(reminder)

            # confirm with the user
            destination = f"in {channel.mention}" if channel else "as a DM"
            await interaction.response.send_message(
                f"Okay! I'll make sure to remind you about '{title}' when it's '{time}'!", 
                ephemeral=True
            )
    except Exception as e:
        await interaction.response.send_message("Failed to set reminder. Please try again.", ephemeral=True)
        print(f"Error setting reminder: {e}")
        
@bot.tree.command(name="list_reminders", description="View your active reminders.")
async def list_reminders(interaction: discord.Interaction):
    user_id = interaction.user.id
    async with aiosqlite.connect(bot.database_file) as db:
        cursor = await db.execute(
            "SELECT id, title, time, interval, message FROM reminders WHERE user_id = ?",
            (user_id,)
        )
        reminders = await cursor.fetchall()

    if not reminders:
        await interaction.response.send_message("You have no active reminders.", ephemeral=True)
        return

    response = "**Your Active Reminders:**\n"
    for reminder in reminders:
        reminder_time = datetime.fromisoformat(reminder[2])
        interval = reminder[3] or "One-time"
        response += f"ID: {reminder[0]} | Title: {reminder[1]} | Time: {reminder_time.strftime('%Y-%m-%d %I:%M%p')} | Interval: {interval} | Message: {reminder[4]}\n"

    await interaction.response.send_message(response, ephemeral=True)

bot.run(os.getenv("TOKEN"))