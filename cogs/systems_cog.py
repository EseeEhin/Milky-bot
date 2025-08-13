# cogs/systems_cog.py
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta, timezone
from utils import data_manager, ai_utils, checks
import os
from typing import Optional
import asyncio
import re
import random
import json

class SystemsCog(commands.Cog, name="核心系统"):
    """负责处理核心的、非管理性的系统，如对话、签到、商店等。"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.CHECKIN_BASE_POINTS = 10
        self.CHECKIN_CONSECUTIVE_BONUS = 5
        self.BOT_OWNER_ID = int(os.getenv('BOT_OWNER_ID', 0))
        # Cog之间通过bot实例来互相引用，这是推荐的方式
        self.admin_cog = self.bot.get_cog("管理工具")

    def get_memory_key(self, message: discord.Message):
        """根据消息上下文生成独立的记忆key"""
        if message.guild:  # 如果是服务器频道消息
            return f"{message.channel.id}_{message.author.id}"
        else:  # 如果是私聊消息
            return f"dm_{message.author.id}"

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot:
            return
        # 屏蔽词检测
        from utils import data_manager, ai_utils
        filtered_words = data_manager.get_filtered_words()
        if filtered_words and any(w in msg.content for w in filtered_words):
            try:
                await msg.delete()
            except Exception:
                pass
            try:
                await msg.author.send(f"你的消息包含屏蔽词，已被撤回。内容：{msg.content}")
            except Exception:
                pass
            return
        # 对于!开头的消息不做AI响应
        if msg.content.strip().startswith('!'):
            return
        # --- 以下为AI对话/私聊/短篇幅等原有功能 ---
        is_dm = msg.guild is None
        is_mention_in_guild = not is_dm and self.bot.user and self.bot.user.mentioned_in(msg) and not msg.mention_everyone
        if not is_dm and not is_mention_in_guild:
            return
        is_owner = (msg.author.id == self.BOT_OWNER_ID)
        private_chat_users = data_manager.get_private_chat_users()
        is_authorized = is_owner or (msg.author.id in private_chat_users)
        if not is_authorized:
            return
        async with msg.channel.typing():
            if not self.bot.user:
                return
            user_msg_content = msg.content.replace(f'<@{self.bot.user.id}>', '').replace(f'<@!{self.bot.user.id}>', '').strip()
            if not user_msg_content:
                return
            # 获取独立的上下文记忆key
            key = self.get_memory_key(msg)
            if is_dm:
                context = f"私聊(用户:{msg.author.id})"
            else:
                context = f"提及(频道:{msg.channel.id}, 用户:{msg.author.id})"
            history = data_manager.get_conversation_history(key)
            # 自动总结：如果历史过长，调用AI总结
            MAX_HISTORY_LEN = 30
            if len(history) > MAX_HISTORY_LEN:
                summary_input = history[:-10]
                summary_text = '\n'.join([f"{m['role']}: {m['content']}" for m in summary_input])
                summary_prompt = "请用简洁中文总结以下对话历史，保留关键信息，便于后续AI继续对话：\n" + summary_text
                summary_result = await ai_utils.call_ai([
                    {"role": "system", "content": "你是对话历史总结助手。"},
                    {"role": "user", "content": summary_prompt}
                ], context_for_error_dm="自动总结历史")
                history = [{"role": "system", "content": f"历史总结：{summary_result}"}] + history[-10:]
            messages = []
            messages.extend(history)
            # 将用户名添加到消息内容中
            user_formatted_content = f"{msg.author.display_name}: {user_msg_content}"
            messages.append({"role": "user", "content": user_formatted_content})
            ai_reply = await ai_utils.call_ai(messages, context_for_error_dm=context)
            print(f"[DEBUG] AI回复内容: {ai_reply}")
            if ai_reply and ai_reply != ai_utils.INTERNAL_AI_ERROR_SIGNAL:
                corrected_reply = ai_reply
                # 记录历史时也包含用户名
                user_formatted_content = f"{msg.author.display_name}: {user_msg_content}"
                new_history_entry = [
                    {"role": "user", "content": user_formatted_content},
                    {"role": "model", "content": corrected_reply}
                ]
                updated_history = history + new_history_entry
                if len(updated_history) > 30:
                    updated_history = updated_history[-30:]
                await data_manager.update_conversation_history(key, updated_history)
                # --- 新增：记录到全局记忆 ---
                await data_manager.add_to_global_memory(
                    user_id=msg.author.id,
                    user_name=msg.author.display_name,
                    message=user_msg_content,
                    bot_reply=corrected_reply
                )
                # --------------------------
                # 根据短篇幅模式决定如何发送消息
                if data_manager.get_short_reply_mode():
                    # 使用 <\n> 标签进行分段发送
                    segments = corrected_reply.split('<\\n>')
                    for idx, seg in enumerate(segments):
                        seg = seg.strip()
                        if not seg:
                            continue
                        try:
                            if idx == 0:
                                await msg.reply(seg, mention_author=False)
                            else:
                                await msg.channel.send(seg)
                        except Exception as e:
                            print(f"[ERROR] 发送AI分段回复失败: {e}")
                        await asyncio.sleep(random.uniform(0.7, 1.3))
                else:
                    # 正常发送完整回复
                    try:
                        await msg.reply(corrected_reply, mention_author=False)
                    except Exception as e:
                        print(f"[ERROR] 发送AI回复失败: {e}")
                # 日志：AI对话
                try:
                    from cogs.admin_cog import AdminCog
                    for cog in self.bot.cogs.values():
                        if isinstance(cog, AdminCog):
                            await cog.send_log(msg.guild.id if msg.guild else 0, "ai_chat", f"用户: {msg.author} ({msg.author.id})\n内容: {user_msg_content}\nAI回复: {corrected_reply}", msg.author)
                            break
                except Exception as e:
                    print(f"AI对话日志记录失败: {e}")
            else:
                print("[ERROR] AI调用失败，未能获取有效回复。")

    @commands.hybrid_command(name="系统", description="核心系统功能合集，所有操作通过功能参数选择")
    @app_commands.describe(
        func="功能类型",
        user="目标用户（部分功能需要）",
        channel="目标频道（部分功能需要）",
        purpose="发起对话的目的/话题"
    )
    @app_commands.choices(func=[
        app_commands.Choice(name="查询积分", value="points")
    ])
    async def system(self, ctx: commands.Context, func: str, user: Optional[discord.User] = None, channel: Optional[discord.TextChannel] = None, purpose: Optional[str] = None):
        await ctx.defer(ephemeral=True)
        from utils import data_manager
        if func == "points":
            user_id = ctx.author.id
            user_data = data_manager.get_user_data(user_id)
            if not user_data:
                user_data = {'points': 0, 'last_checkin_date': None, 'consecutive_days': 0}
            points = user_data.get('points', 0)
            last_checkin = user_data.get('last_checkin_date', '无')
            consecutive_days = user_data.get('consecutive_days', 0)
            emb = discord.Embed(title="🎁 你的通用积分信息", color=discord.Color.gold())
            emb.add_field(name="当前积分", value=str(points), inline=True)
            emb.add_field(name="连续签到天数", value=str(consecutive_days), inline=True)
            emb.add_field(name="上次签到日", value=str(last_checkin), inline=True)
            await ctx.send(embed=emb, ephemeral=True)
        else:
            await ctx.send("未知功能类型。", ephemeral=True)

    @commands.hybrid_command(name="清除记忆", description="清除当前上下文的记忆，开始一段全新的对话。")
    async def clear_memory(self, ctx: commands.Context):
        """清除当前上下文的对话历史，开始新对话。"""
        await ctx.defer(ephemeral=True)
        
        # 使用与 on_message 一致的逻辑来获取记忆key
        key = self.get_memory_key(ctx.message)
        
        # 清空该key的对话历史
        history = data_manager.get_conversation_history(key)
        if not history:
            await ctx.send("你我之间尚未开启对话，无需重置。", ephemeral=True)
            return

        await data_manager.update_conversation_history(key, [])
        
        await ctx.send("好的，我们重新开始吧。你想聊些什么？", ephemeral=True)

    @commands.hybrid_command(name="签到", description="每日签到以获取通用积分。")
    async def checkin(self, ctx: commands.Context):
        """每日签到功能"""
        await ctx.defer(ephemeral=True)
        
        user_id = ctx.author.id
        user_data = data_manager.get_user_data(user_id)
        
        if not user_data:
            user_data = {'points': 0, 'last_checkin_date': None, 'consecutive_days': 0}
        
        today = datetime.now().strftime('%Y-%m-%d')
        last_checkin = user_data.get('last_checkin_date')
        
        if last_checkin == today:
            await ctx.send("你今天已经签到过了，明天再来吧！", ephemeral=True)
            return

        # 计算连续签到天数
        consecutive_days = user_data.get('consecutive_days', 0)
        if last_checkin:
            try:
                last_date = datetime.strptime(last_checkin, '%Y-%m-%d')
                today_date = datetime.strptime(today, '%Y-%m-%d')
                days_diff = (today_date - last_date).days
                
                if days_diff == 1:
                    consecutive_days += 1
                elif days_diff > 1:
                    consecutive_days = 1
                else:
                    consecutive_days = 1
            except:
                consecutive_days = 1
        else:
            consecutive_days = 1
        
        # 计算积分奖励
        base_points = 10
        consecutive_bonus = min(consecutive_days * 2, 20)  # 连续签到奖励，最多20分
        total_points = base_points + consecutive_bonus
        
        # 更新用户数据
        user_data['points'] = user_data.get('points', 0) + total_points
        user_data['last_checkin_date'] = today
        user_data['consecutive_days'] = consecutive_days
        
        await data_manager.update_user_data(user_id, user_data)
        
        # 创建签到成功消息
        emb = discord.Embed(title="✅ 签到成功", color=discord.Color.green())
        emb.add_field(name="今日获得积分", value=f"`{total_points}` 分", inline=True)
        emb.add_field(name="连续签到天数", value=f"`{consecutive_days}` 天", inline=True)
        emb.add_field(name="总积分", value=f"`{user_data['points']}` 分", inline=True)
        if consecutive_days > 1:
            emb.add_field(name="连续签到奖励", value=f"额外获得 `{consecutive_bonus}` 分", inline=False)
        emb.set_footer(text=f"签到时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        await ctx.send(embed=emb, ephemeral=True)
        # 日志：签到
        try:
            from cogs.admin_cog import AdminCog
            for cog in self.bot.cogs.values():
                if isinstance(cog, AdminCog):
                    await cog.send_log(ctx.guild.id if ctx.guild else 0, "user_activity", f"用户: {ctx.author} ({ctx.author.id}) 签到，获得{total_points}分，连续{consecutive_days}天，总积分{user_data['points']}。", ctx.author)
                    break
        except Exception as e:
            print(f"签到日志记录失败: {e}")

    @commands.hybrid_command(name="sayto", description="[主人] 让机器人向指定用户在当前频道发送消息。")
    @app_commands.describe(
        user="要对话的目标用户",
        purpose="对话的目的或想让AI说的话题"
    )
    @commands.check(checks.is_owner)
    async def sayto(self, ctx: commands.Context, user: discord.User, purpose: str):
        """让机器人发起对话"""
        await ctx.defer(ephemeral=True)
        
        from utils import ai_utils
        prompt = f"请主动以如下目的和 {user.display_name} 发起一段自然的开场白：{purpose}"
        ai_reply = await ai_utils.call_ai(
            [{"role": "user", "content": prompt}],
            context_for_error_dm="发起对话"
        )
        
        if ai_reply and ai_reply != ai_utils.INTERNAL_AI_ERROR_SIGNAL:
            try:
                # 始终在当前频道发送，并提及用户
                await ctx.channel.send(f"{user.mention} {ai_reply}")
                await ctx.send(f"✅ 已成功在当前频道向 {user.display_name} 发送消息。", ephemeral=True)
            except discord.Forbidden:
                await ctx.send(f"❌ 无法在当前频道发送消息。请检查机器人权限。", ephemeral=True)
            except Exception as e:
                await ctx.send(f"❌ 发送消息时发生未知错误: {e}", ephemeral=True)
        else:
            await ctx.send(f"❌ AI调用失败，未能生成回复。请检查后台日志以获取详细错误信息。", ephemeral=True)

    @commands.hybrid_command(name="清除所有记忆", description="[主人] 清除机器人存储的所有对话历史。")
    @commands.check(checks.is_owner)
    async def clear_all_memory(self, ctx: commands.Context):
        """清除所有用户的对话历史记录"""
        await ctx.defer(ephemeral=True)
        from utils import data_manager
        data_manager.data["conversation_history"] = {}
        await data_manager.save_data_to_hf()
        await ctx.send("✅ 已清除所有用户的对话历史记录。", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(SystemsCog(bot))
