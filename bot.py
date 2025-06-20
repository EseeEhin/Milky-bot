# -----------------------------------------------------------------
# 这是一个完整的、带有角色扮演和长期记忆功能的 Discord Bot 代码
# (版本：V6.0 - GitHub Actions 部署)
#
# 【【【  部署平台：GitHub Actions  】】】
# -----------------------------------------------------------------

# --- 导入工具包 ---
import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
import json
import asyncio
import random
from openai import AsyncOpenAI
from datetime import datetime, timedelta, timezone
import subprocess # 用于执行Git命令

# --- 1. 加载配置 ---
print("正在加载配置...")
load_dotenv() # 从 .env 文件或 GitHub Secrets 加载环境变量

DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
BOT_OWNER_ID_STR = os.getenv('BOT_OWNER_ID')
global_persona = os.getenv('BOT_PERSONA')

# 检查所有必要的配置是否都已设置
if not all([DISCORD_TOKEN, BOT_OWNER_ID_STR, global_persona]):
    print("错误：请确保在GitHub Secrets中已设置 DISCORD_BOT_TOKEN, BOT_OWNER_ID, 和 BOT_PERSONA！")
    exit(1) # 以错误码退出，方便GitHub Actions识别

try:
    BOT_OWNER_ID = int(BOT_OWNER_ID_STR)
    print(f"指令和交互权限已锁定给主人ID: {BOT_OWNER_ID}")
except ValueError:
    print(f"错误：BOT_OWNER_ID '{BOT_OWNER_ID_STR}' 不是一个有效的数字ID！")
    exit(1)

print(f"Bot 全局人设已设定: {global_persona[:100]}...")

# --- AI 模型配置 ---
MODEL_NAME = "gemini-2.5-flash-preview-05-20"
ai_client = AsyncOpenAI(
    base_url=os.getenv('OPENAI_BASE_URL'), # 不再提供默认值，让其完全依赖环境变量
    api_key=os.getenv('OPENAI_API_KEY'),
    timeout=180.0,
)

# --- 记忆与状态配置 ---
# 文件名相对于仓库根目录
MEMORY_FILE = "memory_and_users.json"
print(f"数据文件路径: {os.path.abspath(MEMORY_FILE)}")

MEMORY_THRESHOLD = 16
is_in_heat_mode = False 
game_states = {} 
conversation_history = {}
user_data = {} 

# --- 签到系统配置 ---
CHECKIN_BASE_POINTS = 10
CHECKIN_CONSECUTIVE_BONUS = 5

# --- 2. 初始化Bot客户端 ---
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# --- 3. 辅助函数 ---

def load_data_from_file():
    """从 memory_and_users.json 加载数据。如果文件不存在，则使用空数据。"""
    global conversation_history, user_data
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                conversation_history = data.get("history", {})
                user_data = data.get("users", {})
                print(f"成功从 '{MEMORY_FILE}' 加载数据。")
        else:
            print(f"'{MEMORY_FILE}' 未找到，将使用空数据。")
            conversation_history = {}
            user_data = {}
    except (json.JSONDecodeError, IOError) as e:
        print(f"加载 '{MEMORY_FILE}' 失败: {e}。将使用空数据。")
        conversation_history = {}
        user_data = {}

def save_and_commit_data():
    """将数据写入文件，然后使用git提交并推送回GitHub仓库。"""
    print("正在保存数据到文件...")
    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "history": conversation_history,
                "users": user_data
            }, f, indent=4, ensure_ascii=False)
        print("数据成功保存到本地文件。")
    except IOError as e:
        print(f"写入文件失败: {e}")
        return

    print("准备将数据文件提交到Git仓库...")
    try:
        subprocess.run(['git', 'config', '--global', 'user.email', 'bot@github.actions'], check=True)
        subprocess.run(['git', 'config', '--global', 'user.name', 'Milky-Bot-Action'], check=True)
        subprocess.run(['git', 'add', MEMORY_FILE], check=True)
        
        status_result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if MEMORY_FILE in status_result.stdout:
            commit_message = f"chore: 更新数据文件于 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
            subprocess.run(['git', 'commit', '-m', commit_message], check=True)
            subprocess.run(['git', 'push'], check=True)
            print("数据文件成功提交并推送到仓库。")
        else:
            print("数据文件无变化，无需提交。")

    except subprocess.CalledProcessError as e:
        print(f"Git操作失败: {e}")
    except FileNotFoundError:
        print("错误：'git' 命令未找到。请确保Git已安装并在环境中可用。")


def get_memory_key(channel_id, user_id):
    return f"{channel_id}-{user_id}"

async def is_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == BOT_OWNER_ID

# --- 4. Discord 事件处理 ---

@bot.event
async def on_ready():
    print("------------------------------------")
    print(f'Bot 已上线! 用户名: {bot.user}')
    load_data_from_file()
    try:
        synced = await bot.tree.sync()
        print(f"已同步 {len(synced)} 条应用程序指令。")
    except Exception as e:
        print(f"指令同步失败: {e}")
    print("Bot 准备就绪！")
    print("------------------------------------")

