from fastapi import FastAPI, Request
from linebot import LineBotApi, WebhookParser
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    JoinEvent, LeaveEvent
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
from datetime import datetime

# ===== LINE BOT 設定 =====
CHANNEL_ACCESS_TOKEN = "9+6Btw2uIRhLtYA9rCISIVYdDCiWUOmTSibpll7VdDBw15UOZkW8hxW2VCwD/R86vKzKGhIoyQ3BQw9gM9+LbEbEjkFu2cvTd8KfqeT/pCWefiCHBoCIvBbUU8TRGB8XRKNQZsFKdNMORu1gPjSCgAdB04t89/1O/w1cDnyilFU="
CHANNEL_SECRET = "3ca5edef3cb6a825e5fc77aaf1ba8a5e"
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
parser = WebhookParser(CHANNEL_SECRET)

# ===== Google Sheet 設定 =====
SHEET_ID = "1xg2n0kcSkgBMohkvHoPU3AWhB2Pkr4gS_W8i6CA-O4k"
SHEET_NAME = "群組清單"

def get_sheet():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/service-account.json", scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

def insert_group(group_id):
    sheet = get_sheet()
    all_rows = sheet.get_all_records()
    group_ids = [row["群組ID"] for row in all_rows]
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

app = FastAPI()

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()

    try:
        events = parser.parse(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        return {"status": "invalid signature"}

    for event in events:
        source = event.source
        group_id = source.group_id if source.type == "group" else None

        if isinstance(event, JoinEvent) and group_id:
            insert_group(group_id)
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="✅ 已加入群組，請輸入 /命名 店名"))

        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
            text = event.message.text.strip()
            if text.startswith("/命名") and group_id:
                parts = text.split(" ", 1)
                if len(parts) == 2:
                    name = parts[1].strip()
                    update_group_name(group_id, name)
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=f"✅ 名稱「{name}」已儲存"))
                else:
                    line_bot_api.reply_message(event.reply_token, TextSendMessage(text="⚠️ 請使用正確格式：/命名 店名"))

        if isinstance(event, LeaveEvent) and group_id:
            delete_group(group_id)
            print(f"🗑️ 已刪除群組資料：{group_id}")

    return "OK"

@app.post("/notify")
async def notify(req: Request):
    data = await req.json()
    group_id = data.get("group_id")
    message = data.get("message")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    if group_id and message:
        text = f"""🔔【新通知來啦】🔔
⏰ {now} ⏰
—————————
{message}
—————————
🔰 請即刻查閱信箱 🔰
service@eltgood.com"""
        line_bot_api.push_message(group_id, TextSendMessage(text=text))
        return {"status": "ok"}
    else:
        return {"status": "missing group_id or message"}
