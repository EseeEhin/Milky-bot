# bot.py
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import threading
from flask import Flask

from utils import data_manager, ai_utils

# --- 加载配置 ---
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
BOT_OWNER_ID_STR = os.getenv('BOT_OWNER_ID')
if not TOKEN or not BOT_OWNER_ID_STR:
    raise ValueError("错误：核心环境变量 DISCORD_BOT_TOKEN 或 BOT_OWNER_ID 未设置！")

# --- Bot 实例 ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# --- Flask 健康检查 ---
FLASK_PORT = int(os.getenv("PORT", 7860))
health_check_app = Flask(__name__)
@health_check_app.route('/')
def health_check():
    if bot.is_ready() and not bot.is_closed():
        return "Milky is awake, connected, and guarding her master.", 200
    return "Milky is connecting or in an unknown state with Discord.", 503

# --- 辅助函数 ---
async def _send_dm_to_owner(message: str):
    try:
        owner = await bot.fetch_user(int(BOT_OWNER_ID_STR))
        await owner.send(message)
    except Exception as e:
        print(f"向主人发送DM失败: {e}")

# --- 主启动逻辑 ---
async def main():
    print("正在初始化工具模块...")
    # 设置辅助函数的传递
    ai_utils.set_dm_sender(_send_dm_to_owner)
    data_manager.set_dm_sender(_send_dm_to_owner)

    # 加载持久化数据
    data_manager.load_data_from_hf()
    
    async with bot:
        print("\n--- 正在加载功能模块 (Cogs) ---")
        # 动态加载所有 cogs
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('_'):
                try:
                    await bot.load_extension(f'cogs.{filename[:-3]}')
                    print(f'  ✔️ 已加载 Cog: {filename}')
                except Exception as e:
                    print(f'  ❌ 加载 Cog {filename} 失败: {e.__class__.__name__} - {e}')
        print("--------------------------------\n")
        
        # 启动 Flask
        print(f"Flask健康检查服务准备在后台线程启动，将监听端口: {FLASK_PORT}")
        threading.Thread(target=lambda: health_check_app.run(host='0.0.0.0', port=FLASK_PORT, debug=False, use_reloader=False), daemon=True).start()
        
        print("正在连接到 Discord...")
        await bot.start(TOKEN)

@bot.event
async def on_ready():
    print(f'\n{bot.user} 已成功登录！')
    try:
        synced = await bot.tree.sync()
        print(f'同步了 {len(synced)} 个应用指令。')
    except Exception as e:
        print(f'同步指令失败: {e}')
    print("米尔可准备就绪！")

@bot.event
async def on_command_error(ctx, error):
    try:
        from cogs.admin_cog import AdminCog
        for cog in bot.cogs.values():
            if isinstance(cog, AdminCog):
                await cog.send_log(ctx.guild.id if ctx.guild else 0, "error", f"命令错误: {error}\n用户: {ctx.author} ({ctx.author.id})\n命令: {ctx.command}", ctx.author)
                break
    except Exception as e:
        print(f"全局错误日志记录失败: {e}")
    await ctx.send(f"❌ 命令执行出错: {error}", ephemeral=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except discord.LoginFailure:
        print("!!!!!! 致命错误：Discord登录失败！请检查您的DISCORD_BOT_TOKEN是否正确。 !!!!!!")
    except Exception as e:
        print(f"机器人主循环发生未知致命错误: {e}")