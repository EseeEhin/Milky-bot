# utils/data_manager.py
import json
import os
import tempfile
from huggingface_hub import hf_hub_download, upload_file
from huggingface_hub.utils import HfHubHTTPError, RepositoryNotFoundError
from datetime import datetime, timezone
import asyncio

# 全局数据字典
data = {
    "user_data": {},        # 积分/签到等, key: user_id
    "autoreact_map": {},    # 自动反应, key: user_id
    "private_chat_users": [], # 私聊权限, list of user_id
    "conversation_history": {} # 对话历史, key: channel_id-user_id
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
        "conversation_history": data["conversation_history"]
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