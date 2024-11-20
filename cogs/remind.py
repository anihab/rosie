import asyncio
import dateparser
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from dateutil import parser
from dateutil.tz import gettz

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ext.commands import Context


class Remind(commands.Cog):
    """
    Commands for users to set and manage recurring or one-time reminders.
    Utilizes dateparser to parse human readable dates and dateutil to standardize timezones.
    """

    def __init__(self, bot):
        self.bot = bot
        self.check_reminders.start()
        self.sleep_event = asyncio.Event()
        self.max_sleep_duration = 24 * 60 * 60  # cap at 24 hours

    async def cog_load(self):
        if not self.check_reminders.is_running():
            self.check_reminders.start()

    async def cog_unload(self):
        if self.check_reminders.is_running():
            self.sleep_event.set()  # wake up sleeping tasks
            self.check_reminders.cancel()

    async def dynamic_sleep(self, sleep_time: float):
        try:
            await asyncio.wait_for(self.sleep_event.wait(), timeout=sleep_time)
        except asyncio.TimeoutError:
            pass
        finally:
            self.sleep_event.clear()
            
    @tasks.loop(minutes=1)
    async def check_reminders(self) -> None:
        """
        Check for the closest reminder and dynamically adjust the next check.
        """
        try:
            # check for any due reminders due now or earlier
            now = datetime.now(gettz("UTC"))
            async with self.bot.db.execute(
                """
                SELECT id, interval, channel_id, role_id, user_id, message
                FROM reminders
                WHERE time <= ?
                """,
                (now.isoformat(),),
            ) as cursor:
                reminders = await cursor.fetchall()

            if reminders:
                await self.process_due_reminders(reminders)

            # calculate the next reminder for the next time check
            async with self.bot.db.execute(
                """
                SELECT id, time
                FROM reminders
                WHERE time > ? ORDER BY time ASC LIMIT 1
                """,
                (now.isoformat(),),
            ) as cursor:
                upcoming_reminders = await cursor.fetchone()

            # sleep until the next reminder is due or a new reminder is added
            if not upcoming_reminders:
                self.bot.logger.info("No reminders found, sleeping for 24 hours.")
                await self.dynamic_sleep(self.max_sleep_duration)
                return

            closest_id, closest_time = upcoming_reminders[0]
            wait_time = (parser.isoparse(closest_time) - now).total_seconds()
            self.bot.logger.info(
                "Next reminder ID: %s at %s in %s seconds", closest_id, closest_time, wait_time
            )
            await self.dynamic_sleep(wait_time)

        except aiosqlite.Error as e:
            self.bot.logger.error("Database error in check_reminders: %s", e)
        except Exception as e:
            self.bot.logger.error("Unexpected error in check_reminders: %s", e)
                
    async def process_due_reminders(self, reminders) -> None:
        """
        Process reminders that are now due and notify the user.
        """
        now = datetime.now(gettz("UTC"))
        try:
            async with self.bot.db.begin():
                for reminder in reminders:
                    reminder_id, interval, channel_id, role_id, user_id, message = reminder
                    user = await self.bot.fetch_user(user_id)
                    channel = self.bot.get_channel(channel_id)

                    if channel:
                        role_mention = f"<@&{role_id}>" if role_id else ""
                        await channel.send(f"{role_mention} {message}")
                    else:
                        await user.send(f"{message}")

                    # handle recurring reminders
                    if interval:
                        next_time = await self.calculate_next_time(now, interval)
                        await self.bot.db.execute(
                            "UPDATE reminders SET time = ? WHERE id = ?",
                            (next_time.isoformat(), reminder_id),
                        )
                    else:
                        await self.bot.db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
                    self.bot.logger.info("Processed reminder ID: %s", reminder_id)

        except aiosqlite.Error as e:
            self.bot.logger.error("Database error processing reminders: %s", e)
        except Exception as e:
            self.bot.logger.error("Unexpected error processing reminders: %s", e)
 
    async def calculate_next_time(self, current_time, interval) -> datetime:
        """ 
        Calculate the next time for a recurring reminder based on the given interval.
        """
        num, unit = interval.split(' ')
        num = int(num)
        if unit == "hours":
            return current_time + timedelta(hours=num)
        elif unit == "days":
            return current_time + timedelta(days=num)
        elif unit == "weeks":
            return current_time + timedelta(weeks=num)
        elif unit == "months":
            return current_time + relativedelta(months=num)
        return None
    
    async def parse_interval(self, interval):
        """
        Parse user-specified interval into numeric value and unit.
        """
        num = 1  # default to 1 if no number is provided
        unit = ""
        interval = interval.lower().strip()
        if interval.startswith("every "):
            parts = interval.split()
            if len(parts) == 2:  # "every <unit>" (e.g., "every day")
                num, unit = 1, parts[1]
            elif len(parts) == 3:  # "every <number> <unit>" (e.g., "every 2 days")
                num, unit = int(parts[1]), parts[2]
        elif interval.endswith("ly"):
            num, unit = 1, interval[:-2]
        else:
            raise ValueError("Invalid interval format.")

        # validate unit
        if unit in [
            "minute", "minutes", "hour", "hours", "day", "days", "week", "weeks", "month", "months"
        ]:
            return num, unit
        raise ValueError("Unsupported time unit.")
    
    async def can_add_reminder(self, user_id):
        """ Check how many active reminders the user has. """
        async with self.bot.db.execute(
            """
            SELECT COUNT(*) FROM reminders
            WHERE user_id = ? AND time > ?
            """,
            (user_id, datetime.now(gettz("UTC")).isoformat()),
        ) as cursor:
            result = await cursor.fetchone()
            reminder_count = result[0]
            return reminder_count < 5

    # Command: create reminder
    @commands.hybrid_command(name="remind", description="Create a new reminder!")
    @app_commands.describe(
        title="What is this reminder for?",
        time="When should I remind you? If it is for today, please say so!(e.g., 'Today at 10:30am' or 'next Monday 8pm')",
        timezone="Add a timezone so I can convert for you! Don't worry, I won't save this information. (e.g., 'America/New_York' or 'UTC')",
        interval="How often should I remind you? If left blank, I'll only remind you once!  (e.g., 'daily', 'every 2 weeks')",
        channel="Is there a channel you'd like me send this reminder in? If not, I'll send you a DM!",
        role="I'll make sure to mention this role. (e.g., '@moderators')",
        message="Any custom message you'd like for the reminder."
    )
    async def create_reminder(self, context: Context, title: str, time: str, timezone: str, interval: str = None,
                              channel: discord.TextChannel = None, role: discord.Role = None, message: str = None):
        # check if user has 5 active reminders
        if not await self.can_add_reminder(context.author.id):
            await context.send("you can only have up to 5 active reminders at a time. sorry, i'm still a small bot!")
            return

        timezone = timezone.strip().replace(" ", "_")
        if not gettz(timezone):
            await context.send(
                "i couldn't find that timezone! please provide a valid timezone like `America/New York` or `UTC`.",
                ephemeral=True
            )
            return

        # parse the reminder time using the given timezone
        settings = {"TIMEZONE": timezone, "TO_TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True}
        parsed_time = dateparser.parse(time, settings=settings)
        if not parsed_time or parsed_time <= datetime.now(gettz("UTC")):
            await context.send(
                "i'm sorry, that time didn't work. please provide a valid future time like 'tomorrow at 9pm' or 'next Monday at 8am'.",
                ephemeral=True,
            )
            return
        
        # parse custom intervals
        parsed_interval = None
        if interval:
            try:
                num, unit = await self.parse_interval(interval.lower())
                parsed_interval = f"{num} {unit}"
            except ValueError:
                await context.send(
                    "i'm sorry, i couldn't understand that interval. try something like 'daily' or 'every 2 hours'.",
                    ephemeral=True
                )
                return
        
        # save the reminder to the database
        try:
            message = (
                f"hey, just checking in! you have a reminder **{title}** at this time.\n"
                f"let me know if you completed this task!"
                if not message
                else message
            )
            
            async with self.bot.db.execute(
                """
                INSERT INTO reminders (title, time, interval, channel_id, role_id, user_id, message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title, parsed_time.isoformat(), parsed_interval, timezone, channel.id if channel else None,
                    role.id if role else None, context.author.id, message
                )
            ):
                self.bot.db.commit()
                
            # signal the background task to wake up and recalculate
            self.sleep_event.set()
            
            await context.send(
                f"all set! i'll send a friendly reminder for **'{title}'** at {time}.",
                ephemeral=True
            )
        except Exception as e:
            await context.send("something went wrong while creating the reminder. please try again later.", ephemeral=True)
            self.bot.logger.error("Error adding reminder: %s", e)
            
    # Command: list reminders
    @commands.hybrid_command(name="reminders", help="View a list of all your active reminders.")
    async def list_reminders(self, context: Context):
        user_id = context.author.id
        try:
            async with self.bot.db.execute(
                """
                SELECT id, title, time, interval, channel_id
                FROM reminders 
                WHERE user_id = ? ORDER BY time ASC
                """,
                (user_id,),
            ) as cursor:
                reminders = await cursor.fetchall()

            if not reminders:
                await context.send("you don't have any reminders set right now!", ephemeral=True)
                return
            
            embed = discord.Embed(title="your reminders", color=0xf8eccf)
            for reminder in reminders:
                reminder_id, title, time, interval, channel_id = reminder
                channel = f"<#{channel_id}>" if channel_id else "DM"
                interval_text = f" (recurring: {interval})" if interval else ""
                embed.add_field(
                    name=f"ID: {reminder_id}",
                    value=f"**{title}**\nTime: {time}{interval_text}\nChannel: {channel}",
                    inline=False,
                )
            await context.send(embed=embed, ephemeral=True)
            
        except Exception as e:
            await context.send("i'm sorry, i couldn't fetch your reminders! try again later.", ephemeral=True)
            self.bot.logger.error("Error listing reminders: %s", e)
       
    # Command: cancel reminder     
    @commands.hybrid_command(name="cancel", help="Cancel an active reminder!")
    @app_commands.describe(reminder_id="The ID of the reminder you want to cancel. Call /list to find the ID!")
    async def delete_reminder(self, context: Context, reminder_id: int):
        try:
            # check if the reminder exists and belongs to the user
            async with self.bot.db.execute(
                "SELECT id FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, context.author.id)
            ) as cursor:
                reminder = await cursor.fetchone()

            if not reminder:
                await context.send("i couldn't find a reminder with that ID that belongs to you.", ephemeral=True)
                return

            # delete the reminder
            async with self.bot.db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,)):
                self.bot.db.commit()
            await context.send(f"i've canceled your reminder with ID `{reminder_id}`!", ephemeral=True)
            
        except Exception as e:
            await context.send("i'm sorry, something went wrong while deleting your reminder! try again later.", ephemeral=True)
            self.bot.logger.error("Error when deleting reminder: %s", e)

async def setup(bot) -> None:
    await bot.add_cog(Remind(bot))