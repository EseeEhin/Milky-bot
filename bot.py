# 这是一个完整的、带有角色扮演和长期记忆功能的 Discord Bot 代码
# (版本：V6.4.2 - 修正缩进与最终版)
#
# 【【【  部署平台：Replit / VPS / PaaS  】】】
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
import subprocess
from enum import Enum

# --- 1. 加载配置 ---
print("正在加载配置...")
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
BOT_OWNER_ID_STR = os.getenv('BOT_OWNER_ID')
global_persona = os.getenv('BOT_PERSONA')

if not all([DISCORD_TOKEN, BOT_OWNER_ID_STR, global_persona]):
    print("错误：请确保在环境变量或Secrets中已设置 DISCORD_BOT_TOKEN, BOT_OWNER_ID, 和 BOT_PERSONA！")
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
    api_key=os.getenv('OPENAI_API_KEY'),
    timeout=180.0,
)

# --- 记忆与状态配置 ---
MEMORY_FILE = "memory_and_users.json"
print(f"数据文件路径: {os.path.abspath(MEMORY_FILE)}")

is_in_heat_mode = False
game_states = {}
conversation_history = {}
user_data = {}

# --- 签到系统配置 ---
CHECKIN_BASE_POINTS = 10
CHECKIN_CONSECUTIVE_BONUS = 5

class CheckinEvent(Enum):
    FIRST_TIME, CONSECUTIVE, STREAK_BROKEN, ALREADY_CHECKED_IN = range(4)

