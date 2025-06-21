# utils/checks.py
from discord.ext import commands
import os

# 加载一次，避免重复读取
try:
    BOT_OWNER_ID = int(os.getenv('BOT_OWNER_ID'))
except (ValueError, TypeError):
    print("警告：无法从环境变量解析 BOT_OWNER_ID，主人专属指令将失效。")
    BOT_OWNER_ID = 0

async def is_owner(ctx: commands.Context) -> bool:
    """检查交互发起者是否为机器人主人"""
    user_to_check = ctx.author
    if ctx.interaction:
        user_to_check = ctx.interaction.user
        
    if user_to_check.id != BOT_OWNER_ID:
        if ctx.interaction:
            error_message = "抱歉，这个指令只有我的主人才能使用哦~（歪头）"
            # 优先使用 is_done() 检查，更可靠
            if not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(error_message, ephemeral=True)
            else:
                # 如果响应已完成（例如，在 defer 后），使用 followup
                try:
                    await ctx.interaction.followup.send(error_message, ephemeral=True)
                except discord.NotFound:
                    pass # 交互已过期，无需操作
        return False
    return True