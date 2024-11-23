import re
import dateparser
from dateutil.tz import gettz

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context


class Schedule(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self.active_events = {}
        self.suggestions = []

    @commands.hybrid_command(
        name="plan_hangout", describe="Send out a message to plan a group event."
    )
    @commands.has_permissions(manage_events=True)
    @app_commands.describe(
        activity="The activity you'd like to do. (e.g., We're thinking about **a group study session**) ",
        role="Any role you'd like to ping.",
        color="The message color. Provide a hex code like `#ffffff`",
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
            f"🌸 **let's plan an event!**"
            f"we're thinking about **{activity}**. \n"
            f"suggest a time using `/suggest_time`, or vote for someone else's idea by reacting with the corresponding emoji!\n\n"
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
            f"your event has been created! others can suggest times using `/suggest_time {message.id}`",
            ephemeral=True,
        )

    @commands.hybrid_command(
        name="suggest_time",
        description="Suggest a time for an event and an emoji for others to vote with.",
    )
    @app_commands.describe(
        event_id="The ID of the event message.",
        channel="The channel that the event message is in.",
        time="The time you would like to propose (e.g., 'Friday at 8pm')",
        timezone="Your timezone (e.g., 'America/New_York' or 'UTC').",
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
        self.suggestions[event_id].append((suggested_time, context.author))

        # add the suggestion
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
            f"{emoji} {suggested_time.strftime('%m-%d %H:%M %Z')} "
            f"(suggested by {context.author.mention})"
        )
        embed.description += f"\n{new_suggestion}"
        await event_message.edit(embed=embed)
        await event_message.add_reaction(emoji)

        await context.send(
            f"yay! your suggestion was added to the event message:\n{new_suggestion}",
            ephemeral=True,
        )

    # @commands.hybrid_command(name="set_hangout_time")
    # async def set_hangout_time(self, context: Context, event_id: int):
    #     """Finalize a time for the event based on suggestions."""
    #     if event_id not in self.active_events:
    #         await context.send("something went wrong, the event no longer exists!")

    #     if not self.suggestions[event_id]:
    #         await context.send(
    #             "it looks like no one has suggested a time yet. i can't schedule an event without a time!"
    #         )

    #     summary = "\n".join(
    #         f"{i + 1}. {time.strftime('%m-%d %H:%M %Z')} (suggested by {user.display_name})"
    #         for i, (time, user) in enumerate(self.suggestions[event_id])
    #     )

    #     event_msg = await context.send(
    #         f"🌷 **Time Suggestions for our hangout:**\n{summary}\n\n"
    #         "React with the number that works best for you!"
    #     )

    #     for i in range(len(self.suggestions[event_id])):
    #         await event_msg.add_reaction(f"{i + 1}\N{COMBINING ENCLOSING KEYCAP}")

    #     # await asyncio.sleep(60)  # Wait for reactions

    #     event_msg = await context.channel.fetch_message(event_msg.id)
    #     votes = []
    #     for reaction in event_msg.reactions:
    #         if reaction.emoji.isdigit():
    #             votes[int(reaction.emoji)] += reaction.count - 1

    #     if not votes:
    #         await context.send("oh no! no one voted... let's try again later!")
    #         return

    #     winning_index = max(votes, key=votes.get)
    #     final_time, suggester = self.suggestions[event_id][winning_index - 1]

    #     await context.send(
    #         f"🎉 The time is set! We'll hang out at {final_time.strftime('%Y-%m-%d %H:%M %Z')} "
    #         f"(suggested by {suggester.display_name}). Can't wait to see you all!"
    #     )


async def setup(bot) -> None:
    await bot.add_cog(Schedule(bot))