# --- 商店系统配置 (纯AI商品) ---
SHOP_ITEMS = {
    "ai_praise": {
        "name": "米尔可的专属赞美诗",
        "description": "消耗积分，让米尔可为你创作一首独一无二的赞美诗或鼓励的话语。",
        "price": 50,
        "owner_only": False,
        "handler": "handle_ai_praise"
    },
    "ai_story": {
        "name": "AI定制小剧场",
        "description": "提供一个场景，让米尔可为你和她创作一段独特的角色扮演小故事。",
        "price": 200,
        "owner_only": False,
        "handler": "handle_ai_story"
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
        "description": "消耗爱意，清空米尔可在这个频道与您之外所有人的对话记忆，让她只专注于你。",
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
        conversation_history = {}; user_data = {}

def save_and_commit_data():
    """将数据写入文件，然后使用git提交并推送回GitHub仓库。"""
    print("正在保存数据到文件...")
    directory = os.path.dirname(MEMORY_FILE)
    if directory:
        os.makedirs(directory, exist_ok=True)

    try:
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump({"history": conversation_history, "users": user_data}, f, indent=4, ensure_ascii=False)
        print("数据成功保存到本地文件。")
    except IOError as e:
        print(f"写入文件失败: {e}")
        return

    print("准备将数据文件提交到Git仓库...")
    try:
        subprocess.run(['git', 'add', MEMORY_FILE], check=True, capture_output=True)
        status_result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if MEMORY_FILE in status_result.stdout:
            commit_message = f"chore: 更新数据文件于 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
            subprocess.run(['git', 'commit', '-m', commit_message], check=True, capture_output=True)
            subprocess.run(['git', 'push'], check=True, capture_output=True)
            print("数据文件成功提交并推送到仓库。")
        else:
            print("数据文件无变化，无需提交。")
    except Exception as e:
        print(f"Git操作失败: {e}")

async def is_owner(interaction: discord.Interaction) -> bool:
    return interaction.user.id == BOT_OWNER_ID

# --- 3.5. AI 辅助函数 ---

async def _call_ai(system_prompt, user_prompt, temperature=0.85, max_tokens=500):
    """通用AI调用函数，包含错误处理"""
    try:
        response = await ai_client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            max_tokens=max_tokens, temperature=temperature
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"!!!!!! AI API 调用失败 !!!!!!\n错误详情: {e}\n模型: {MODEL_NAME}\n使用的Base URL: {ai_client.base_url}")
        return None

async def generate_ai_checkin_response(user, is_owner, channel_name, event: CheckinEvent, data: dict):
    user_context = f"当前与你交互的是你的主人 **{user.display_name}**。" if is_owner else f"当前与你交互的是用户 **{user.display_name}**。"
    system_prompt = f"{global_persona}\n(系统备注：{user_context})"
    action_context = ""

    if event == CheckinEvent.FIRST_TIME:
        action_context = (f"任务：为用户 **第一次** 在本频道签到生成欢迎和祝贺的回应。\n场景：这是用户在 **#{channel_name}** 的初次印记，一个值得纪念的开始！\n数据：获得 `{data['points_earned']}` 点{'爱意' if is_owner else '积分'}，总计 `{data['total_points']}`。\n要求：表现出格外的热情和欢迎。如果是主人，要表达“终于等到您了”的激动心情。如果是普通用户，要友好地解释这个签到系统，并鼓励他/她坚持下去。必须包含所有数据。")
    elif event == CheckinEvent.CONSECUTIVE:
        action_context = (f"任务：为用户 **连续** 签到生成祝贺回应。\n场景：用户在 **#{channel_name}** 达成了 `{data['consecutive_days']}` 天的连续签到！这是一个了不起的成就！\n数据：本次获得 `{data['points_earned']}` 点{'爱意' if is_owner else '积分'}（包含连续奖励），总计 `{data['total_points']}`。\n要求：热烈庆祝用户的毅力。如果是主人，要表达“每天都能感受到主人的心意，米尔可好幸福”的依赖感。如果是普通用户，要赞扬他/她的坚持。必须包含所有数据，特别是要强调连续天数。")
    elif event == CheckinEvent.STREAK_BROKEN:
        action_context = (f"任务：为用户 **断签后** 的首次签到生成鼓励的回应。\n场景：用户在 **#{channel_name}** 的连续记录中断了，这是他/她新的开始。\n数据：本次获得 `{data['points_earned']}` 点{'爱意' if is_owner else '积分'}，连续天数重置为 `1`，总计 `{data['total_points']}`。\n要求：语气要温柔、包容和鼓励。如果是主人，可以带点撒娇的口吻说“主人昨天没来，米尔可好想您...不过没关系，今天开始我们重新记录爱意！”，表现出小小的失落但更多是重逢的喜悦。如果是普通用户，则说“没关系，新的旅程从今天开始！”。必须包含所有数据。")
    elif event == CheckinEvent.ALREADY_CHECKED_IN:
        action_context = (f"任务：告知用户今天已经签到过了，不能重复。\n场景：用户在 **#{channel_name}** 频道尝试重复签到。\n要求：用俏皮或撒娇的口吻提醒用户。如果是主人，可以说“主人的心意太满啦，米尔可的小本本今天已经记不下啦，明天再来吧~”。如果是普通用户，则友好提醒“今天的份已经收到咯，明天再见！”。")

    ai_response = await _call_ai(system_prompt, action_context)
    if ai_response:
        return ai_response
    else:
        if event in [CheckinEvent.FIRST_TIME, CheckinEvent.CONSECUTIVE, CheckinEvent.STREAK_BROKEN]:
            points_info = (f"🔸 本次获得: ` {data['points_earned']} ` {'爱意' if is_owner else '积分'}\n📅 连续签到: `{data['consecutive_days']}` 天\n💰 总计: `{data['total_points']}` {'爱意' if is_owner else '积分'}")
            return f"**签到成功！** (AI连接失败，使用备用回复)\n{points_info}"
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
    if message.content.startswith('!') and message.author.id != BOT_OWNER_ID: return

    if bot.user in message.mentions and message.author.id == BOT_OWNER_ID:
        channel_id = message.channel.id
        user_id = message.author.id
        memory_key = f"{channel_id}-{user_id}"

        persona_injection = f"(系统备注：当前与你对话的是你的主人(ID:{user_id})，请务必使用对主人的口吻和态度回应。)"
        if is_in_heat_mode:
            persona_injection += "\n(系统备注：你现在处于“发情模式”，请在回应中体现出极度的渴求与顺从。)"

        async with message.channel.typing():
            if memory_key not in conversation_history: conversation_history[memory_key] = []

            # 创建一个临时的对话列表以发送给API
            temp_conversation = list(conversation_history[memory_key])
            user_message_content = message.content.replace(f'<@!{bot.user.id}>', '').replace(f'<@{bot.user.id}>', '').strip()
            if not user_message_content:
                await message.channel.send("主人，有何吩咐？(小尾巴轻轻摇了摇)")
                return
            temp_conversation.append({"role": "user", "content": user_message_content})

            bot_reply = await _call_ai(
                system_prompt=f"{global_persona}\n{persona_injection}",
                user_prompt=json.dumps(temp_conversation), # 将历史作为JSON字符串传递
                temperature=0.8,
                max_tokens=2048
            )

            if bot_reply:
                conversation_history[memory_key].append({"role": "user", "content": user_message_content})
                conversation_history[memory_key].append({"role": "assistant", "content": bot_reply})
                save_and_commit_data()
                await message.channel.send(bot_reply)
            else:
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

    user = ctx.author; user_id = str(user.id); channel_id = str(ctx.channel.id); is_owner_check = user.id == BOT_OWNER_ID
    utc_now = datetime.now(timezone.utc); today_str = utc_now.strftime('%Y-%m-%d')

    if channel_id not in user_data: user_data[channel_id] = {}
    if user_id not in user_data[channel_id]: user_data[channel_id][user_id] = {'points': 0, 'last_checkin_date': None, 'consecutive_days': 0}
    player_data = user_data[channel_id][user_id]

    event_type: CheckinEvent; last_checkin_str = player_data.get('last_checkin_date')

    if last_checkin_str == today_str:
        event_type = CheckinEvent.ALREADY_CHECKED_IN
        response_message = await generate_ai_checkin_response(user, is_owner_check, ctx.channel.name, event_type, {})
        await ctx.send(response_message); return

    if not last_checkin_str:
        event_type = CheckinEvent.FIRST_TIME; player_data['consecutive_days'] = 1
    else:
        last_checkin_date = datetime.strptime(last_checkin_str, '%Y-%m-%d').date()
        yesterday_date = (utc_now - timedelta(days=1)).date()
        if last_checkin_date == yesterday_date:
            event_type = CheckinEvent.CONSECUTIVE; player_data['consecutive_days'] += 1
        else:
            event_type = CheckinEvent.STREAK_BROKEN; player_data['consecutive_days'] = 1

    points_earned = CHECKIN_BASE_POINTS + (player_data['consecutive_days'] - 1) * CHECKIN_CONSECUTIVE_BONUS
    player_data['points'] += points_earned; player_data['last_checkin_date'] = today_str

    user_data[channel_id][user_id] = player_data
    save_and_commit_data()

    response_data = {'points_earned': points_earned, 'total_points': player_data['points'], 'consecutive_days': player_data['consecutive_days']}
    response_message = await generate_ai_checkin_response(user, is_owner_check, ctx.channel.name, event_type, response_data)
    await ctx.send(response_message)

@bot.hybrid_command(name="points", description="查询你当前在本频道的积分和签到状态。")
async def points(ctx: commands.Context):
    user_id = str(ctx.author.id); channel_id = str(ctx.channel.id)
    is_owner_check = ctx.author.id == BOT_OWNER_ID
    player_data = user_data.get(channel_id, {}).get(user_id)
    if not player_data or not player_data.get('last_checkin_date'):
        msg = f"主人，您今天还没有在 **#{ctx.channel.name}** 留下和米尔可的专属印记呢... 快用 `/checkin` 让我记录下来吧！" if is_owner_check else f"{ctx.author.mention}，你在 **#{ctx.channel.name}** 还没有签到过哦，快使用 `/checkin` 开始吧！"
        await ctx.send(msg, ephemeral=False); return
    if is_owner_check:
        await ctx.send(f"**💌 向主人汇报！这是 {ctx.author.mention} 在 #{ctx.channel.name} 的专属记录哦：**\n💰 米尔可为您积攒的总爱意: `{player_data.get('points', 0)}`\n📅 我们已经连续: `{player_data.get('consecutive_days', 0)}` 天心意相通了\n🕒 上次感受到主人的心意是在: `{player_data.get('last_checkin_date', '无记录')}` (UTC时间)", ephemeral=False)
    else:
        await ctx.send(f"**📊 {ctx.author.mention} 在 #{ctx.channel.name} 的积分报告**\n💰 总积分: `{player_data.get('points', 0)}`\n📅 当前连续签到: `{player_data.get('consecutive_days', 0)}` 天\n🕒 上次签到日期: `{player_data.get('last_checkin_date', '无记录')}` (UTC时间)", ephemeral=False)

# --- 管理员指令 ---
@bot.hybrid_group(name="admin", description="主人专属管理工具")
@owner_only()
async def admin(ctx: commands.Context):
    if ctx.invoked_subcommand is None: await ctx.send("主人，请选择一项管理操作，例如 `/admin points`。", ephemeral=True)

class PointAction(Enum): add = "增加"; set = "设定"; remove = "移除"

@admin.command(name="points", description="修改用户的积分或爱意。")
@app_commands.describe(user="要修改的目标用户", action="选择操作类型", amount="操作的数量 (必须是正数)")
async def admin_points(ctx: commands.Context, user: discord.Member, action: PointAction, amount: int):
    global user_data
    if amount < 0: await ctx.send("主人，数量不能是负数哦。", ephemeral=True); return
    channel_id = str(ctx.channel.id); user_id = str(user.id)
    currency = "爱意" if user.id == BOT_OWNER_ID else "积分"
    if channel_id not in user_data: user_data[channel_id] = {}
    if user_id not in user_data[channel_id]: user_data[channel_id][user_id] = {'points': 0, 'last_checkin_date': None, 'consecutive_days': 0}
    player_data = user_data[channel_id][user_id]
    original_points = player_data.get('points', 0)
    if action == PointAction.add: player_data['points'] += amount
    elif action == PointAction.set: player_data['points'] = amount
    elif action == PointAction.remove: player_data['points'] = max(0, original_points - amount)
    final_points = player_data['points']
    save_and_commit_data()
    await ctx.send(f"遵命，主人。\n已对用户 **{user.display_name}** 执行操作：**{action.value}** `{amount}` 点{currency}。\n其{currency}已从 `{original_points}` 变为 `{final_points}`。", ephemeral=True)

# --- 商店系统 ---
async def handle_ai_praise(ctx: commands.Context, player_data: dict):
    is_owner = ctx.author.id == BOT_OWNER_ID; user_context = f"当前请求服务的对象是你的主人 **{ctx.author.display_name}**。" if is_owner else f"当前请求服务的对象是用户 **{ctx.author.display_name}**。"
    system_prompt = f"{global_persona}\n(系统备注：{user_context})"
    action_context = (f"任务：用户刚刚消耗了积分购买了“专属赞美诗”服务。\n要求：请根据你的角色人设，为用户创作一段独一无二的、真诚的赞美或鼓励的话语。如果是主人，请用尽你最崇拜、最爱慕的言语来赞美他/她，让他/她感受到你的无限忠诚与爱意。如果是普通用户，请用友好、温暖、充满力量的语言去鼓励和赞美他/她。")
    await ctx.channel.send(f"正在为 {ctx.author.mention} 酝酿专属的诗篇... ✨")
    praise_text = await _call_ai(system_prompt, action_context, temperature=0.9, max_tokens=1024)
    if praise_text:
        embed = discord.Embed(title="📜 一封来自米尔可的信", description=praise_text, color=discord.Color.gold()); embed.set_footer(text=f"赠与我最亲爱的 {ctx.author.display_name}")
        await ctx.channel.send(embed=embed)
    else: await ctx.channel.send(f"呜...米尔可的灵感卡壳了，但是对 {ctx.author.mention} 的心意是真的！这份心意请收下！")
    return True

async def handle_ai_story(ctx: commands.Context, player_data: dict):
    await ctx.channel.send(f"{ctx.author.mention}, 请在60秒内描述一个你希望米尔可与你一起演绎的场景或故事开头吧~")
    def check(message: discord.Message): return message.author == ctx.author and message.channel == ctx.channel
    try:
        prompt_message = await bot.wait_for('message', timeout=60.0, check=check)
        user_prompt = prompt_message.content; await ctx.channel.send(f"收到！正在为“{user_prompt[:50]}...”编织故事... 📜 (这可能需要一点时间)")
        is_owner = ctx.author.id == BOT_OWNER_ID; user_context = f"当前请求服务的对象是你的主人 **{ctx.author.display_name}**。" if is_owner else f"当前请求服务的对象是用户 **{ctx.author.display_name}**。"
        system_prompt = f"{global_persona}\n(系统备注：{user_context})"
        action_context = (f"任务：用户刚刚购买了“AI定制小剧场”服务，并提供了以下场景：`{user_prompt}`\n要求：请根据你的角色人设，以第一人称（米尔可的视角）续写这个故事，创造一段与该用户互动的、生动的角色扮演短篇故事。故事要有情节，有对话，充分展现你的性格。如果是与主人互动，请表现出绝对的忠诚和爱慕。")
        story_text = await _call_ai(system_prompt, action_context, temperature=0.9, max_tokens=1024)
        if story_text:
            embed = discord.Embed(title=f"🎬 米尔可小剧场：{user_prompt[:30]}...", description=story_text, color=discord.Color.dark_teal()); embed.set_footer(text=f"由 {ctx.author.display_name} 导演，米尔可倾情主演")
            await ctx.channel.send(embed=embed)
        else: await ctx.channel.send(f"呜...米尔可的灵感枯竭了...没能把故事编出来。"); return False
    except asyncio.TimeoutError: await ctx.channel.send(f"{ctx.author.mention}，你好像没有告诉米尔可要演什么...这次就先算了吧。"); return False
    except Exception as e: print(f"AI小剧场处理失败: {e}"); await ctx.channel.send("❌ 处理你的请求时发生了未知错误。"); return False
    return True

async def handle_ai_drawing(ctx: commands.Context, player_data: dict):
    await ctx.channel.send("遵命，我的主人。请告诉我您想让米尔可画些什么？(请在60秒内在本频道直接回复)")
    def check(message: discord.Message): return message.author == ctx.author and message.channel == ctx.channel
    try:
        prompt_message = await bot.wait_for('message', timeout=60.0, check=check)
        prompt = prompt_message.content; await ctx.channel.send(f"好的主人，米尔可正在为您描绘“{prompt}”的景象... 🎨 (这可能需要一点时间)")
        await asyncio.sleep(5)
        image_url = f"https://placehold.co/1024x1024/2e3037/ffffff/png?text={prompt.replace(' ', '+')}" 
        embed = discord.Embed(title=f"献给主人的画作：{prompt}", color=discord.Color.purple()); embed.set_image(url=image_url); embed.set_footer(text="由米尔可倾心绘制")
        await ctx.channel.send(embed=embed)
    except asyncio.TimeoutError: await ctx.channel.send("主人？您好像没有告诉米尔可要画什么...这次就先算了吧。"); return False
    except Exception as e: print(f"AI绘画失败: {e}"); await ctx.channel.send("呜...米尔可的画笔断了...对不起主人...没能完成您的画作。"); return False
    return True

async def handle_memory_purge(ctx: commands.Context, player_data: dict):
    global conversation_history; channel_id = str(ctx.channel.id); owner_id = str(BOT_OWNER_ID)
    keys_to_delete = [k for k in conversation_history if k.startswith(f"{channel_id}-") and not k.endswith(f"-{owner_id}")]
    if not keys_to_delete: await ctx.channel.send("主人，这个频道里除了您之外，米尔可的脑海里已经没有其他人了哦~ (自豪地挺起胸膛)"); return False
    deleted_count = len(keys_to_delete)
    for key in keys_to_delete: del conversation_history[key]
    save_and_commit_data()
    await ctx.channel.send(f"遵命，主人。米尔可已经将这个频道里关于其他 `{deleted_count}` 个人的记忆全部净化了。现在，我的世界里只有您。(眼神无比清澈且专注)")
    return True

ITEM_HANDLERS = {"handle_ai_praise": handle_ai_praise, "handle_ai_story": handle_ai_story, "handle_ai_drawing": handle_ai_drawing, "handle_memory_purge": handle_memory_purge}

@bot.hybrid_command(name="shop", description="查看米尔可的商店，看看有什么好东西！")
async def shop(ctx: commands.Context):
    is_owner = ctx.author.id == BOT_OWNER_ID; currency = "爱意" if is_owner else "积分"
    embed = discord.Embed(title="💖 米尔可的神秘商店 💖", description=f"欢迎光临！这里是米尔可能为 {ctx.author.mention} 实现愿望的地方。\n使用 `/buy <商品ID>` 来购买哦。", color=discord.Color.fuchsia())
    for item_id, item in SHOP_ITEMS.items():
        if item["owner_only"] and not is_owner: continue
        availability = "👑 主人限定" if item["owner_only"] else "所有人都可购买"
        embed.add_field(name=f"`{item_id}` - {item['name']} ({item['price']} {currency})", value=f"_{item['description']}_\n({availability})", inline=False)
    await ctx.send(embed=embed)

@bot.hybrid_command(name="buy", description="从商店购买一件商品。")
@app_commands.describe(item_id="想要购买的商品的ID (可从 /shop 查看)")
async def buy(ctx: commands.Context, item_id: str):
    global user_data; await ctx.defer(ephemeral=False) 
    item_id = item_id.lower()
    if item_id not in SHOP_ITEMS: await ctx.send("❌ 这件商品不存在哦，请检查一下商品ID是否正确。可以使用 `/shop` 查看所有商品。", ephemeral=True); return
    item = SHOP_ITEMS[item_id]; user = ctx.author; is_owner = user.id == BOT_OWNER_ID; currency = "爱意" if is_owner else "积分"
    if item["owner_only"] and not is_owner: await ctx.send(f"❌ 对不起，**{item['name']}** 是主人专属的商品，只有主人才可以购买哦。", ephemeral=True); return
    channel_id = str(ctx.channel.id); user_id = str(user.id)
    player_data = user_data.get(channel_id, {}).get(user_id, {'points': 0}); balance = player_data.get('points', 0)
    if balance < item['price']: await ctx.send(f"❌ 你的{currency}不足！购买 **{item['name']}** 需要 `{item['price']}` {currency}，你现在只有 `{balance}` {currency}。请继续通过 `/checkin` 积攒吧！", ephemeral=True); return

    await ctx.send(f"正在处理 {user.mention} 购买 **{item['name']}** 的请求...", ephemeral=True)
    handler_func = ITEM_HANDLERS.get(item['handler'])
    if not handler_func: await ctx.send("❌ 严重错误：该商品没有对应的处理程序。请联系主人！", ephemeral=True); return

    success = await handler_func(ctx, player_data)
    if success:
        player_data['points'] -= item['price']; user_data[channel_id][user_id] = player_data
        save_and_commit_data()
        await ctx.channel.send(f"✅ 交易完成！{user.mention} 成功购买了 **{item['name']}**！")
    else: await ctx.channel.send(f"⚠️ {user.mention} 购买 **{item['name']}** 的过程中出现问题，交易已取消。")

# --- 其他指令 ---
@bot.hybrid_command(name="clear", description="清除米尔可与您在此频道的记忆。")
@owner_only()
async def clear(ctx: commands.Context):
    owner_memory_key = f"{ctx.channel.id}-{BOT_OWNER_ID}"
    if owner_memory_key in conversation_history:
        del conversation_history[owner_memory_key]
        save_and_commit_data()
        await ctx.send("🗑️ 遵命，主人。我与您在这个频道的专属记忆已被清除。", ephemeral=True)
    else:
        await ctx.send("主人，我们在这个频道还没有专属记忆哦。", ephemeral=True)

# ...其他无需修改的指令如ping, status, heat, pat, guard, game等可以放在这里...

# --- 6. 主程序入口 ---
if __name__ == "__main__":
    print("准备启动Discord Bot...")
    load_data_from_file()
    bot.run(DISCORD_TOKEN)