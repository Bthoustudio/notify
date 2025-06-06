import os
import json
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from datetime import datetime

# === 環境變數 ===
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")
SHEET_ID = os.getenv("SHEET_ID")

# === 初始化 LINE Bot ===
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

# === 初始化 Google Sheets ===
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('/etc/secrets/service-account.json', scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).sheet1

# === FastAPI app ===
app = FastAPI()


# === /callback：LINE 事件處理 ===
@app.post("/callback")
async def callback(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Line-Signature")
    try:
        handler.handle(body.decode("utf-8"), signature)
    except Exception as e:
        print(f"❌ LINE webhook error: {e}")
        return JSONResponse(content={"status": "error"}, status_code=400)
    return JSONResponse(content={"status": "ok"})


# === LINE 訊息處理器 ===
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    group_id = getattr(event.source, "group_id", None)
    text = event.message.text

    print(f"✅ 收到來自群組 {group_id} 的訊息：{text}")

    # 新增資料到 Google Sheets
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row([now, group_id or "私訊", user_id, text])

    # 回覆固定訊息
    reply_text = "收到囉！📬"
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))


# === /notify：curl 發送通知用 ===
@app.post("/notify")
async def notify(request: Request):
    data = await request.json()
    group_id = data.get("group_id")
    message = data.get("message")

    if not group_id or not message:
        return JSONResponse(content={"error": "group_id and message are required"}, status_code=400)

    # 組合格式化訊息
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = f"""🔔【新通知來啦】🔔
⏰ {now} ⏰
—————————
{message}
—————————
🔰 請即刻查閱信箱 🔰
service@eltgood.com"""

    try:
        line_bot_api.push_message(group_id, TextSendMessage(text=text))
        return JSONResponse(content={"status": "sent"}, status_code=200)
    except Exception as e:
        print(f"❌ 發送失敗：{e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

