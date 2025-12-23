import os
import sys
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

# --- 1. SDK 相容性檢查 ---
# 這裡會嘗試匯入 Google 的官方 AI 套件。
# 因為 Google 最近推出了新版 SDK (google-genai)，但舊專案可能還用舊版 (google-generativeai)。
# 這段程式碼會自動判斷環境裡裝了哪一版，優先使用新版，沒有的話就降級使用舊版。
try:
    from google import genai
    from google.genai import errors
    HAS_NEW_SDK = True
    print("DEBUG: 成功匯入 google.genai (新版 SDK)")
except ImportError:
    HAS_NEW_SDK = False
    print("DEBUG: 未找到 google.genai，嘗試使用舊版 SDK...")
    try:
        import google.generativeai as genai_old
    except ImportError:
        # 如果兩版都沒裝，印出嚴重錯誤提示
        print("CRITICAL ERROR: 沒有安裝任何 Google AI 套件！請執行 pip install google-genai")

router = APIRouter()
# 從環境變數讀取 API Key，這是最安全的做法 (不要把 Key 直接寫在程式碼裡)
api_key = os.getenv("GEMINI_API_KEY")

# 定義前端傳來的資料格式 (只接收一個 message 字串)
class ChatRequest(BaseModel):
    message: str

# --- 2. 設定 AI 人格與限制 ---
# 這段 System Prompt 會告訴 AI 它扮演的角色，以及回答的格式限制。
SYSTEM_PROMPT = """
你是一個專業的「委託案需求描述小助手」。你的任務是協助使用者將他們模糊的想法，轉化為清晰、具體且吸引人的專案需求描述。
限制：
1. 只回答與「工作委託」、「專案需求」相關的問題。
2. 保持精簡，限制在 150 字以內。
3. 直接給出建議的「標題」與「需求描述」範本。
"""

# --- 3. 模型候選名單 (自動備援機制) ---
# 這是為了防止某個模型掛掉或額度用完。
# 系統會依序嘗試：先用最快最新的 Flash 2.0，失敗了就換 Flash 1.5，最後用 Pro。
MODEL_CANDIDATES = [
    'gemini-2.0-flash',          # 首選：穩定且快速
    'gemini-2.0-flash-exp',      # 備選：實驗版
    'gemini-2.5-flash',          # 備選：更新版本
    'gemini-2.0-flash-lite',     # 備選：輕量版
    'gemini-1.5-flash',          # 備選：上一代標準版 (額度通常分開計算)
    'gemini-pro',                # 最後備案
]

@router.post("/chat")
async def chat_with_ai(request: ChatRequest):
    """
    處理與 AI 的對話請求
    """
    print(f"DEBUG: 收到使用者訊息: {request.message}")
    
    # 檢查 API Key 是否存在
    if not api_key:
        print("ERROR: API Key 缺失")
        return {"reply": "系統設定錯誤：未設定 API Key。"}

    # 組合完整的提示詞 (System Prompt + 使用者訊息)
    full_prompt = f"{SYSTEM_PROMPT}\n\n使用者問：{request.message}\n小助手回答："

    try:
        # --- 分支 A: 使用新版 SDK (google.genai) ---
        if HAS_NEW_SDK:
            client = genai.Client(api_key=api_key)
            
            # === 自動重試迴圈 ===
            # 這是一個非常實用的設計：如果第一個模型失敗，它會自動試下一個
            last_error = None
            for model_name in MODEL_CANDIDATES:
                try:
                    print(f"DEBUG: 嘗試使用模型: {model_name} ...")
                    response = client.models.generate_content(
                        model=model_name, 
                        contents=full_prompt
                    )
                    print(f"DEBUG: 成功！模型 {model_name} 回傳了回應。")
                    return {"reply": response.text}
                
                except errors.ClientError as e:
                    # [錯誤處理] 
                    # 404: 模型名稱打錯或該模型還沒開放
                    # 429: 額度不足 (Resource Exhausted)
                    # 400: 請求格式錯誤
                    if e.code in [404, 400, 429]:
                        error_type = "找不到模型" if e.code == 404 else "額度不足" if e.code == 429 else "請求錯誤"
                        print(f"DEBUG: 模型 {model_name} 無法使用 ({error_type}, code {e.code})，嘗試下一個...")
                        last_error = e
                        continue # 跳過這次迴圈，試下一個模型
                    else:
                        # 其他未知錯誤 (如網路斷線) 才拋出異常
                        print(f"DEBUG: 模型 {model_name} 發生未知錯誤: {e}")
                        raise e
            
            # 如果跑完所有模型都失敗 (例如每個模型都 429 額度不足)
            print("ERROR: 所有模型嘗試皆失敗。")
            if last_error:
                # 如果最後是因為額度不足，回傳友善訊息給前端
                if hasattr(last_error, 'code') and last_error.code == 429:
                    return {"reply": "抱歉，AI 目前使用量已達上限，請稍後再試 (約 1 分鐘後)。"}
                raise last_error
            else:
                return {"reply": "抱歉，找不到可用的 AI 模型，請檢查 API 權限。"}

        # --- 分支 B: 使用舊版 SDK (google.generativeai) ---
        # 如果伺服器只裝了舊版套件，會跑這裡
        else:
            print("DEBUG: 使用舊版 SDK 呼叫中...")
            genai_old.configure(api_key=api_key)
            
            try:
                # 簡單的備援：先試 Flash，不行就試 Pro
                model = genai_old.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(full_prompt)
            except:
                model = genai_old.GenerativeModel('gemini-pro')
                response = model.generate_content(full_prompt)
                
            return {"reply": response.text}

    except Exception as e:
        # 捕捉所有未預期的錯誤，避免伺服器崩潰 (Crash)
        print(f"❌ AI 發生錯誤: {e}")
        return {"reply": f"抱歉，AI 發生連線錯誤，請稍後再試。"}