# cogs/autoreact_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from utils import data_manager, checks

class AutoReactCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_message_tasks = {}
        self.last_reacted_message = {}
        self.AUTOREACT_DELAY = 1.5

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return

        autoreact_map = data_manager.get_autoreact_map()
        if msg.author.id in autoreact_map:
            emoji_to_add = autoreact_map.get(msg.author.id)
            if not emoji_to_add:
                return

            task_key = (msg.channel.id, msg.author.id)
            
            if task_key in self.last_message_tasks:
                self.last_message_tasks[task_key].cancel()

            async def react_logic_task(new_message, emoji, key):
                try:
                    await asyncio.sleep(self.AUTOREACT_DELAY)
                    
                    if key in self.last_reacted_message:
                        old_message = self.last_reacted_message[key]
                        if old_message.id != new_message.id:
                            try:
                                await old_message.remove_reaction(emoji, self.bot.user)
                            except (discord.NotFound, discord.Forbidden):
                                pass
                    
                    await new_message.add_reaction(emoji)
                    self.last_reacted_message[key] = new_message

                except asyncio.CancelledError:
                    return
                finally:
                    if key in self.last_message_tasks:
                        del self.last_message_tasks[key]

            new_task = asyncio.create_task(react_logic_task(msg, emoji_to_add, task_key))
            self.last_message_tasks[task_key] = new_task

    @commands.hybrid_group(name="autoreact", description="[主人]管理自动反应")
    @commands.check(checks.is_owner)
    async def autoreact(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.interaction.response.send_message("请提供子命令 (add, remove, list)。", ephemeral=True)

    @autoreact.command(name="add", description="[主人]为用户添加一个自动反应表情")
    @app_commands.describe(user="目标用户", emoji="要自动反应的表情 (标准或自定义)")
    async def add_react(self, ctx: commands.Context, user: discord.User, emoji: str):
        await ctx.interaction.response.defer(ephemeral=True)
        try:
            partial_emoji = await commands.PartialEmojiConverter().convert(ctx, emoji.strip())
            emoji_to_store = str(partial_emoji)
        except commands.CommandError:
            await ctx.interaction.followup.send(f"错误：'{emoji}' 不是一个有效的表情符号。", ephemeral=True)
            return
        
        autoreact_map = data_manager.get_autoreact_map()
        autoreact_map[user.id] = emoji_to_store
        data_manager.save_data_to_hf()
        await ctx.interaction.followup.send(f"设置成功！现在我会用 {emoji_to_store} 自动反应 {user.mention} 的最后一条消息。", ephemeral=True)

    @autoreact.command(name="remove", description="[主人]移除用户的自动反应")
    @app_commands.describe(user="目标用户")
    async def remove_react(self, ctx: commands.Context, user: discord.User):
        autoreact_map = data_manager.get_autoreact_map()
        if user.id not in autoreact_map:
            await ctx.interaction.response.send_message(f"{user.mention} 不在自动反应列表中。", ephemeral=True)
            return

        del autoreact_map[user.id]
        
        keys_to_delete = [key for key in self.last_reacted_message if key[1] == user.id]
        for key in keys_to_delete:
            del self.last_reacted_message[key]
            
        data_manager.save_data_to_hf()
        await ctx.interaction.response.send_message(f"移除了对 {user.mention} 的自动反应。", ephemeral=True)

    @autoreact.command(name="list", description="[主人]显示所有自动反应规则")
    async def list_reacts(self, ctx: commands.Context):
        # ... (list 指令逻辑)
        pass

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoReactCog(bot))