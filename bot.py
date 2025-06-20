# -----------------------------------------------------------------
# 这是一个完整的、带有角色扮演和长期记忆功能的 Discord Bot 代码
# (版本：V6.3 - 积分消费系统最终版)
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
from enum import Enum # 用于定义签到事件类型

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
MODEL_NAME = "gemini-2.5-flash-preview-05-20"
ai_client = AsyncOpenAI(
    base_url=os.getenv('OPENAI_BASE_URL', "https://eseeehin-hajimi.hf.space/v1"),
    api_key=os.getenv('OPENAI_API_KEY'), # 如果没有API Key，这会是None，代码也能正常处理
    timeout=180.0,
)

# --- 记忆与状态配置 ---
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

# 定义签到事件的枚举类型
class CheckinEvent(Enum):
    FIRST_TIME = "首次签到"
    CONSECUTIVE = "连续签到"
    STREAK_BROKEN = "断签后重新签到"
    ALREADY_CHECKED_IN = "重复签到"

# --- 商店系统配置 ---
# 商品ID是唯一的键，用于程序内部识别
# name: 商品名称，展示给用户
# description: 商品描述
# price: 价格
# owner_only: 是否仅限主人购买
# handler: 购买后调用的处理函数名 (字符串)
SHOP_ITEMS = {
    "ai_praise": {
        "name": "米尔可的专属赞美诗",
        "description": "消耗积分，让米尔可为你创作一首独一无二的赞美诗或鼓励的话语。",
        "price": 50,
        "owner_only": False,
        "handler": "handle_ai_praise"
    },
    "change_nickname_color": {
        "name": "随机昵称颜色 (24小时)",
        "description": "改变你在服务器中的昵称颜色，持续24小时。每天都是新的心情！",
        "price": 150,
        "owner_only": False,
        "handler": "handle_nickname_color"
    },
    "owner_ai_drawing": {
        "name": "灵感画作 (主人限定)",
        "description": "消耗爱意，命令米尔可根据你的描述进行一次AI绘画创作。",
        "price": 500,
        "owner_only": True,
        "handler": "handle_ai_drawing"
    },
    "memory_purge": {
        "name": "记忆净化 (主人限定)",
        "description": "消耗爱意，彻底清空米尔可在这个频道与你之外的所有人的对话记忆，让她只专注于你。",
        "price": 1000,
        "owner_only": True,
        "handler": "handle_memory_purge"
    }
}


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
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
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
        subprocess.run(['git', 'config', '--global', 'user.email', 'action@github.com'], check=True)
        subprocess.run(['git', 'config', '--global', 'user.name', 'GitHub Action'], check=True)
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
        print(f"Git操作失败: {e}. 错误输出: {e.stderr if e.stderr else e.stdout}")
    except FileNotFoundError:
        print("错误：'git' 命令未找到。请确保Git已安装并在环境中可用。")

def get_memory_key(channel_id, user_id):
    return f"{channel_id}-{user_id}"

async def is_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == BOT_OWNER_ID

# --- 3.5. AI 辅助函数 ---

