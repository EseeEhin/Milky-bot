# cogs/admin_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import os
import json
from datetime import datetime
from typing import Literal, Optional, ClassVar, Any
from enum import Enum
from utils import checks, data_manager, emoji_manager
import aiofiles
import tempfile
from utils import ai_utils
import pathlib
import asyncio
from collections import defaultdict
import aiohttp

# 将枚举定义在类外部，作为模块级别的常量，这是一种更通用的做法
class PointAction(str, Enum):
    add = "增加"
    set = "设定"
    remove = "移除"

# --- 人格管理 ---
# PERSONA_FILE = os.path.join(os.path.dirname(__file__), "../utils/persona_data.json")
# def load_personas():
#     try:
#         with open(PERSONA_FILE, "r", encoding="utf-8") as f:
#             return json.load(f)
#     except Exception:
#         return {}
# def save_personas(personas):
#     with open(PERSONA_FILE, "w", encoding="utf-8") as f:
#         json.dump(personas, f, ensure_ascii=False, indent=2)

from utils import data_manager

class AdminCog(commands.Cog, name="管理工具"):
    """主人专属的后台管理指令"""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 模式状态现在由此 Cog 独立管理
        self.is_in_heat_mode: bool = False 
        
        # 从环境变量中获取配置，提供默认值以防万一
        self.BOT_OWNER_ID: int = int(os.getenv('BOT_OWNER_ID', 0))
        self.AI_MODEL_NAME: str = os.getenv('AI_MODEL_NAME', '未配置')
        self.HF_DATA_REPO_ID: str = os.getenv('HF_DATA_REPO_ID', '未配置')
        # 加载所有人格
        self.personas = data_manager.get_personas()
        # 环境变量人格优先
        env_persona = os.getenv('BOT_PERSONA', '')
        if env_persona:
            self.personas['环境变量人格'] = env_persona
        # 设置默认激活的人格
        active_persona = data_manager.get_active_persona()
        if not active_persona:
            data_manager.set_active_persona('环境变量人格')

    @commands.hybrid_command(name="ping", description="测试AI延迟、与Discord的延迟和趣味信息。")
    async def ping(self, ctx: commands.Context):
        import time
        t1 = time.perf_counter()
        msg = await ctx.send("Pinging... 🏓")
        t2 = time.perf_counter()
        latency = round((t2 - t1) * 1000)
        await msg.edit(content=f"🏓 Pong! 响应延迟: `{latency}ms` | Discord延迟: `{round(self.bot.latency*1000)}ms`")

    @commands.hybrid_command(name="status", description="[主人] 查看米尔可的内部状态报告。")
    @commands.check(checks.is_owner)
    async def status(self, ctx: commands.Context):
        from utils import ai_utils
        await ctx.defer(ephemeral=True)
        mode = "发情模式" if getattr(self, 'is_in_heat_mode', False) else "常规待命模式"
        
        # 通过动态构建函数获取当前完整的系统指令
        current_persona_full_instruction = ai_utils.build_system_instruction()
        
        emb = discord.Embed(title="🔧 米尔可内部状态报告", color=discord.Color.blue())
        emb.add_field(name="🤖 运行模式", value=mode, inline=True)
        emb.add_field(name="💬 当前人格", value=current_persona_full_instruction[:1000] + "..." if len(current_persona_full_instruction) > 1000 else current_persona_full_instruction, inline=False)
        emb.add_field(name="⏰ 运行状态", value="✅ 正常运行", inline=True)
        await ctx.send(embed=emb, ephemeral=True)

    @commands.hybrid_command(name="热恋模式", description="[主人] 切换米尔可特殊情感模式。")
    @app_commands.describe(state="开启或关闭")
    @commands.check(checks.is_owner)
    async def heatmode(self, ctx: commands.Context, state: Literal["开启", "关闭"]):
        """切换热恋模式"""
        await ctx.defer(ephemeral=True)
        enable = (state == "开启")
        await data_manager.set_heat_mode(enable)
        
        msg = "遵命，主人...身体...开始奇怪了...（脸红急促...）" if enable else "呜...好多了，谢谢主人...（燥热退去，眼神清明...）"
        await ctx.send(msg, ephemeral=True)
        await self.send_log(ctx.guild.id if ctx.guild else 0, "admin", f"{'开启' if enable else '关闭'}热恋模式 by {ctx.author} ({ctx.author.id})", ctx.author)

    @commands.hybrid_command(name="短篇幅模式", description="[主人] 开启或关闭AI短篇幅连续回复模式")
    @app_commands.describe(state="开启或关闭")
    @commands.check(checks.is_owner)
    async def short_reply_mode(self, ctx: commands.Context, state: Literal["开启", "关闭"]):
        """开启或关闭短篇幅模式"""
        await ctx.defer(ephemeral=True)
        from utils import data_manager
        enable = (state == "开启")
        await data_manager.set_short_reply_mode(enable)
        await ctx.send(f"{'✅ 已开启' if enable else '❎ 已关闭'}短篇幅模式。", ephemeral=True)
        # 日志
        await self.send_log(ctx.guild.id if ctx.guild else 0, "admin", f"{'开启' if enable else '关闭'}短篇幅模式 by {ctx.author} ({ctx.author.id})", ctx.author)

    @commands.hybrid_command(name="字数要求", description="[主人] 通过提示词引导AI的回复字数")
    @app_commands.describe(requirement="设置字数要求（如 '200字', '一段话'），输入 '无' 或 '清除' 来移除要求")
    @commands.check(checks.is_owner)
    async def word_count_request(self, ctx: commands.Context, requirement: Optional[str] = None):
        """设置或查看通过提示词引导的AI回复字数要求"""
        await ctx.defer(ephemeral=True)
        from utils import data_manager
        if requirement is None:
            current_request = data_manager.get_word_count_request()
            if current_request:
                await ctx.send(f"ℹ️ 当前AI回复字数要求为: `{current_request}`。", ephemeral=True)
            else:
                await ctx.send("ℹ️ 当前没有设置AI回复字数要求。", ephemeral=True)
        else:
            if requirement.lower() in ["无", "清除", "none", "clear"]:
                await data_manager.set_word_count_request("")
                await ctx.send("✅ 已清除AI回复字数要求。", ephemeral=True)
                await self.send_log(ctx.guild.id if ctx.guild else 0, "admin", f"清除了AI字数要求 by {ctx.author} ({ctx.author.id})", ctx.author)
            else:
                await data_manager.set_word_count_request(requirement)
                await ctx.send(f"✅ 已将AI回复字数要求设置为: `{requirement}`。", ephemeral=True)
                await self.send_log(ctx.guild.id if ctx.guild else 0, "admin", f"设置AI字数要求为 '{requirement}' by {ctx.author} ({ctx.author.id})", ctx.author)

    @commands.hybrid_command(name="管理", description="[主人] 管理工具合集，所有操作通过功能参数选择")
    @app_commands.describe(
        func="功能类型",
        user="目标用户（部分功能需要）",
        action="操作类型（仅积分操作需要）",
        amount="数量（仅积分操作需要）",
        points="设定新的总积分/爱意（仅签到数据操作需要）",
        consecutive_days="设定新的连续签到天数（仅签到数据操作需要）",
        last_checkin_date="设定上次签到日 (格式: YYYY-MM-DD, 或输入 'reset' 清空)"
    )
    @app_commands.choices(func=[
        app_commands.Choice(name="积分操作", value="points"),
        app_commands.Choice(name="签到数据", value="checkin")
    ])
    @app_commands.choices(action=[
        app_commands.Choice(name="增加", value="增加"),
        app_commands.Choice(name="设定", value="设定"),
        app_commands.Choice(name="移除", value="移除")
    ])
    @commands.check(checks.is_owner)
    async def manage(self, ctx: commands.Context, func: str, user: Optional[discord.User] = None, action: Optional[str] = None, amount: Optional[int] = None, points: Optional[int] = None, consecutive_days: Optional[int] = None, last_checkin_date: Optional[str] = None):
        await ctx.defer(ephemeral=True)
        from utils import data_manager
        if func == "points":
            if not (user and action and amount is not None):
                await ctx.send("请提供目标用户、操作类型和数量。", ephemeral=True)
                return
            orig_pts = data_manager.get_user_data(user.id).get('points', 0) if data_manager.get_user_data(user.id) else 0
            if action == "增加":
                new_pts = orig_pts + amount
            elif action == "设定":
                new_pts = amount
            elif action == "移除":
                new_pts = max(0, orig_pts - amount)
            else:
                await ctx.send("未知操作类型。", ephemeral=True)
                return
            p_data = data_manager.get_user_data(user.id) or {'points': 0, 'last_checkin_date': None, 'consecutive_days': 0}
            p_data['points'] = new_pts
            await data_manager.update_user_data(user.id, p_data)
            await ctx.send(f"已将用户 {user.display_name} 的积分从 {orig_pts} 调整为 {new_pts}。", ephemeral=True)
        elif func == "checkin":
            if not user:
                await ctx.send("请提供目标用户。", ephemeral=True)
                return
            p_data = data_manager.get_user_data(user.id) or {'points': 0, 'last_checkin_date': None, 'consecutive_days': 0}
        changes = []
        if points is not None:
            if points < 0:
                    await ctx.send("点数不能为负。", ephemeral=True); return
            p_data['points'] = points
            changes.append(f"总点数设为`{points}`")
        if consecutive_days is not None:
            if consecutive_days < 0:
                    await ctx.send("连续天数不能为负。", ephemeral=True); return
            p_data['consecutive_days'] = consecutive_days
            changes.append(f"连续天数设为`{consecutive_days}`")
        if last_checkin_date is not None:
            if last_checkin_date.lower() in ["reset", "none", "null", ""]:
                p_data['last_checkin_date'] = None
                changes.append("上次签到日已重置")
            else:
                try:
                    datetime.strptime(last_checkin_date, '%Y-%m-%d')
                    p_data['last_checkin_date'] = last_checkin_date
                    changes.append(f"上次签到日设为`{last_checkin_date}`")
                except ValueError:
                        await ctx.send("日期格式无效。请用YYYY-MM-DD或'reset'。", ephemeral=True); return
            if not changes:
                await ctx.send("未指定任何修改项。", ephemeral=True); return
            await data_manager.update_user_data(user.id, p_data)
            await ctx.send(f"用户 {user.display_name} 的签到数据已修改：{'，'.join(changes)}", ephemeral=True)
        else:
            await ctx.send("未知功能类型。", ephemeral=True)

    @commands.hybrid_command(name="人格", description="[主人] 切换AI人格。支持默认人格和已上传人格。")
    @app_commands.describe(name="人格名称")
    @commands.check(checks.is_owner)
    async def personality(self, ctx: commands.Context, name: str):
        """切换人格功能"""
        await ctx.defer(ephemeral=True)
        
        # 统一使用 data_manager 来设置激活的人格
        persona_to_set = name
        if name.lower() in ["默认", "default", "环境变量", "env"]:
            persona_to_set = '环境变量人格'

        # 检查人格是否存在
        if persona_to_set != '环境变量人格' and persona_to_set not in self.personas:
            await ctx.send(f"❌ 未找到人格 `{name}`。\n\n可用选项：\n• `默认` - 使用环境变量人格\n• 已上传的人格：{', '.join(list(self.personas.keys())[:5])}{'...' if len(self.personas) > 5 else ''}", ephemeral=True)
            return

        await data_manager.set_active_persona(persona_to_set)
        await ctx.send(f"🎭 已切换到人格 `{persona_to_set}`。", ephemeral=True)
        # 日志
        await self.send_log(ctx.guild.id if ctx.guild else 0, "admin", f"切换人格为：{name} by {ctx.author} ({ctx.author.id})", ctx.author)

    @personality.autocomplete('name')
    async def personality_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        """人格切换的自动完成功能"""
        choices = []
        # 只添加唯一的默认人格选项
        if "默认".startswith(current) or current.strip() == "":
            choices.append(app_commands.Choice(name="默认人格", value="默认"))
        # 添加已上传的人格
        for persona_name in self.personas.keys():
            if current.lower() in persona_name.lower():
                choices.append(app_commands.Choice(name=persona_name, value=persona_name))
        return choices[:25]  # Discord限制最多25个选项

    @commands.hybrid_command(name="人格列表", description="[主人] 查看所有可用的人格。")
    @commands.check(checks.is_owner)
    async def personality_list(self, ctx: commands.Context):
        """查看人格列表"""
        await ctx.defer(ephemeral=True)
        emb = discord.Embed(title="📋 人格列表", color=discord.Color.blue())
        # 从 data_manager 获取当前激活的人格
        active_persona = data_manager.get_active_persona()
        
        # 显示所有可用的人格
        for name, content in self.personas.items():
            current_marker = " ✅" if name == active_persona else ""
            preview = content[:50] + "..." if len(content) > 50 else content
            field_name = f"{name}{current_marker}"
            if name == '环境变量人格':
                field_name = f"默认人格 (环境变量){current_marker}"
            
            emb.add_field(
                name=field_name,
                value=f"```{preview}```", 
                inline=False
            )
        
        if not self.personas:
            emb.description = "暂无任何人格。请使用 `/上传人格` 添加。"
            
        emb.set_footer(text=f"当前使用: {active_persona or '未设置'}")
        await ctx.send(embed=emb, ephemeral=True)

    @commands.hybrid_command(name="风格", description="[主人] 切换AI风格。仅支持自定义上传/切换。")
    @app_commands.describe(style="风格内容")
    @commands.check(checks.is_owner)
    async def style(self, ctx: commands.Context, style: str):
        await data_manager.set_style(style) # 假设你会在data_manager中创建一个set_style的异步函数
        await ctx.send(f"🎨 已切换到新风格。", ephemeral=True)

    @commands.hybrid_command(name="屏蔽词", description="[主人] 管理屏蔽词，所有操作通过操作参数选择")
    @app_commands.describe(
        action="操作类型",
        word="要添加/移除的屏蔽词，多个用英文逗号分隔"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="添加", value="add"),
        app_commands.Choice(name="移除", value="remove"),
        app_commands.Choice(name="清空", value="clear"),
        app_commands.Choice(name="列表", value="list")
    ])
    @commands.check(checks.is_owner)
    async def filterword(self, ctx: commands.Context, action: str, word: Optional[str] = None):
        from utils import data_manager
        if action == "add":
            if not word:
                await ctx.send("请提供要添加的屏蔽词。", ephemeral=True)
                return
            words = [w.strip() for w in word.split(',') if w.strip()]
            added = []
            for w in words:
                if w and w not in data_manager.get_filtered_words():
                    await data_manager.add_filtered_word(w)
                    added.append(w)
            if added:
                await ctx.send(f"✅ 已添加屏蔽词：{', '.join(added)}", ephemeral=True)
                await self.send_log(ctx.guild.id if ctx.guild else 0, "admin", f"添加屏蔽词：{', '.join(added)} by {ctx.author} ({ctx.author.id})", ctx.author)
            else:
                await ctx.send("⚠️ 没有新词被添加。", ephemeral=True)
        elif action == "remove":
            if not word:
                await ctx.send("请提供要移除的屏蔽词。", ephemeral=True)
                return
            words = [w.strip() for w in word.split(',') if w.strip()]
            removed = []
            for w in words:
                if w in data_manager.get_filtered_words():
                    await data_manager.remove_filtered_word(w)
                    removed.append(w)
            if removed:
                await ctx.send(f"✅ 已移除屏蔽词：{', '.join(removed)}", ephemeral=True)
                await self.send_log(ctx.guild.id if ctx.guild else 0, "admin", f"移除屏蔽词：{', '.join(removed)} by {ctx.author} ({ctx.author.id})", ctx.author)
            else:
                await ctx.send("⚠️ 没有词被移除。", ephemeral=True)
        elif action == "clear":
            words = list(data_manager.get_filtered_words())
            for w in words:
                await data_manager.remove_filtered_word(w)
            await ctx.send("✅ 已清空所有屏蔽词。", ephemeral=True)
            await self.send_log(ctx.guild.id if ctx.guild else 0, "admin", f"清空所有屏蔽词 by {ctx.author} ({ctx.author.id})", ctx.author)
        elif action == "list":
            await ctx.defer(ephemeral=True)
            filtered_words = data_manager.get_filtered_words()
            if not filtered_words:
                await ctx.send("当前没有设置任何屏蔽词。", ephemeral=True)
                return
            embed = discord.Embed(title="🚫 屏蔽词列表", color=discord.Color.red())
            words_text = "\n".join([f"• {word}" for word in filtered_words])
            embed.description = words_text[:4000] + "..." if len(words_text) > 4000 else words_text
            await ctx.send(embed=embed, ephemeral=True)
        else:
            await ctx.send("未知操作类型。", ephemeral=True)

    @commands.hybrid_command(name="日志", description="[主人] 管理日志发送/配置/删除/查看功能，所有操作通过类型参数选择")
    @app_commands.describe(
        type="操作类型",
        guild="目标服务器（部分操作需要）",
        channel="目标频道（仅设置频道时需要）",
        log_type="日志类型（仅设置/发送/删除时需要）",
        message="日志内容（仅发送时需要）"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="设置频道", value="set"),
        app_commands.Choice(name="发送日志", value="send"),
        app_commands.Choice(name="查看配置", value="list"),
        app_commands.Choice(name="删除配置", value="delete")
    ])
    @app_commands.choices(log_type=[
        app_commands.Choice(name="系统日志", value="system"),
        app_commands.Choice(name="用户活动", value="user_activity"),
        app_commands.Choice(name="错误日志", value="error"),
        app_commands.Choice(name="AI对话", value="ai_chat"),
        app_commands.Choice(name="管理操作", value="admin"),
        app_commands.Choice(name="所有日志", value="all"),
        app_commands.Choice(name="全局日志", value="global"),
        app_commands.Choice(name="删除整个服务器", value="all"),
        app_commands.Choice(name="删除全局日志", value="global")
    ])
    @commands.check(checks.is_owner)
    async def log(self, ctx: commands.Context, type: str, guild: Optional[discord.abc.GuildChannel] = None, channel: Optional[discord.TextChannel] = None, log_type: Optional[str] = None, message: Optional[str] = None):
        await ctx.defer(ephemeral=True)
        from utils import data_manager
        if type == "set":
            if not (guild and channel and log_type):
                await ctx.send("请提供服务器、频道和日志类型。", ephemeral=True)
                return
            if channel.guild.id != guild.id:
                await ctx.send("❌ 指定的频道不属于指定的服务器。", ephemeral=True)
                return
            if not channel.permissions_for(guild.me).send_messages:
                await ctx.send("❌ 机器人没有在该频道发送消息的权限。", ephemeral=True)
                return
            current_config = data_manager.get_logging_config(guild.id) or {}
            if log_type == "global":
                all_log_types = ["system", "user_activity", "error", "ai_chat", "admin"]
                global_config = {lt: channel.id for lt in all_log_types}
                await data_manager.set_global_logging_config(global_config)
                emb = discord.Embed(title="✅ 全局日志频道设置成功", color=discord.Color.green())
                emb.add_field(name="服务器", value=f"{guild.name} ({guild.id})", inline=True)
                emb.add_field(name="频道", value=f"#{channel.name} ({channel.id})", inline=True)
                emb.add_field(name="日志类型", value="全局日志（接收所有服务器）", inline=True)
                emb.set_footer(text=f"设置者: {ctx.author.display_name}")
                await ctx.send(embed=emb, ephemeral=True)
                return
            elif log_type == "all":
                all_log_types = ["system", "user_activity", "error", "ai_chat", "admin"]
                await data_manager.set_logging_config(guild.id, channel.id, all_log_types)
            else:
                current_config[log_type] = channel.id
                await data_manager.set_logging_config(guild.id, channel.id, list(current_config.keys()))
            emb = discord.Embed(title="✅ 日志频道设置成功", color=discord.Color.green())
            emb.add_field(name="服务器", value=f"{guild.name} ({guild.id})", inline=True)
            emb.add_field(name="频道", value=f"#{channel.name} ({channel.id})", inline=True)
            emb.add_field(name="日志类型", value=log_type, inline=True)
            emb.set_footer(text=f"设置者: {ctx.author.display_name}")
            await ctx.send(embed=emb, ephemeral=True)
        elif type == "send":
            if not (guild and log_type and message):
                await ctx.send("请提供服务器、日志类型和内容。", ephemeral=True)
                return
            config = data_manager.get_logging_config(guild.id)
            if not config or log_type not in config:
                await ctx.send("❌ 该日志类型没有配置频道。", ephemeral=True)
                return
            channel_id = config[log_type]
            try:
                channel_obj = guild.get_channel(channel_id)
                if not channel_obj or not isinstance(channel_obj, discord.TextChannel):
                    await ctx.send("❌ 找不到配置的日志频道。", ephemeral=True)
                    return
                await self.send_log(guild.id, log_type, message, ctx.author)
                emb = discord.Embed(title="✅ 日志发送成功", color=discord.Color.green())
                emb.add_field(name="服务器", value=guild.name, inline=True)
                emb.add_field(name="频道", value=f"#{channel_obj.name}", inline=True)
                emb.add_field(name="日志类型", value=log_type, inline=True)
                emb.add_field(name="内容", value=message[:100] + "..." if len(message) > 100 else message, inline=False)
                await ctx.send(embed=emb, ephemeral=True)
            except Exception as e:
                await ctx.send(f"❌ 发送日志时出错: {e}", ephemeral=True)
        elif type == "list":
            all_configs = data_manager.get_all_logging_configs()
            global_config = data_manager.get_global_logging_config()
            if not all_configs and not global_config:
                await ctx.send("📋 当前没有配置任何日志频道。", ephemeral=True)
                return
            emb = discord.Embed(title="📋 日志频道配置列表", color=discord.Color.blue())
            if global_config:
                global_info = []
                for log_type, channel_id in global_config.items():
                    target_channel = None
                    for g in self.bot.guilds:
                        ch = g.get_channel(channel_id)
                        if ch and isinstance(ch, discord.TextChannel):
                            target_channel = ch
                            break
                    channel_name = f"#{target_channel.name}" if target_channel else f"未知频道 ({channel_id})"
                    global_info.append(f"**{log_type}**: {channel_name}")
                emb.add_field(name="🌍 全局日志配置（接收所有服务器）", value="\n".join(global_info), inline=False)
            for guild_id_str, config in all_configs.items():
                try:
                    guild_id_int = int(guild_id_str)
                    g = self.bot.get_guild(guild_id_int)
                    guild_name = g.name if g else f"未知服务器 ({guild_id_str})"
                    log_info = []
                    for log_type, channel_id in config.items():
                        if g:
                            ch = g.get_channel(channel_id)
                            channel_name = f"#{ch.name}" if ch else f"未知频道 ({channel_id})"
                        else:
                            channel_name = f"未知频道 ({channel_id})"
                        log_info.append(f"**{log_type}**: {channel_name}")
                    emb.add_field(name=f"🏠 {guild_name}", value="\n".join(log_info), inline=False)
                except Exception as e:
                    emb.add_field(name=f"❌ 服务器 {guild_id_str}", value=f"获取信息失败: {e}", inline=False)
            await ctx.send(embed=emb, ephemeral=True)
        elif type == "delete":
            if not guild:
                await ctx.send("请提供服务器。", ephemeral=True)
                return
            if not log_type:
                await ctx.send("请提供日志类型。", ephemeral=True)
                return
            if log_type == "global":
                await data_manager.set_global_logging_config({})
                emb = discord.Embed(title="✅ 全局日志配置删除成功", color=discord.Color.green())
                emb.add_field(name="操作", value="已删除全局日志配置", inline=True)
                emb.set_footer(text=f"操作者: {ctx.author.display_name}")
                await ctx.send(embed=emb, ephemeral=True)
                return
            config = data_manager.get_logging_config(guild.id)
            if not config:
                await ctx.send("❌ 该服务器没有配置日志频道。", ephemeral=True)
                return
            if log_type == "all":
                await data_manager.remove_logging_config(guild.id)
                await ctx.send(f"✅ 已删除服务器 {guild.name} 的所有日志配置。", ephemeral=True)
                return
            if log_type in config:
                del config[log_type]
                if config:
                    # 还有其他日志类型，取第一个频道ID（所有类型都指向同一频道）
                    remaining_channel_id = list(config.values())[0]
                    remaining_log_types = list(config.keys())
                    await data_manager.set_logging_config(guild.id, remaining_channel_id, remaining_log_types)
                    await ctx.send(f"✅ 已删除 {guild.name} 的 {log_type} 日志配置。", ephemeral=True)
                else:
                    await data_manager.remove_logging_config(guild.id)
                    await ctx.send(f"✅ 已删除服务器 {guild.name} 的所有日志配置。", ephemeral=True)
            else:
                await ctx.send("❌ 未找到该日志类型的配置。", ephemeral=True)
        else:
            await ctx.send("未知操作类型。", ephemeral=True)

    @commands.hybrid_command(name="查看id", description="查看当前服务器和频道的ID信息")
    async def viewid(self, ctx: commands.Context):
        """查看ID信息"""
        await ctx.defer(ephemeral=True)
        
        if not ctx.guild:
            await ctx.send("此命令只能在服务器中使用。", ephemeral=True)
            return
        
        emb = discord.Embed(title="🆔 ID信息", color=discord.Color.blue())
        
        # 服务器信息
        emb.add_field(
            name="🏠 服务器信息", 
            value=f"**名称**: {ctx.guild.name}\n**ID**: `{ctx.guild.id}`", 
            inline=False
        )
        
        # 当前频道信息
        if isinstance(ctx.channel, discord.TextChannel):
            emb.add_field(
                name="📺 当前频道", 
                value=f"**名称**: #{ctx.channel.name}\n**ID**: `{ctx.channel.id}`", 
                inline=False
            )
        else:
            emb.add_field(
                name="📺 当前频道", 
                value=f"**类型**: {type(ctx.channel).__name__}\n**ID**: `{ctx.channel.id}`", 
                inline=False
            )
        
        # 其他频道信息（最多显示10个）
        text_channels = [ch for ch in ctx.guild.text_channels if ch != ctx.channel][:10]
        if text_channels:
            channel_list = []
            for ch in text_channels:
                channel_list.append(f"**#{ch.name}**: `{ch.id}`")
            
            emb.add_field(
                name="📋 其他频道", 
                value="\n".join(channel_list), 
                inline=False
            )
        
        # 使用说明
        emb.add_field(
            name="💡 使用说明", 
            value="• 复制ID用于其他需要ID的命令\n• 日志设置现在可以直接选择服务器和频道\n• 使用 `/log set` 命令进行日志配置", 
            inline=False
        )
        
        emb.set_footer(text=f"请求者: {ctx.author.display_name}")
        
        await ctx.send(embed=emb, ephemeral=True)

    @commands.hybrid_command(name="详细id", description="[主人] 查看详细的ID信息，包括用户、角色等")
    @app_commands.describe(target="要查看的目标（用户、角色、频道等）")
    @commands.check(checks.is_owner)
    async def detailedid(self, ctx: commands.Context, target: Optional[str] = None):
        """查看详细ID信息"""
        await ctx.defer(ephemeral=True)
        
        if not target:
            # 显示当前服务器的详细信息
            guild = ctx.guild
            if not guild:
                await ctx.send("此命令只能在服务器中使用。", ephemeral=True)
                return
                
            emb = discord.Embed(title=f"📋 {guild.name} 详细信息", color=discord.Color.blue())
            emb.add_field(name="🏠 服务器", value=f"ID: `{guild.id}`\n名称: {guild.name}", inline=False)
            if guild.owner:
                emb.add_field(name="👑 拥有者", value=f"ID: `{guild.owner_id}`\n名称: {guild.owner.display_name}", inline=False)
            emb.add_field(name="👥 成员数", value=f"{guild.member_count} 人", inline=True)
            emb.add_field(name="📝 频道数", value=f"{len(guild.channels)} 个", inline=True)
            emb.add_field(name="🎭 角色数", value=f"{len(guild.roles)} 个", inline=True)
            
            await ctx.send(embed=emb, ephemeral=True)
            return
            
        # 尝试解析目标
        try:
            # 尝试作为用户ID解析
            user = await self.bot.fetch_user(int(target))
            emb = discord.Embed(title=f"👤 用户信息", color=discord.Color.green())
            emb.add_field(name="用户", value=f"ID: `{user.id}`\n名称: {user.display_name}\n用户名: {user.name}", inline=False)
            emb.set_thumbnail(url=user.display_avatar.url)
            await ctx.send(embed=emb, ephemeral=True)
            return
        except (ValueError, discord.NotFound):
            pass
            
        try:
            # 尝试作为角色ID解析
            if ctx.guild:
                role = ctx.guild.get_role(int(target))
                if role:
                    emb = discord.Embed(title=f"🎭 角色信息", color=role.color)
                    emb.add_field(name="角色", value=f"ID: `{role.id}`\n名称: {role.name}\n颜色: {role.color}", inline=False)
                    emb.add_field(name="权限", value=f"位置: {role.position}\n提及: {'是' if role.mentionable else '否'}", inline=True)
                    await ctx.send(embed=emb, ephemeral=True)
                    return
        except ValueError:
            pass
            
        try:
            # 尝试作为频道ID解析
            if ctx.guild:
                channel = ctx.guild.get_channel(int(target))
                if channel:
                    emb = discord.Embed(title=f"📝 频道信息", color=discord.Color.blue())
                    emb.add_field(name="频道", value=f"ID: `{channel.id}`\n名称: {channel.name}\n类型: {channel.type.name}", inline=False)
                    await ctx.send(embed=emb, ephemeral=True)
                    return
        except ValueError:
            pass
            
        await ctx.send(f"无法找到ID为 `{target}` 的目标。", ephemeral=True)

    async def send_log(self, guild_id: int, log_type: str, message: str, author: Optional[discord.abc.User] = None):
        """发送日志到指定频道"""
        try:
            # 首先尝试发送到全局日志频道
            global_config = data_manager.get_global_logging_config()
            if global_config and log_type in global_config:
                await self._send_log_to_channel(global_config[log_type], log_type, message, author, guild_id)
            
            # 然后发送到服务器本地日志频道
            config = data_manager.get_logging_config(guild_id)
            if config and log_type in config:
                await self._send_log_to_channel(config[log_type], log_type, message, author, guild_id)
            
            return True
            
        except Exception as e:
            print(f"发送日志失败: {e}")
            return False

    async def _send_log_to_channel(self, channel_id: int, log_type: str, message: str, author: Optional[discord.abc.User] = None, source_guild_id: Optional[int] = None):
        """发送日志到指定频道"""
        try:
            # 查找频道所属的服务器
            target_guild = None
            target_channel = None
            
            for guild in self.bot.guilds:
                channel = guild.get_channel(channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    target_guild = guild
                    target_channel = channel
                    break
            
            if not target_channel:
                return False
            
            # 创建日志embed
            emb = discord.Embed(
                title=f"📝 {log_type.upper()} 日志",
                description=message,
                color=self.get_log_color(log_type),
                timestamp=discord.utils.utcnow()
            )
            
            if author:
                emb.set_author(name=author.display_name, icon_url=author.avatar)
            
            # 如果是跨服务器日志，添加来源服务器信息
            if source_guild_id and target_guild and source_guild_id != target_guild.id:
                source_guild = self.bot.get_guild(source_guild_id)
                if source_guild:
                    emb.add_field(name="来源服务器", value=f"{source_guild.name} ({source_guild_id})", inline=True)
            
            emb.set_footer(text=f"日志类型: {log_type}")
            
            await target_channel.send(embed=emb)
            return True
            
        except Exception as e:
            print(f"发送日志到频道失败: {e}")
            return False

    def get_log_color(self, log_type: str) -> discord.Color:
        """获取日志类型的颜色"""
        colors = {
            "system": discord.Color.blue(),
            "user_activity": discord.Color.green(),
            "error": discord.Color.red(),
            "ai_chat": discord.Color.purple(),
            "admin": discord.Color.orange()
        }
        return colors.get(log_type, discord.Color.greyple())

    @commands.hybrid_command(name="上传人格", description="[主人] 上传自定义AI人格（名称+内容），支持覆写")
    @app_commands.describe(name="人格名称", content="人格内容")
    @commands.check(checks.is_owner)
    async def upload_persona(self, ctx: commands.Context, name: str, content: str):
        """上传自定义AI人格，支持覆写同名人格"""
        await ctx.defer(ephemeral=True)
        name = name.strip()
        content = content.strip()
        if not name or not content:
            await ctx.send("❌ 人格名称和内容不能为空。", ephemeral=True)
            return
        await data_manager.set_persona(name, content)
        self.personas = data_manager.get_personas()
        await ctx.send(f"✅ 已上传人格 `{name}`，可用 /人格 命令切换。", ephemeral=True)
        await self.send_log(ctx.guild.id if ctx.guild else 0, "admin", f"上传人格：{name} by {ctx.author} ({ctx.author.id})", ctx.author)

    @commands.hybrid_group(name="授权", description="[主人] 管理可以与机器人对话的用户")
    @commands.check(checks.is_owner)
    async def authorize(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("请选择一个子命令: `添加`, `移除`, 或 `列表`。", ephemeral=True)

    @authorize.command(name="添加", description="[主人] 授权一个用户与机器人对话")
    @app_commands.describe(user="要授权的用户")
    async def authorize_add(self, ctx: commands.Context, user: discord.User):
        await ctx.defer(ephemeral=True)
        private_chat_users = data_manager.get_private_chat_users()
        if user.id in private_chat_users:
            await ctx.send(f"用户 {user.display_name} 已被授权。", ephemeral=True)
        else:
            private_chat_users.append(user.id)
            data_manager.data["private_chat_users"] = private_chat_users
            await data_manager.save_data_to_hf()
            await ctx.send(f"✅ 已授权用户 {user.display_name} 与机器人对话。", ephemeral=True)
            await self.send_log(ctx.guild.id if ctx.guild else 0, "admin", f"授权用户: {user.display_name} ({user.id}) by {ctx.author} ({ctx.author.id})", ctx.author)

    @authorize.command(name="移除", description="[主人] 取消一个用户的对话授权")
    @app_commands.describe(user="要取消授权的用户")
    async def authorize_remove(self, ctx: commands.Context, user: discord.User):
        await ctx.defer(ephemeral=True)
        private_chat_users = data_manager.get_private_chat_users()
        if user.id not in private_chat_users:
            await ctx.send(f"用户 {user.display_name} 未被授权。", ephemeral=True)
        else:
            private_chat_users.remove(user.id)
            data_manager.data["private_chat_users"] = private_chat_users
            await data_manager.save_data_to_hf()
            await ctx.send(f"✅ 已取消用户 {user.display_name} 的对话授权。", ephemeral=True)
            await self.send_log(ctx.guild.id if ctx.guild else 0, "admin", f"取消授权用户: {user.display_name} ({user.id}) by {ctx.author} ({ctx.author.id})", ctx.author)

    @authorize.command(name="列表", description="[主人] 查看所有已授权的用户")
    async def authorize_list(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        private_chat_users = data_manager.get_private_chat_users()
        if not private_chat_users:
            await ctx.send("目前没有授权任何用户。", ephemeral=True)
            return

        embed = discord.Embed(title="👑 已授权用户列表", color=discord.Color.gold())
        user_mentions = []
        for user_id in private_chat_users:
            try:
                user = await self.bot.fetch_user(user_id)
                user_mentions.append(f"• {user.display_name} (`{user.id}`)")
            except discord.NotFound:
                user_mentions.append(f"• 未知用户 (`{user_id}`)")
        
        embed.description = "\n".join(user_mentions)
        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name="手动描述表情", description="[主人] 手动为指定的表情添加或更新描述。")
    @app_commands.describe(
        emoji="要描述的表情",
        description="为表情设置的描述文本"
    )
    @commands.check(checks.is_owner)
    async def describe_emoji(self, ctx: commands.Context, emoji: discord.Emoji, description: str):
        """手动为表情添加或更新描述。"""
        await ctx.defer(ephemeral=True)
        
        success = emoji_manager.update_emoji_description(emoji.id, description)
        
        if success:
            await ctx.send(f"✅ 成功将表情 {emoji} 的描述更新为：`{description}`", ephemeral=True)
        else:
            # 这种情况通常发生在表情不在机器人的任何服务器中
            await ctx.send(f"❌ 更新失败！机器人似乎无法访问表情 {emoji}。请确保它是一个自定义表情，并且机器人在其所在的服务器中。", ephemeral=True)

    @commands.hybrid_command(name="生成表情描述", description="[主人] 使用AI为当前服务器的表情生成描述。")
    @commands.check(checks.is_owner)
    async def generate_emoji_descriptions(self, ctx: commands.Context):
        """使用AI为当前服务器的表情生成描述，并在当前频道显示进度。"""
        if not ctx.guild:
            await ctx.send("❌ 此命令只能在服务器中使用。", ephemeral=True)
            return

        # 先发送一个确认消息，告知任务已开始
        await ctx.send(f"✅ 收到请求！即将开始为服务器 **{ctx.guild.name}** 的表情生成AI描述...", ephemeral=True)

        # 创建并发送初始的嵌入式消息
        embed = discord.Embed(
            title=f"🎨 表情AI描述生成任务",
            description=f"正在初始化，请稍候...",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"由 {ctx.author.display_name} 发起")
        progress_message = await ctx.channel.send(embed=embed)

        # --- 定义回调函数 ---
        async def on_progress(current, total, name):
            embed.title = f"🎨 表情AI描述生成中..."
            embed.description = f"正在处理: **{name}**"
            embed.color = discord.Color.gold()
            embed.clear_fields()
            embed.add_field(name="进度", value=f"**{current} / {total}**", inline=True)
            await progress_message.edit(embed=embed)

        async def on_completion(processed_count, total_emojis):
            embed.title = f"✅ 任务完成"
            embed.description = f"成功为 **{processed_count}** 个新表情生成了描述。"
            embed.color = discord.Color.green()
            embed.clear_fields()
            embed.add_field(name="服务器表情总数", value=str(total_emojis), inline=True)
            embed.add_field(name="本次处理数", value=str(processed_count), inline=True)
            await progress_message.edit(embed=embed)

        async def on_no_work():
            embed.title = f"ℹ️ 无需处理"
            embed.description = "这个服务器的所有表情都已经拥有AI描述了。"
            embed.color = discord.Color.dark_grey()
            await progress_message.edit(embed=embed)

        async def on_error(error_msg):
            # 可以在这里添加更复杂的错误处理，比如将错误记录到一个字段里
            embed.add_field(name="⚠️ 处理错误", value=error_msg, inline=False)
            await progress_message.edit(embed=embed)

        # --- 调用核心逻辑 ---
        try:
            await emoji_manager.generate_descriptions_for_guild(
                guild_id=ctx.guild.id,
                on_progress=on_progress,
                on_completion=on_completion,
                on_no_work=on_no_work,
                on_error=on_error
            )
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ 发生致命错误",
                description=f"执行表情描述生成时发生意外错误: {e}",
                color=discord.Color.red()
            )
            await progress_message.edit(embed=error_embed)
            print(f"Fatal error during generate_emoji_descriptions: {e}")


async def setup(bot: commands.Bot):
    """将此 Cog 添加到机器人中"""
    await bot.add_cog(AdminCog(bot))
