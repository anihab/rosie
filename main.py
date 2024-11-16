import os
import logging
from datetime import datetime, timedelta

import aiosqlite
import dateparser
import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.reactions = True

load_dotenv()
GUILD_ID = discord.Object(os.getenv("GID"))

class RosieBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.database_file = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "database", "database.db"
        )
        self.reminders = []

    async def setup_hook(self):
        guild_id = discord.Object(int(os.getenv("GID")))
        await self.tree.sync(guild=guild_id)
        await self.init_db()
        await self.load_db()

    async def on_ready(self):
        logger.info("Logged on as %s!", self.user.name)
        try:
            guild = GUILD_ID
            synced_commands = await self.tree.sync(guild=guild)
            logger.info("Synced %d commands to guild %d.", len(synced_commands), guild.id)
            self.check_reminders.start()
        except Exception as e:
            logger.error("Error syncing commands: %s", {e})

    async def init_db(self) -> None:
        async with aiosqlite.connect(self.database_file) as db:
            schema_path = os.path.join(
                os.path.dirname(os.path.realpath(__file__)), "database", "schema.sql"
            )
            with open(schema_path, "r") as schema_file:
                await db.executescript(schema_file.read())
            await db.commit()

    async def load_db(self):
        async with aiosqlite.connect(self.database_file) as db:
            try:
                async with db.execute(
                    """
                    SELECT id, title, time, interval, channel, mention, user_id, message
                    FROM reminders
                    """
                ) as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        reminder = {
                            "id": row[0],
                            "title": row[1],
                            "time": datetime.fromisoformat(row[2]),
                            "interval": row[3],
                            "channel": row[4],
                            "mention": row[5],
                            "user_id": row[6],
                            "message": row[7],
                        }
                        self.reminders.append(reminder)
            except Exception as e:
                logger.error("Error loading the database: %s", e)

    @tasks.loop(minutes=1)
    async def check_reminders(self):
        now = datetime.now()
        async with aiosqlite.connect(self.database_file) as db:
            for reminder in self.reminders[:]:
                if reminder["time"] <= now:
                    # Send the reminder to specified channel or DM user
                    try:
                        if reminder["channel"]:
                            channel = self.get_channel(reminder["channel"])
                            if channel:
                                mention_str = f"<@&{reminder['mention']}>" if reminder["mention"] else ""
                                await channel.send(f"{mention_str} **Reminder:** {reminder['message']}")
                        else:
                            user = await self.fetch_user(reminder["user_id"])
                            if user:
                                await user.send(f"**Reminder:** {reminder['message']}")
                    except Exception as e:
                        logger.error("Failed to set reminder: %s", {e})

                    # Handle recurring reminders
                    if reminder["interval"] == "minutes":
                        reminder["time"] += timedelta(minutes=1)
                    elif reminder["interval"] == "hourly":
                        reminder["time"] += timedelta(hours=1)
                    elif reminder["interval"] == "daily":
                        reminder["time"] += timedelta(days=1)
                    elif reminder["interval"] == "weekly":
                        reminder["time"] += timedelta(weeks=1)
                    elif reminder["interval"] == "monthly":
                        reminder["time"] += timedelta(days=30)
                    else:
                        self.reminders.remove(reminder)        # delete one-time reminders
                        await db.execute(
                            "DELETE FROM reminders WHERE id = ?",
                            (reminder["id"],),
                        )
                        await db.commit()
                        continue

                    # Update recurring reminder time in the database
                    await db.execute(
                        "UPDATE reminders SET time = ? WHERE id = ?",
                        (reminder["time"].isoformat(), reminder["id"])
                    )
                    await db.commit()

    async def on_message(self, message):
        if message.author == self.user or message.author.bot:
            return
        await self.process_commands(message)

rosie = RosieBot(command_prefix="!", intents=intents)

# Command: hello
@rosie.tree.command(name="hello", description="Say hello!", guild=GUILD_ID)
async def say_hello(interaction: discord.Interaction):
    await interaction.response.send_message("Hello there!")