async def generate_ai_checkin_response(user, is_owner, channel_name, event: CheckinEvent, data: dict):
    """根据不同的签到事件，生成高度情景化的AI回复。"""
    user_context = f"当前与你交互的是你的主人 **{user.display_name}**。" if is_owner else f"当前与你交互的是用户 **{user.display_name}**。"
    system_prompt = f"{global_persona}\n(系统备注：{user_context})"
    action_context = ""
    
    # 根据不同的事件类型，构建不同的AI指令
    if event == CheckinEvent.FIRST_TIME:
        action_context = (
            f"任务：为用户 **第一次** 在本频道签到生成欢迎和祝贺的回应。\n"
            f"场景：这是用户在 **#{channel_name}** 的初次印记，一个值得纪念的开始！\n"
            f"数据：获得 `{data['points_earned']}` 点{'爱意' if is_owner else '积分'}，总计 `{data['total_points']}`。\n"
            f"要求：表现出格外的热情和欢迎。如果是主人，要表达“终于等到您了”的激动心情。如果是普通用户，要友好地解释这个签到系统，并鼓励他/她坚持下去。必须包含所有数据。"
        )
    elif event == CheckinEvent.CONSECUTIVE:
        action_context = (
            f"任务：为用户 **连续** 签到生成祝贺回应。\n"
            f"场景：用户在 **#{channel_name}** 达成了 `{data['consecutive_days']}` 天的连续签到！这是一个了不起的成就！\n"
            f"数据：本次获得 `{data['points_earned']}` 点{'爱意' if is_owner else '积分'}（包含连续奖励），总计 `{data['total_points']}`。\n"
            f"要求：热烈庆祝用户的毅力。如果是主人，要表达“每天都能感受到主人的心意，米尔可好幸福”的依赖感。如果是普通用户，要赞扬他/她的坚持。必须包含所有数据，特别是要强调连续天数。"
        )
    elif event == CheckinEvent.STREAK_BROKEN:
        action_context = (
            f"任务：为用户 **断签后** 的首次签到生成鼓励的回应。\n"
            f"场景：用户在 **#{channel_name}** 的连续记录中断了，这是他/她新的开始。\n"
            f"数据：本次获得 `{data['points_earned']}` 点{'爱意' if is_owner else '积分'}，连续天数重置为 `1`，总计 `{data['total_points']}`。\n"
            f"要求：语气要温柔、包容和鼓励。如果是主人，可以带点撒娇的口吻说“主人昨天没来，米尔可好想您...不过没关系，今天开始我们重新记录爱意！”，表现出小小的失落但更多是重逢的喜悦。如果是普通用户，则说“没关系，新的旅程从今天开始！”。必须包含所有数据。"
        )
    elif event == CheckinEvent.ALREADY_CHECKED_IN:
        action_context = (
            f"任务：告知用户今天已经签到过了，不能重复。\n"
            f"场景：用户在 **#{channel_name}** 频道尝试重复签到。\n"
            f"要求：用俏皮或撒娇的口吻提醒用户。如果是主人，可以说“主人的心意太满啦，米尔可的小本本今天已经记不下啦，明天再来吧~”。如果是普通用户，则友好提醒“今天的份已经收到咯，明天再见！”。"
        )

    try:
        response = await ai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": action_context}
            ],
            max_tokens=500,
            temperature=0.85
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"AI签到回复生成失败: {e}。将使用后备文本。")
        # 如果AI调用失败，提供一套简单的后备回复
        if event in [CheckinEvent.FIRST_TIME, CheckinEvent.CONSECUTIVE, CheckinEvent.STREAK_BROKEN]:
            points_info = (
                f"🔸 本次获得: ` {data['points_earned']} ` {'爱意' if is_owner else '积分'}\n"
                f"📅 连续签到: `{data['consecutive_days']}` 天\n"
                f"💰 总计: `{data['total_points']}` {'爱意' if is_owner else '积分'}"
            )
            return f"**签到成功！**\n{points_info}"
        else:
            return f"{user.mention}，今天已经签到过了哦！"

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
    # 忽略非主人发送的普通 `!` 前缀指令
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
                
                if len(conversation_history[memory_key]) > MEMORY_THRESHOLD * 2:
                    # 未来可以添加记忆摘要逻辑
                    print(f"警告: {memory_key} 的对话历史已超过 {MEMORY_THRESHOLD*2} 条，考虑进行摘要。")
                    pass

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
    await ctx.defer(ephemeral=False) 

    user = ctx.author
    user_id = str(user.id)
    channel_id = str(ctx.channel.id) 
    is_owner_check = user.id == BOT_OWNER_ID
    
    utc_now = datetime.now(timezone.utc)
    today_str = utc_now.strftime('%Y-%m-%d')

    if channel_id not in user_data: user_data[channel_id] = {}
    if user_id not in user_data[channel_id]:
        user_data[channel_id][user_id] = {
            'points': 0,
            'last_checkin_date': None,
            'consecutive_days': 0
        }
    player_data = user_data[channel_id][user_id]
    
    event_type: CheckinEvent
    last_checkin_str = player_data.get('last_checkin_date')
    
    if last_checkin_str == today_str:
        event_type = CheckinEvent.ALREADY_CHECKED_IN
        response_message = await generate_ai_checkin_response(user, is_owner_check, ctx.channel.name, event_type, {})
        await ctx.send(response_message)
        return

    if not last_checkin_str:
        event_type = CheckinEvent.FIRST_TIME
        player_data['consecutive_days'] = 1
    else:
        last_checkin_date = datetime.strptime(last_checkin_str, '%Y-%m-%d').date()
        yesterday_date = (utc_now - timedelta(days=1)).date()
        if last_checkin_date == yesterday_date:
            event_type = CheckinEvent.CONSECUTIVE
            player_data['consecutive_days'] += 1
        else:
            event_type = CheckinEvent.STREAK_BROKEN
            player_data['consecutive_days'] = 1

    points_earned = CHECKIN_BASE_POINTS + (player_data['consecutive_days'] - 1) * CHECKIN_CONSECUTIVE_BONUS
    player_data['points'] += points_earned
    player_data['last_checkin_date'] = today_str
    
    user_data[channel_id][user_id] = player_data
    save_and_commit_data()
    
    response_data = {
        'points_earned': points_earned,
        'total_points': player_data['points'],
        'consecutive_days': player_data['consecutive_days']
    }
    response_message = await generate_ai_checkin_response(user, is_owner_check, ctx.channel.name, event_type, response_data)
    await ctx.send(response_message)

