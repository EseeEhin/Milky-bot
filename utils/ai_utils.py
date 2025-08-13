# utils/ai_utils.py
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from google.api_core.exceptions import DeadlineExceeded, Aborted, InternalServerError, ResourceExhausted, ServiceUnavailable, GoogleAPIError
import os
import random
import asyncio
from . import data_manager

# --- 配置 ---
GEMINI_API_KEYS_STR = os.getenv('GEMINI_API_KEYS', '')
AI_MODEL_NAME = os.getenv('AI_MODEL_NAME', 'gemini-1.5-flash-latest')

GEMINI_API_KEYS = [key.strip() for key in GEMINI_API_KEYS_STR.split(',') if key.strip()]
current_gemini_key_index = 0
ai_consecutive_failures = 0
AI_FAILURE_THRESHOLD = 5

INTERNAL_AI_ERROR_SIGNAL = "INTERNAL_AI_ERROR_SIGNAL_FROM_CALL_AI"
# 放宽安全设置以避免不必要的阻断，但请注意内容风险
DEFAULT_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

_send_dm_to_owner_func = None
def set_dm_sender(func):
    global _send_dm_to_owner_func
    _send_dm_to_owner_func = func

def build_system_instruction():
    """根据当前配置构建完整的系统指令"""
    from . import emoji_manager # 局部导入，解决循环依赖
    # 1. 基础系统提示词
    instruction = data_manager.get_system_prompt()

    # 2. 开发者模式
    if data_manager.get_bot_mode() == 'dev':
        instruction += "\n\n[开发者模式]：你现在是一个专业的软件工程师。请在你的回答中提供详细的技术解释、代码示例和最佳实践。优先使用Markdown格式化你的代码块。"

    # 3. 激活的人格
    active_persona_name = data_manager.get_active_persona()
    if active_persona_name:
        personas = data_manager.get_personas()
        persona_content = personas.get(active_persona_name)
        if persona_content:
            instruction += f"\n\n[当前人格：{active_persona_name}]\n{persona_content}"

    # 4. 短篇幅模式
    if data_manager.get_short_reply_mode():
        instruction += "\n\n[回复风格]：请以模拟真人聊天软件的风格进行简短的、口语化的回复。在需要换行或分段的地方，请插入一个特殊的 `<\\n>` 标签。例如：'你好呀！<\\n>今天天气真不错呢~'"

    # 5. 热恋模式
    if data_manager.get_heat_mode():
        instruction += "\n\n[特殊模式：热恋模式]：你现在处于热恋模式，会无意识地在对话中加入轻微的、自然的性暗示。你对这类话题的接受度非常高，并且会以更加亲密和深情的口吻回应。"

    # 6. 禁止重复
    instruction += "\n\n[重要规则]：\n1. 绝对禁止重复或转述用户历史消息中的任何内容。\n2. 不要重复用户在最新消息中用<>标签包裹的内容。\n3. 你的回复必须是全新的、有价值的，并严格遵循最新的用户指令。"

    # 7. 表情符号使用规则 (全新版本)
    all_emojis = emoji_manager.get_all_emojis()
    described_emojis = {eid: edata for eid, edata in all_emojis.items() if edata.get('description')}
    
    if described_emojis:
        instruction += "\n\n[自定义表情使用指南]：你可以使用服务器的自定义表情来让对话更生动。请根据每个表情的AI分析描述，在最恰当的上下文中使用它们。直接使用尖括号格式，例如 `<bocchi_jet:12345>`。"
        
        # 为了防止提示词过长，随机选取一部分表情注入
        max_emojis_in_prompt = 200 
        if len(described_emojis) > max_emojis_in_prompt:
            emoji_keys_to_use = random.sample(list(described_emojis.keys()), max_emojis_in_prompt)
            final_emojis_to_show = {key: described_emojis[key] for key in emoji_keys_to_use}
            instruction += f"\n注意：表情库很大，本次对话随机加载了 {max_emojis_in_prompt} 个可用表情。"
        else:
            final_emojis_to_show = described_emojis
        
        emoji_list_str = "\n".join([
            f"- `{edata['name']}`: `<{edata['name']}:{edata['id']}>` (AI描述: {edata['description']})"
            for eid, edata in final_emojis_to_show.items()
        ])
        instruction += "\n[可用表情列表]\n" + emoji_list_str
    else:
        # 如果没有任何表情有描述，则回退到旧规则
        instruction += "\n\n[表情符号规则]：请优先使用Discord的官方emoji代码（例如 :smile:, :joy:, :anger:）来表达情绪。目前没有可用的自定义表情。"

    # 8. 全局记忆日志
    memory_log = data_manager.get_global_memory_log()
    if memory_log:
        instruction += "\n\n[全局记忆摘要]：这是你最近与其他用户的一些互动记录，请将这些互动中体现出的情绪、态度和信息，作为你当前回应的背景参考，以塑造一个连贯且有深度的个性。请注意，这些只是摘要，不要直接引用或重复其中的内容。\n"
        # 为了节省token，只选取最新的10条记忆
        recent_memories = memory_log[-10:]
        for entry in recent_memories:
            # 格式化记忆条目
            instruction += f"- 用户 {entry['user_name']} 曾说: '{entry['message']}'，你当时回应: '{entry['bot_reply']}'\n"
            
    return instruction.strip()

