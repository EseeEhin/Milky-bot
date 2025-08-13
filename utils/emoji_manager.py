# utils/emoji_manager.py
import json
import os
from typing import Dict, Any, List
import aiohttp
import asyncio
import google.generativeai as genai

# --- 常量 ---
DATA_DIR = 'data'
EMOJIS_FILE = os.path.join(DATA_DIR, 'emojis.json')

# --- 内部变量 ---
_emojis_cache: Dict[str, Dict[str, Any]] = {}
_send_dm_to_owner_func = None

# --- 辅助函数 ---
def set_dm_sender(func):
    """设置一个函数，用于向机器人所有者发送DM。"""
    global _send_dm_to_owner_func
    _send_dm_to_owner_func = func

def _ensure_data_dir():
    """确保数据目录存在。"""
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def load_emojis():
    """从 JSON 文件加载表情数据到缓存。"""
    global _emojis_cache
    _ensure_data_dir()
    try:
        if os.path.exists(EMOJIS_FILE):
            with open(EMOJIS_FILE, 'r', encoding='utf-8') as f:
                _emojis_cache = json.load(f)
            print(f"成功从 {EMOJIS_FILE} 加载了 {len(_emojis_cache)} 个表情数据。")
        else:
            _emojis_cache = {}
            print(f"表情文件 {EMOJIS_FILE} 不存在，已初始化为空缓存。")
    except (json.JSONDecodeError, IOError) as e:
        print(f"错误：加载表情文件 {EMOJIS_FILE} 失败: {e}")
        _emojis_cache = {}

def save_emojis():
    """将缓存中的表情数据保存到 JSON 文件。"""
    _ensure_data_dir()
    try:
        with open(EMOJIS_FILE, 'w', encoding='utf-8') as f:
            json.dump(_emojis_cache, f, indent=4, ensure_ascii=False)
        # print(f"已成功将 {len(_emojis_cache)} 个表情数据保存到 {EMOJIS_FILE}。")
    except IOError as e:
        print(f"错误：保存表情文件 {EMOJIS_FILE} 失败: {e}")

# --- 核心功能 ---
async def update_all_emojis(bot):
    """
    遍历机器人所在的所有服务器，更新所有自定义表情的基础信息。
    这会覆盖旧的列表，但会智能地保留已经存在的AI描述。
    """
    global _emojis_cache
    print("正在开始全面更新所有服务器的表情符号...")
    new_emoji_map: Dict[str, Dict[str, Any]] = {}
    total_emojis = 0

    for guild in bot.guilds:
        for emoji in guild.emojis:
            total_emojis += 1
            emoji_id_str = str(emoji.id)
            
            # 从旧缓存中继承AI描述（如果存在）
            existing_description = _emojis_cache.get(emoji_id_str, {}).get('description', None)
            
            new_emoji_map[emoji_id_str] = {
                'id': emoji.id,
                'name': emoji.name,
                'url': str(emoji.url),
                'animated': emoji.animated,
                'guild_id': guild.id,
                'guild_name': guild.name,
                'description': existing_description # 保留旧描述
            }

    _emojis_cache = new_emoji_map
    save_emojis()
    
    update_message = f"表情符号更新完成！共扫描到 {len(bot.guilds)} 个服务器，发现 {total_emojis} 个自定义表情。数据已刷新。"
    print(update_message)
    if _send_dm_to_owner_func:
        await _send_dm_to_owner_func(f"【系统通知】\n{update_message}")


def get_all_emojis() -> Dict[str, Dict[str, Any]]:
    """获取所有表情的数据。"""
    return _emojis_cache

def get_emoji_by_id(emoji_id: int) -> Dict[str, Any] | None:
    """通过ID获取单个表情的数据。"""
    return _emojis_cache.get(str(emoji_id))

def update_emoji_description(emoji_id: int, description: str) -> bool:
    """
    为指定的表情手动更新或添加描述。
    """
    emoji_id_str = str(emoji_id)
    if emoji_id_str in _emojis_cache:
        _emojis_cache[emoji_id_str]['description'] = description
        save_emojis()
        return True
    return False