# Command: create reminder
@rosie.tree.command(name="remind", description="Create a new reminder.", guild=GUILD_ID)
@app_commands.describe(
    title="Title of the reminder",
    time="Time for the reminder (e.g., Monday at 8am)",
    interval="Repeat interval (e.g., daily, weekly, every 2 months)",
    channel="Channel to send the reminder in. If no channel is set, Rosie will DM you.",
    mention="Role to mention",
    message="Custom message for the reminder"
)
async def create_reminder(
    interaction: discord.Interaction,
    title: str,
    time: str,
    interval: str = None,
    channel: discord.TextChannel = None,
    mention: discord.Role = None,
    message: str = None,
):
    try:
        reminder_datetime = dateparser.parse(time)
        if not reminder_datetime or reminder_datetime <= datetime.now():
            raise ValueError("Invalid or past time.")
    except ValueError:
        await interaction.response.send_message(
            "I'm sorry, that time didn't work. Please provide a valid future time like 'tomorrow at 9pm' or 'next Monday at 8am'.",
            ephemeral=True
        )
        return
    
    reminder = {
        "title": title,
        "time": reminder_datetime,
        "interval": interval.lower() if interval else None,
        "channel": channel.id if channel else None, # use None for DM
        "mention": mention.id if mention else None,
        "user_id": interaction.user.id,  # save the user ID for DM
        "message": message if message else f"This is your reminder: **{title}**"
    }
    
    # parse custom intervals
    if interval:
        num = 0
        unit = ""
        if "every" in interval:
            # Handle common variations in interval formatting
            parts = interval.split()
            if len(parts) == 2:
                # if the interval is "every <X>" (e.g., "every day", "every week")
                num = 1
                unit = parts[1]
            elif len(parts) == 3:
                # if the interval is "every <X> <unit>" (e.g., "every 2 days")
                try:
                    num = int(parts[1])
                    unit = parts[2]
                except ValueError:
                    await interaction.response.send_message(
                        "I'm sorry, I couldn't understand that interval. Try something like 'daily' or 'every 2 hours'.",
                        ephemeral=True
                    )
                    return
            else:
                await interaction.response.send_message(
                        "I'm sorry, I couldn't understand that interval. Try something like 'daily' or 'every 2 hours'.",
                        ephemeral=True
                )
                return
        else:
            # Handle fixed intervals like 'daily'
            if interval == "daily":
                num = 1
                unit = "days"
            elif interval == "weekly":
                num = 1
                unit = "weeks"
            elif interval == "monthly":
                num = 1
                unit = "months"
            else:
                await interaction.response.send_message(
                    f"I'm sorry, I couldn't understand that interval. Try something like 'daily' or 'every 2 hours'.",
                    ephemeral=True
                )
                return
            
        # Now, handle the valid interval unit    
        if unit in ["minutes", "hours", "days", "weeks", "months"]:
            reminder["interval"] = (num, unit)
        else:
            await interaction.response.send_message(
                "I'm sorry, I couldn't understand that time. Use one of: minutes, hours, days, weeks, months.",
                ephemeral=True
            )
            return
    
    try:
        async with aiosqlite.connect(rosie.database_file) as db:
            cursor = await db.execute('''
                INSERT INTO reminders (title, time, interval, channel, mention, user_id, message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                reminder["title"],
                reminder["time"].isoformat(),
                reminder["interval"],
                reminder["channel"],
                reminder["mention"],
                reminder["user_id"], 
                reminder["message"]
            ))
            reminder["id"] = cursor.lastrowid
            await db.commit()
            rosie.reminders.append(reminder)

            # confirm with the user
            destination = f"in {channel.mention}" if channel else "through DM"
            await interaction.response.send_message(
                f"Okay! I'll make sure to remind you about '{title}' '{destination}' when it's '{time}'!", 
                ephemeral=True
            )
    except Exception as e:
        logger.error(f"Failed to create reminder: {e}")
        await interaction.response.send_message(
            "An error occurred while setting the reminder. Please try again.",
            ephemeral=True
        )
  
# Command: list reminders      
@rosie.tree.command(name="list", description="View your active reminders.")
async def list_reminders(interaction: discord.Interaction):
    user_id = interaction.user.id
    async with aiosqlite.connect(rosie.database_file) as db:
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

rosie.run(os.getenv("TOKEN"))