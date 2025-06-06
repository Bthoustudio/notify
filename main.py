from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import *
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
import json

# === LINE 設定（從環境變數讀取）===
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# === Google Sheet 設定 ===
SHEET_ID = os.getenv("SHEET_ID")
SHEET_NAME = "群組清單"

def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(
        "/etc/secrets/service-account.json", scope
    )
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

def insert_group(group_id):
    sheet = get_sheet()
    group_ids = [row["群組ID"] for row in sheet.get_all_records()]
    if group_id not in group_ids:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sheet.append_row(["", group_id, now, ""])

def update_group_name(group_id, name):
    sheet = get_sheet()
    rows = sheet.get_all_records()
    for idx, row in enumerate(rows):
        if row["群組ID"] == group_id:
            sheet.update_cell(idx + 2, 1, name)
            return True
    return False

def delete_group(group_id):
    sheet = get_sheet()
    rows = sheet.get_all_records()
    for idx, row in enumerate(rows):
        if row["群組ID"] == group_id:
            sheet.delete_rows(idx + 2)
            return True
    return False

# === FastAPI 啟動 ===
app = FastAPI()

@app.get("/")
async def root():
    return PlainTextResponse("✅ LINE Webhook Server is live.")

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()

    # Debug 用：列印 webhook JSON
    print("🔔 Webhook Received:")
    print(json.dumps(json.loads(body), indent=2, ensure_ascii=False))

    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        return PlainTextResponse("Invalid signature", status_code=400)

    return PlainTextResponse("OK", status_code=200)

# === LINE 事件處理 ===
@handler.add(JoinEvent)
def handle_join(event):
    group_id = event.source.group_id
    insert_group(group_id)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(
        text="✅ 已加入群組，請輸入 /命名 店名"
    ))

@handler.add(MessageEvent)
def handle_message(event):
    text = event.message.text.strip()
    group_id = event.source.group_id if event.source.type == "group" else None
    if text.startswith("/命名") and group_id:
        parts = text.split(" ", 1)
        if len(parts) == 2:
            name = parts[1].strip()
            update_group_name(group_id, name)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text=f"✅ 名稱「{name}」已儲存"
            ))
        else:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(
                text="⚠️ 請使用正確格式：/命名 店名"
            ))

@handler.add(LeaveEvent)
def handle_leave(event):
    group_id = event.source.group_id
    delete_group(group_id)
    print(f"🗑️ 已從 Google Sheet 移除 groupId：{group_id}")

# === 發送訊息 API ===
@app.post("/notify")
async def notify(request: Request):
    data = await request.json()
    group_id = data.get("group_id")
    message = data.get("message")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    text = f"""🔔【新通知來啦】🔔
⏰ {now} ⏰
—————————
{message}
—————————
🔰 請即刻查閱信箱 🔰
service@eltgood.com"""
    line_bot_api.push_message(group_id, TextSendMessage(text=text))
    print(f"✅ 已通知 LINE 群組 {group_id}")
    return {"status": "sent"}
