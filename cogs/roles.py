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
# matches lines like "emoji: <@&role_id>"
ROLES_FORMAT = re.compile(r"^.+?: <@&\d+>$")


class ReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def fetch_reaction_roles(self, message_id):
        async with self.bot.db.execute(
            "SELECT emoji, role_id FROM reaction_roles WHERE message_id = ?",
            (message_id,),
        ) as cursor:
            return {row[0]: row[1] for row in await cursor.fetchall()}

    async def update_reaction_roles(self, message_id, channel_id, emoji_role_pairs, guild_id):
        """
        Updates reaction roles by upserting records for the given message_id.
        Existing mappings will be updated; new mappings will be added.
        """
        try:
            for emoji, role_id in emoji_role_pairs.items():
                await self.bot.db.execute(
                    """
                    INSERT INTO reaction_roles (message_id, channel_id, emoji, role_id, guild_id)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(message_id, emoji)
                    DO UPDATE SET role_id = excluded.role_id, guild_id = excluded.guild_id
                    """,
                    (message_id, emoji, role_id, guild_id),
                )
            await self.bot.db.commit()  # Commit after the loop
        except Exception as e:
            self.bot.logger.error("Error when updating reaction roles: %s", e)

    async def parse_reaction(self, reaction):
        """
        Parses a reaction and fetches the corresponding role.
        """
        guild = reaction.message.guild
        if not guild:
            return None

        emoji_role_pairs = await self.fetch_reaction_roles(reaction.message.id)

        role_id = emoji_role_pairs.get(str(reaction.emoji))
        if not role_id:
            self.bot.logger.warning(
                "No role found for emoji: %s in message_id: %s",
                reaction.emoji,
                reaction.message.id,
            )
            return None

        role = guild.get_role(role_id)
        if not role:
            self.bot.logger.warning(
                "Role not found for role_id: %s in guild_id: %s", role_id, guild.id
            )
            return None

        return role

    async def wait_for_message(self, context, check, prompt=None, timeout=120):
        """Helper function to handle message waits with timeout."""
        if prompt:
            await context.send(prompt)

        try:
            return await self.bot.wait_for("message", timeout=timeout, check=check)
        except asyncio.TimeoutError:
            await context.send(
                "are you still there? just call me if you'd like to try again later!"
            )
            return None

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        async with self.bot.db.execute(
            "SELECT 1 FROM reaction_roles WHERE message_id = ? LIMIT 1",
            (reaction.message.id,),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return

        role = await self.parse_reaction(reaction)
        if not role:
            self.bot.logger.warning("Failed to parse reaction: %s", reaction)
        await user.add_roles(role)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        async with self.bot.db.execute(
            "SELECT 1 FROM reaction_roles WHERE message_id = ? LIMIT 1",
            (reaction.message.id),
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return

        role = await self.parse_reaction(reaction)
        if not role:
            self.bot.logger.warning("Failed to parse reaction: %s", reaction)
        await user.remove_roles(role)

    # Command Group: /rr
    @commands.hybrid_group(name="rr", description="Manage reaction roles.")
    @commands.has_permissions(manage_roles=True)
    async def reaction_role(self, context: Context):
        """Main command for managing reaction roles (called /rr)"""
        await context.send(
            "Please use a subcommand to manage reaction roles. Try `/rr add` or `/rr edit`.",
            ephemeral=True
        )

    # Command: /rr add
    @reaction_role.command(
        name="add",
        description="Create a new reaction role message. First, provide some basic info!",
    )
    @app_commands.describe(
        title="The message title.",
        description="The message description. Type {roles} to include the list of roles!",
        channel="The text channel to send the message in (e.g., #rules).",
        color="The message color. Provide a hex code like `#ffffff`).",
    )
    async def add(
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
            f"please list the emoji-role pairs for me in this format: `emoji: role-name`.\n"
            f"send pairs one by one and just type `done` when you're finished! for example: "
            f"\n ```🌷: member\n🌸: admin\ndone```\n you can start whenever you're ready!"
        )

        emoji_role_pairs = {}
        while True:
            role_message = await self.wait_for_message(
                context, check_author, timeout=300
            )
            if role_message.content.lower() == "done":
                break

            try:
                emoji, role_name = map(str.strip, role_message.content.split(":", 1))

                if not EMOJI_REGEX.fullmatch(emoji):
                    raise ValueError("Invalid emoji format.")

                role = await commands.RoleConverter().convert(context, role_name)
                emoji_role_pairs[emoji] = role.id

                await role_message.add_reaction("🥕")
            except ValueError:
                await context.send(
                    "oh no! i couldn't process that. make sure to format it like "
                    "`emoji: role name`, don't forget the colon!"
                )
            except commands.BadArgument:
                await context.send(
                    "i couldn't find that role! double-check the name and try again."
                )

        embed = discord.Embed(title=title, description=description, color=embed_color)
        if "{roles}" in description:
            roles_description = "\n\n" + "\n".join(
                [
                    f"{emoji}: <@&{role_id}>"
                    for emoji, role_id in emoji_role_pairs.items()
                ]
            )
            embed.description = description.replace("{roles}", roles_description)

        await context.send(
            "almost done! here's what the message will look like, should i post it?\n"
            "please reply with either `yes` or `no`.\n\n",
            embed=embed,
        )

        confirmation_message = await self.wait_for_message(
            context, check_author, timeout=60
        )

        if confirmation_message.content.lower() == "yes":
            await confirmation_message.add_reaction("🥕")
            sent_message = await channel.send(embed=embed)
            for emoji in emoji_role_pairs.keys():
                await sent_message.add_reaction(emoji)
            await self.update_reaction_roles(
                message_id=sent_message.id,
                channel_id=channel.id,
                emoji_role_pairs=emoji_role_pairs,
                guild_id=context.guild.id,
            )
            await context.send(
                f"yay! your reaction role message has been posted!\n"
                f"here is the message id, in case you want to change "
                f"anything later:\n `{sent_message.id}`"
            )
        elif confirmation_message.content.lower() == "no":
            await confirmation_message.add_reaction("🥕")
            await context.send(
                "no problem! i won't send it.\nlet me know if you'd like to try again later."
            )

    # Command: /rr edit
    @reaction_role.command(
        name="edit", description="Edit an existing reaction role message."
    )
    @app_commands.describe(
        message_id="the ID of the message you'd like to edit.",
        channel="The channel where the message is located.",
    )
    async def edit(
        self, context: Context, message_id: str, channel: discord.TextChannel
    ):
        """Edit the emoji-role pairs for a reaction role message."""
        try:
            message = await channel.fetch_message(int(message_id))
        except discord.NotFound:
            await context.send(
                "hmm, i couldn't find that message. please check the ID and try again!"
            )
            return
        except discord.Forbidden:
            await context.send(
                "i'm sorry, i don't have permission to access messages in that channel."
            )
            return
        except ValueError:
            await context.send(
                "that doesn't seem like a valid message ID. please check and try again!"
            )
            return

        if not message.embeds:
            await context.send(
                "this message doesn't have an embed. i can only edit messages with embeds."
            )
            return
        embed = message.embeds[0]

        await context.send(
            "got it! please provide the updated emoji-role pairs in the format `emoji: role-name`.\n"
            "send pairs one by one and just type `done` when you're finished! for example: "
            "\n ```🌷: member\n🌸: admin\ndone```\n you can start whenever you're ready!"
        )

        def check_author(message):
            return (
                message.author == context.author and message.channel == context.channel
            )

        emoji_role_pairs = {}
        while True:
            role_message = await self.wait_for_message(
                context, check_author, timeout=300
            )
            if role_message.content.lower() == "done":
                break

            try:
                emoji, role_name = map(str.strip, role_message.content.split(":", 1))
                role = await commands.RoleConverter().convert(context, role_name)

                emoji_role_pairs[emoji] = role.id
                await role_message.add_reaction("🥕")
            except ValueError:
                await context.send(
                    "hmm, i couldn't process that. make sure to format it as `emoji: role-name`."
                )
            except commands.BadArgument:
                await context.send(
                    "i couldn't find that role! double-check the name and try again."
                )

        # update the database and embed message
        await self.update_reaction_roles(
            message_id=message.id,
            channel_id=channel.id,
            emoji_role_pairs=emoji_role_pairs,
            guild_id=context.guild.id,
        )

        description_lines = embed.description.split("\n")
        # keep lines that aren't role mappings
        updated_lines = [
            line for line in description_lines if not re.match(ROLES_FORMAT, line)
        ]

        new_roles_list = "\n".join(
            [f"{emoji}: <@&{role_id}>" for emoji, role_id in emoji_role_pairs.items()]
        )
        updated_lines.insert(1, new_roles_list)

        # update the embed with the new description
        embed.description = "\n\n" + "\n".join(updated_lines)
        await message.edit(embed=embed)

        # update the reactions on the message
        existing_reactions = {str(reaction.emoji) for reaction in message.reactions}
        for emoji in emoji_role_pairs.keys():
            if emoji not in existing_reactions:
                await message.add_reaction(emoji)

        for reaction in message.reactions:
            if str(reaction.emoji) not in emoji_role_pairs:
                await message.clear_reaction(reaction.emoji)

        await context.send("all set! the reaction role message has been updated.")


async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))
