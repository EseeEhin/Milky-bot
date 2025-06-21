# cogs/admin_cog.py
import discord
from discord.ext import commands
from discord import app_commands
import os
import json
from datetime import datetime
from typing import Literal, Optional, ClassVar
from enum import Enum
from utils import checks, data_manager

# 将枚举定义在类外部，作为模块级别的常量，这是一种更通用的做法
class PointAction(str, Enum):
    add = "增加"
    set = "设定"
    remove = "移除"

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

    @commands.hybrid_command(name="status", description="[主人]查看米尔可的内部状态报告。")
    @commands.check(checks.is_owner)
    async def status(self, ctx: commands.Context):
        """显示机器人的内部运行状态和配置信息。"""
        await ctx.defer(ephemeral=True)
        mode = "发情模式" if self.is_in_heat_mode else "常规待命模式"
        
        emb = discord.Embed(title="米尔可内部状态报告", color=discord.Color.from_rgb(178, 190, 195)) # 银灰色
        emb.add_field(name="当前模式", value=f"`{mode}`", inline=True)
        emb.add_field(name="忠诚度", value="`∞%`", inline=True)
        
        # 从数据管理器获取实时数据
        autoreact_rules = len(data_manager.get_autoreact_map())
        private_chat_users = len(data_manager.get_private_chat_users())
        
        emb.add_field(name="自动反应规则数", value=f"`{autoreact_rules}` 条", inline=False)
        emb.add_field(name="私聊授权用户数", value=f"`{private_chat_users}` 人", inline=False)

        emb.add_field(name="AI 模型", value=f"`{self.AI_MODEL_NAME}`", inline=False)
        emb.add_field(name="数据仓库", value=f"`{self.HF_DATA_REPO_ID}`", inline=False)
        emb.set_footer(text=f"报告于: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        await ctx.send(embed=emb)

    @commands.hybrid_command(name="heat", description="[主人]切换米尔可特殊情感模式。")
    @app_commands.describe(state="开启或关闭")
    @commands.check(checks.is_owner)
    async def heat(self, ctx: commands.Context, state: Literal["on", "off"]):
        """切换米尔可的AI人格是否处于“发情”模式。"""
        self.is_in_heat_mode = (state.lower() == 'on')
        msg = "遵命，主人...身体...开始奇怪了...（脸红急促...）" if self.is_in_heat_mode else "呜...好多了，谢谢主人...（燥热退去，眼神清明...）"
        await ctx.send(msg)

    @commands.hybrid_group(name="admin", description="[主人]核心管理工具")
    @commands.check(checks.is_owner)
    async def admin(self, ctx: commands.Context):
        """管理指令的根命令，本身不执行任何操作。"""
        if ctx.invoked_subcommand is None:
            await ctx.send("主人，请选择管理操作。例如 `/admin points` 或 `/admin set_checkin_stats`。", ephemeral=True)

    @admin.command(name="points", description="[主人]修改用户的通用积分/爱意。")
    @app_commands.describe(user="目标用户", action="操作", amount="数量")
    async def admin_points(self, ctx: commands.Context, user: discord.User, action: PointAction, amount: int):
        """增加、设定或移除用户的积分。"""
        await ctx.defer(ephemeral=True)
        if amount < 0:
            await ctx.send("主人，数量不能为负。", ephemeral=True)
            return

        is_owner_target = (user.id == self.BOT_OWNER_ID)
        curr = "爱意" if is_owner_target else "积分"
        
        p_data = data_manager.get_user_data(user.id)
        if not p_data:
            p_data = {'points': 0, 'last_checkin_date': None, 'consecutive_days': 0}
        
        orig_pts = p_data.get('points', 0)
        
        if action == PointAction.add:
            p_data['points'] = orig_pts + amount
        elif action == PointAction.set:
            p_data['points'] = amount
        elif action == PointAction.remove:
            p_data['points'] = max(0, orig_pts - amount)
            
        data_manager.update_user_data(user.id, p_data)
        await ctx.send(f"遵命，主人。\n用户 **{user.display_name}** 的通用{curr}已修改。\n操作: {action.value} `{amount}`\n{curr}从 `{orig_pts}` 变为 `{p_data['points']}`。", ephemeral=True)

    @admin.command(name="set_checkin_stats", description="[主人][高危]修改用户的通用签到数据。")
    @app_commands.describe(
        user="目标用户",
        points="设定新的总积分/爱意",
        consecutive_days="设定新的连续签到天数",
        last_checkin_date="设定上次签到日 (格式: YYYY-MM-DD, 或输入 'reset' 清空)"
    )
    async def admin_set_checkin_stats(self, ctx: commands.Context, user: discord.User, points: Optional[int] = None, consecutive_days: Optional[int] = None, last_checkin_date: Optional[str] = None):
        """手动修改用户的详细签到数据，此操作具有高风险。"""
        await ctx.defer(ephemeral=True)
        
        p_data = data_manager.get_user_data(user.id)
        if not p_data:
            p_data = {'points': 0, 'last_checkin_date': None, 'consecutive_days': 0}
        
        changes = []

        if points is not None:
            if points < 0:
                await ctx.send("错误：点数不能为负。", ephemeral=True); return
            p_data['points'] = points
            changes.append(f"总点数设为`{points}`")
        if consecutive_days is not None:
            if consecutive_days < 0:
                await ctx.send("错误：连续天数不能为负。", ephemeral=True); return
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
                    await ctx.send(f"错误：日期格式无效。请使用 YYYY-MM-DD 或 'reset'。", ephemeral=True); return

        if not changes:
            await ctx.send(f"主人，未指定任何修改项，用户 {user.mention} 的数据没有发生更改。", ephemeral=True); return

        data_manager.update_user_data(user.id, p_data)
        await ctx.send(f"遵命，主人。\n用户 **{user.display_name}** 的签到数据已修改如下：\n- {'; '.join(changes)}", ephemeral=True)

async def setup(bot: commands.Bot):
    """将此 Cog 添加到机器人中"""
    await bot.add_cog(AdminCog(bot))