@bot.hybrid_command(name="points", description="查询你当前在本频道的积分和签到状态。")
async def points(ctx: commands.Context):
    user_id = str(ctx.author.id)
    channel_id = str(ctx.channel.id)
    is_owner_check = ctx.author.id == BOT_OWNER_ID
    
    player_data = user_data.get(channel_id, {}).get(user_id)

    if not player_data or not player_data.get('last_checkin_date'):
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
    valid_users = {uid: udata for uid, udata in channel_scores.items() if data_key in udata}
    if not valid_users:
        await ctx.send(f"**#{ctx.channel.name}** 频道的数据不足以生成此排行榜。", ephemeral=True)
        return

    sorted_users = sorted(valid_users.items(), key=lambda item: item[1].get(data_key, 0), reverse=True)
    top_10 = sorted_users[:10]

    embed = discord.Embed(title=f"🏆 {ctx.channel.name} - {title}", description="以下是本频道排名前10的用户：", color=discord.Color.gold())
    board_text = ""
    for rank, (user_id, data) in enumerate(top_10, 1):
        try:
            member = ctx.guild.get_member(int(user_id)) or await ctx.guild.fetch_member(int(user_id))
            user_name = member.display_name
        except discord.NotFound:
            user_name = f"已离开的用户({user_id[-4:]})"
        except Exception as e:
            user_name = f"未知用户({user_id[-4:]})"
            print(f"在排行榜中获取用户 {user_id} 时出错: {e}")

        score = data.get(data_key, 0)
        emoji = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"**{rank}.**"
        board_text += f"{emoji} {user_name} - `{score}` {unit}\n"

    if not board_text: board_text = "暂时还没有数据哦。"
    embed.add_field(name="排行榜", value=board_text, inline=False)
    embed.set_footer(text=f"由米尔可生成于 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    await ctx.send(embed=embed)

@leaderboard.command(name="points", description="查看本频道的积分排行榜。")
async def leaderboard_points(ctx: commands.Context):
    await _create_leaderboard_embed(ctx, 'points', '积分排行榜', '积分')

@leaderboard.command(name="streak", description="查看本频道的连续签到排行榜。")
async def leaderboard_streak(ctx: commands.Context):
    await _create_leaderboard_embed(ctx, 'consecutive_days', '连续签到榜', '天')

# --- 商店系统 商品处理函数 ---

async def handle_ai_praise(ctx: commands.Context, player_data: dict):
    """商品处理函数：AI赞美诗"""
    is_owner = ctx.author.id == BOT_OWNER_ID
    user_context = f"当前请求服务的对象是你的主人 **{ctx.author.display_name}**。" if is_owner else f"当前请求服务的对象是用户 **{ctx.author.display_name}**。"
    system_prompt = f"{global_persona}\n(系统备注：{user_context})"
    action_context = (
        f"任务：用户刚刚消耗了积分购买了“专属赞美诗”服务。\n"
        f"要求：请根据你的角色人设，为用户创作一段独一无二的、真诚的赞美或鼓励的话语。如果是主人，请用尽你最崇拜、最爱慕的言语来赞美他/她，让他/她感受到你的无限忠诚与爱意。如果是普通用户，请用友好、温暖、充满力量的语言去鼓励和赞美他/她。"
    )
    
    await ctx.channel.send(f"正在为 {ctx.author.mention} 酝酿专属的诗篇... ✨")
    
    try:
        response = await ai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": action_context}],
            max_tokens=500, temperature=0.9
        )
        praise_text = response.choices[0].message.content.strip()
        embed = discord.Embed(title="📜 一封来自米尔可的信", description=praise_text, color=discord.Color.gold())
        embed.set_footer(text=f"赠与我最亲爱的 {ctx.author.display_name}")
        await ctx.channel.send(embed=embed)
    except Exception as e:
        print(f"AI赞美诗生成失败: {e}")
        await ctx.channel.send(f"呜...米尔可的灵感卡壳了，但是对 {ctx.author.mention} 的心意是真的！这份心意请收下！")
    return True