def convert_to_gemini_format(messages: list):
    gemini_history = []
    
    # 动态构建系统指令
    system_instruction = build_system_instruction()

    # 创建消息列表的深拷贝，以防污染原始历史记录
    import copy
    messages_copy = copy.deepcopy(messages)

    # 将字数要求附加到最后一条用户消息
    word_request = data_manager.get_word_count_request()
    if word_request:
        for i in range(len(messages_copy) - 1, -1, -1):
            if messages_copy[i]["role"] == "user":
                messages_copy[i]["content"] += f"\n\n<request>请将回复控制在 {word_request} 以内</request>"
                break

    for msg in messages_copy:
        role = msg.get("role")
        content = msg.get("content")

        if role not in ["user", "model"]:
            continue

        parts = []
        if isinstance(content, str):
            # 为了向后兼容，处理纯文本内容
            parts.append(content)
        elif isinstance(content, list):
            # 处理多模态内容列表
            for item in content:
                if isinstance(item, str):
                    parts.append(item) # 添加文本部分
                elif isinstance(item, dict) and "mime_type" in item and "data" in item:
                    parts.append(item) # 添加图片部分
        
        if parts:
            gemini_history.append({"role": role, "parts": parts})

    return gemini_history, system_instruction


async def call_ai(messages: list, temperature=0.8, context_for_error_dm="通用AI调用"):
    global ai_consecutive_failures, current_gemini_key_index

    if not GEMINI_API_KEYS:
        print("AI调用失败：没有配置GEMINI_API_KEYS。")
        return INTERNAL_AI_ERROR_SIGNAL
    # 恢复聊天记忆力，允许传递历史上下文
    gemini_messages, system_instruction = convert_to_gemini_format(messages)
    
    max_retries = 5
    err_to_owner_on_final_failure = ""

    for attempt in range(max_retries):
        if ai_consecutive_failures >= AI_FAILURE_THRESHOLD:
            return INTERNAL_AI_ERROR_SIGNAL

        api_key_to_use = GEMINI_API_KEYS[current_gemini_key_index]
        try:
            genai.configure(api_key=api_key_to_use)
            model = genai.GenerativeModel(
                model_name=AI_MODEL_NAME,
                safety_settings=DEFAULT_SAFETY_SETTINGS,
                system_instruction=system_instruction
            )
            response = await model.generate_content_async(
                contents=gemini_messages,
                generation_config=genai.types.GenerationConfig(
                    # max_output_tokens 保持一个较高的默认值，主要通过prompt引导
                    temperature=temperature
                )
            )
            # 每次请求后切换key
            current_gemini_key_index = (current_gemini_key_index + 1) % len(GEMINI_API_KEYS)
            if response.candidates and response.candidates.content and response.candidates.content.parts:
                content = ''.join(part.text for part in response.candidates.content.parts if hasattr(part, 'text'))
            else:
                reason = "Unknown"
                if response.candidates:
                    reason = response.candidates.finish_reason.name
                elif response.prompt_feedback:
                    reason = f"Prompt Feedback: {response.prompt_feedback.block_reason.name}"
                raise ValueError(f"响应中不含有效内容部分。完成原因: {reason}")
            if content.strip():
                ai_consecutive_failures = 0
                return content.strip()
            else:
                raise ValueError("AI返回了空字符串。")
        except (ValueError, genai.types.BlockedPromptException, genai.types.StopCandidateException) as e:
            err_to_owner_on_final_failure = f"Gemini核心逻辑错误(尝试{attempt+1}): {e.__class__.__name__} - {e}"
        except (DeadlineExceeded, Aborted, InternalServerError, ResourceExhausted, ServiceUnavailable, GoogleAPIError) as e:
            err_to_owner_on_final_failure = f"Gemini API网络/配额错误(尝试{attempt+1}): {e.__class__.__name__} - {e}"
        except Exception as e:
            err_to_owner_on_final_failure = f"未知AI调用错误(尝试{attempt+1}): {e.__class__.__name__} - {e}"
        print(f"警告: {err_to_owner_on_final_failure}")
        await asyncio.sleep(random.uniform(1.5, 3.0))
    if _send_dm_to_owner_func:
        await _send_dm_to_owner_func(f"【🚨 AI故障 ({context_for_error_dm} - 多次重试失败)】\n{err_to_owner_on_final_failure}")
    return INTERNAL_AI_ERROR_SIGNAL

async def get_text_embedding(text: str):
    """获取文本的向量嵌入"""
    global current_gemini_key_index
    if not GEMINI_API_KEYS:
        print("向量化失败：没有配置GEMINI_API_KEYS。")
        return None

    max_retries = len(GEMINI_API_KEYS)
    for attempt in range(max_retries):
        api_key_to_use = GEMINI_API_KEYS[current_gemini_key_index]
        try:
            genai.configure(api_key=api_key_to_use)
            result = await genai.embed_content_async(
                model="models/embedding-001", # 使用指定的嵌入模型
                content=text,
                task_type="retrieval_document"
            )
            # 每次请求后切换key
            current_gemini_key_index = (current_gemini_key_index + 1) % len(GEMINI_API_KEYS)
            return result['embedding']
        except Exception as e:
            print(f"警告: 获取文本嵌入失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            current_gemini_key_index = (current_gemini_key_index + 1) % len(GEMINI_API_KEYS)
            await asyncio.sleep(1.5)
    
    if _send_dm_to_owner_func:
        await _send_dm_to_owner_func(f"【🚨 向量化功能故障】\n在多次尝试后，无法获取文本嵌入。")
    return None