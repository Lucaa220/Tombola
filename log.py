import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict
from telegram import Update, Chat
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from telegram.ext import ContextTypes
import os
# --------------------------------------------------------------------
# MODIFICA: rimuoviamo tutti i riferimenti a JSONBin
# --------------------------------------------------------------------
# import aiohttp
# from variabili import JSONBIN_API_KEY, OWNER_USER_ID, LOG_BIN_ID

# --------------------------------------------------------------------
# IMPORT PER FIREBASE
# --------------------------------------------------------------------
import firebase_admin
from firebase_admin import db, credentials

# --------------------------------------------------------------------
# Caricamento credenziali Firebase Admin (assicurati di avere GOOGLE_APPLICATION_CREDENTIALS e DATABASE_URL impostati)
# --------------------------------------------------------------------
SERVICE_ACCOUNT_PATH = None  # Il path viene preso dalla variabile d'ambiente GOOGLE_APPLICATION_CREDENTIALS
DATABASE_URL = None         # Preso dalla variabile d'ambiente FIREBASE_DATABASE_URL

# Inizializza l'app Firebase Admin se non già fatto
if not firebase_admin._apps:
    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    firebase_admin.initialize_app(cred, {
        "databaseURL": DATABASE_URL or os.getenv("FIREBASE_DATABASE_URL")
    })

# --------------------------------------------------------------------
# Costanti e configurazioni
# --------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_COMMANDS = {
    '/trombola', '/estrai', '/stop', '/azzera',
    '/impostami', '/send_logs'
}

OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))  # Usa variabile d'ambiente OWNER_USER_ID

# --------------------------------------------------------------------
# Funzione che registra immediatamente ogni log su Firebase
# --------------------------------------------------------------------
async def log_interaction(user_id: int, username: str, chat_id: int, command: str, group_name: str):
    """
    Registra un'interazione (se il comando è valido) direttamente in Firebase.
    Ogni voce viene salvata sotto /logs/{chat_id}/{push_id}.
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
    try:
        ref = db.reference(f"logs/{chat_id}")
        new_ref = ref.push()
        new_ref.set(entry)
        logger.info(f"Log registrato su Firebase: {entry}")
    except Exception as e:
        logger.error(f"[log_interaction] Errore nel salvare log su Firebase: {e}")


# --------------------------------------------------------------------
# HELPERS PER CARICARE I LOG DA FIREBASE
# --------------------------------------------------------------------
def _fetch_all_logs_from_firebase() -> List[Dict]:
    """
    Recupera tutti i log disponibili sotto /logs da Firebase.
    Restituisce una lista di dizionari, ognuno rappresenta un log entry.
    """
    try:
        all_logs_dict = db.reference("logs").get() or {}
        flattened: List[Dict] = []
        # all_logs_dict ha struttura { chat_id: { push_id: entry_dict, ... }, ... }
        for gid_str, entries in all_logs_dict.items():
            if not isinstance(entries, dict):
                continue
            for entry in entries.values():
                # entry già contiene 'chat_id', ma assicuriamoci che sia corretto
                flattened.append(entry)
        return flattened
    except Exception as e:
        logger.error(f"[fetch_all_logs_from_firebase] Errore nel recuperare i log: {e}")
        return []


# --------------------------------------------------------------------
# FUNZIONE /send_logs: invia i log raggruppati per gruppo (ultima 24h o data specifica)
# --------------------------------------------------------------------
async def send_logs_by_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_USER_ID:
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

    all_logs = _fetch_all_logs_from_firebase()
    cutoff = datetime.utcnow() - timedelta(hours=24)
    by_group: Dict[int, List[dict]] = {}
    for log in all_logs:
        try:
            ts = datetime.fromisoformat(log['timestamp'])
        except Exception:
            continue

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
            if log['command'] not in VALID_COMMANDS:
                continue

            dt = datetime.fromisoformat(log['timestamp'])
            cmd = escape_markdown(log['command'], version=2)
            user = escape_markdown(log['username'], version=2)
            log_message = f"*👤 Utente\\:* @{user}\n*ℹ️ Comando\\:* {cmd}\n\n"

            if sum(len(msg) for msg in cumulative_message) + len(log_message) > 4000:
                await update.message.reply_text(
                    ''.join(cumulative_message),
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=True
                )
                cumulative_message = []

            cumulative_message.append(log_message)

        cumulative_message.append("\n")

    if cumulative_message:
        await update.message.reply_text(
            ''.join(cumulative_message),
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True
        )


# --------------------------------------------------------------------
# FUNZIONE /send_all_logs: invia TUTTI i log senza filtro
# --------------------------------------------------------------------
async def send_all_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_USER_ID:
        await update.message.reply_text("🚫 Non autorizzato.")
        return

    all_logs = _fetch_all_logs_from_firebase()
    if not all_logs:
        await update.message.reply_text("⚠️ Nessun log trovato.")
        return

    cumulative_message = ["*_Ecco tutti i log registrati\\:_*\n\n"]

    for log in all_logs:
        if log['command'] not in VALID_COMMANDS:
            continue

        try:
            dt = datetime.fromisoformat(log['timestamp'])
        except Exception:
            continue

        timestamp = escape_markdown(dt.strftime('%d-%m-%Y ore %H:%M'), version=2)
        username = escape_markdown(log['username'], version=2)
        user_id_log = log['user_id']
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
            f"*👤 Utente\\:* _@{username} \\[`{user_id_log}`\\]_\n"
            f"*ℹ️ Comando\\:* _{command}_\n"
            f"*🌐 Gruppo\\:* _[{group_name}]({group_link}) \\[`{chat_id_esc}`\\]_\n\n"
        )

        if sum(len(msg) for msg in cumulative_message) + len(log_message) > 4000:
            await update.message.reply_text(
                ''.join(cumulative_message),
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True
            )
            cumulative_message = []

        cumulative_message.append(log_message)

    if cumulative_message:
        await update.message.reply_text(
            ''.join(cumulative_message),
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True
        )


# --------------------------------------------------------------------
# HELPER PER RECUPERARE (O CREARE) UN LINK DI INVITO AL GRUPPO
# --------------------------------------------------------------------
async def _make_group_link(bot, chat_id: int) -> str:
    try:
        chat: Chat = await bot.get_chat(chat_id)
        if chat.invite_link:
            return chat.invite_link
    except Exception as e:
        logging.debug(f"[make_group_link] get_chat fallito: {e}")

    try:
        invite_link = await bot.export_chat_invite_link(chat_id)
        return invite_link
    except Exception as e:
        logging.debug(f"[make_group_link] export_chat_invite_link fallito: {e}")

    return None
