import os
import dateparser
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ext.commands import Context
from dotenv import load_dotenv

load_dotenv()
GUILD = discord.Object(os.getenv("GID"))

class Reminder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.reminders = []
        self.check_reminders.start()

    async def cog_load(self):
        await self.load_db()

    async def load_db(self):
        async with aiosqlite.connect(self.bot.database_file) as db:
            try:
                async with db.execute(
                    "SELECT id, title, time, interval, channel, mention, user_id, message FROM reminders"
                ) as cursor:
                    rows = await cursor.fetchall()
                    for row in rows:
                        self.bot.reminders.append({
                            "id": row[0],
                            "title": row[1],
                            "time": datetime.fromisoformat(row[2]),
                            "interval": row[3],
                            "channel": row[4],
                            "mention": row[5],
                            "user_id": row[6],
                            "message": row[7],
                        })
            except Exception as e:
                self.bot.logger.error("Error loading database: %s", e)

    @tasks.loop(minutes=1)
    async def check_reminders(self):
        """ Check reminders and send notifications. """
        now = datetime.now()
        async with aiosqlite.connect(self.bot.database_file) as db:
            for reminder in self.bot.reminders[:]:
                try:
                    if reminder["time"] <= now:
                        # Send the reminder
                        if reminder["channel"]:
                            channel = self.bot.get_channel(reminder["channel"])
                            if channel:
                                mention = f"<@&{reminder['mention']}>" if reminder["mention"] else ""
                                await channel.send(f"{mention} **Reminder:** {reminder['message']}")
                        else:
                            user = await self.bot.fetch_user(reminder["user_id"])
                            if user:
                                await user.send(f"**Reminder:** {reminder['message']}")

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
                            reminder["time"] += relativedelta(months=1)
                        else:
                            self.bot.reminders.remove(reminder)
                            await db.execute("DELETE FROM reminders WHERE id = ?", (reminder["id"],))
                            await db.commit()
                            continue

                        # Update recurring reminder
                        await db.execute(
                            "UPDATE reminders SET time = ? WHERE id = ?",
                            (reminder["time"].isoformat(), reminder["id"])
                        )
                        await db.commit()
                except Exception as e:
                    self.bot.logger.error("Error processing reminder %s: %s", reminder["id"], e)

    # Command: create reminder
    @commands.hybrid_command(name="remind", description="Create a new reminder")
    @app_commands.describe(
        title="Title of the reminder",
        time="Time for the reminder (e.g., 'Monday at 8pm')",
        interval="Repeat interval (e.g., 'daily', 'every 2 weeks')",
        channel="Channel to send the reminder in. Leave blank for a DM.",
        mention="Role to mention with the reminder.",
        message="Custom message for the reminder."
    )
    @app_commands.guilds(GUILD)
    async def create_reminder(
        self,
        context: Context, 
        title: str, 
        time: str, 
        interval: str = None, 
        channel: discord.TextChannel = None, 
        mention: discord.Role = None,
        message: str = None
    ):
        """ Create a new reminder. """
        try:
            reminder_time = dateparser.parse(time)
            if not reminder_time or reminder_time <= datetime.now():
                raise ValueError("Invalid or past time.")
        except ValueError:
            await context.send(
                "I'm sorry, that time didn't work. Please provide a valid future time like 'tomorrow at 9pm' or 'next Monday at 8am'.",
                ephemeral=True
            )
            return

        reminder = {
            "title": title,
            "time": reminder_time,
            "interval": interval.lower() if interval else None,
            "channel": channel.id if channel else None,
            "mention": mention.id if mention else None,
            "user_id": context.author.id,
            "message": message or f"This is your reminder: **{title}**"
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
                        await context.send(
                            "I'm sorry, I couldn't understand that interval. Try something like 'daily' or 'every 2 hours'.",
                            ephemeral=True
                        )
                        return
                else:
                    await context.send(
                            "I'm sorry, I couldn't understand that interval. Try something like 'daily' or 'every 2 hours'.",
                            ephemeral=True
                    )
                    return
            else:
                # handle fixed intervals like 'daily'
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
                    await context.send(
                        "I'm sorry, I couldn't understand that interval. Try something like 'daily' or 'every 2 hours'.",
                        ephemeral=True
                    )
                    return
            
            # set the interval unit   
            if unit in ["minutes", "hours", "days", "weeks", "months"]:
                reminder["interval"] = (num, unit)
            else:
                await context.send(
                    "I'm sorry, I couldn't understand that time. Use one of: minutes, hours, days, weeks, months.",
                    ephemeral=True
                )
                return
            
        try:
            async with aiosqlite.connect(self.bot.database) as db:
                cursor = await db.execute(
                    '''
                    INSERT INTO reminders (title, time, interval, channel, mention, user_id, message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        reminder["title"],
                        reminder["time"].isoformat(),
                        reminder["interval"],
                        reminder["channel"],
                        reminder["mention"],
                        reminder["user_id"],
                        reminder["message"]
                    )
                )
                reminder["id"] = cursor.lastrowid
                await db.commit()
                self.bot.reminders.append(reminder)

                destination = f"in {channel.mention}" if channel else "via DM"
                await context.send(
                    f"Reminder '{title}' created for {time} {destination}.", ephemeral=True
                )
        except Exception as e:
            await context.send(
                "An error occurred while creating the reminder. Please try again later.",
                ephemeral=True
            )

    # Command: list reminders
    @commands.hybrid_command(name="list", description="View your active reminders")
    @app_commands.guilds(GUILD)
    async def list_reminders(self, context: Context):
        """ List all reminders for the user. """
        user_id = context.author.id
        async with aiosqlite.connect(self.bot.database) as db:
            cursor = await db.execute(
                "SELECT id, title, time, interval, message FROM reminders WHERE user_id = ?",
                (user_id,)
            )
            reminders = await cursor.fetchall()

        if not reminders:
            await context.send("You have no active reminders.", ephemeral=True)
            return

        response = "**Your Active Reminders:**\n"
        for reminder in reminders:
            reminder_time = datetime.fromisoformat(reminder[2])
            interval = reminder[3] or "One-time"
            response += f"ID: {reminder[0]} | Title: {reminder[1]} | Time: {reminder_time.strftime('%Y-%m-%d %I:%M%p')} | Interval: {interval} | Message: {reminder[4]}\n"

        await context.send(response, ephemeral=True)

async def setup(bot) -> None:
    await bot.add_cog(Reminder(bot))