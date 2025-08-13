# utils/data_manager.py
import os
os.environ["HF_HOME"] = "/tmp/hf_cache"
import json
import tempfile
from huggingface_hub import hf_hub_download, upload_file
from huggingface_hub.errors import HfHubHTTPError, RepositoryNotFoundError
from datetime import datetime, timezone
import asyncio

# 全局数据字典
data = {
    "user_data": {},
    "autoreact_map": {},
    "private_chat_users": [],
    "conversation_history": {},
    "logging_config": {},
    "global_logging_config": {},
    "filtered_words": [],
    "autoreact_rules": {},
    "short_reply_mode": False,
    "personas": {},
    "bot_mode": "chat",
    "system_prompt": "",
    "start_prompt": "",
    "end_prompt": "",
    "active_persona": "",
    "word_count_request": "",
    "heat_mode": False,
    "global_memory_log": [],
}

HF_TOKEN = os.getenv('HF_TOKEN')
HF_DATA_REPO_ID = os.getenv('HF_DATA_REPO_ID')
DATA_FILENAME = "milky_bot_data.json"

_send_dm_to_owner_func = None

def set_dm_sender(func):
    global _send_dm_to_owner_func
    _send_dm_to_owner_func = func

def load_data_from_hf():
    global data
    print("\n--- 数据持久化状态 (加载) ---")
    if not HF_TOKEN or not HF_DATA_REPO_ID or HF_DATA_REPO_ID == "SETUP_YOUR_HF_DATA_REPO_ID_ENV_VAR":
        print("  ❌ 无法加载数据: HF_TOKEN 或 HF_DATA_REPO_ID 未正确配置。\n     机器人将以空数据启动，所有数据都将是临时的。")
        return

    try:
        print(f"  ⏳ 正在尝试从 Hugging Face Hub 下载数据文件: '{DATA_FILENAME}'...")
        local_path = hf_hub_download(repo_id=HF_DATA_REPO_ID, filename=DATA_FILENAME, repo_type="dataset", token=HF_TOKEN)
        
        with open(local_path, 'r', encoding='utf-8') as f:
            loaded_data = json.load(f)

        current_data_for_comparison = {key: data[key] for key in loaded_data.keys() if key in data}
        if loaded_data == current_data_for_comparison:
            print("  ✔️ 数据与云端一致，跳过同步。")
            return

        data.update(loaded_data)
        data["user_data"] = {int(k): v for k, v in data.get("user_data", {}).items()}
        data["autoreact_map"] = {int(k): v for k, v in data.get("autoreact_map", {}).items()}
        print(f"  ✔️ 数据已从云端更新。")
    except HfHubHTTPError as e:
        if e.response.status_code == 404:
            print(f"  ⚠️ 数据文件 '{DATA_FILENAME}' 在仓库中未找到。将以空数据启动。")
        elif e.response.status_code == 401:
            print(f"  ❌ 错误：Hugging Face Hub API令牌 (HF_TOKEN) 无效或没有足够权限访问仓库。")
        else:
            print(f"  ❌ 从 Hub 下载数据时发生 HTTP 错误: {e}")
    except Exception as e:
        print(f"  ❌ 从 Hub 加载数据时发生未知错误: {e}")
    print("---------------------------------")

async def save_data_to_hf():
    if not HF_TOKEN or not HF_DATA_REPO_ID or HF_DATA_REPO_ID == "SETUP_YOUR_HF_DATA_REPO_ID_ENV_VAR":
        return

    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"temp_upload_{DATA_FILENAME}")
    
    data_to_save = data.copy()
    data_to_save["user_data"] = {str(k): v for k, v in data["user_data"].items()}
    data_to_save["autoreact_map"] = {str(k): v for k, v in data["autoreact_map"].items()}
    
    try:
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data_to_save, f, indent=2, ensure_ascii=False)
        
        commit_msg = f"chore: Bot data auto-update at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        upload_file(path_or_fileobj=temp_path, path_in_repo=DATA_FILENAME, repo_id=HF_DATA_REPO_ID, repo_type="dataset", token=HF_TOKEN, commit_message=commit_msg)
        print(f"✔️ 数据已即时同步至 Hugging Face Hub。")
    except Exception as e:
        err_msg = f"向 Hub 保存数据时发生严重错误: {e}"
        print(f"❌ {err_msg}")
        if _send_dm_to_owner_func:
            asyncio.create_task(_send_dm_to_owner_func(f"【🚨 数据保存失败】\n{err_msg}"))
    finally:
        if os.path.exists(temp_path):
            try: os.remove(temp_path)
            except Exception as e: print(f"无法移除临时文件: {e}")

