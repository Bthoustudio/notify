from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError, LineBotApiError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, JoinEvent
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import datetime
import pytz
import json
import logging

# 設定 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# LINE Bot credentials
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Google Sheets setup
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('service-account.json', scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(os.getenv("SHEET_ID"))

# 工作表
group_sheet = sheet.worksheet('群組清單')
notify_sheet = sheet.worksheet('群組通知規則')

# 時區設定
taipei_tz = pytz.timezone('Asia/Taipei')

# === 共用工具 ===

def insert_group(group_id):
    values = group_sheet.col_values(2)  # 群組ID在 B 欄
    if group_id not in values:
        group_sheet.append_row(['未命名群組', group_id, datetime.datetime.now(taipei_tz).strftime("%Y-%m-%d %H:%M:%S"), ''])
        logger.info(f"✅ 新增群組 {group_id}")

def get_notify_text(subject):
    rows = notify_sheet.get_all_records()
    for row in rows:
        if str(row.get('是否啟用')).strip() != '是':
            continue
        if row.get('主旨關鍵字') in subject:
            return {
                "text": row.get('通知文字'),
                "group_id": row.get('通知群組ＩＤ')
            }
    return None

def safe_reply(reply_token, text):
    try:
        if reply_token and reply_token != "00000000000000000000000000000000":
            line_bot_api.reply_message(reply_token, TextSendMessage(text=text))
    except LineBotApiError as e:
        logger.error(f"❌ reply_message 推送失敗: {e}")
    except Exception as e:
        logger.error(f"❌ 其他 reply_message 錯誤: {e}")

# === FastAPI Route ===

@app.post("/callback")
async def callback(request: Request):
    try:
        signature = request.headers['x-line-signature']
        body = await request.body()
        body = body.decode('utf-8')
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.warning("❌ LINE webhook error: Invalid signature")
        return JSONResponse(content={"message": "Invalid signature"}, status_code=400)
    except Exception as e:
        logger.exception("❌ callback 發生未預期錯誤")
        return JSONResponse(content={"message": "Internal Server Error"}, status_code=500)
    return JSONResponse(content={"message": "OK"}, status_code=200)

@app.post("/notify")
async def notify(request: Request):
    data = await request.json()
    group_id = data.get("group_id")
    message = data.get("message")
    now = datetime.datetime.now(taipei_tz).strftime("%Y-%m-%d %H:%M")

    text = f"🔔【新通知來啦】🔔\n⏰ {now} ⏰\n———————\n{message}\n———————\n🔰 請即刻查閱信箱 🔰\nservice@eltgood.com"

    try:
        line_bot_api.push_message(group_id, TextSendMessage(text=text))
        logger.info(f"✅ 推播成功到群組 {group_id}")
        return {"status": "ok"}
    except LineBotApiError as e:
        logger.error(f"❌ 推播失敗：{e}")
        if "You have reached your monthly limit" in str(e):
            return {"status": "error", "message": "月額度已用盡"}
        return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.exception("❌ 推播過程發生錯誤")
        return {"status": "error", "message": str(e)}

# === LINE Event Handlers ===

@handler.add(JoinEvent)
def handle_join(event):
    group_id = event.source.group_id
    insert_group(group_id)
    safe_reply(event.reply_token, "✅ 已加入群組，請輸入 /命名 店名")

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        text = event.message.text.strip()
        user_type = event.source.type
        source_id = event.source.user_id if user_type == 'user' else event.source.group_id
        logger.info(f"📨 收到訊息：「{text}」，來自：{user_type}（ID: {source_id}）")

        if user_type == 'group':
            group_id = event.source.group_id

            # 群組命名指令
            if text.startswith("/命名"):
                new_name = text.replace("/命名", "").strip()
                cells = group_sheet.get_all_records()
                for idx, row in enumerate(cells):
                    if row['群組ID'] == group_id:
                        group_sheet.update_cell(idx + 2, 1, new_name)
                        safe_reply(event.reply_token, f"✅ 命名成功：{new_name}")
                        return
                group_sheet.append_row([new_name, group_id, datetime.datetime.now(taipei_tz).strftime("%Y-%m-%d %H:%M:%S"), ''])
                safe_reply(event.reply_token, f"✅ 已新增並命名：{new_name}")
    except Exception as e:
        logger.exception("❌ handle_message 發生錯誤")
