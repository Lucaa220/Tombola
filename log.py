import os
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict
import aiohttp
from telegram import Update
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from telegram.ext import ContextTypes
from variabili import JSONBIN_API_KEY, OWNER_USER_ID, LOG_BIN_ID

# Lista dei comandi validi del bot
VALID_COMMANDS = {
    '/trombola', '/estrai', '/stop', '/azzera',
    '/impostami'
}

# Buffer in memoria per i log
_log_buffer: List[Dict] = []
_buffer_lock = asyncio.Lock()
_flush_interval = 60  # secondi
_batch_size = 50      # flush quando buffer supera questa soglia

async def _flush_logs_periodically():
    """
    Task di background: ogni _flush_interval secondi, invia il buffer a JSONBin.
    """
    async with aiohttp.ClientSession(headers={
        'X-Master-Key': JSONBIN_API_KEY,
        'Content-Type': 'application/json'
    }) as session:
        while True:
            await asyncio.sleep(_flush_interval)
            await _flush_buffer(session)

async def _flush_buffer(session: aiohttp.ClientSession):
    """
    Invia logs accumulati al bin, poi svuota il buffer.
    """
    async with _buffer_lock:
        if not _log_buffer:
            return
        # Prepara payload: un array di entry
        payload = _log_buffer.copy()
        _log_buffer.clear()

    url = f"https://api.jsonbin.io/v3/b/{LOG_BIN_ID}"
    try:
        async with session.put(url, json=payload) as resp:
            resp.raise_for_status()
    except Exception as e:
        # In caso di errore, reinserisci i dati nel buffer
        async with _buffer_lock:
            _log_buffer[0:0] = payload  # re-inserimento all'inizio
        print(f"[LogFlushError] Errore salvataggio log: {e}")

async def init_logging_loop():
    """
    Avvia il task di flush periodico. Chiamare all'avvio del bot.
    """
    asyncio.create_task(_flush_logs_periodically())

async def log_interaction(user_id: int, username: str, chat_id: int, command: str, group_name: str):
    """
    Registra nel buffer solo i comandi validi.
    """
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
        # Se buffer grande, flush immediato
        if len(_log_buffer) >= _batch_size:
            # usa session temporanea
            async with aiohttp.ClientSession(headers={
                'X-Master-Key': JSONBIN_API_KEY,
                'Content-Type': 'application/json'
            }) as session:
                await _flush_buffer(session)

async def send_logs_by_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Comando /log: mostra i log raggruppati per chat nelle ultime 24 ore o per data.
    Solo OWNER_USER_ID può usarlo.
    """
    user_id = update.effective_user.id
    if user_id != int(OWNER_USER_ID):
        await update.message.reply_text("🚫 Non autorizzato.")
        return

    args = context.args
    specific_date = None
    if args:
        try:
            specific_date = datetime.strptime(args[0], "%Y-%m-%d").date()
        except ValueError:
            await update.message.reply_text("Formato data invalido, usa AAAA-MM-GG.")
            return

    all_logs = await _fetch_all_logs()
    # Filtra entrate
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

    # Costruisci testo
    parts = []
    for gid, logs in by_group.items():
        gname = escape_markdown(logs[0]['group_name'], version=2)
        parts.append(f"*Log gruppo:* {gname} (`{gid}`)\n")
        for log in logs:
            t = datetime.fromisoformat(log['timestamp']).strftime('%H:%M:%S')
            cmd = escape_markdown(log['command'], version=2)
            user = escape_markdown(log['username'], version=2)
            parts.append(f"`[{t}]` {user} -> {cmd}\n")
        parts.append("\n")
    
    # Unire tutto il testo e applicare escape
    text = ''.join(parts)
    escaped_text = escape_markdown(text, version=2)

    # Spezza in chunk
    for i in range(0, len(escaped_text), 4000):
        await update.message.reply_text(escaped_text[i:i+4000], parse_mode=ParseMode.MARKDOWN_V2)

async def _fetch_all_logs() -> List[dict]:
    url = f"https://api.jsonbin.io/v3/b/{LOG_BIN_ID}/latest"
    headers = {'X-Master-Key': JSONBIN_API_KEY}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.json()
            record = data.get('record', {})
            # Gestione incapsulamenti
            if isinstance(record, dict) and 'record' in record:
                return record['record']
            if isinstance(record, list):
                return record
    return []