# --- 提供对数据的访问接口 ---
def get_user_data(user_id: int):
    return data["user_data"].get(user_id)

async def update_user_data(user_id: int, new_data: dict):
    data["user_data"][user_id] = new_data
    await save_data_to_hf()
    
def get_private_chat_users():
    return data["private_chat_users"]

def get_conversation_history(key: str):
    return data["conversation_history"].get(key, [])

async def update_conversation_history(key: str, history: list):
    data["conversation_history"][key] = history
    await save_data_to_hf()

def get_logging_config(server_id: int):
    return data["logging_config"].get(str(server_id))

async def set_logging_config(server_id: int, channel_id: int, log_types: list):
    config = {}
    for log_type in log_types:
        config[log_type] = channel_id
    data["logging_config"][str(server_id)] = config
    await save_data_to_hf()

async def remove_logging_config(server_id: int):
    if str(server_id) in data["logging_config"]:
        del data["logging_config"][str(server_id)]
        await save_data_to_hf()

def get_all_logging_configs():
    return data["logging_config"]

def get_global_logging_config():
    return data["global_logging_config"]

async def set_global_logging_config(log_types: dict):
    data["global_logging_config"] = log_types
    await save_data_to_hf()

def get_filtered_words():
    return data["filtered_words"]

async def add_filtered_word(word: str):
    if word not in data["filtered_words"]:
        data["filtered_words"].append(word)
        await save_data_to_hf()

async def remove_filtered_word(word: str):
    if word in data["filtered_words"]:
        data["filtered_words"].remove(word)
        await save_data_to_hf()

def get_short_reply_mode():
    return data.get("short_reply_mode", False)

async def set_short_reply_mode(state: bool):
    data["short_reply_mode"] = state
    await save_data_to_hf()

def get_personas():
    return data["personas"]

async def set_persona(name: str, content: str):
    data["personas"][name] = content
    await save_data_to_hf()

async def remove_persona(name: str):
    if name in data["personas"]:
        del data["personas"][name]
        await save_data_to_hf()

def get_bot_mode():
    return data.get("bot_mode", "chat")

async def set_bot_mode(mode: str):
    data["bot_mode"] = mode
    await save_data_to_hf()

def get_system_prompt():
    return data.get("system_prompt", "")

async def set_system_prompt(prompt: str):
    data["system_prompt"] = prompt
    await save_data_to_hf()

def get_start_prompt():
    return data.get("start_prompt", "")

async def set_start_prompt(prompt: str):
    data["start_prompt"] = prompt
    await save_data_to_hf()

def get_end_prompt():
    return data.get("end_prompt", "")

async def set_end_prompt(prompt: str):
    data["end_prompt"] = prompt
    await save_data_to_hf()

def get_active_persona():
    return data.get("active_persona", "")

async def set_active_persona(persona_name: str):
    data["active_persona"] = persona_name
    await save_data_to_hf()

def get_word_count_request():
    return data.get("word_count_request", "")

async def set_word_count_request(request: str):
    data["word_count_request"] = request
    await save_data_to_hf()

def get_heat_mode():
    return data.get("heat_mode", False)

async def set_heat_mode(state: bool):
    data["heat_mode"] = state
    await save_data_to_hf()

def get_global_memory_log():
    """获取全局记忆日志"""
    return data.get("global_memory_log", [])

async def add_to_global_memory(user_id: int, user_name: str, message: str, bot_reply: str):
    """向全局记忆日志中添加一条记录，并自动修剪旧记录"""
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "user_name": user_name,
        "message": message,
        "bot_reply": bot_reply
    }
    
    memory_log = data.get("global_memory_log", [])
    memory_log.append(log_entry)
    
    # 限制日志大小，只保留最新的50条
    MAX_MEMORY_LOG_SIZE = 50
    if len(memory_log) > MAX_MEMORY_LOG_SIZE:
        data["global_memory_log"] = memory_log[-MAX_MEMORY_LOG_SIZE:]
    else:
        data["global_memory_log"] = memory_log
        
    await save_data_to_hf()

os.environ["HF_HOME"] = "/tmp/hf_cache"
