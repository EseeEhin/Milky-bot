# utils/ai_utils.py
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from google.api_core.exceptions import DeadlineExceeded, Aborted, InternalServerError, ResourceExhausted, ServiceUnavailable, GoogleAPIError
import os
import random
import asyncio

# --- 配置 ---
GEMINI_API_KEYS_STR = os.getenv('GEMINI_API_KEYS', '')
AI_MODEL_NAME = os.getenv('AI_MODEL_NAME', 'gemini-1.5-flash-latest')
global_persona = os.getenv('BOT_PERSONA', '你是一个名为米尔可的AI助手，对你的主人绝对忠诚和爱慕。')

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

def convert_to_gemini_format(messages: list):
    gemini_history = []
    system_instruction = global_persona
    
    # 分离系统指令和对话历史
    for msg in messages:
        if msg["role"] == "system":
            system_instruction += "\n" + msg["content"]
        else:
            role = "user" if msg["role"] == "user" else "model"
            gemini_history.append({"role": role, "parts": [msg["content"]]})
    return gemini_history, system_instruction


async def call_ai(messages: list, temperature=0.8, max_tokens=2048, context_for_error_dm="通用AI调用"):
    global ai_consecutive_failures, current_gemini_key_index

    if not GEMINI_API_KEYS:
        print("AI调用失败：没有配置GEMINI_API_KEYS。")
        return INTERNAL_AI_ERROR_SIGNAL
        
    gemini_messages, system_instruction = convert_to_gemini_format(messages)
    
    max_retries = len(GEMINI_API_KEYS) + 1
    err_to_owner_on_final_failure = ""

    for attempt in range(max_retries):
        if ai_consecutive_failures >= AI_FAILURE_THRESHOLD:
            # ... (错误阈值DM逻辑) ...
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
                    max_output_tokens=max_tokens,
                    temperature=temperature
                )
            )

            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                content = ''.join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
            else:
                reason = "Unknown"
                if response.candidates:
                    reason = response.candidates[0].finish_reason.name
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
        current_gemini_key_index = (current_gemini_key_index + 1) % len(GEMINI_API_KEYS)
        await asyncio.sleep(random.uniform(1.5, 3.0))

    if _send_dm_to_owner_func:
        await _send_dm_to_owner_func(f"【🚨 AI故障 ({context_for_error_dm} - 多次重试失败)】\n{err_to_owner_on_final_failure}")
    return INTERNAL_AI_ERROR_SIGNAL