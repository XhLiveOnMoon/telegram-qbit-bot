import asyncio
import html
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

import requests
from torznab import parse_torznab_results
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, filters,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO"),
)
log = logging.getLogger("telegram-qbit-bot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USERS = {
    int(value.strip())
    for value in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",")
    if value.strip().isdigit()
}
JACKETT_BASE = os.environ.get("JACKETT_BASE_URL", "http://jackett:9117").rstrip("/")
JACKETT_KEY = os.environ["JACKETT_API_KEY"]
QBIT_BASE = os.environ["QBIT_BASE_URL"].rstrip("/")
QBIT_USER = os.environ["QBIT_USERNAME"]
QBIT_PASS = os.environ["QBIT_PASSWORD"]
QBIT_CATEGORY = os.environ.get("QBIT_CATEGORY", "telegram-bot")
SEARCH_LIMIT = max(1, min(20, int(os.environ.get("SEARCH_LIMIT", "10"))))
POLL_SECONDS = max(20, int(os.environ.get("POLL_INTERVAL_SECONDS", "60")))
IDLE_POLL_SECONDS = max(
    POLL_SECONDS,
    int(os.environ.get("IDLE_POLL_INTERVAL_SECONDS", "300")),
)
STATE_FILE = Path(os.environ.get("STATE_PATH", "/data/state.json"))

http = requests.Session()
qbit_lock = threading.Lock()
search_cache = {}
previous_progress = {}
last_qbit_login = 0.0


def authorized(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in ALLOWED_USERS)


async def deny(update: Update):
    if update.effective_message:
        await update.effective_message.reply_text("未授权。请将你的 Telegram 数字用户 ID 加入 TELEGRAM_ALLOWED_USER_IDS。")


def qbit_login(force=False):
    global last_qbit_login
    with qbit_lock:
        if not force and time.time() - last_qbit_login < 300:
            return
        response = http.post(
            f"{QBIT_BASE}/api/v2/auth/login",
            data={"username": QBIT_USER, "password": QBIT_PASS},
            timeout=15,
        )
        response.raise_for_status()
        if response.status_code not in (200, 204):
            raise RuntimeError(
                f"qBittorrent login failed: HTTP {response.status_code}, "
                f"{response.text[:120]}"
            )
        if response.status_code == 200 and response.text.strip() != "Ok.":
            raise RuntimeError(f"qBittorrent login failed: {response.text[:120]}")
        last_qbit_login = time.time()


def qbit_request(method, path, **kwargs):
    qbit_login()
    response = http.request(method, f"{QBIT_BASE}{path}", timeout=30, **kwargs)
    if response.status_code == 403:
        qbit_login(force=True)
        response = http.request(method, f"{QBIT_BASE}{path}", timeout=30, **kwargs)
    response.raise_for_status()
    return response


def jackett_search(query):
    response = requests.get(
        f"{JACKETT_BASE}/api/v2.0/indexers/all/results/torznab/api",
        params={"apikey": JACKETT_KEY, "t": "search", "q": query},
        timeout=90,
    )
    response.raise_for_status()
    return parse_torznab_results(response.content, SEARCH_LIMIT)

def human_size(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "未知大小"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if number < 1024 or unit == "TB":
            return f"{number:.1f} {unit}"
        number /= 1024
    return "未知大小"


def validate_qbit_add_response(response):
    body = response.text.strip()
    if body.lower() in ("", "ok."):
        return

    try:
        result = response.json()
    except ValueError:
        raise RuntimeError(f"qBittorrent 添加任务返回异常：{body[:150]}")

    if isinstance(result, dict):
        success_count = int(result.get("success_count", 0))
        pending_count = int(result.get("pending_count", 0))
        failure_count = int(result.get("failure_count", 0))
        if failure_count == 0 and (success_count > 0 or pending_count > 0):
            return

    raise RuntimeError(f"qBittorrent 添加任务失败：{body[:150]}")


def add_qbit_url(url):
    if not url.startswith(("magnet:", "http://", "https://")):
        raise ValueError("只接受 magnet:、HTTP 或 HTTPS 下载链接。")
    response = qbit_request(
        "POST", "/api/v2/torrents/add",
        data={"urls": url, "category": QBIT_CATEGORY},
    )
    validate_qbit_add_response(response)


def load_state():
    global previous_progress
    try:
        data = json.loads(STATE_FILE.read_text())
        previous_progress = {
            str(key): float(value) for key, value in data.get("progress", {}).items()
        }
    except Exception:
        previous_progress = {}


def save_state():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"progress": previous_progress}))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await deny(update)
    await update.message.reply_text(
        "家庭下载助手已就绪。\n"
        "/search 片名 - 搜索资源\n"
        "/list - 查看下载任务\n"
        "也可以直接发送磁力链接或 .torrent 文件。"
    )


async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await deny(update)
    query_text = " ".join(context.args).strip()
    if not query_text:
        return await update.message.reply_text("用法：/search 电影或电视剧名称")
    status = await update.message.reply_text("正在查询 Jackett 索引站点…")
    try:
        results = await asyncio.to_thread(jackett_search, query_text)
        if not results:
            return await status.edit_text("没有找到结果。请检查 Jackett 中是否已配置并启用索引站点。")
        token = str(time.time_ns())
        search_cache[token] = results
        while len(search_cache) > 30:
            search_cache.pop(next(iter(search_cache)))
        lines = [f"搜索：<b>{html.escape(query_text)}</b>", ""]
        keyboard = []
        for index, item in enumerate(results):
            lines.append(
                f"<b>{index + 1}.</b> {html.escape(item['title'][:180])}\n"
                f"做种：{html.escape(item['seeders'] or '未知')} · 大小：{human_size(item['size'])}"
            )
            keyboard.append([InlineKeyboardButton(
                f"下载 #{index + 1}", callback_data=f"dl:{token}:{index}"
            )])
        await status.edit_text(
            "\n\n".join(lines), parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True,
        )
    except Exception as exc:
        log.exception("search failed")
        await status.edit_text(f"搜索失败：{html.escape(str(exc)[:300])}")