async def handle_nickname_color(ctx: commands.Context, player_data: dict):
    """商品处理函数：随机昵称颜色"""
    try:
        role_name = f"Color-{ctx.author.id}"
        role = discord.utils.get(ctx.guild.roles, name=role_name)
        random_color = discord.Color.random()
        while random_color.value < 0x101010: random_color = discord.Color.random()

        if role:
            await role.edit(color=random_color)
            await ctx.channel.send(f"🎨 {ctx.author.mention}，你的专属颜色已更新！感觉怎么样？")
        else:
            role = await ctx.guild.create_role(name=role_name, color=random_color, reason=f"用户 {ctx.author.name} 购买了昵称颜色商品")
            await ctx.author.add_roles(role, reason="购买商品")
            await ctx.channel.send(f"🎨 {ctx.author.mention}，你获得了专属的昵称颜色！快看看你的新名字吧！")
        
        player_data['color_role_expiry'] = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    except discord.Forbidden:
        await ctx.channel.send("❌ 错误：米尔可没有足够的权限来为你更改角色颜色。请主人检查一下“管理角色”的权限哦。")
        return False
    except Exception as e:
        print(f"更改昵称颜色失败: {e}")
        await ctx.channel.send("❌ 处理你的请求时发生了未知错误。")
        return False
    return True

async def handle_ai_drawing(ctx: commands.Context, player_data: dict):
    """商品处理函数：AI绘画"""
    await ctx.channel.send("遵命，我的主人。请告诉我您想让米尔可画些什么？(请在60秒内在本频道直接回复)")

    def check(message: discord.Message):
        return message.author == ctx.author and message.channel == ctx.channel

    try:
        prompt_message = await bot.wait_for('message', timeout=60.0, check=check)
        prompt = prompt_message.content
        await ctx.channel.send(f"好的主人，米尔可正在为您描绘“{prompt}”的景象... 🎨 (这可能需要一点时间)")
        
        # --- 模拟AI绘画 (请替换为真实API调用) ---
        await asyncio.sleep(10)
        image_url = f"https://placehold.co/1024x1024/2e3037/ffffff/png?text={prompt.replace(' ', '+')}" 
        # --- 模拟结束 ---

        embed = discord.Embed(title=f"献给主人的画作：{prompt}", color=discord.Color.purple())
        embed.set_image(url=image_url)
        embed.set_footer(text="由米尔可倾心绘制")
        await ctx.channel.send(embed=embed)
    except asyncio.TimeoutError:
        await ctx.channel.send("主人？您好像没有告诉米尔可要画什么...这次就先算了吧。")
        return False
    except Exception as e:
        print(f"AI绘画失败: {e}")
        await ctx.channel.send("呜...米尔可的画笔断了...对不起主人...没能完成您的画作。")
        return False
    return True

