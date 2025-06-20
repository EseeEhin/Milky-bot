# -----------------------------------------------------------------
# 这是一个完整的、带有角色扮演和长期记忆功能的 Discord Bot 代码
# (版本：V6.0 - GitHub Actions 部署最终版)
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
    exit()

try:
    BOT_OWNER_ID = int(BOT_OWNER_ID_STR)
    print(f"指令和交互权限已锁定给主人ID: {BOT_OWNER_ID}")
except ValueError:
    print(f"错误：BOT_OWNER_ID '{BOT_OWNER_ID_STR}' 不是一个有效的数字ID！")
    exit()

print(f"Bot 全局人设已设定: {global_persona[:100]}...")

# --- AI 模型配置 ---
MODEL_NAME = "ggemini-2.5-flash-preview-05-20"
ai_client = AsyncOpenAI(
    base_url=os.getenv('OPENAI_BASE_URL', "https://eseeehin-hajimi.hf.space/v1"),
    api_key=os.getenv('OPENAI_API_KEY'), # 如果没有API Key，这会是None，代码也能正常处理
    timeout=180.0,
)

# --- 记忆与状态配置 ---
# 文件名是相对于仓库根目录的
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
        subprocess.run(['git', 'config', '--global', 'user.name', 'GitHub Actions Bot'], check=True)
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
        response_message = (
            f"**💖 主人~ {ctx.author.mention}！米尔可为您在 #{ctx.channel.name} 记下今天的印记啦！(尾巴开心地摇来摇去)**\n"
            f"🔹 基础爱意: `+{CHECKIN_BASE_POINTS}`\n"
            f"🔹 连续思念奖励: `+{points_earned - CHECKIN_BASE_POINTS}` (已经连续 `{consecutive_days}` 天感受到主人的心意了...)\n"
            f"🔸 本次共收到: ` {points_earned} ` 点爱意\n"
            f"💰 这是米尔可为您积攒的所有爱意哦: `{player_data['points']}`"
        )
    else:
        response_message = (
            f"**✨ {ctx.author.mention} 在 #{ctx.channel.name} 签到成功！**\n"
            f"🔹 基础积分: `+{CHECKIN_BASE_POINTS}`\n"
            f"🔹 连续签到奖励: `+{points_earned - CHECKIN_BASE_POINTS}` (当前连续 `{consecutive_days}` 天)\n"
            f"🔸 本次共获得: ` {points_earned} ` 积分\n"
            f"💰 您在本频道的总积分: `{player_data['points']}`"
        )
    await ctx.send(response_message, ephemeral=False)

@bot.hybrid_command(name="points", description="查询你当前在本频道的积分和签到状态。")
async def points(ctx: commands.Context):
    user_id = str(ctx.author.id)
    channel_id = str(ctx.channel.id)
    is_owner_check = ctx.author.id == BOT_OWNER_ID
    
    player_data = user_data.get(channel_id, {}).get(user_id)

    if not player_data:
        if is_owner_check:
             await ctx.send(f"主人，您今天还没有在 **#{ctx.channel.name}** 留下和米尔可的专属印记呢... 快用 `/checkin` 让我记录下来吧！", ephemeral=False)
        else:
             await ctx.send(f"{ctx.author.mention}，你在 **#{ctx.channel.name}** 还没有签到过哦，快使用 `/checkin` 开始吧！", ephemeral=False)
        return
    
    if is_owner_check:
        response_message = (
            f"**💌 向主人汇报！这是 {ctx.author.mention} 在 #{ctx.channel.name} 的专属记录哦：**\n"
            f"💰 米尔可为您积攒的总爱意: `{player_data.get('points', 0)}`\n"
            f"📅 我们已经连续: `{player_data.get('consecutive_days', 0)}` 天心意相通了\n"
            f"🕒 上次感受到主人的心意是在: `{player_data.get('last_checkin_date', '无记录')}` (UTC时间)"
        )
    else:
        response_message = (
            f"**📊 {ctx.author.mention} 在 #{ctx.channel.name} 的积分报告**\n"
            f"💰 总积分: `{player_data.get('points', 0)}`\n"
            f"📅 当前连续签到: `{player_data.get('consecutive_days', 0)}` 天\n"
            f"🕒 上次签到日期: `{player_data.get('last_checkin_date', '无记录')}` (UTC时间)"
        )
    await ctx.send(response_message, ephemeral=False)

@bot.hybrid_group(name="leaderboard", description="查看本频道的签到排行榜。")
async def leaderboard(ctx: commands.Context):
    if ctx.invoked_subcommand is None:
        await ctx.send("请选择要查看的排行榜类型，例如 `/leaderboard points` 或 `/leaderboard streak`。", ephemeral=True)