async def generate_descriptions_for_guild(guild_id: int, on_progress, on_completion, on_no_work, on_error):
    """
    为指定服务器中所有尚无描述的表情生成AI描述，并通过回调函数报告进度。
    """
    all_guild_emojis = {
        eid: edata for eid, edata in _emojis_cache.items()
        if edata.get('guild_id') == guild_id
    }
    
    target_emojis_to_process = {
        eid: edata for eid, edata in all_guild_emojis.items()
        if not edata.get('description')
    }

    if not target_emojis_to_process:
        await on_no_work()
        return

    total_to_process = len(target_emojis_to_process)
    processed_count = 0
    
    async with aiohttp.ClientSession() as session:
        for emoji_id, emoji_data in target_emojis_to_process.items():
            processed_count += 1
            
            try:
                # 1. 报告当前进度
                await on_progress(processed_count, total_to_process, emoji_data['name'])

                # 2. 下载图片
                async with session.get(emoji_data['url']) as response:
                    if response.status != 200:
                        error_msg = f"下载表情图片失败: {emoji_data['name']} (HTTP {response.status})"
                        print(f"  ❌ {error_msg}")
                        await on_error(error_msg)
                        continue
                    image_bytes = await response.read()

                # 3. 调用AI进行识图
                description = await _describe_image_with_gemini(image_bytes)

                if description:
                    _emojis_cache[emoji_id]['description'] = description
                    print(f"  ✔️ 成功生成描述: {emoji_data['name']} -> {description[:30]}...")
                else:
                    error_msg = f"未能为表情 {emoji_data['name']} 生成描述。"
                    print(f"  ⚠️ {error_msg}")
                    await on_error(error_msg)

                # 4. 保存进度并等待
                save_emojis()
                await asyncio.sleep(1.5) # 遵守API调用频率限制

            except Exception as e:
                error_msg = f"处理表情 {emoji_data['name']} 时发生未知错误: {e}"
                print(f"  ❌ {error_msg}")
                await on_error(error_msg)
                continue
    
    # 5. 报告最终完成情况
    await on_completion(processed_count, len(all_guild_emojis))


async def _describe_image_with_gemini(image_bytes: bytes) -> str | None:
    """使用Gemini Pro Vision模型描述图片内容。"""
    from . import ai_utils # 局部导入，解决循环依赖
    try:
        # 复用 ai_utils 中的 key 管理和模型名称
        api_key = ai_utils.GEMINI_API_KEYS[ai_utils.current_gemini_key_index]
        genai.configure(api_key=api_key)
        
        model = genai.GenerativeModel(model_name='gemini-1.5-pro-latest') # 使用支持视觉的模型
        
        prompt = "你是一个表情符号分析专家。请用非常简洁的、不超过15个字的中文短语来描述这个表情图片。请聚焦于表情传达的核心情绪、动作或物品，例如：'开心地跳跃'、'尴尬地微笑'、'愤怒地挥拳'、'一个美味的汉堡'。你的描述将用于指导AI在对话中正确使用这个表情。请直接给出描述，不要说任何额外的话。"
        
        image_part = {"mime_type": "image/png", "data": image_bytes}
        
        response = await model.generate_content_async([prompt, image_part])
        
        # 轮换key
        ai_utils.current_gemini_key_index = (ai_utils.current_gemini_key_index + 1) % len(ai_utils.GEMINI_API_KEYS)
        
        if response.candidates and response.text:
            return response.text.strip()
        return None
    except Exception as e:
        print(f"Gemini Vision API 调用失败: {e}")
        # 发生错误时也轮换key
        ai_utils.current_gemini_key_index = (ai_utils.current_gemini_key_index + 1) % len(ai_utils.GEMINI_API_KEYS)
        return None


# --- 初始化 ---
load_emojis()