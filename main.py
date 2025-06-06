
from fastapi import FastAPI, Request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, JoinEvent
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import datetime
import json

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

# 用來記錄哪些群組正在等待命名
pending_naming = {}

# 加入新群組
def insert_group(group_id):
    values = group_sheet.col_values(2)  # 假設群組ID在 B 欄
    if group_id not in values:
        group_sheet.append_row(['未命名群組', group_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ''])
        pending_naming[group_id] = True

# 根據主旨關鍵字找通知文字
def get_notify_text(subject):
    rows = notify_sheet.get_all_records()
    for row in rows:
        if str(row['是否啟用']).strip() != '是':
            continue
        if row['主旨關鍵字'] in subject:
            return {
                "text": row['通知文字'],
                "group_id": row['通知群組ＩＤ']
            }
    return None

@app.post("/callback")
async def callback(request: Request):
    signature = request.headers['x-line-signature']
    body = await request.body()
    body = body.decode('utf-8')
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ LINE webhook error: <InvalidSignatureError>")
        return 'Signature error'
    return 'OK'

@handler.add(JoinEvent)
def handle_join(event):
    group_id = event.source.group_id
    insert_group(group_id)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="✅ 已加入群組，請輸入 /命名 店名")
    )

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    group_id = event.source.group_id if event.source.type == 'group' else None

    # 僅允許命名一次，之後不再監聽
    if group_id and pending_naming.get(group_id):
        if text.startswith("/命名"):
            new_name = text.replace("/命名", "").strip()
            cells = group_sheet.get_all_records()
            for idx, row in enumerate(cells):
                if row['群組ID'] == group_id:
                    group_sheet.update_cell(idx + 2, 1, new_name)
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text=f"✅ 命名成功：{new_name}")
                    )
                    pending_naming[group_id] = False
                    return
            # 若找不到群組，加入新群組資料
            group_sheet.append_row([new_name, group_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ''])
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"✅ 已新增並命名：{new_name}")
            )
            pending_naming[group_id] = False
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請先輸入 /命名 店名 來命名這個群組！")
            )

@app.post("/notify")
async def notify(request: Request):
    data = await request.json()
    group_id = data.get("group_id")
    message = data.get("message")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    text = f"🔔【新通知來啦】🔔\n⏰ {now} ⏰\n———————\n{message}\n———————\n🔰 請即刻查閱信箱 🔰\nservice@eltgood.com"

    try:
        line_bot_api.push_message(group_id, TextSendMessage(text=text))
        return {"status": "ok"}
    except Exception as e:
        print("❌ 推送失敗：", e)
        return {"status": "error", "message": str(e)}
