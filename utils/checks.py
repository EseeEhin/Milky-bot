# utils/checks.py
from discord.ext import commands
import discord
import os

# 加载一次，避免重复读取
try:
    BOT_OWNER_ID = int(os.getenv('BOT_OWNER_ID'))
except (ValueError, TypeError):
    print("警告：无法从环境变量解析 BOT_OWNER_ID，主人专属指令将失效。")
    BOT_OWNER_ID = 0

async def is_owner(interaction: discord.Interaction) -> bool:
    """
    一个通用的检查器，用于检查交互的发起者是否为机器人主人。
    这适用于所有类型的应用命令（斜杠命令、上下文菜单等）。
    """
    if interaction.user.id != BOT_OWNER_ID:
        error_message = "抱歉，这个指令只有我的主人才能使用哦~（歪头）"
        # 对于应用命令，我们总是可以安全地发送一个临时的回应
        if not interaction.response.is_done():
            await interaction.response.send_message(error_message, ephemeral=True)
        else:
            # 如果响应已完成（例如，在 defer 后），使用 followup
            try:
                await interaction.followup.send(error_message, ephemeral=True)
            except discord.NotFound:
                pass # 交互已过期，无需操作
        return False
    return True

# 保留旧的基于 Context 的检查器，以兼容可能存在的旧式前缀命令
def is_owner_context():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id != BOT_OWNER_ID:
            await ctx.send("抱歉，这个指令只有我的主人才能使用哦~（歪头）", ephemeral=True)
            return False
        return True
    return commands.check(predicate)