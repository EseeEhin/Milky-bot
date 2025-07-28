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
    "user_data": {},        # 积分/签到等, key: user_id
    "autoreact_map": {},    # 自动反应, key: user_id
    "private_chat_users": [], # 私聊权限, list of user_id
    "conversation_history": {}, # 对话历史, key: channel_id-user_id
    "logging_config": {},   # 日志配置, key: server_id -> {log_type: channel_id}
    "global_logging_config": {}, # 全局日志配置, {log_type: channel_id}
    "filtered_words": [],   # 屏蔽词列表
    "autoreact_rules": {},   # 自动反应规则, key: server_id -> {trigger: reaction}
    "short_reply_mode": False, # 短篇幅模式开关
    "personas": {}, # AI人格数据
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
            data["user_data"] = {int(k): v for k, v in loaded_data.get("user_data", {}).items()}
            data["autoreact_map"] = {int(k): v for k, v in loaded_data.get("autoreact_map", {}).items()}
            data["private_chat_users"] = loaded_data.get("private_chat_users", [])
            data["conversation_history"] = loaded_data.get("conversation_history", {})
            data["logging_config"] = loaded_data.get("logging_config", {})
            data["global_logging_config"] = loaded_data.get("global_logging_config", {})
            data["filtered_words"] = loaded_data.get("filtered_words", [])
            data["autoreact_rules"] = loaded_data.get("autoreact_rules", {})
            data["short_reply_mode"] = loaded_data.get("short_reply_mode", False)
            data["personas"] = loaded_data.get("personas", {})
        print(f"  ✔️ 数据成功从 Hub 加载。")
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

def save_data_to_hf():
    if not HF_TOKEN or not HF_DATA_REPO_ID or HF_DATA_REPO_ID == "SETUP_YOUR_HF_DATA_REPO_ID_ENV_VAR":
        return

    temp_dir = tempfile.gettempdir()
    temp_path = os.path.join(temp_dir, f"temp_upload_{DATA_FILENAME}")
    
    data_to_save = {
        "user_data": {str(k): v for k, v in data["user_data"].items()},
        "autoreact_map": {str(k): v for k, v in data["autoreact_map"].items()},
        "private_chat_users": data["private_chat_users"],
        "conversation_history": data["conversation_history"],
        "logging_config": data["logging_config"],
        "global_logging_config": data["global_logging_config"],
        "filtered_words": data["filtered_words"],
        "autoreact_rules": data["autoreact_rules"],
        "short_reply_mode": data["short_reply_mode"],
        "personas": data["personas"]
    }
    
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

def update_user_data(user_id: int, new_data: dict):
    data["user_data"][user_id] = new_data
    save_data_to_hf()
    
def get_autoreact_map():
    return data["autoreact_map"]

def get_private_chat_users():
    return data["private_chat_users"]

def get_conversation_history(key: str):
    return data["conversation_history"].get(key, [])

def update_conversation_history(key: str, history: list):
    data["conversation_history"][key] = history
    save_data_to_hf()

# --- 新增的持久化数据访问接口 ---
def get_logging_config(server_id: int):
    """获取服务器的日志配置"""
    return data["logging_config"].get(str(server_id))

def set_logging_config(server_id: int, channel_id: int, log_types: list):
    """设置服务器的日志配置"""
    config = {}
    for log_type in log_types:
        config[log_type] = channel_id
    data["logging_config"][str(server_id)] = config
    save_data_to_hf()

def remove_logging_config(server_id: int):
    """移除服务器的日志配置"""
    if str(server_id) in data["logging_config"]:
        del data["logging_config"][str(server_id)]
        save_data_to_hf()

def get_all_logging_configs():
    """获取所有日志配置"""
    return data["logging_config"]

def get_global_logging_config():
    """获取全局日志配置"""
    return data["global_logging_config"]

def set_global_logging_config(log_types: dict):
    """设置全局日志配置"""
    data["global_logging_config"] = log_types
    save_data_to_hf()

def get_filtered_words():
    """获取屏蔽词列表"""
    return data["filtered_words"]

def add_filtered_word(word: str):
    """添加屏蔽词"""
    if word not in data["filtered_words"]:
        data["filtered_words"].append(word)
        save_data_to_hf()

def remove_filtered_word(word: str):
    """移除屏蔽词"""
    if word in data["filtered_words"]:
        data["filtered_words"].remove(word)
        save_data_to_hf()

def get_autoreact_rules(server_id: int):
    """获取服务器的自动反应规则"""
    return data["autoreact_rules"].get(str(server_id), {})

def set_autoreact_rules(server_id: int, rules: dict):
    """设置服务器的自动反应规则"""
    data["autoreact_rules"][str(server_id)] = rules
    save_data_to_hf()

def add_autoreact_rule(server_id: int, trigger: str, reaction: str):
    """添加自动反应规则"""
    server_id_str = str(server_id)
    if server_id_str not in data["autoreact_rules"]:
        data["autoreact_rules"][server_id_str] = {}
    data["autoreact_rules"][server_id_str][trigger] = reaction
    save_data_to_hf()

def remove_autoreact_rule(server_id: int, trigger: str):
    """移除自动反应规则"""
    server_id_str = str(server_id)
    if server_id_str in data["autoreact_rules"] and trigger in data["autoreact_rules"][server_id_str]:
        del data["autoreact_rules"][server_id_str][trigger]
        save_data_to_hf()

def get_all_autoreact_rules():
    """获取所有自动反应规则"""
    return data["autoreact_rules"]

def get_short_reply_mode():
    return data.get("short_reply_mode", False)

def set_short_reply_mode(state: bool):
    data["short_reply_mode"] = state
    save_data_to_hf()

def get_personas():
    return data["personas"]

def set_persona(name: str, content: str):
    data["personas"][name] = content
    save_data_to_hf()

def remove_persona(name: str):
    if name in data["personas"]:
        del data["personas"][name]
        save_data_to_hf()

os.environ["HF_HOME"] = "/tmp/hf_cache"