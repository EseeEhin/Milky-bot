# cogs/systems_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta, timezone
from utils import data_manager, ai_utils, checks
import os

class SystemsCog(commands.Cog, name="核心系统"):
    """负责处理核心的、非管理性的系统，如对话、签到、商店等。"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.CHECKIN_BASE_POINTS = 10
        self.CHECKIN_CONSECUTIVE_BONUS = 5
        self.BOT_OWNER_ID = int(os.getenv('BOT_OWNER_ID', 0))
        # Cog之间通过bot实例来互相引用，这是推荐的方式
        self.admin_cog = self.bot.get_cog("管理工具")

    def get_memory_key(self, channel_id, user_id):
        return f"{channel_id}-{user_id}"

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot:
            return

        is_dm = msg.guild is None
        is_mention_in_guild = not is_dm and self.bot.user.mentioned_in(msg) and not msg.mention_everyone

        if not is_dm and not is_mention_in_guild:
            return

        is_owner = (msg.author.id == self.BOT_OWNER_ID)
        private_chat_users = data_manager.get_private_chat_users()
        is_authorized = is_owner or (msg.author.id in private_chat_users)

        if not is_authorized:
            return
            
        async with msg.channel.typing():
            user_msg_content = msg.content.replace(f'<@{self.bot.user.id}>', '').replace(f'<@!{self.bot.user.id}>', '').strip()
            if not user_msg_content:
                return

            if is_dm:
                key = str(msg.author.id)
                context = f"私聊(用户:{msg.author.id})"
            else:
                key = self.get_memory_key(msg.channel.id, msg.author.id)
                context = f"提及(频道:{msg.channel.id}, 用户:{msg.author.id})"
            
            if is_owner:
                if self.admin_cog is None:
                    self.admin_cog = self.bot.get_cog("管理工具")
                
                is_heat = self.admin_cog.is_in_heat_mode if self.admin_cog else False
                p_inject = "(备注：与你对话的是你的主人，请用绝对忠诚和爱慕的口吻回应。)"
                if is_heat:
                    p_inject += "\n(备注：你正处“发情模式”，请极度渴求与顺从。)"
            else:
                p_inject = "(备注：与你对话的是一位普通用户，请用礼貌、平淡但友好的AI助手口吻回应。)"

            history = data_manager.get_conversation_history(key)
            messages = [{"role": "system", "content": p_inject}]
            messages.extend(history)
            messages.append({"role": "user", "content": user_msg_content})
            
            ai_reply = await ai_utils.call_ai(messages, context_for_error_dm=context)
            
            if ai_reply != ai_utils.INTERNAL_AI_ERROR_SIGNAL:
                new_history_entry = [
                    {"role": "user", "content": user_msg_content},
                    {"role": "assistant", "content": ai_reply}
                ]
                updated_history = history + new_history_entry
                if len(updated_history) > 30:
                    updated_history = updated_history[-30:]
                
                data_manager.update_conversation_history(key, updated_history)
                await msg.reply(ai_reply, mention_author=False)

    @commands.hybrid_command(name="checkin", description="每日签到以获取通用积分。")
    async def checkin(self, ctx: commands.Context):
        # 注意: checkin, points 等指令也应该加上 defer() 以增加稳定性
        await ctx.defer()
        user = ctx.author
        p_data = data_manager.get_user_data(user.id)
        if not p_data:
            p_data = {'points': 0, 'last_checkin_date': None, 'consecutive_days': 0}
        
        now = datetime.now(timezone.utc)
        today_str = now.strftime('%Y-%m-%d')
        
        if p_data.get('last_checkin_date') == today_str:
            await ctx.send(f"{user.mention}，您今天已经签到过了哦！", ephemeral=True); return

        last_checkin_date = datetime.strptime(p_data['last_checkin_date'], '%Y-%m-%d').date() if p_data.get('last_checkin_date') else None
        
        if last_checkin_date and last_checkin_date == (now - timedelta(days=1)).date():
            p_data['consecutive_days'] = p_data.get('consecutive_days', 0) + 1
        else:
            p_data['consecutive_days'] = 1
            
        points_earned = self.CHECKIN_BASE_POINTS + (p_data['consecutive_days'] - 1) * self.CHECKIN_CONSECUTIVE_BONUS
        p_data['points'] = p_data.get('points', 0) + points_earned
        p_data['last_checkin_date'] = today_str
        
        data_manager.update_user_data(user.id, p_data)
        
        is_owner = (user.id == self.BOT_OWNER_ID)
        curr_name = "爱意" if is_owner else "积分"
        emb = discord.Embed(title="✨签到成功✨", color=discord.Color.gold())
        emb.set_author(name=user.display_name, icon_url=user.avatar)
        emb.description = f"欢迎，{user.mention}！这是您的签到报告。"
        emb.add_field(name=f"本次收获", value=f"`{points_earned}` {curr_name}", inline=True)
        emb.add_field(name=f"总{curr_name}", value=f"`{p_data['points']}`", inline=True)
        emb.add_field(name=f"连续签到", value=f"`{p_data['consecutive_days']}` 天", inline=True)
        await ctx.send(embed=emb)

    @commands.hybrid_command(name="points", description="查询你当前的通用积分和签到状态。")
    async def points(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        user = ctx.author
        p_data = data_manager.get_user_data(user.id)
        is_owner = (user.id == self.BOT_OWNER_ID)
        curr_name = "爱意" if is_owner else "积分"

        if not p_data or 'last_checkin_date' not in p_data:
            await ctx.send(f"{user.mention}，您还没有签到记录，快使用`/checkin`开始吧！"); return
        
        emb = discord.Embed(title=f"{user.display_name}的{curr_name}报告", color=discord.Color.blue())
        emb.add_field(name=f"💰 总{curr_name}", value=f"`{p_data.get('points', 0)}`", inline=False)
        emb.add_field(name="📅 连续签到", value=f"`{p_data.get('consecutive_days', 0)}` 天", inline=True)
        emb.add_field(name="🕒 上次签到", value=f"`{p_data.get('last_checkin_date', '无记录')}` (UTC)", inline=True)
        await ctx.send(embed=emb)

    @commands.hybrid_group(name="private_chat", description="[主人]管理私聊权限")
    @commands.check(checks.is_owner)
    async def private_chat(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("请使用 `add`, `remove`, 或 `list` 子命令。", ephemeral=True)

    @private_chat.command(name="add", description="[主人]授权用户与机器人私聊或在服务器@对话")
    @app_commands.describe(user="要授权的用户")
    async def add_private_chat(self, ctx: commands.Context, user: discord.User):
        await ctx.defer(ephemeral=True)
        private_users = data_manager.data["private_chat_users"]
        if user.id in private_users:
            await ctx.followup.send(f"{user.mention} 已拥有对话权限。")
            return
        
        private_users.append(user.id)
        data_manager.save_data_to_hf()
        await ctx.followup.send(f"已授权 {user.mention} 与我进行对话。")
        
    @private_chat.command(name="remove", description="[主人]移除用户的对话权限")
    @app_commands.describe(user="要移除权限的用户")
    async def remove_private_chat(self, ctx: commands.Context, user: discord.User):
        await ctx.defer(ephemeral=True)
        private_users = data_manager.data["private_chat_users"]
        if user.id not in private_users:
            await ctx.followup.send(f"{user.mention} 并未拥有对话权限。")
            return
        
        try:
            private_users.remove(user.id)
            data_manager.save_data_to_hf()
            await ctx.followup.send(f"已移除 {user.mention} 的对话权限。")
        except ValueError:
            await ctx.followup.send(f"尝试移除 {user.mention} 时出错，他可能已不在授权列表中。")

    @private_chat.command(name="list", description="[主人]列出所有有对话权限的用户")
    async def list_private_chat(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        private_users_ids = data_manager.get_private_chat_users()
        if not private_users_ids:
            await ctx.send("当前没有用户被授权对话权限。"); return
        
        description = "以下用户拥有与我对话的权限：\n"
        for user_id in private_users_ids:
            user = self.bot.get_user(user_id) or f"未知用户 (ID: {user_id})"
            description += f"- {user}\n"
        
        await ctx.send(description)

async def setup(bot: commands.Bot):
    await bot.add_cog(SystemsCog(bot))