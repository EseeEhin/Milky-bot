# bot.py
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import threading
from flask import Flask, request, redirect, url_for

# --- 加载配置 ---
load_dotenv()

from utils import data_manager, ai_utils, emoji_manager
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
bot = commands.Bot(command_prefix=[], intents=intents, help_command=None)

# --- Flask 管理面板 ---
FLASK_PORT = int(os.getenv("PORT", 7861))
health_check_app = Flask(__name__)

# --- 辅助函数 ---
def get_current_bot_config():
    """获取当前机器人配置用于网页显示"""
    return {
        "bot_mode": data_manager.get_bot_mode(),
        "system_prompt": data_manager.get_system_prompt(),
        "start_prompt": data_manager.get_start_prompt(),
        "end_prompt": data_manager.get_end_prompt(),
        "personas": data_manager.get_personas(),
        "active_persona": data_manager.get_active_persona(),
        "word_count_request": data_manager.get_word_count_request(),
    }

@health_check_app.route('/')
def health_check():
    if bot.is_ready() and not bot.is_closed():
        return "Milky is awake, connected, and guarding her master.", 200
    return "Milky is connecting or in an unknown state with Discord.", 503

@health_check_app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if request.method == 'POST':
        # 所有POST请求都通过这个异步处理器来执行，以避免同步/异步冲突
        future = asyncio.run_coroutine_threadsafe(handle_admin_post(request.form), bot.loop)
        future.result()  # 等待操作完成，以确保数据保存后再重定向
        return redirect(url_for('admin_panel'))

    # GET 请求，显示页面
    config = get_current_bot_config()
    
    # 构建人格选项
    persona_options = ''.join([f'<option value="{name}" {"selected" if config["active_persona"] == name else ""}>{name}</option>' for name in config['personas']])
    
    # 构建人格管理区域
    persona_management_html = ''
    for name, content in config['personas'].items():
        persona_management_html += f'''
        <div class="persona-editor">
            <form method="post" style="display: inline;">
                <input type="hidden" name="action" value="save_persona">
                <input type="text" name="persona_name" value="{name}" readonly>
                <textarea name="persona_content" rows="5">{content}</textarea>
                <button type="submit">保存此人格</button>
            </form>
            <form method="post" style="display: inline;">
                <input type="hidden" name="action" value="delete_persona">
                <input type="hidden" name="persona_name" value="{name}">
                <button type="submit" class="delete-btn">删除此人格</button>
            </form>
        </div>
        '''

    return f'''
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <title>Milky Bot 管理面板</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 2em; background-color: #f4f4f9; color: #333; }}
            .container {{ max-width: 900px; margin: auto; background: #fff; padding: 2em; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            h1, h2 {{ color: #5a67d8; border-bottom: 2px solid #eaeaea; padding-bottom: 0.5em;}}
            .form-group {{ margin-bottom: 1.5em; }}
            label {{ display: block; margin-bottom: 0.5em; font-weight: bold; color: #4a5568; }}
            textarea, select, input[type="text"] {{ width: 100%; padding: 0.8em; border: 1px solid #cbd5e0; border-radius: 4px; box-sizing: border-box; font-size: 1em; }}
            button {{ background-color: #5a67d8; color: white; padding: 0.8em 1.5em; border: none; border-radius: 4px; cursor: pointer; font-size: 1em; transition: background-color 0.2s; margin-top: 0.5em;}}
            button:hover {{ background-color: #434190; }}
            .delete-btn {{ background-color: #e53e3e; }}
            .delete-btn:hover {{ background-color: #c53030; }}
            .info-box {{ background-color: #e2e8f0; padding: 1em; border-radius: 5px; margin-bottom: 2em; }}
            .persona-editor {{ border: 1px solid #ddd; padding: 1em; margin-bottom: 1em; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Milky Bot 管理面板</h1>
            
            <div class="info-box">
                <h2>提示词组合顺序</h2>
                <p>最终发送给 AI 的提示词将按照以下顺序组合：</p>
                <ol>
                    <li><b>系统提示词 (System Prompt)</b>: 定义 AI 的基本角色和行为准则。</li>
                    <li><b>当前人格 (Active Persona)</b>: 从下方选择的已保存的人格内容。</li>
                    <li><b>起始提示词 (Start Prompt)</b>: 在用户消息前添加的固定内容。</li>
                    <li><b>用户消息 (User Message)</b>: 用户实际发送的消息。</li>
                    <li><b>结束提示词 (End Prompt)</b>: 在用户消息后添加的固定内容。</li>
                </ol>
            </div>

            <form method="post">
                <input type="hidden" name="action" value="save_prompts">
                <h2>核心设置</h2>
                <div class="form-group">
                    <label for="bot_mode">机器人模式:</label>
                    <select id="bot_mode" name="bot_mode">
                        <option value="chat" {'selected' if config['bot_mode'] == 'chat' else ''}>标准聊天</option>
                        <option value="dev" {'selected' if config['bot_mode'] == 'dev' else ''}>开发者模式</option>
                    </select>
                </div>
                <div class="form-group">
                    <label for="active_persona">当前激活人格:</label>
                    <select id="active_persona" name="active_persona">
                        <option value="">无</option>
                        {persona_options}
                    </select>
                </div>
                <div class="form-group">
                    <label for="system_prompt">系统提示词 (System Prompt):</label>
                    <textarea id="system_prompt" name="system_prompt" rows="6">{config['system_prompt']}</textarea>
                </div>
                <div class="form-group">
                    <label for="start_prompt">起始提示词 (Start Prompt):</label>
                    <textarea id="start_prompt" name="start_prompt" rows="4">{config['start_prompt']}</textarea>
                </div>
                <div class="form-group">
                    <label for="end_prompt">结束提示词 (End Prompt):</label>
                    <textarea id="end_prompt" name="end_prompt" rows="4">{config['end_prompt']}</textarea>
                </div>
                <div class="form-group">
                    <label for="word_count_request">字数要求 (Word Count Request):</label>
                    <input type="text" id="word_count_request" name="word_count_request" value="{config['word_count_request']}" placeholder="例如: 200字, 一段话">
                </div>
                <button type="submit">保存核心设置</button>
            </form>

            <hr style="margin: 3em 0;">

            <h2>人格管理</h2>
            {persona_management_html}
            
            <h3>新增人格</h3>
            <div class="persona-editor">
                <form method="post">
                    <input type="hidden" name="action" value="save_persona">
                    <div class="form-group">
                        <label for="new_persona_name">新人格名称:</label>
                        <input type="text" id="new_persona_name" name="persona_name" placeholder="例如：小助手">
                    </div>
                    <div class="form-group">
                        <label for="new_persona_content">新人格内容:</label>
                        <textarea id="new_persona_content" name="persona_content" rows="5" placeholder="你是一个乐于助人的助手..."></textarea>
                    </div>
                    <button type="submit">添加新人格</button>
                </form>
            </div>
        </div>
    </body>
    </html>
    '''

