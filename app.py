import os
import logging
from flask import Flask, request, abort

from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

import google.generativeai as genai

# ===============================
# Logging（Render 會收）
# ===============================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ===============================
# Environment Variables
# ===============================
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not all([CHANNEL_ACCESS_TOKEN, CHANNEL_SECRET, GEMINI_API_KEY]):
    raise RuntimeError("Missing required environment variables")

# ===============================
# LINE Bot
# ===============================
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# ===============================
# Gemini
# ===============================
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    "gemini-1.5-flash",
    generation_config={
        "temperature": 0.7,
        "max_output_tokens": 512,
    }
)

# ===============================
# Flask App
# ===============================
app = Flask(__name__)

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.warning("Invalid LINE signature")
        abort(400)
    except Exception as e:
        logger.exception("Webhook error")
        abort(500)

    return "OK"

# ===============================
# Message Handler
# ===============================
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()

    # 空訊息防呆
    if not user_text:
        return

    try:
        response = model.generate_content(
            user_text,
            request_options={"timeout": 8}  # 防止卡死
        )

        reply_text = response.text or "（沒有回應）"

    except Exception as e:
        # 記錄錯誤，但不洩漏給使用者
        logger.exception("Gemini API error")
        reply_text = "⚠️ 系統忙碌中，請稍後再試"

    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
    except Exception:
        logger.exception("LINE reply failed")

# ===============================
# Render / Gunicorn
# ===============================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
