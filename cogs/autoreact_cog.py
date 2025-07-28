# cogs/autoreact_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from utils import data_manager, checks

class AutoReactCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_reacted_message = {}
        self.AUTOREACT_DELAY = 0.3  # 减少延迟到0.3秒
        self.cleanup_tasks = {}

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot or not msg.guild:
            return

        # 检查用户级别的自动反应
        autoreact_map = data_manager.get_autoreact_map()
        if msg.author.id in autoreact_map:
            emoji_to_add = autoreact_map.get(msg.author.id)
            if not emoji_to_add:
                return

            task_key = (msg.channel.id, msg.author.id)
            
            # 立即清理之前的反应任务
            if task_key in self.cleanup_tasks:
                self.cleanup_tasks[task_key].cancel()
            
            # 立即清理之前的反应
            await self.cleanup_previous_reaction(task_key, emoji_to_add)
            
            # 创建新的反应任务
            new_task = asyncio.create_task(self.delayed_react(msg, emoji_to_add, task_key))
            self.cleanup_tasks[task_key] = new_task

        # 检查服务器级别的自动反应规则
        server_rules = data_manager.get_autoreact_rules(msg.guild.id)
        if server_rules:
            for trigger, reaction in server_rules.items():
                if trigger.lower() in msg.content.lower():
                    try:
                        await msg.add_reaction(reaction)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                        print(f"服务器自动反应错误: {e}")
                    break  # 只应用第一个匹配的规则

    async def cleanup_previous_reaction(self, task_key: tuple, emoji: str):
        """立即清理之前的反应"""
        if task_key in self.last_reacted_message:
            old_message = self.last_reacted_message[task_key]
            try:
                await old_message.remove_reaction(emoji, self.bot.user)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass  # 忽略清理错误
            finally:
                del self.last_reacted_message[task_key]

    async def delayed_react(self, msg: discord.Message, emoji: str, task_key: tuple):
        """延迟添加反应"""
                try:
                    await asyncio.sleep(self.AUTOREACT_DELAY)
                    
            # 检查消息是否仍然存在且未被删除
            try:
                await msg.channel.fetch_message(msg.id)
            except discord.NotFound:
                return  # 消息已被删除
            
            # 添加新反应
            await msg.add_reaction(emoji)
            self.last_reacted_message[task_key] = msg

                except asyncio.CancelledError:
                    return
        except Exception as e:
            print(f"自动反应错误: {e}")
                finally:
            # 清理任务引用
            if task_key in self.cleanup_tasks:
                del self.cleanup_tasks[task_key]

    @commands.hybrid_group(name="自动反应", description="[主人] 管理自动反应")
    @commands.check(checks.is_owner)
    async def 自动反应(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("请提供子命令 (添加, 移除, 列表)。", ephemeral=True)

    @自动反应.command(name="添加", description="[主人] 为用户添加一个自动反应表情")
    @app_commands.describe(user="目标用户", emoji="要自动反应的表情 (标准或自定义)")
    async def 添加(self, ctx: commands.Context, user: discord.User, emoji: str):
        await ctx.defer(ephemeral=True)
        try:
            partial_emoji = await commands.PartialEmojiConverter().convert(ctx, emoji.strip())
            emoji_to_store = str(partial_emoji)
        except commands.CommandError:
            await ctx.send(f"错误：'{emoji}' 不是一个有效的表情符号。", ephemeral=True)
            return
        
        autoreact_map = data_manager.get_autoreact_map()
        autoreact_map[user.id] = emoji_to_store
        data_manager.save_data_to_hf()
        await ctx.send(f"设置成功！现在我会用 {emoji_to_store} 自动反应 {user.mention} 的消息。", ephemeral=True)

    @自动反应.command(name="移除", description="[主人] 移除用户的自动反应")
    @app_commands.describe(user="目标用户")
    async def 移除(self, ctx: commands.Context, user: discord.User):
        await ctx.defer(ephemeral=True)
        autoreact_map = data_manager.get_autoreact_map()
        if user.id not in autoreact_map:
            await ctx.send(f"{user.mention} 不在自动反应列表中。", ephemeral=True)
            return

        emoji = autoreact_map[user.id]
        del autoreact_map[user.id]
        
        # 清理该用户的所有反应
        keys_to_delete = [key for key in self.last_reacted_message if key[1] == user.id]
        for key in keys_to_delete:
            try:
                await self.cleanup_previous_reaction(key, emoji)
            except:
                pass
            
        # 取消该用户的所有任务
        tasks_to_cancel = [key for key in self.cleanup_tasks if key[1] == user.id]
        for key in tasks_to_cancel:
            if key in self.cleanup_tasks:
                self.cleanup_tasks[key].cancel()
                del self.cleanup_tasks[key]
            
        data_manager.save_data_to_hf()
        await ctx.send(f"移除了对 {user.mention} 的自动反应。", ephemeral=True)

    @自动反应.command(name="列表", description="[主人] 显示所有自动反应规则")
    async def 列表(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        autoreact_map = data_manager.get_autoreact_map()
        
        if not autoreact_map:
            await ctx.send("当前没有设置任何自动反应规则。", ephemeral=True)
            return
        
        embed = discord.Embed(title="🤖 自动反应规则列表", color=discord.Color.blue())
        
        for user_id, emoji in autoreact_map.items():
            try:
                user = await self.bot.fetch_user(user_id)
                embed.add_field(
                    name=f"{user.display_name} ({user.name})", 
                    value=f"反应: {emoji}", 
                    inline=False
                )
            except:
                embed.add_field(
                    name=f"未知用户 ({user_id})", 
                    value=f"反应: {emoji}", 
                    inline=False
                )
        
        await ctx.send(embed=embed, ephemeral=True)

    @自动反应.command(name="延迟", description="[主人] 设置自动反应延迟时间")
    @app_commands.describe(delay="延迟时间（秒，0.1-2.0）")
    async def 延迟(self, ctx: commands.Context, delay: float):
        await ctx.defer(ephemeral=True)
        
        if not 0.1 <= delay <= 2.0:
            await ctx.send("延迟时间必须在0.1到2.0秒之间。", ephemeral=True)
            return
        
        self.AUTOREACT_DELAY = delay
        await ctx.send(f"自动反应延迟已设置为 {delay} 秒。", ephemeral=True)

    @自动反应.command(name="服务器添加", description="[主人] 为服务器添加关键词自动反应")
    @app_commands.describe(trigger="触发关键词", emoji="要自动反应的表情")
    async def 服务器添加(self, ctx: commands.Context, trigger: str, emoji: str):
        await ctx.defer(ephemeral=True)
        
        if not ctx.guild:
            await ctx.send("此命令只能在服务器中使用。", ephemeral=True)
            return
            
        try:
            partial_emoji = await commands.PartialEmojiConverter().convert(ctx, emoji.strip())
            emoji_to_store = str(partial_emoji)
        except commands.CommandError:
            await ctx.send(f"错误：'{emoji}' 不是一个有效的表情符号。", ephemeral=True)
            return
        
        data_manager.add_autoreact_rule(ctx.guild.id, trigger.lower(), emoji_to_store)
        await ctx.send(f"设置成功！现在当消息包含 '{trigger}' 时，我会自动反应 {emoji_to_store}。", ephemeral=True)

    @自动反应.command(name="服务器移除", description="[主人] 移除服务器的关键词自动反应")
    @app_commands.describe(trigger="要移除的触发关键词")
    async def 服务器移除(self, ctx: commands.Context, trigger: str):
        await ctx.defer(ephemeral=True)
        
        if not ctx.guild:
            await ctx.send("此命令只能在服务器中使用。", ephemeral=True)
            return
        
        server_rules = data_manager.get_autoreact_rules(ctx.guild.id)
        if trigger.lower() not in server_rules:
            await ctx.send(f"关键词 '{trigger}' 不在自动反应规则中。", ephemeral=True)
            return

        data_manager.remove_autoreact_rule(ctx.guild.id, trigger.lower())
        await ctx.send(f"已移除关键词 '{trigger}' 的自动反应规则。", ephemeral=True)

    @自动反应.command(name="服务器列表", description="[主人] 显示当前服务器的自动反应规则")
    async def 服务器列表(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        
        if not ctx.guild:
            await ctx.send("此命令只能在服务器中使用。", ephemeral=True)
            return
            
        server_rules = data_manager.get_autoreact_rules(ctx.guild.id)
        
        if not server_rules:
            await ctx.send("当前服务器没有设置任何自动反应规则。", ephemeral=True)
            return
        
        embed = discord.Embed(title=f"🤖 {ctx.guild.name} 自动反应规则", color=discord.Color.blue())
        
        for trigger, emoji in server_rules.items():
            embed.add_field(
                name=f"关键词: {trigger}", 
                value=f"反应: {emoji}", 
                inline=False
            )
        
        await ctx.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoReactCog(bot))