async def handle_admin_post(form_data):
    """在bot的事件循环中处理来自web面板的POST请求"""
    action = form_data.get('action')
    
    if action == 'save_prompts':
        await data_manager.set_bot_mode(form_data.get('bot_mode', 'chat'))
        await data_manager.set_system_prompt(form_data.get('system_prompt', ''))
        await data_manager.set_start_prompt(form_data.get('start_prompt', ''))
        await data_manager.set_end_prompt(form_data.get('end_prompt', ''))
        await data_manager.set_active_persona(form_data.get('active_persona', ''))
        await data_manager.set_word_count_request(form_data.get('word_count_request', ''))

    elif action == 'save_persona':
        persona_name = form_data.get('persona_name')
        persona_content = form_data.get('persona_content')
        if persona_name:
            await data_manager.set_persona(persona_name, persona_content)
            
    elif action == 'delete_persona':
        persona_name = form_data.get('persona_name')
        if persona_name:
            await data_manager.remove_persona(persona_name)

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
    emoji_manager.set_dm_sender(_send_dm_to_owner)

    # 加载持久化数据
    data_manager.load_data_from_hf()
    # emoji_manager 已在导入时自动加载
    
    async with bot:
        print("\n--- 正在加载功能模块 (Cogs) ---")
        # 动态加载所有 cogs
        cogs_dir = os.path.join(os.path.dirname(__file__), 'cogs')
        for filename in os.listdir(cogs_dir):
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
    
    # 更新所有表情
    await emoji_manager.update_all_emojis(bot)
    
    print("米尔可准备就绪！")

@bot.event
async def on_guild_emojis_update(guild, before, after):
    """当服务器的表情符号更新时，重新同步所有表情。"""
    print(f"检测到服务器 '{guild.name}' 的表情符号发生变化，将触发全体更新...")
    await emoji_manager.update_all_emojis(bot)

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
