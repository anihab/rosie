import asyncio
import discord
from discord import app_commands, PartialEmoji
from discord.ext import commands
from discord.ext.commands import Context

class ReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
    async def fetch_reaction_roles(self, message_id):
        async with self.bot.db.execute(
            "SELECT emoji, role_id FROM reaction_roles WHERE message_id = ?",
            (message_id,)
        ) as cursor:
            return {row[0]: row[1] for row in await cursor.fetchall()}
                
    async def update_reaction_roles(self, message_id, emoji_role_mapping, guild_id):
        # clear existing mappings
        async with self.bot.db.execute(
            "DELETE FROM reaction_roles WHERE message_id = ?", (message_id,)
        ):
            pass
        # insert new mappings
        for emoji, role_id in emoji_role_mapping.items():
            await self.bot.db.execute(
                "INSERT INTO reaction_roles (message_id, emoji, role_id, guild_id) VALUES (?, ?, ?, ?)",
                (message_id, emoji, role_id, guild_id),
            )
        await self.bot.db.commit()
        
    async def parse_reaction_payload(self, payload):
        emoji_role_mapping = await self.fetch_reaction_roles(payload.message_id)
        role_id = emoji_role_mapping.get(str(payload.emoji))
        if role_id:
            guild = self.bot.get_guild(payload.guild_id)
            role = guild.get_role(role_id)
            user = guild.get_member(payload.user_id)
            if role and user:
                return role, user
        
    async def wait_for_message(self, context, check, timeout=120):
        """Helper function to handle message waits with timeout."""
        try:
            return await self.bot.wait_for("message", timeout=timeout, check=check)
        except asyncio.TimeoutError:
            await context.send("are you still there? just call me if you'd like to try again later~")
            return None
        
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        role, user = self.parse_reaction_payload(payload)
        if role and user:
            await user.add_roles(role)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        role, user = self.parse_reaction_payload(payload)
        if role and user:
            await user.remove_roles(role)
            
    # Command: reactionrole
    @commands.hybrid_command(name="reactionrole", description="Set up a reaction role message with my help!")
    @commands.has_permissions(administrator=True)
    async def reaction_roles(self, context: Context):
        """ Start a step-by-step setup for reaction roles. """
        def check_author(message):
            return message.author == context.author and message.channel == context.channel

        await context.send("hello! so you'd like me to set up a reaction role?\n"
                           "which channel would you like the message to be in? please mention it like `#channel`.")

        # Step 1: Select channel
        channel_msg = await self.wait_for_message(context, check_author)
        channel = await commands.TextChannelConverter().convert(context, channel_msg.content)

        await context.send(f"alright, the channel is {channel.mention}! what would you like the message to say? "
                           "use `|` to separate the title from the description, like so:\n"
                           "`This is a title | this is a description`.\n"
                           "if you'd like the message to include list of roles and their emojis, type `{roles}` "
                           "in the description field.")

        # Step 2: Compose message
        message_content = await self.wait_for_message(context, check_author)
        if "|" not in message_content.content:
            await context.send("i couldn't understand that format. make sure to separate the title and "
                                "description with `|`.")
            return
        title, description = map(str.strip, message_content.content.split("|", 1))

        await context.send("got it! would you like the message to have a color? respond with a hex code like `#ffffff` "
                           "or type `none` to skip.")

        # Step 3: Choose color
        color_msg = await self.wait_for_message(context, check_author)
        if color_msg.content.lower() == "none":
            embed_color = discord.Color.default()
        else:
            try:
                embed_color = discord.Color(int(color_msg.content.lstrip("#"), 16))
            except ValueError:
                await context.send("that doesn't look like a valid hex code. try again?")

        await context.send("now it's time to add roles! type each pair as `emoji: role name`, one per line. "
                           "when you're done, type `done`.")

        # Step 4: Add emoji-role pairs
        emoji_role_pairs = {}
        while True:
            role_msg = await self.wait_for_message(context, check_author, timeout=300)
            if role_msg.content.lower() == "done":
                break

            try:
                emoji_str, role_name = map(str.strip, role_msg.content.split(":", 1))
                emoji = PartialEmoji.from_str(emoji_str)
                if not emoji.is_unicode_emoji() and not emoji.id:
                    raise ValueError("Invalid emoji format.")
                
                role = await commands.RoleConverter().convert(context, role_name)
                emoji_role_pairs[str(emoji)] = role.id
                await role_msg.add_reaction("✅")
            except Exception:
                await context.send("oh no! i couldn't process that. make sure to format it like `emoji: role name`. "
                                    "don't forget the colon and make sure the role exists!")

        # Step 5: Confirm and post the message
        embed = discord.Embed(title=title, description=description, color=embed_color)
        if "{roles}" in description:
            roles_description = "\n".join([f"{emoji}: {role}" for emoji, role in emoji_role_pairs.items()])
            embed.description = description.replace("{roles}", roles_description)
        else:
            embed.description = description

        confirmation_message = await context.send("here's what the message will look like! should i post it?", embed=embed)
        await confirmation_message.add_reaction("✅")
        await confirmation_message.add_reaction("❌")

        def check_reaction(reaction, user):
            return user == context.author and str(reaction.emoji) in ["✅", "❌"]

        try:
            reaction, _ = await self.bot.wait_for("reaction_add", timeout=60.0, check=check_reaction)
            if str(reaction.emoji) == "✅":
                sent_message = await channel.send(embed=embed)
                for emoji in emoji_role_pairs.keys():
                    await sent_message.add_reaction(emoji)
                    
                await self.update_reaction_roles(message_id=sent_message.id, emoji_role_mapping=emoji_role_pairs, 
                                                 guild_id=context.guild.id)

                await context.send(f"yay! i've posted the message and set up the reaction roles!\n"
                                   f"here's the message ID in case you'd like to change anything later:\n"
                                   f"`{sent_message.id}`")
            else:
                await context.send("okay! i won't post the message. let me know if you'd like to try again later.")
        except asyncio.TimeoutError:
                await context.send("are you still there? just call me if you'd like to try again later~")
     
     # Command: reactionroles-edit       
    @commands.hybrid_command(name="reactionroles-edit", description="Edit an existing reaction roles message.")
    @app_commands.describe(message_id="The ID of the message you would like to edit.")
    @commands.has_permissions(administrator=True)
    async def edit_reaction_roles(self, context: Context, message_id, channel: discord.TextChannel):
        """ Edit an existing reaction roles message """
        # Step 1: Fetch the message
        try:
            message = await channel.fetch_message(message_id)
            embed = message.embeds[0]
        except Exception:
            await context.send(
                "i couldn't find that message! please make sure the ID and channel are correct.",
                ephemeral=True
            )
            return

        await context.send("what would you like to edit? reply with either `title`, `description`, `color`, `roles`."
                           "you can keep editing until you're satisfied. just type `done` to let me know when you're finished!")

        def check(m):
            return m.author == context.author and m.channel == context.channel

        while True:
            reply = await self.bot.wait_for_message(context, check=check, timeout=300)
            if reply.content.lower() == "done":
                break

            if reply.content.lower() == "title":
                await context.send("what should the new title be?")
                title_msg = await self.bot.wait_for_message(context, check=check)
                embed.title = title_msg.content
                await context.send("title updated!")

            elif reply.content.lower() == "description":
                await context.send("what should the new description be?")
                description_msg = await self.bot.wait_for_message(context, check=check)
                embed.description = description_msg.content
                await context.send("description updated!")

            elif reply.content.lower() == "color":
                await context.send("what color should the embed be? (hex code like `#ffffff` or `none`)")
                color_msg = await self.bot.wait_for_message(context, check=check)
                if color_msg.content.lower() == "none":
                    embed.color = discord.Color.default()
                else:
                    try:
                        embed.color = discord.Color(int(color_msg.content.strip("#"), 16))
                        await context.send("color updated!")
                    except ValueError:
                        await context.send("i'm sorry, that's not a valid hex color code.")

            elif reply.content.lower() == "roles":
                await context.send(
                    "let's update the reaction roles!\n"
                    "please enter them in this format: `emoji: role name`. type `done` when finished."
                )
                roles = {}
                while True:
                    role_msg = await self.bot.wait_for_message(context, check=check, timeout=300)
                    if role_msg.content.lower() == "done":
                        break

                    try:
                        emoji, role_name = role_msg.content.split(":")
                        emoji = emoji.strip()
                        role_name = role_name.strip()
                        roles[emoji] = role_name
                    except ValueError:
                        await context.send("oh no! i couldn't process that. make sure to format it like `emoji: role name`. "
                                        "don't forget the colon and make sure the role exists!")

                if "{roles}" in embed.description:
                    roles_description = "\n".join([f"{emoji}: {role}" for emoji, role in roles.items()])
                    embed.description = embed.description.replace("{roles}", roles_description)
                else:
                    embed.description += f"\n\n{roles_description}"
                await context.send("roles updated!")

        # Step 3: Update the message
        await message.edit(embed=embed)
        await context.send("all done! i've updated the message for you.")

async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))