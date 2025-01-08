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

    async def get_event_id(self, message_id, channel_id):
        async with self.bot.db.execute(
            "SELECT eventID FROM events WHERE message = ? AND channel = ?",
            (message_id, channel_id),
        ) as cursor:
             return (await cursor.fetchone())[0]
        
    async def get_event_message(self, event_id):
        async with self.bot.db.execute(
            "SELECT message FROM events WHERE eventID = ?", (event_id,)
        ) as cursor:
             return (await cursor.fetchone())[0]
        
    async def validate_event_and_permissions(self, context, event_id):
        async with self.bot.db.execute(
            "SELECT eventID, message, channel, creator, role FROM events WHERE eventID = ?", (event_id,)
        ) as cursor:
             event_data = await cursor.fetchone()
        
        if not event_data:
            await context.send("oh no! i couldn't find an event with that ID. try again?", ephemeral=True)
            return None

        event_id, message_id, channel_id, creator_id, _ = event_data
        if context.author.id != creator_id:
            await context.send("only the event creator can finalize the event time!", ephemeral=True)
            return None

        try:
            channel = self.bot.get_channel(channel_id)
            message = await channel.fetch_message(message_id)
        except:
            await context.send("the event message is missing or corrupted.", ephemeral=True)
            return None

        return event_data, channel, message

    async def get_suggestions_and_votes(self, event_id, message):
        async with self.bot.db.execute(
            "SELECT time, emoji FROM suggestions WHERE eventID = ?", (event_id,)
        ) as cursor:
            suggestions = await cursor.fetchall()
        
        if not suggestions:
            return None, None

        vote_counts = {}
        for reaction in message.reactions:
            for suggestion in suggestions:
                if suggestion[1] == reaction.emoji:
                    vote_counts[suggestion[0]] = reaction.count - 1  # subtract bot's reaction

        return suggestions, vote_counts
        
    async def create_event(self, eventID, message, channel, time, role_id = None):
        embed = message.embeds[0]
        embed.description += (
            f"\n\n**chosen time:** <t:{int(time.timestamp())}:F>\nvoting is now closed!"
        )
        await message.edit(embed=embed)

        # notify the guild
        role_mention = f"<@&{role_id}> " if role_id else ""
        notification = (
            f"{role_mention}🌟 *our event has been finalized!*\n"
            f"we'll be meeting at <t:{int(time.timestamp())}:F>.\n"
            f"hope to see you there!"
        )
        await channel.send(notification)

        # clean up DB
        await self.bot.db.execute(
            "DELETE FROM events WHERE eventID = ?", (eventID,)
        )
        await self.bot.db.commit()

    # Command Group: /event
    @commands.hybrid_group(name="event", description="Manage events.")
    async def event(self, context: Context):
        await context.send(
            "Use a subcommand to manage events. Try `/event plan` or `/event list`.",
            ephemeral=True,
        )
        return

    # Command: /event plan
    @event.command(name="plan", describe="Send a message to plan an event with friends!")
    @commands.has_permissions(manage_events=True)
    @app_commands.describe(
        activity="The activity to plan. (e.g., a group study session) ",
        channel="The channel to send the message in.",
        role="Role to ping.",
        color="Embed color (hex code, e.g. #ffffff)",
    )
    async def plan(
        self,
        context: Context,
        activity: str,
        channel: discord.TextChannel,
        role: discord.Role = None,
        color: str = discord.Color.default(),
    ):
        if color:
            try:
                embed_color = discord.Color(int(color.lstrip("#"), 16))
            except ValueError:
                await context.send(
                    "sorry but that doesn't look like a valid hex code! try again?",
                    ephemeral=True,
                )
                return

        role_mention = f"<@&{role.id}>\n" if role else ""
        description = (
            f"{role_mention}"
            f"🌸 *let's plan an event!*\n"
            f"**{activity}**.\n"
            f"suggest a time using `/event suggest`, or vote for an existing suggestion with reactions!\n\n"
            f"`this message will be updated with suggestions as they are added.\n`"
        )
        embed = discord.Embed(description=description, color=embed_color)
        message = await channel.send(embed=embed)

        await self.bot.db.execute(
            """
            INSERT INTO events (message, channel, creator, role_mention)
            VALUES (?, ?, ?, ?)
            """,
            (message.id, channel.id, context.author.id, role.id if role else None)
        )
        await self.bot.db.commit()

        event_id = await self.get_event_id(message.id, channel.id)

        embed.description += f"**event id:** `{event_id}`\n\n"
        await message.edit(embed=embed)

        await context.send(
            f"your event has been created! others can suggest times using `/event suggest {event_id}`!\n"
            f"you can use `/event tally` when you're ready to finalize the event!",
            ephemeral=True,
        )

    # Command: /event suggest
    @event.command(name="suggest", description="Suggest a time for an event.")
    @app_commands.describe(
        event_id="The event ID.",
        time="The time to suggest (e.g., 'Friday at 8pm')",
        timezone="A timezone (e.g., 'UTC'). Don't worry, I won't save this!",
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
                INSERT INTO suggestions (eventID, suggestionID, time, emoji)
                VALUES (?, ?, ?, ?)
                """,
                (event_id, parsed_time.isoformat(), emoji)
            )
            await self.bot.db.commit()

            message = await self.get_event_message(event_id)
            
            embed = message.embeds[0]
            embed.description += (
                f"{emoji} <t:{unix_timestamp}> (suggested by {context.author.mention})"
            )
            await message.edit(embed=embed)
            await message.add_reaction(emoji)

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
    @event.command(name="tally", description="Finalize event time by vote results.")
    @app_commands.describe(event_id="The event ID.")
    @commands.has_permissions(manage_events=True)
    async def tally(self, context: Context, event_id: str):
        event_data = await self.validate_event_and_permissions(context, event_id)
        if not event_data:
            return

        _, channel, message = event_data
        _, vote_counts = await self.get_suggestions_and_votes(event_id, message)

        if not vote_counts:
            await context.send("it looks like no one voted on the suggestions yet. try again later!", ephemeral=True)
            return

        # find the time(s) with the most votes
        max_votes = max(vote_counts.values())
        top_suggestions = [
            time for time, votes in vote_counts.items() if votes == max_votes
        ]

        if len(top_suggestions) > 1:
            # notify the event creator in case of a tie
            ties = "\n".join(
                f"<t:{int(time.timestamp())}> ({max_votes} votes)"
                for time in top_suggestions
            )
            await context.send(
                f"there's a tie between these times:\n{ties}\n"
                f"<@{context.author.id}>, please decide which time to finalize by using `/event choose`.",
                ephemeral=True,
            )
            return

        # if no tie, finalize the event with the winning time (most votes)
        await self.create_event(event_id, message, channel, top_suggestions[0], event_data[4])
        return

    # Command: /event choose
    @event.command(
        name="choose",
        description="Choose a suggested event time as the creator.",
    )
    @app_commands.describe(
        event_id="The event ID.",
        emoji="The emoji corresponding to the chosen time.",
    )
    @commands.has_permissions(manage_events=True)
    async def choose(self, context: Context, event_id: str, emoji: str):
        event_data = await self.validate_event_and_permissions(context, event_id)
        if not event_data:
            return

        _, channel, message = event_data
        async with self.bot.db.execute(
            "SELECT time FROM suggestions WHERE eventID = ? AND emoji = ?", (event_id, emoji)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            await context.send("i couldn't find that emoji among the suggestions. try again?", ephemeral=True)
            return

        chosen_time = row[0]
        await self.create_event(event_id, message, channel, chosen_time, event_data[4])
        return

    # Command: /event list
    @event.command(
        name="list",
        description="List all of your active events.",
    )
    @commands.has_permissions(manage_events=True)
    async def list(self, context: Context):
        async with self.bot.db.execute(
            "SELECT eventID, creator, activity FROM events WHERE creator = ?",
            (context.author.id,)
        ) as cursor:
            events = await cursor.fetchall()

        if not events:
            await context.send("you aren't planning any events right now.", ephemeral=True)
            return

        event_list = []
        for event_id, activity in events:
            event_list.append(
                f"**{activity}**\n- ID: `{event_id}`\n"
            )

        formatted_list = "\n\n".join(event_list)
        await context.send(
            f"your active event plans:\n\n{formatted_list}",
            ephemeral=True
        )

async def setup(bot) -> None:
    await bot.add_cog(Event(bot))
