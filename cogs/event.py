import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context
from datetime import datetime
from dateutil.tz import gettz
import dateparser


class Event(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    async def fetch_event_message(self, context: Context, event_id: str):
        """Fetch the event message from Discord."""
        async with self.bot.db.execute(
            "SELECT channel_id FROM events WHERE id = ?", (event_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                await context.send(
                    "oh no! i couldn't find the original event message. please check and try again.",
                    ephemeral=True,
                )
                return

        channel = self.bot.get_channel(row[0])
        if not channel:
            await context.send(
                "oh no! i couldn't find the event channel. please check and try again.",
                ephemeral=True,
            )
            return

        event_message = await channel.fetch_message(event_id)
        if not event_message.embeds:
            await context.send(
                "The event message is missing or corrupted.", ephemeral=True
            )
            return

    async def fetch_suggestions(bot, event_id):
        async with bot.db.execute(
            "SELECT time, emoji FROM suggestions WHERE event_id = ?", (event_id,)
        ) as cursor:
            return await cursor.fetchall()

    async def create_event(self, event_message: discord.Message, time):
        async with self.bot.db.execute(
            "SELECT channel_id, role_id FROM events WHERE message_id = ?",
            (event_message.id,),
        ) as cursor:
            event_data = await cursor.fetchone()

        if not event_data:
            raise ValueError("Event not found in the database.")

        channel_id, role_id = event_data
        channel = self.bot.get_channel(channel_id)
        if not channel:
            raise ValueError("Channel not found.")

        event_message = await channel.fetch_message(event_message.id)
        embed = event_message.embeds[0]
        embed.description += (
            f"\n\n**chosen time:** <t:{int(time.timestamp())}:F>"
            f"\nvotes will no longer be counted!"
        )
        await event_message.edit(embed=embed)

        # notify the guild
        role_mention = f"<@&{role_id}> " if role_id else ""
        notif_message = (
            f"{role_mention}🌟 *our event has been finalized!*\n"
            f"we'll be meeting at <t:{int(time.timestamp())}:F>.\n"
            f"hope to see you there!"
        )
        await channel.send(notif_message)

        await self.bot.db.execute(
            "DELETE FROM events WHERE message_id = ?", (event_message.id,)
        )
        await self.bot.db.commit()

    # Command Group: /event
    @commands.hybrid_group(name="event", description="Manage events.")
    async def event(self, context: Context):
        await context.send(
            "Please use a subcommand to manage events. Try `/event plan` or `/event list`.",
            ephemeral=True,
        )

    # Command: /event plan
    @event.command(name="plan", describe="Send out a message to plan a group event.")
    @commands.has_permissions(manage_events=True)
    @app_commands.describe(
        activity="The activity you'd like to do. (e.g., a group study session) ",
        channel="The channel you'd like to send this message in.",
        role="A role to ping.",
        color="A hex-code color for the embed. (e.g., #ffffff)",
    )
    async def plan(
        self,
        context: Context,
        activity: str,
        channel: discord.TextChannel,
        role: discord.Role = None,
        color: str = None,
    ):
        """Start planning a group event with friends!"""
        embed_color = discord.Color.default()
        if color:
            try:
                embed_color = discord.Color(int(color.lstrip("#"), 16))
            except ValueError:
                await context.send(
                    "sorry but that doesn't look like a valid hex code! try again?",
                    ephemeral=True,
                )

        role_mention = f"<@&{role.id}>\n" if role else ""
        description = (
            f"{role_mention}"
            f"🌸 *let's plan an event!*\n"
            f"we're thinking about **{activity}**.\n"
            f"suggest a time using `/event suggest`, or vote for someone else's idea by reacting with the corresponding emoji!\n\n"
            f"`this message will be updated with suggestions as they are added.`"
        )
        embed = discord.Embed(description=description, color=embed_color)
        message = await channel.send(embed=embed)

        await self.bot.db.execute(
            """
                INSERT INTO events (message_id, channel_id, creator_id, role_id, activity)
                VALUES (?, ?, ?, ?, ?)
                """,
            (
                message.id,
                channel.id,
                context.author.id,
                role.id if role else None,
                activity,
            ),
        )
        await self.bot.db.commit()
        
        embed.description += f"\n**event id:** `{message.id}`\n\n"
        await message.edit(embed=embed)

        await context.send(
            f"your event has been created! others can suggest times using `/event suggest {message.id}`!\n"
            f"you can use `/event tally` when you're ready to finalize the event!",
            ephemeral=True,
        )

    # Command: /event suggest
    @event.command(
        name="suggest",
        description="Suggest a time for an event and an emoji for others to vote with.",
    )
    @app_commands.describe(
        event_id="The event message ID.",
        time="The time you would like to propose (e.g., 'Friday at 8pm')",
        timezone="A timezone (e.g., 'America/New York' or 'UTC'). Don't worry, I won't save this!",
        emoji="An emoji for others to vote on your suggestion.",
    )
    async def suggest(
        self,
        context: Context,
        event_id: str,
        time: str,
        timezone: str,
        emoji: str,
    ):
        """Suggest a time for an event."""
        

        timezone = timezone.strip().replace(" ", "_")
        if not gettz(timezone):
            await context.send(
                "i couldn't find that timezone!",
                ephemeral=True,
            )
            return

        # parse the suggested time using the given timezone
        settings = {
            "TIMEZONE": timezone,
            "TO_TIMEZONE": "UTC",
            "RETURN_AS_TIMEZONE_AWARE": True,
        }
        parsed_time = dateparser.parse(time, settings=settings)
        if not parsed_time or parsed_time <= datetime.now(gettz("UTC")):
            await context.send(
                "i'm sorry, that time didn't work. please provide a valid future time like 'tomorrow at 9pm' or 'next Monday at 8am'.",
                ephemeral=True,
            )
            return

        # convert the time to a UNIX timestamp
        unix_timestamp = int(parsed_time.timestamp())

        # add the suggestion to the event
        try:
            await self.bot.db.execute(
                """
                INSERT INTO suggestions (event_id, user_id, time, emoji)
                VALUES (?, ?, ?, ?)
                """,
                (event_id, context.author.id, parsed_time.isoformat(), emoji),
            )
            await self.bot.db.commit()

            embed = event_message.embeds[0]
            embed.description += (
                f"{emoji} <t:{unix_timestamp}> (suggested by {context.author.mention})"
            )
            await event_message.edit(embed=embed)
            await event_message.add_reaction(emoji)

            await context.send(
                f"yay! your suggestion was added to the event message.",
                ephemeral=True,
            )
        except discord.HTTPException:
            await context.send(
                f"sorry, but `{emoji}` doesn't seem like a valid emoji! try again?",
                ephemeral=True,
            )
            return

    # Command: /event tally
    @event.command(
        name="tally",
        description="Finalize the time for an event based on vote results.",
    )
    @app_commands.describe(event_id="The event message ID.")
    @commands.has_permissions(manage_events=True)
    async def tally(self, context: Context, event_id: str):
        """Finalize the time for an event based on vote results."""
        async with self.bot.db.execute(
            """
            SELECT channel_id, creator_id
            FROM events
            WHERE message_id = ?
            """,
            (event_id,),
        ) as cursor:
            event_data = await cursor.fetchone()

        if not event_data:
            await context.send(
                "oh no! i couldn't find an event with that ID. please double-check and try again.",
                ephemeral=True,
            )
            return

        channel_id, creator_id = event_data
        channel = self.bot.get_channel(channel_id)
        if not channel:
            await context.send(
                "i couldn't find the event's channel. please check the event setup.",
                ephemeral=True,
            )
            return

        event_message = await channel.fetch_message(event_id)
        if not event_message.embeds:
            await context.send(
                "The event message is missing or corrupted.", ephemeral=True
            )
            return

        # tally votes for each suggestion
        async with self.bot.db.execute(
            """
            SELECT time, emoji
            FROM suggestions
            WHERE event_id = ?
            """,
            (event_id,),
        ) as cursor:
            suggestions = await cursor.fetchall()

        if not suggestions:
            await context.send(
                "it looks like no one voted on the suggestions yet. try again later!",
                ephemeral=True,
            )
            return

        vote_counts = {}
        for reaction in event_message.reactions:
            for suggestion in suggestions:
                if suggestion[1] == reaction.emoji:
                    vote_counts[suggestion[0]] = (
                        reaction.count - 1
                    )  # subtract 1 for bot's reaction

        if not vote_counts:
            await context.send(
                "it looks like no one voted on the suggestions yet. try again later!",
                ephemeral=True,
            )
            return

        # find the time(s) with the most votes
        max_votes = max(vote_counts.values())
        top_suggestions = [
            time for time, votes in vote_counts.items() if votes == max_votes
        ]

        if len(top_suggestions) > 1:
            # notify the event creator in case of a tie
            creator_id = self.active_events[event_id]["creator"]
            ties = "\n".join(
                f"<t:{int(time.timestamp())}> ({max_votes} votes)"
                for time in top_suggestions
            )
            await context.send(
                f"there's a tie between these times:\n{ties}\n"
                f"<@{creator_id}>, please decide which time to finalize by using `/event choose`.",
                ephemeral=True,
            )
            return

        # if no tie, finalize the event with the winning time (most votes)
        await self.create_event(channel, event_message, top_suggestions[0])
        return

    # Command: /event choose
    @event.command(
        name="choose",
        description="Finalize the time for the event as the creator.",
    )
    @app_commands.describe(
        event_id="The ID of the event message.",
        emoji="The emoji corresponding to the time you'd like to choose.",
    )
    @commands.has_permissions(manage_events=True)
    async def choose(self, context: Context, event_id: str, emoji: str):
        """Finalize the event time using an emoji."""
        async with self.bot.db.execute(
            """
            SELECT channel_id, creator_id
            FROM events
            WHERE message_id = ?
            """,
            (event_id,),
        ) as cursor:
            event_data = await cursor.fetchone()

        if not event_data:
            await context.send(
                "oh no! i couldn't find an event with that ID. please double-check and try again.",
                ephemeral=True,
            )
            return

        channel_id, creator_id = event_data
        if context.author.id != creator_id:
            await context.send(
                "only the event creator can choose the final time!",
                ephemeral=True,
            )
            return

        channel = self.bot.get_channel(channel_id)
        if not channel:
            await context.send(
                "i couldn't find the event's channel. please check the event setup.",
                ephemeral=True,
            )
            return

        event_message = await channel.fetch_message(event_id)
        if not event_message.embeds:
            await context.send(
                "The event message is missing or corrupted.", ephemeral=True
            )
            return

        # validate the given emoji
        async with self.bot.db.execute(
            """
            SELECT time
            FROM suggestions
            WHERE event_id = ? AND emoji = ?
            """,
            (event_id, emoji),
        ) as cursor:
            chosen_time = await cursor.fetchone()

        if not chosen_time:
            await context.send(
                "i couldn't find that emoji among the suggestions. please double-check and try again!",
                ephemeral=True,
            )
            return

        # finalize the time
        await self.create_event(event_message, chosen_time[0])
        return

    # Command: /event list
    @event.command(
        name="list",
        description="List all active event plans and their suggested times.",
    )
    @commands.has_permissions(manage_events=True)
    async def list(self, context: Context):
        """List all active events."""
        async with self.bot.db.execute(
            """
            SELECT e.message_id, e.channel_id, e.creator_id, s.time, s.emoji
            FROM events e
            LEFT JOIN suggestions s ON e.message_id = s.event_id
            """
        ) as cursor:
            results = await cursor.fetchall()

        if not results:
            await context.send(
                "you're not planning an events right now! why not start one with `/event plan`?",
                ephemeral=True,
            )
            return

        # group results by event
        events = {}
        for message_id, channel_id, creator_id, time, emoji in results:
            if message_id not in events:
                events[message_id] = {
                    "channel_id": channel_id,
                    "creator_id": creator_id,
                    "suggestions": [],
                }
            if time or emoji:  # Add suggestions only if they exist
                events[message_id]["suggestions"].append((time, emoji))

        # build response
        response = ""
        for message_id, event_data in events.items():
            channel = self.bot.get_channel(event_data["channel_id"])
            if not channel:
                continue

            event_message_link = f"https://discord.com/channels/{context.guild.id}/{event_data['channel_id']}/{message_id}"
            response += f"**Event ID:** `{message_id}`\n"
            response += f"**Channel:** <#{event_data['channel_id']}>\n"
            response += f"**Creator:** <@{event_data['creator_id']}>\n"
            response += f"**Event Message:** [Click here]({event_message_link})\n"
            response += "**Suggestions:**\n"

            if not event_data["suggestions"]:
                response += "- No suggestions yet.\n"
            else:
                for time, emoji in event_data["suggestions"]:
                    time_text = f"<t:{int(time.timestamp())}:F>"
                    response += f"- {emoji} {time_text}\n"

            response += "\n"


async def setup(bot) -> None:
    await bot.add_cog(Event(bot))
