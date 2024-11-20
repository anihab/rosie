import asyncio
import dateparser
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from dateutil import parser
from dateutil.tz import gettz

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
            self.bot.logger.info("Started check_reminders background task")
            now = datetime.now(gettz("UTC"))
            async with self.bot.db.execute(
                "SELECT id, time FROM reminders WHERE time > ? ORDER BY time ASC",
                (now.isoformat(),),
            ) as cursor:
                reminders = await cursor.fetchall()
            
            if not reminders:
                self.bot.logger.info("No reminders found, sleeping for 24 hours.")
                await self.dynamic_sleep(self.max_sleep_duration)
                return
            
            closest_id, closest_time = reminders[0]
            wait_time = (parser.isoparse(closest_time) - now).total_seconds()
            self.bot.logger.info("Next reminder ID: %s at %s in %s seconds", closest_id, closest_time, wait_time)
            
            # sleep until the next reminder is due or a new reminder is added
            await self.dynamic_sleep(wait_time)
            await self.process_due_reminders()
        except Exception as e:
            self.bot.logger.error("Error in check_reminders: %s", e) 
                
    async def process_due_reminders(self) -> None:
        """
        Process reminders that are now due and notify the user.
        """
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
            try:
                if interval:
                    next_time = await self.calculate_next_time(now, interval)
                    await self.bot.db.transaction(
                        "UPDATE reminders SET time = ? WHERE id = ?",
                        (next_time.isoformat(), reminder_id),
                    )
                else:
                    await self.bot.db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
                self.bot.logger.info("Processed reminder ID: %s", reminder_id)
            except Exception as e:
                self.bot.logger.error("Error updating reminder in database: %s", e)  
 
    async def calculate_next_time(self, current_time, interval) -> datetime:
        """ 
        Calculate the next time for a recurring reminder based on the given interval.
        """
        num, unit = interval.split(' ')
        if unit == "minutes":
            return current_time + timedelta(minutes=num)
        elif unit == "hours":
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
        num = 1 # default to 1 if no number is provided
        unit = ""
        interval = interval.lower().strip()
        if interval.startswith("every "):
            parts = interval.split()
            if len(parts) == 2:                      # "every <unit>" (e.g., "every day")
                num, unit = 1, parts[1]
            elif len(parts) == 3:                    # "every <number> <unit>" (e.g., "every 2 days")
                num, unit = int(parts[1]), parts[2]
        elif interval.endswith("ly"):
            num, unit = 1, interval[:-2]
        else:
            raise ValueError("Invalid interval format.")
        
        # validate unit
        if unit in ["minute", "minutes", "hour", "hours", "day", "days", "week", "weeks", "month", "months"]:
            return num, unit
        raise ValueError("Unsupported time unit.")

    # Command: create reminder
    @commands.hybrid_command(name="remind", description="Create a new reminder!")
    @app_commands.describe(
        title="What is this reminder for?",
        time="What time should I remind you at? If it it for today, please say so!(e.g., 'Today at 10:30am' or 'Monday at 8pm')",
        timezone="Include a timezone so I can accurately convert for you! Don't worry, I won't save this information. (e.g., 'America/New_York' or 'UTC')",
        interval="How often should I remind you? If left blank, I'll only remind you once!  (e.g., 'daily', 'every 2 weeks')",
        channel="Is there a channel you'd like me send this reminder in? If not, I'll send you a DM!",
        role="I'll make sure to mention this role. (e.g., '@moderators')",
        message="Any custom message you'd like for the reminder."
    )
    async def create_reminder(self, context: Context, title: str, time: str, timezone: str, interval: str = None, 
                              channel: discord.TextChannel = None, role: discord.Role = None, message: str = None):
        timezone = timezone.strip().replace(" ", "_")
        if not gettz(timezone):
            await context.send("i couldn't find that timezone! please provide a valid timezone like `America/New_York` or `UTC`.", ephemeral=True)
            return
        
        # parse the reminder time using the given timezone
        settings={"TIMEZONE": timezone, "TO_TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True}
        parsed_time = dateparser.parse(time, settings=settings)
        self.bot.logger.info("parsed_time comparison: %s", parsed_time <= datetime.now(gettz("UTC")))
        self.bot.logger.info("parsed time: %s", parsed_time)
        self.bot.logger.info("now: %s", datetime.now(gettz("UTC")))
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
            default_message = (f"hey, just checking in! you have a reminder for **{title}** at this time.\n"
                               "let me know if you completed this task!")
            
            async with self.bot.db.execute(
                "INSERT INTO reminders (title, time, interval, channel_id, role_id, user_id, message) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    title,
                    parsed_time.isoformat(),
                    parsed_interval,
                    channel.id if channel else None,
                    role.id if role else None,
                    context.author.id,
                    message if message else default_message,
                ),
            ) as cursor:
                pass
            await self.bot.db.commit()
            self.sleep_event.set() # signal the background task to wake up and recalculate
        
            # notify the user
            destination = f"in {channel.mention}" if channel else "though DM"
            await context.send(
                f"all set! i've created the reminder **'{title}'** for {time}- that's {parsed_time}!\n"
                "i'll let you know {destination}!",
                ephemeral=True
            )
        except Exception as e:
            await context.send("something went wrong while creating the reminder. please try again later.", ephemeral=True)
            self.bot.logger.error("Error when creating reminder: %s", e)
            
    # Command: view reminders
    @commands.hybrid_command(name="reminders", help="View a list of all your active reminders.")
    async def list_reminders(self, context: Context):
        user_id = context.author.id
        try:
            async with self.bot.db.execute(
                "SELECT id, title, time, interval, channel_id FROM reminders WHERE user_id = ? ORDER BY time ASC",
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
            self.bot.logger.error("Error in list_reminders: %s", e)
       
    # Command: delete reminder     
    @commands.hybrid_command(name="deletereminder", help="Delete one of your reminders by its ID.")
    async def delete_reminder(self, context: Context, reminder_id: int):
        user_id = context.author.id
        try:
            # check if the reminder exists and belongs to the user
            async with self.bot.db.execute(
                "SELECT id FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id)
            ) as cursor:
                reminder = await cursor.fetchone()

            if not reminder:
                await context.send("i couldn't find a reminder with that ID that belongs to you.", ephemeral=True)
                return

            # delete the reminder
            await self.bot.db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
            await self.bot.db.commit()
            await context.send(f"reminder with ID `{reminder_id}` has been deleted!", ephemeral=True)
        except Exception as e:
            await context.send("'m sorry, something went wrong while deleting your reminder! try again later.", ephemeral=True)
            self.bot.logger.error(f"Error in delete_reminder: {e}")

async def setup(bot) -> None:
    await bot.add_cog(Remind(bot))