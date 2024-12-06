import dateparser
from dateutil.tz import gettz

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context


class Event(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.active_events = {}
        self.suggestions = []

    async def create_event(
        self, context: Context, event_message: discord.Message, time
    ):
        """Helper function to create the event in Discord."""
        embed = event_message.embeds[0]
        embed.description += (
            f"\n\n**chosen time:** <t:{int(time.timestamp())}:F>"
            f"\nvotes will no longer be counted!"
        )
        await event_message.edit(embed=embed)

        # notify the guild
        role_mention = ""
        if "role" in self.active_events[event_message.id]:
            role_id = self.active_events[event_message.id]["role"]
            role_mention = f"<@&{role_id}> "

        message = (
            f"{role_mention}🌟 _our event has been finalized!_\n"
            f"we'll be meeting at <t:{int(time.timestamp())}:F>.\n"
            f"get ready for **{self.active_events[event_message.id]['activity']}**!"
        )
        await context.send(message)

    # Command Group: /event
    @commands.hybrid_group(name="event", description="Manage events.")
    async def event(self, context: Context):
        await context.send(
            "Please use a subcommand to manage events. Try `/event plan` or `/event suggest`.",
            ephemeral=True,
        )

    # Command: /event plan
    @event.command(name="plan", describe="Send out a message to plan a group event.")
    @commands.has_permissions(manage_events=True)
    @app_commands.describe(
        activity="The activity you'd like to do. (e.g., We're thinking about **a group study session**) ",
        role="Any role you'd like to ping.",
        color="A color for the embed. Provide a hex code like `#ffffff`",
    )
    async def plan_hangout(
        self,
        context: Context,
        activity: str,
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
            f"🌸 _let's plan an event!_"
            f"we're thinking about **{activity}**. \n"
            f"suggest a time using `/event suggest`, or vote for someone else's idea by reacting with the corresponding emoji!\n\n"
            f"`this message will be updated with suggestions as they are added`"
            f"**event id:** `{context.message.id}`"
        )
        embed = discord.Embed(description=description, color=embed_color)
        message = await context.send(embed=embed)

        self.active_events[message.id] = {
            "activity": activity,
            "creator": context.author.id,
        }
        self.suggestions[message.id] = []

        await context.send(
            f"your event has been created! others can suggest times using `/event suggest {message.id}`!",
            f"\nyou can use `/event tally` when you're ready to finalize the event!",
            ephemeral=True,
        )

    # Command: suggest time
    @event.command(
        name="suggest",
        description="Suggest a time for an event and an emoji for others to vote with.",
    )
    @app_commands.describe(
        event_id="The event message ID.",
        channel="The channel that the event message is in.",
        time="The time you would like to propose (e.g., 'Friday at 8pm')",
        timezone="A timezone (e.g., 'America/New York' or 'UTC'). Don't worry, I won't save this!",
        emoji="An emoji for others to vote on your suggestion.",
    )
    async def suggest_time(
        self,
        context: Context,
        event_id: int,
        channel: discord.TextChannel,
        time: str,
        timezone: str,
        emoji: str,
    ):
        """Suggest a time for an event."""
        if event_id not in self.active_events:
            await context.send(
                "oh no! i couldn't find an event with that ID. please double check and try again.",
                ephemeral=True,
            )
            return

        timezone = timezone.strip().replace(" ", "_")
        if not gettz(timezone):
            await context.send(
                "i couldn't find that timezone! please provide a valid timezone like `America/New York` or `UTC`.",
                ephemeral=True,
            )
            return

        try:
            await context.message.add_reaction(emoji)
        except discord.HTTPException:
            await context.send(
                f"sorry, but `{emoji}` doesn't seem like a valid emoji! try again?",
                ephemeral=True,
            )
            return

        # parse the suggested time using the given timezone
        settings = {
            "TIMEZONE": timezone,
            "TO_TIMEZONE": "UTC",
            "RETURN_AS_TIMEZONE_AWARE": True,
        }
        suggested_time = dateparser.parse(time, settings=settings)

        if not suggested_time:
            await context.send(
                "i couldn't parse that time! try something like 'Friday at 8pm' or 'next Tuesday at 7am'.",
                ephemeral=True,
            )
            return

        # convert the time to a UNIX timestamp
        unix_timestamp = int(suggested_time.timestamp())

        # add the suggestion to the event
        self.suggestions.append(
            {
                "event_id": event_id,
                "time": suggested_time,
                "emoji": emoji,
                "user": context.author,
            }
        )

        try:
            event_message = await channel.fetch_message(event_id)
        except discord.NotFound:
            await context.send(
                "oh no! i couldn't find the original event message. please check the channel and ID and try again.",
                ephemeral=True,
            )
            return

        embed = event_message.embeds[0]
        new_suggestion = (
            f"{emoji} <t:{unix_timestamp}> " f"(suggested by {context.author.mention})"
        )
        embed.description += f"\n{new_suggestion}"
        await event_message.edit(embed=embed)
        await event_message.add_reaction(emoji)

        await context.send(
            f"yay! your suggestion was added to the event message:\n{new_suggestion}",
            ephemeral=True,
        )

    # Command: /event tally
    @event.command(
        name="tally",
        description="Finalize the time for an event based on vote results.",
    )
    @app_commands.describe(
        event_id="The event message ID.",
        channel="The channel where the event message is located.",
    )
    @commands.has_permissions(manage_events=True)
    async def finalize_event(
        self,
        context: Context,
        event_id: int,
        channel: discord.TextChannel,
    ):
        """Finalize the time for an event based on vote results."""
        if event_id not in self.active_events:
            await context.send(
                "oh no! i couldn't find an event with that ID. please double-check and try again.",
                ephemeral=True,
            )
            return

        try:
            event_message = await channel.fetch_message(event_id)
        except discord.NotFound:
            await context.send(
                "oh no! i couldn't find the original event message. please check the channel and ID and try again.",
                ephemeral=True,
            )
            return

        # tally votes for each suggestion
        vote_counts = {}
        for reaction in event_message.reactions:
            for suggestion in self.suggestions:
                if (
                    suggestion["event_id"] == event_id
                    and reaction.emoji == suggestion["emoji"]
                ):
                    vote_counts[suggestion["time"]] = (
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
        tied_times = [time for time, votes in vote_counts.items() if votes == max_votes]

        if len(tied_times) > 1:
            # notify the event creator in case of a tie
            creator_id = self.active_events[event_id]["creator"]
            tied_times_list = "\n".join(
                f"<t:{int(time.timestamp())}> ({max_votes} votes)"
                for time in tied_times
            )
            await context.send(
                f"there's a tie between these times:\n{tied_times_list}\n"
                f"<@{creator_id}>, please decide which time to finalize by using `/event choose`.",
                ephemeral=True,
            )
            return

        # if no tie, finalize the event with the winning time (most votes)
        winning_time = tied_times[0]
        await self.create_event(context, event_message, winning_time)
        unix_timestamp = int(winning_time.timestamp())
        await self.create_event(context, event_message, winning_time)

    # Command: choose time
    @event.command(
        name="choose",
        description="Finalize the time for the event as the creator.",
    )
    @app_commands.describe(
        event_id="The ID of the event message.",
        channel="The channel where the event message is located.",
        emoji="The emoji corresponding to the time you'd like to choose."
    )
    @commands.has_permissions(manage_events=True)
    async def choose_time(self, context: Context, event_id: int, channel: discord.TextChannel, emoji: str):
        """Finalize the event time using an emoji."""
        if event_id not in self.active_events:
            await context.send(
                "oh no! i couldn't find an event with that ID. please double check and try again.",
                ephemeral=True,
            )
            return

        if context.author.id != self.active_events[event_id]["creator"]:
            await context.send(
                "only the event creator can choose the final time!",
                ephemeral=True,
            )
            return

        try:
            event_message = await channel.fetch_message(event_id)
        except discord.NotFound:
            await context.send(
                "oh no! i couldn't find the original event message. please check the channel and ID and try again.",
                ephemeral=True,
            )
            return

        if not self.suggestions[event_id]:
            await context.send(
                "there are no time suggestions for this event yet. please wait for participants to suggest times!",
                ephemeral=True,
            )
            return

        # validate the given emoji
        chosen = next(
            (s for s in self.suggestions[event_id] if s["emoji"] == emoji), None
        )
        if not chosen:
            await context.send(
                "i couldn't find that emoji among the suggestions. please double-check and try again!",
                ephemeral=True,
            )
            return

        # finalize the time
        await self.create_event(context, event_message, chosen["time"])

async def setup(bot) -> None:
    await bot.add_cog(Event(bot))