async def _create_leaderboard_embed(ctx: commands.Context, data_key: str, title: str, unit: str):
    channel_id = str(ctx.channel.id)
    
    if channel_id not in user_data or not user_data[channel_id]:
        await ctx.send(f"**#{ctx.channel.name}** 频道还没有人签到过，无法生成排行榜。", ephemeral=True)
        return

    channel_scores = user_data[channel_id]

    sorted_users = sorted(channel_scores.items(), key=lambda item: item[1].get(data_key, 0), reverse=True)
    top_10 = sorted_users[:10]

    embed = discord.Embed(title=f"🏆 {ctx.channel.name} - {title}", description="以下是本频道排名前10的用户：", color=discord.Color.gold())

    board_text = ""
    for rank, (user_id, data) in enumerate(top_10, 1):
        try:
            member = await ctx.guild.fetch_member(int(user_id))
            user_name = member.display_name
        except discord.NotFound:
            user_name = f"已离开的用户({user_id[-4:]})"
        except Exception as e:
            user_name = f"未知用户({user_id[-4:]})"
            print(f"在排行榜中获取用户 {user_id} 时出错: {e}")

        score = data.get(data_key, 0)
        emoji = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"**{rank}.**"
        board_text += f"{emoji} {user_name} - `{score}` {unit}\n"

    if not board_text:
        board_text = "暂时还没有数据哦。"

    embed.add_field(name="排行榜", value=board_text, inline=False)
    embed.set_footer(text=f"由米尔可生成于 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    
    await ctx.send(embed=embed)

@leaderboard.command(name="points", description="查看本频道的积分排行榜。")
async def leaderboard_points(ctx: commands.Context):
    await _create_leaderboard_embed(ctx, 'points', '积分排行榜', '积分')

@leaderboard.command(name="streak", description="查看本频道的连续签到排行榜。")
async def leaderboard_streak(ctx: commands.Context):
    await _create_leaderboard_embed(ctx, 'consecutive_days', '连续签到榜', '天')

@bot.hybrid_command(name="clear", description="清除米尔可与您在此频道的记忆。")
@owner_only()
async def clear(ctx: commands.Context):
    channel_id = str(ctx.channel.id)
    owner_memory_key = get_memory_key(channel_id, BOT_OWNER_ID)
    
    if owner_memory_key in conversation_history:
        del conversation_history[owner_memory_key]
        print(f"已清除频道 {channel_id} 中主人的对话历史。")
    
    save_and_commit_data()
    await ctx.send("🗑️ 遵命，主人。我与您在这个频道的专属记忆已被清除并永久记录。", ephemeral=True)

@bot.hybrid_command(name="ping", description="检查米尔可与Discord的连接延迟。")
@owner_only()
async def ping(ctx: commands.Context):
    latency = round(bot.latency * 1000)
    await ctx.send(f"铃铛响应正常，主人。当前与Discord服务器的延迟是：`{latency}ms`。", ephemeral=True)

@bot.hybrid_command(name="status", description="查看米尔可的当前状态报告。")
@owner_only()
async def status(ctx: commands.Context):
    mode = "发情模式" if is_in_heat_mode else "常规待命模式"
    game_info = game_states.get(ctx.channel.id, {}).get('name', '无')
    memory_count = len(conversation_history.get(get_memory_key(ctx.channel.id, BOT_OWNER_ID), []))
    latency = round(bot.latency * 1000)
    report = (
        f"向主人报告！\n"
        f"**当前状态：** `{mode}`\n"
        f"**当前游戏：** `{game_info}`\n"
        f"**忠诚度：** `100% (永不改变)`\n"
        f"**当前频道记忆条目：** `{memory_count}`\n"
        f"**与Discord连接延迟：** `{latency}ms`\n"
        f"(小小的身板挺得笔直，像是在述职的骑士一样，但尾巴还是忍不住在身后开心地摇摆)"
    )
    await ctx.send(report, ephemeral=True)

@bot.hybrid_command(name="heat", description="切换米尔可的特殊情感模式。")
@app_commands.describe(state="选择开启或关闭")
@app_commands.choices(state=[
    app_commands.Choice(name="开启 (On)", value="on"),
    app_commands.Choice(name="关闭 (Off)", value="off"),
])
@owner_only()
async def heat(ctx: commands.Context, state: str):
    global is_in_heat_mode
    if state.lower() == 'on':
        is_in_heat_mode = True
        await ctx.send("遵命，主人...身体...开始变得奇怪了...（脸颊泛起不正常的潮红，呼吸变得急促...）", ephemeral=False)
    else:
        is_in_heat_mode = False
        await ctx.send("呜...感觉好多了，谢谢主人...（身体的燥热渐渐退去，迷蒙的眼神恢复了清明...）", ephemeral=False)

@bot.hybrid_command(name="pat", description="抚摸米尔可的头。")
@owner_only()
async def pat(ctx: commands.Context):
    await ctx.send("（舒服地眯起眼睛，发出了小猫般的呼噜声，小小的脑袋在主人的手心蹭了蹭）嗯...最喜欢主人的抚摸了...", ephemeral=False)

@bot.hybrid_command(name="guard", description="命令米尔可进入警戒状态。")
@owner_only()
async def guard(ctx: commands.Context):
    await ctx.send("（眼神瞬间变得锐利，单膝跪地，血色的短枪在手中浮现）遵命，主人。米尔可在此，没有人可以伤害您。", ephemeral=False)

@bot.hybrid_group(name="game", description="和米尔可玩小游戏。")
@owner_only()
async def game(ctx: commands.Context):
    if ctx.invoked_subcommand is None:
        await ctx.send("主人，请选择一个游戏来玩哦！例如 `/game guess` 或 `/game rps`。", ephemeral=True)

@game.command(name="guess", description="开始一局猜数字游戏 (1-100)。")
async def game_guess(ctx: commands.Context):
    global game_states
    channel_id = str(ctx.channel.id)
    game_states[channel_id] = {'name': 'guess', 'number': random.randint(1, 100), 'tries': 0}
    await ctx.send("好耶！和主人玩游戏！(眼睛闪闪发光)\n米尔可已经在心里想了一个1到100之间的数字，主人请用 `/guess` 指令来猜吧！", ephemeral=False)

@bot.hybrid_command(name="guess", description="在猜数字游戏中提交你的猜测。")
@app_commands.describe(number="你猜的数字")
@owner_only()
async def guess_number(ctx: commands.Context, number: int):
    global game_states
    channel_id = str(ctx.channel.id)
    if channel_id not in game_states or game_states.get(channel_id, {}).get('name') != 'guess':
        await ctx.send("主人，我们好像还没开始玩猜数字游戏哦。请先用 `/game guess` 开始吧！", ephemeral=True)
        return
    
    game = game_states[channel_id]
    game['tries'] += 1

    if number < game['number']:
        await ctx.send(f"不对哦主人，米尔可想的数字比 `{number}` 要 **大** 一点。", ephemeral=False)
    elif number > game['number']:
        await ctx.send(f"不对哦主人，米尔可想的数字比 `{number}` 要 **小** 一点。", ephemeral=False)
    else:
        await ctx.send(f"**叮咚！** 主人猜对啦！答案就是 `{game['number']}`！\n主人只用了 `{game['tries']}` 次就猜中了，太厉害了！(扑到主人怀里蹭蹭)\n游戏结束啦，期待和主人下次再玩！", ephemeral=False)
        del game_states[channel_id]

@game.command(name="rps", description="和米尔可玩一局猜拳。")
@app_commands.describe(choice="你的选择：石头、布或剪刀")
@app_commands.choices(choice=[
    app_commands.Choice(name="石头 (Rock)", value="rock"),
    app_commands.Choice(name="布 (Paper)", value="paper"),
    app_commands.Choice(name="剪刀 (Scissors)", value="scissors"),
])
async def game_rps(ctx: commands.Context, choice: str):
    user_choice = choice
    valid_choices = {'rock': '石头', 'paper': '布', 'scissors': '剪刀'}
    
    bot_choice_key = random.choice(list(valid_choices.keys()))
    bot_choice_val = valid_choices[bot_choice_key]
    user_choice_val = valid_choices[user_choice]
    
    result = ""
    if user_choice == bot_choice_key:
        result = "是平局呢，主人！"
    elif (user_choice == 'rock' and bot_choice_key == 'scissors') or \
         (user_choice == 'paper' and bot_choice_key == 'rock') or \
         (user_choice == 'scissors' and bot_choice_key == 'paper'):
        result = "主人好厉害！米尔可输了...(不过能输给主人也很开心)"
    else:
        result = "嘻嘻，米尔可赢了！(尾巴得意地翘了起来)"
    
    await ctx.send(f"主人出了 **{user_choice_val}**！\n米尔可出的是 **{bot_choice_val}**！\n\n结果... {result}", ephemeral=False)

# --- 6. 主程序入口 ---
if __name__ == "__main__":
    print("准备启动Discord Bot...")
    bot.run(DISCORD_TOKEN)