async def choose_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not authorized(update):
        await query.answer("未授权", show_alert=True)
        return
    await query.answer()
    try:
        _, token, index_text = query.data.split(":")
        item = search_cache[token][int(index_text)]
        await asyncio.to_thread(add_qbit_url, item["url"])
        await query.edit_message_text(
            f"已提交 qBittorrent：\n{html.escape(item['title'])}",
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        log.exception("add selected torrent failed")
        await query.message.reply_text(f"添加失败：{str(exc)[:300]}")


async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await deny(update)
    try:
        response = await asyncio.to_thread(qbit_request, "GET", "/api/v2/torrents/info")
        torrents = response.json()
        if not torrents:
            return await update.message.reply_text("当前没有下载任务。")
        lines = []
        for torrent in torrents[:20]:
            percent = float(torrent.get("progress", 0)) * 100
            name = html.escape(torrent.get("name", "未知任务")[:90])
            state = html.escape(torrent.get("state", "unknown"))
            lines.append(f"<b>{name}</b>\n{percent:.1f}% · {state}")
        await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.HTML)
    except Exception as exc:
        log.exception("list tasks failed")
        await update.message.reply_text(f"查询失败：{str(exc)[:300]}")


async def incoming_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await deny(update)
    message_text = (update.message.text or "").strip()
    magnet_match = re.search(r"magnet:\?[^\s]+", message_text)
    if magnet_match:
        url = magnet_match.group(0).rstrip("，。；;")
        try:
            await asyncio.to_thread(add_qbit_url, url)
            await update.message.reply_text("磁力链接已提交给 qBittorrent。")
        except Exception as exc:
            await update.message.reply_text(f"添加失败：{str(exc)[:300]}")
        return
    if message_text.startswith(("http://", "https://")):
        try:
            await asyncio.to_thread(add_qbit_url, message_text)
            await update.message.reply_text("下载链接已提交给 qBittorrent。")
        except Exception as exc:
            await update.message.reply_text(f"添加失败：{str(exc)[:300]}")


async def incoming_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update):
        return await deny(update)
    document = update.message.document
    if not document or not (document.file_name or "").lower().endswith(".torrent"):
        return await update.message.reply_text("目前只接收 .torrent 文件。")
    try:
        tg_file = await document.get_file()
        content = await tg_file.download_as_bytearray()
        files = {"torrents": (document.file_name, bytes(content), "application/x-bittorrent")}
        response = await asyncio.to_thread(
            qbit_request, "POST", "/api/v2/torrents/add",
            data={"category": QBIT_CATEGORY}, files=files,
        )
        validate_qbit_add_response(response)
        await update.message.reply_text("种子文件已提交给 qBittorrent。")
    except Exception as exc:
        log.exception("torrent upload failed")
        await update.message.reply_text(f"种子添加失败：{str(exc)[:300]}")


async def notify_completed(app: Application):
    while True:
        next_interval = IDLE_POLL_SECONDS
        try:
            response = await asyncio.to_thread(qbit_request, "GET", "/api/v2/torrents/info")
            torrents = response.json()
            current = {}
            has_incomplete_task = False
            for torrent in torrents:
                torrent_hash = torrent.get("hash", "")
                if not torrent_hash:
                    continue
                progress = float(torrent.get("progress", 0))
                current[torrent_hash] = progress
                if progress < 1.0:
                    has_incomplete_task = True
                old_progress = previous_progress.get(torrent_hash)
                # Notify only on a later transition to 100%; first-seen tasks form the baseline.
                if old_progress is not None and old_progress < 1.0 <= progress:
                    name = html.escape(torrent.get("name", "任务")[:150])
                    for user_id in ALLOWED_USERS:
                        await app.bot.send_message(
                            user_id, f"下载完成：<b>{name}</b>",
                            parse_mode=ParseMode.HTML,
                        )
            previous_progress.update(current)
            save_state()
            next_interval = POLL_SECONDS if has_incomplete_task else IDLE_POLL_SECONDS
        except Exception:
            # Keep the normal retry cadence after errors; do not enter a long idle sleep.
            log.exception("completion polling failed")
            next_interval = POLL_SECONDS
        await asyncio.sleep(next_interval)


async def post_init(app: Application):
    app.bot_data["completion_task"] = asyncio.create_task(
        notify_completed(app),
        name="completion-poller",
    )


async def post_stop(app: Application):
    task = app.bot_data.get("completion_task")
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def main():
    if not ALLOWED_USERS:
        raise RuntimeError("TELEGRAM_ALLOWED_USER_IDS is empty; configure your numeric Telegram user ID.")
    load_state()
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).post_stop(post_stop).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(CommandHandler("list", list_tasks))
    app.add_handler(CallbackQueryHandler(choose_result, pattern=r"^dl:"))
    app.add_handler(MessageHandler(filters.Document.ALL, incoming_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, incoming_text))
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