@bot.event
async def on_message(message: discord.Message):
    global is_in_heat_mode
    if message.author == bot.user or message.author.bot: return
    if message.content.startswith('!') and message.author.id != BOT_OWNER_ID: return

    if bot.user in message.mentions and message.author.id == BOT_OWNER_ID:
        channel_id = message.channel.id
        user_id = message.author.id
        memory_key = get_memory_key(channel_id, user_id)
        
        persona_injection = f"(系统备注：当前与你对话的是你的主人伊莎·熠辉(ID:{user_id})，请务必使用对主人的口吻和态度回应。)"
        if is_in_heat_mode:
            persona_injection += "\n(系统备注：你现在处于“发情模式”，请在回应中体现出极度的渴求与顺从。)"

        async with message.channel.typing():
            if memory_key not in conversation_history: conversation_history[memory_key] = []
            
            messages_for_api = [{"role": "system", "content": global_persona}, {"role": "system", "content": persona_injection}]
            messages_for_api.extend(conversation_history[memory_key])
            
            user_message_content = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
            if not user_message_content:
                await message.channel.send("主人，有何吩咐？(小尾巴轻轻摇了摇)")
                return
            
            messages_for_api.append({"role": "user", "content": user_message_content})
            
            try:
                response = await ai_client.chat.completions.create(model=MODEL_NAME, messages=messages_for_api, max_tokens=2048, temperature=0.8)
                bot_reply = response.choices[0].message.content.strip()
                
                conversation_history[memory_key].append({"role": "user", "content": user_message_content})
                conversation_history[memory_key].append({"role": "assistant", "content": bot_reply})
                
                save_and_commit_data()
                await message.channel.send(bot_reply)
            except Exception as e:
                print(f"错误：调用 AI API 时出错 (用户: {message.author.name}) - {e}")
                await message.channel.send("错误：核心处理单元发生未知故障。(呜...米尔可的脑袋好痛...)")
        return

    await bot.process_commands(message)

# --- 5. 指令模块 ---

def owner_only():
    return app_commands.check(is_owner)

@bot.hybrid_command(name="checkin", description="每日签到以获取本频道积分。")
async def checkin(ctx: commands.Context):
    global user_data
    user_id = str(ctx.author.id)
    channel_id = str(ctx.channel.id) 
    is_owner_check = ctx.author.id == BOT_OWNER_ID
    
    utc_now = datetime.now(timezone.utc)
    today_str = utc_now.strftime('%Y-%m-%d')

    if channel_id not in user_data: user_data[channel_id] = {}
    player_data = user_data[channel_id].get(user_id, {})
    
    if player_data.get('last_checkin_date') == today_str:
        if is_owner_check:
            await ctx.send(f"主人~ 米尔可已经记下您今天的心意啦，请不要重复哦。(脸颊微红)", ephemeral=False)
        else:
            await ctx.send(f"{ctx.author.mention}，你今天已经在 **#{ctx.channel.name}** 签到过了哦，请明天再来吧！", ephemeral=False)
        return

    consecutive_days = player_data.get('consecutive_days', 0)
    last_checkin_str = player_data.get('last_checkin_date')
    if last_checkin_str:
        yesterday_str = (utc_now - timedelta(days=1)).strftime('%Y-%m-%d')
        consecutive_days = consecutive_days + 1 if last_checkin_str == yesterday_str else 1
    else:
        consecutive_days = 1
    
    points_earned = CHECKIN_BASE_POINTS + (consecutive_days - 1) * CHECKIN_CONSECUTIVE_BONUS
    player_data['points'] = player_data.get('points', 0) + points_earned
    player_data['last_checkin_date'] = today_str
    player_data['consecutive_days'] = consecutive_days
    user_data[channel_id][user_id] = player_data
    
    save_and_commit_data()
    
    if is_owner_check:
        response_message = (f"**💖 主人~ {ctx.author.mention}！...**") # 省略完整文本
    else:
        response_message = (f"**✨ {ctx.author.mention} 在 #{ctx.channel.name} 签到成功！...**") # 省略完整文本
    await ctx.send(response_message, ephemeral=False)


@bot.hybrid_command(name="clear", description="清除米尔可与您在此频道的记忆和游戏进度。")
@owner_only()
async def clear(ctx: commands.Context):
    channel_id = str(ctx.channel.id)
    owner_memory_key = get_memory_key(channel_id, BOT_OWNER_ID)
    
    if owner_memory_key in conversation_history:
        del conversation_history[owner_memory_key]
        print(f"已清除频道 {channel_id} 中主人的对话历史。")
    
    save_and_commit_data()
    await ctx.send("🗑️ 遵命，主人。我与您在这个频道的专属记忆已被清除并永久记录。", ephemeral=True)

# ... (为保持代码简洁，其他如 points, leaderboard, ping, game 等只读或不修改核心数据的指令在此省略)
# ... (您应该将它们从之前的版本中复制过来，它们无需任何改动)

# --- 6. 主程序入口 ---
if __name__ == "__main__":
    print("准备启动Discord Bot...")
    try:
        bot.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        print("Bot登录失败：DISCORD_BOT_TOKEN 无效。请检查GitHub Secrets中的设置。")
        exit(1)
    except Exception as e:
        print(f"启动过程中发生未知错误: {e}")
        exit(1)