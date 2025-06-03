import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict
import aiohttp
from telegram import Update, Chat
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from telegram.ext import ContextTypes
from variabili import JSONBIN_API_KEY, OWNER_USER_ID, LOG_BIN_ID

# Lista dei comandi validi del bot
VALID_COMMANDS = {
    '/trombola', '/estrai', '/stop', '/azzera',
    '/impostami', '/send_logs' 
}

# Buffer in memoria per i log
_log_buffer: List[Dict] = []
_buffer_lock = asyncio.Lock()
_flush_interval = 60  # secondi
_batch_size = 50      # flush quando buffer supera questa soglia

async def _flush_logs_periodically():
    async with aiohttp.ClientSession(headers={
        'X-Master-Key': JSONBIN_API_KEY,
        'Content-Type': 'application/json'
    }) as session:
        while True:
            await asyncio.sleep(_flush_interval)
            await _flush_buffer(session)

async def _flush_buffer(session: aiohttp.ClientSession):
    async with _buffer_lock:
        if not _log_buffer:
            return
        payload = _log_buffer.copy()
        _log_buffer.clear()

    url = f"https://api.jsonbin.io/v3/b/{LOG_BIN_ID}"
    try:
        async with session.put(url, json=payload) as resp:
            resp.raise_for_status()
    except Exception as e:
        async with _buffer_lock:
            _log_buffer[0:0] = payload  # re-inserimento all'inizio
        print(f"[LogFlushError] Errore salvataggio log: {e}")

async def init_logging_loop():
    asyncio.create_task(_flush_logs_periodically())

async def log_interaction(user_id: int, username: str, chat_id: int, command: str, group_name: str):
    # Controlla se il comando è valido e non è un messaggio di bottone
    if command not in VALID_COMMANDS:
        return

    entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'user_id': user_id,
        'username': username,
        'chat_id': chat_id,
        'group_name': group_name,
        'command': command
    }
    async with _buffer_lock:
        _log_buffer.append(entry)
        print(f"Log registrato: {entry}")  # Messaggio di conferma
        if len(_log_buffer) >= _batch_size:
            async with aiohttp.ClientSession(headers={
                'X-Master-Key': JSONBIN_API_KEY,
                'Content-Type': 'application/json'
            }) as session:
                await _flush_buffer(session)


async def _make_group_link(bot, chat_id: int) -> str:
    try:
        # 1) Provo a leggere le info del gruppo
        chat: Chat = await bot.get_chat(chat_id)
        # Se esiste già un invite_link pubblico, lo restituisco
        if chat.invite_link:
            return chat.invite_link
    except Exception as e:
        logging.debug(f"[make_group_link] get_chat fallito: {e}")
        # Non posso recuperare chat info, proseguo al tentativo di export
        pass

    # 2) Provo a esportarne uno nuovo (serve che il bot sia admin)
    try:
        invite_link = await bot.export_chat_invite_link(chat_id)
        return invite_link
    except Exception as e:
        logging.debug(f"[make_group_link] export_chat_invite_link fallito: {e}")
        # Se qui fallisce (bot non admin o gruppo vieta inviti), ricado nel fallback
        pass

    # 3) Nessun invite disponibile: restituisco None
    return None

async def send_logs_by_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != int(OWNER_USER_ID):
        await update.message.reply_text("🚫 Non autorizzato.")
        return

    args = context.args
    specific_date = None
    if args:
        try:
            specific_date = datetime.strptime(args[0], "%d-%m-%Y").date()
        except ValueError:
            await update.message.reply_text("Formato data invalido, usa GG-MM-YYYY.")
            return

    all_logs = await _fetch_all_logs()
    cutoff = datetime.utcnow() - timedelta(hours=24)
    by_group: Dict[int, List[dict]] = {}
    for log in all_logs:
        ts = datetime.fromisoformat(log['timestamp'])
        if specific_date:
            if ts.date() != specific_date:
                continue
        elif ts < cutoff:
            continue
        gid = log['chat_id']
        by_group.setdefault(gid, []).append(log)

    if not by_group:
        await update.message.reply_text("⚠️ Nessun log trovato.")
        return

    cumulative_message = []
    for gid, logs in by_group.items():
        gname = escape_markdown(logs[0]['group_name'], version=2)
        invite_link = await _make_group_link(context.bot, gid)
        if invite_link:
            group_link = invite_link
        else:
            group_link = f"<ID non invertibile: {gid}>"

        grid = escape_markdown(str(gid), version=2)
        cumulative_message.append(f"*Log gruppo\\:* _[{gname}]({group_link})_ \\[`{grid}`\\]\n")

        for log in logs:
            if log['command'] == logs[0]['group_name'] or log['command'] not in VALID_COMMANDS:
                continue
            else:
                dt = datetime.fromisoformat(log['timestamp'])

                cmd = escape_markdown(log['command'], version=2)
                user = escape_markdown(log['username'], version=2)
                log_message = f"*👤 Utente\\:* @{user}\n*ℹ️ Comando\\:* {cmd}\n\n"

                if sum(len(msg) for msg in cumulative_message) + len(log_message) > 4000:
                    await update.message.reply_text(''.join(cumulative_message), parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
                    cumulative_message = []

                cumulative_message.append(log_message)

        cumulative_message.append("\n")

    if cumulative_message:
        await update.message.reply_text(''.join(cumulative_message), parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)

async def send_all_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != int(OWNER_USER_ID):
        await update.message.reply_text("🚫 Non autorizzato.")
        return

    all_logs = await _fetch_all_logs()
    if not all_logs:
        await update.message.reply_text("⚠️ Nessun log trovato.")
        return

    cumulative_message = ["*_Ecco tutti i log registrati\\:_*\n\n"]

    for log in all_logs:
        if log['command'] not in VALID_COMMANDS:
                continue
        else:
            dt = datetime.fromisoformat(log['timestamp'])
            timestamp = escape_markdown(dt.strftime('%d-%m-%Y ore %H:%M'), version=2)

            username = escape_markdown(log['username'], version=2)
            user_id = log['user_id']
            command = escape_markdown(log['command'], version=2)
            group_name = escape_markdown(log['group_name'], version=2)
            chat_id = log['chat_id']

            invite_link = await _make_group_link(context.bot, chat_id)
            if invite_link:
                group_link = invite_link
            else:
                group_link = f"<ID non invertibile: {chat_id}>"

            chat_id_esc = escape_markdown(str(chat_id), version=2)

            log_message = (
                f"*🕐 Data e Ora\\:* _{timestamp}_\n"
                f"*👤 Utente\\:* _@{username} \\[`{user_id}`\\]_\n"
                f"*ℹ️ Comando\\:* _{command}_\n"
                f"*🌐 Gruppo\\:* _[{group_name}]({group_link}) \\[`{chat_id_esc}`\\]_\n\n"
            )

            if sum(len(msg) for msg in cumulative_message) + len(log_message) > 4000:
                await update.message.reply_text(''.join(cumulative_message), parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
                cumulative_message = []

            cumulative_message.append(log_message)

    if cumulative_message:
        await update.message.reply_text(''.join(cumulative_message), parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)

async def _fetch_all_logs() -> List[dict]:
    url = f"https://api.jsonbin.io/v3/b/{LOG_BIN_ID}/latest"
    headers = {'X-Master-Key': JSONBIN_API_KEY}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()
            record = data.get('record', {})
            if isinstance(record, dict) and 'record' in record:
                return record['record']
            if isinstance(record, list):
                return record
    return []


