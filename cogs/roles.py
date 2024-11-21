import re
import asyncio

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import Context

# matches unicode emojis or custom discord emojis (<:name:id> or <a:name:id>)
EMOJI_REGEX = re.compile(
    r"(<a?:\w+:\d{18}>|[\U0001F600-\U0001F64F]|[\U0001F300-\U0001F5FF]|"
    r"[\U0001F680-\U0001F6FF]|[\U0001F1E6-\U0001F1FF]|[\u2600-\u26FF]|"
    r"[\U0001F900-\U0001F9FF]|[\U0001FA70-\U0001FAFF]|[\U0001F700-\U0001F77F])"
)


class ReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def fetch_reaction_roles(self, message_id):
        async with self.bot.db.execute(
            "SELECT emoji, role_id FROM reaction_roles WHERE message_id = ?",
            (message_id,),
        ) as cursor:
            return {row[0]: row[1] for row in await cursor.fetchall()}

    async def update_reaction_roles(self, message_id, emoji_role_mapping, guild_id):
        """
        Updates reaction roles by upserting records for the given message_id.
        Existing mappings will be updated; new mappings will be added.
        """
        try:
            for emoji, role_id in emoji_role_mapping.items():
                await self.bot.db.execute(
                    """
                    INSERT INTO reaction_roles (message_id, emoji, role_id, guild_id)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(message_id, emoji)
                    DO UPDATE SET role_id = excluded.role_id, guild_id = excluded.guild_id
                    """,
                    (message_id, emoji, role_id, guild_id),
                )
            await self.bot.db.commit()  # Commit after the loop
        except Exception as e:
            self.bot.logger.error("Error when updating reaction roles: %s", e)

    async def parse_reaction_payload(self, payload):
        """
        Parses a reaction payload and fetches the corresponding role and user.
        Returns a tuple of (role, user) or None if any lookup fails.
        """
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return None
        
        emoji_role_pairs = await self.fetch_reaction_roles(payload.message_id)
        role = guild.get_role(emoji_role_pairs.get(str(payload.emoji)))
        user = guild.get_member(payload.user_id)

        if not role or not user:
            self.bot.logger.warning(
                "Role or user not found. Role: %s, User: %s (payload.guild_id: %s, payload.user_id: %s)",
                role,
                user,
                payload.guild_id,
                payload.user_id,
            )
            return None

        if not role:
            self.bot.logger.warning(
                "No role found for emoji: %s in message_id: %s",
                payload.emoji,
                payload.message_id,
            )
            return None

        return role, user

    async def wait_for_message(self, context, check, prompt=None, timeout=120):
        """Helper function to handle message waits with timeout."""
        if prompt:
            await context.send(prompt)

        try:
            return await self.bot.wait_for("message", timeout=timeout, check=check)
        except asyncio.TimeoutError:
            await context.send(
                "are you still there? just call me if you'd like to try again later~"
            )
            return None

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        async with self.bot.db.execute(
            "SELECT 1 FROM reaction_roles WHERE message_id = ? LIMIT 1", (payload.message_id,)
        ) as cursor:
            row = await cursor.fetchone()
        
        if not row:
            return
        
        role, user = await self.parse_reaction_payload(payload)
        if role and user:
            await user.add_roles(role)
        else:
            self.bot.logger.warning("Failed to parse reaction payload: %s", payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        async with self.bot.db.execute(
            "SELECT 1 FROM reaction_roles WHERE message_id = ? LIMIT 1", (payload.message_id,)
        ) as cursor:
            row = await cursor.fetchone()
        
        if not row:
            return
        
        role, user = await self.parse_reaction_payload(payload)
        if role and user:
            await user.remove_roles(role)
        else:
            self.bot.logger.warning("Failed to parse reaction payload: %s", payload)

    # Command: reaction role
    @commands.hybrid_command(
        name="reactionrole",
        description="Set up a reaction role message. Give me some basic info and then we'll get started!",
    )
    @commands.has_permissions(manage_roles=True)
    @app_commands.describe(
        title="What would you like the message title to be?",
        description="What would you like the description to be? Type {roles} to include the list of roles!",
        channel="What channel would you like the message to be in?",
        color="What color should the embed be? (hex code like `#ffffff`)",
    )
    async def reaction_role(
        self,
        context: Context,
        title: str,
        description: str,
        channel: discord.TextChannel,
        color: str = None,
    ):
        """Create a reaction roles message."""

        def check_author(message):
            return (
                message.author == context.author and message.channel == context.channel
            )

        def check_reaction(reaction, user):
            return user == context.author and str(reaction.emoji) in [
                ":white_check_mark",
                ":x:",
            ]

        embed_color = discord.Color.default()
        if color:
            try:
                embed_color = discord.Color(int(color.lstrip("#"), 16))
            except ValueError:
                await context.send(
                    "sorry but that doesn't look like a valid hex code! try again?"
                )

        await context.send(
            f"hello! so you'd like to set up a reaction role message in {channel.mention}?\n"
            f"let's get started! please list the emoji-role pairs for me in this format: "
            f"`emoji: role-name`. send pairs one by one and just type `done` when you're "
            f"finished! for example:\n ```🌷: member\n🌸: admin\ndone```\n just start "
            f"whenever you're ready!"
        )

        emoji_role_pairs = {}
        while True:
            role_msg = await self.wait_for_message(context, check_author, timeout=300)
            if role_msg.content.lower() == "done":
                break

            try:
                emoji, role_name = map(str.strip, role_msg.content.split(":", 1))

                if not EMOJI_REGEX.fullmatch(emoji):
                    raise ValueError("Invalid emoji format.")
                
                role = await commands.RoleConverter().convert(context, role_name)
                emoji_role_pairs[emoji] = role.id
                
                await role_msg.add_reaction("✅")
            except ValueError:
                await context.send(
                    "oh no! i couldn't process that. make sure to format it like "
                    "`emoji: role name`. remember the colon and make sure the role exists!"
                )
            except commands.BadArgument:
                await context.send("i couldn't find that role! double-check the name and try again.")

        embed = discord.Embed(title=title, description=description, color=embed_color)
        if "{roles}" in description:
            roles_description = "\n\n" + "\n".join(
                [
                    f"{emoji}: <@&{role_id}>"
                    for emoji, role_id in emoji_role_pairs.items()
                ]
            )
            embed.description = description.replace("{roles}", roles_description)

        confirmation_message = await context.send(
            "almost done! here's what the message will look like, should i post it?",
            embed=embed,
        )
        await confirmation_message.add_reaction("✅")
        await confirmation_message.add_reaction("❌")

        try:
            reaction, _ = await self.bot.wait_for(
                "reaction_add", timeout=60.0, check=check_reaction
            )
            if str(reaction.emoji) == "✅":
                sent_message = await channel.send(embed=embed)
                for emoji in emoji_role_pairs.keys():
                    await sent_message.add_reaction(emoji)

                await self.update_reaction_roles(
                    message_id=sent_message.id,
                    emoji_role_mapping=emoji_role_pairs,
                    guild_id=context.guild.id,
                )

                await context.send("yay! your reaction role message has been posted!")
            else:
                await context.send(
                    "no problem! let me know if you'd like to try again later."
                )
        except asyncio.TimeoutError:
            await context.send(
                "are you still there? just call me if you'd like to try again later~"
            )

async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))