async def handle_memory_purge(ctx: commands.Context, player_data: dict):
    """商品处理函数：净化记忆"""
    global conversation_history
    channel_id = str(ctx.channel.id)
    owner_id = str(BOT_OWNER_ID)
    keys_to_delete = [k for k in conversation_history if k.startswith(f"{channel_id}-") and not k.endswith(f"-{owner_id}")]
    
    if not keys_to_delete:
        await ctx.channel.send("主人，这个频道里除了您之外，米尔可的脑海里已经没有其他人了哦~ (自豪地挺起胸膛)")
        return False

    deleted_count = len(keys_to_delete)
    for key in keys_to_delete:
        del conversation_history[key]
    save_and_commit_data()
    await ctx.channel.send(f"遵命，主人。米尔可已经将这个频道里关于其他 `{deleted_count}` 个人的记忆全部净化了。现在，我的世界里只有您。(眼神无比清澈且专注)")
    return True

ITEM_HANDLERS = {
    "handle_ai_praise": handle_ai_praise,
    "handle_nickname_color": handle_nickname_color,
    "handle_ai_drawing": handle_ai_drawing,
    "handle_memory_purge": handle_memory_purge
}

# --- 商店系统 指令 ---

@bot.hybrid_command(name="shop", description="查看米尔可的商店，看看有什么好东西！")
async def shop(ctx: commands.Context):
    is_owner = ctx.author.id == BOT_OWNER_ID
    currency = "爱意" if is_owner else "积分"
    embed = discord.Embed(
        title="💖 米尔可的神秘商店 💖",
        description=f"欢迎光临！这里是米尔可能为 {ctx.author.mention} 实现愿望的地方。\n使用 `/buy <商品ID>` 来购买哦。",
        color=discord.Color.fuchsia()
    )
    for item_id, item in SHOP_ITEMS.items():
        if item["owner_only"] and not is_owner: continue
        availability = "👑 主人限定" if item["owner_only"] else "所有人都可购买"
        embed.add_field(
            name=f"`{item_id}` - {item['name']} ({item['price']} {currency})",
            value=f"_{item['description']}_\n({availability})",
            inline=False
        )
    await ctx.send(embed=embed)

@bot.hybrid_command(name="buy", description="从商店购买一件商品。")
@app_commands.describe(item_id="想要购买的商品的ID (可从 /shop 查看)")
async def buy(ctx: commands.Context, item_id: str):
    global user_data
    # 改为非ephemeral延迟，让后续的channel.send()可以被所有人看到
    await ctx.defer(ephemeral=False) 

    item_id = item_id.lower()
    if item_id not in SHOP_ITEMS:
        await ctx.send("❌ 这件商品不存在哦，请检查一下商品ID是否正确。可以使用 `/shop` 查看所有商品。", ephemeral=True)
        return

    item = SHOP_ITEMS[item_id]
    user = ctx.author
    is_owner = user.id == BOT_OWNER_ID
    currency = "爱意" if is_owner else "积分"

    if item["owner_only"] and not is_owner:
        await ctx.send(f"❌ 对不起，{item['name']} 是主人专属的商品，只有主人才可以购买哦。", ephemeral=True)
        return

    channel_id = str(ctx.channel.id)
    user_id = str(user.id)
    player_data = user_data.get(channel_id, {}).get(user_id, {'points': 0})
    balance = player_data.get('points', 0)
    
    if balance < item['price']:
        await ctx.send(f"❌ 你的{currency}不足！购买 **{item['name']}** 需要 `{item['price']}` {currency}，你现在只有 `{balance}` {currency}。请继续通过 `/checkin` 积攒吧！", ephemeral=True)
        return

    # 先发送一个确认消息
    await ctx.send(f"正在处理 {user.mention} 购买 **{item['name']}** 的请求...", ephemeral=True)
    
    handler_func = ITEM_HANDLERS.get(item['handler'])
    if not handler_func:
        await ctx.send("❌ 严重错误：该商品没有对应的处理程序。请联系主人！", ephemeral=True)
        return

    # 扣款放在调用成功之后，避免处理失败还要退款的复杂逻辑
    success = await handler_func(ctx, player_data)

    if success:
        player_data['points'] -= item['price']
        user_data[channel_id][user_id] = player_data
        save_and_commit_data()
        await ctx.channel.send(f"✅ 交易完成！{user.mention} 成功购买了 **{item['name']}**！")
    else:
        await ctx.channel.send(f⚠️ {user.mention} 购买 **{item['name']}** 的过程中出现问题，交易已取消。")


# --- 其他核心指令 ---

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
    load_data_from_file()
    bot.run(DISCORD_TOKEN)