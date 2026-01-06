import logging
import asyncio
from datetime import datetime, timedelta, time as _time
from typing import List, Dict
from telegram import Update, Chat
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
import os
from utils import safe_escape_markdown as esc
import io
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import timezone
import json
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

    # Usa fuso orario locale per il timestamp
    entry = {
        'timestamp': datetime.now().astimezone().isoformat(),
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
                flattened.append(entry)
        return flattened
    except Exception as e:
        logger.error(f"[fetch_all_logs_from_firebase] Errore nel recuperare i log: {e}")
        return []


def _get_all_group_ids() -> List[int]:
    try:
        data = db.reference("logs").get() or {}
        return [int(k) for k in data.keys() if str(k).isdigit()]
    except Exception as e:
        logger.error(f"[get_all_group_ids] Errore recupero gruppi: {e}")
        return []


def _fetch_logs_for_group_in_range(group_id: int, start_iso: str = None, end_iso: str = None) -> List[Dict]:
    try:
        ref = db.reference(f"logs/{group_id}")
        # Per evitare la necessità di avere .indexOn definito nelle regole,
        # recuperiamo tutti i log del gruppo e applichiamo il filtro lato client.
        data = ref.get() or {}
        flattened = []
        for entry in (data.values() if isinstance(data, dict) else []):
            try:
                ts = entry.get('timestamp')
            except Exception:
                ts = None

            # Se sono specificati range, filtra confrontando le ISO timestamps.
            # Le stringhe ISO8601 sono ordinabili lessicograficamente, quindi
            # il confronto diretto funziona per i confronti di range.
            if ts and (start_iso or end_iso):
                try:
                    if start_iso and ts < start_iso:
                        continue
                    if end_iso and ts > end_iso:
                        continue
                except Exception:
                    # In caso di valori malformati, includi l'entry per sicurezza
                    pass

            flattened.append(entry)

        return flattened
    except Exception as e:
        logger.error(f"[fetch_logs_for_group_in_range] Errore recupero logs per {group_id}: {e}")
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

    # Calcola intervallo in ISO locale
    now_local = datetime.now().astimezone()
    if specific_date:
        local_tz = now_local.tzinfo
        start_dt = datetime.combine(specific_date, _time.min).replace(tzinfo=local_tz)
        end_dt = (start_dt + timedelta(days=1))
    else:
        end_dt = now_local
        start_dt = now_local - timedelta(hours=24)

    start_iso = start_dt.isoformat()
    end_iso = end_dt.isoformat()

    by_group: Dict[int, List[dict]] = {}
    group_ids = _get_all_group_ids()
    for gid in group_ids:
        entries = _fetch_logs_for_group_in_range(gid, start_iso=start_iso, end_iso=end_iso)
        if not entries:
            continue
        # Filtra valid commands e aggiungi
        for log in entries:
            if log.get('command') not in VALID_COMMANDS:
                continue
            by_group.setdefault(gid, []).append(log)

    if not by_group:
        await update.message.reply_text("⚠️ Nessun log trovato.")
        return

    cumulative_message = []
    for gid, logs in by_group.items():
        gname = esc(logs[0]['group_name'])
        invite_link = await _make_group_link(context.bot, gid)
        if invite_link:
            group_link = invite_link
        else:
            group_link = f"<ID non invertibile: {gid}>"

        grid = esc(str(gid))
        cumulative_message.append(f"*Log gruppo\\:* _[{gname}]({group_link})_ \\[`{grid}`\\]\n")

        for log in logs:
            # abbiamo già filtrato per valid_commands
            try:
                dt = datetime.fromisoformat(log['timestamp'])
                # normalizza a fuso locale
                dt_local = dt.astimezone()
            except Exception:
                continue
            cmd = esc(log.get('command'))
            user = esc(log.get('username'))
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

    # Recuperiamo tutti i gruppi e carichiamo logs per gruppo
    group_ids = _get_all_group_ids()
    all_logs = []
    for gid in group_ids:
        entries = _fetch_logs_for_group_in_range(gid)
        for e in entries:
            if e.get('command') in VALID_COMMANDS:
                all_logs.append(e)

    if not all_logs:
        await update.message.reply_text("⚠️ Nessun log trovato.")
        return

    cumulative_message = ["*_Ecco tutti i log registrati\\:_*\n\n"]

    for log in all_logs:

        try:
            dt = datetime.fromisoformat(log['timestamp'])
            dt_local = dt.astimezone()
        except Exception:
            continue

        timestamp = esc(dt_local.strftime('%d-%m-%Y ore %H:%M'))
        username = esc(log.get('username'))
        user_id_log = log['user_id']
        command = esc(log.get('command'))
        group_name = esc(log.get('group_name'))
        chat_id = log['chat_id']

        invite_link = await _make_group_link(context.bot, chat_id)
        if invite_link:
            group_link = invite_link
        else:
            group_link = f"<ID non invertibile: {chat_id}>"

        chat_id_esc = esc(str(chat_id))

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


async def logstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Invia statistiche delle ultime 24 ore solo al founder in chat privata.

    Statistiche: gruppi attivi, partite avviate (/trombola), estrazioni (/estrai), errori (se presenti nei log)
    Invia anche un grafico con l'andamento orario delle attività.
    """
    user_id = update.effective_user.id
    # Controllo founder
    if user_id != OWNER_USER_ID:
        return

    # Deve essere usato solo in privato
    chat = update.effective_chat
    if getattr(chat, 'type', None) != 'private':
        return

    now_local = datetime.now().astimezone()
    start_dt = now_local - timedelta(hours=24)

    # Recupera tutti i log e filtra per le ultime 24h
    all_logs = _fetch_all_logs_from_firebase()
    recent_logs = []
    for entry in all_logs:
        ts_raw = entry.get('timestamp')
        if not ts_raw:
            continue
        try:
            dt = datetime.fromisoformat(ts_raw)
            dt_local = dt.astimezone()
        except Exception:
            continue
        if dt_local >= start_dt and dt_local <= now_local:
            recent_logs.append((dt_local, entry))

    if not recent_logs:
        await context.bot.send_message(chat_id=chat.id, text="Nessuna attività nelle ultime 24 ore.")
        return

    # Statistiche
    groups_active = set()
    count_trombola = 0
    count_estrai = 0
    count_errors = 0
    hourly_counts = {}

    for dt_local, entry in recent_logs:
        gid = entry.get('chat_id') or entry.get('group_id')
        if gid:
            groups_active.add(gid)
        cmd = entry.get('command')
        if cmd == '/trombola':
            count_trombola += 1
        if cmd == '/estrai':
            count_estrai += 1
        # Consideriamo eventuali voci di errori se presenti
        if cmd and str(cmd).lower().startswith('error'):
            count_errors += 1

        # hour bucket
        hour = dt_local.replace(minute=0, second=0, microsecond=0)
        hourly_counts[hour] = hourly_counts.get(hour, 0) + 1

    # Prepara grafico orario per le ultime 24 ore
    hours = []
    counts = []
    cur = start_dt.replace(minute=0, second=0, microsecond=0)
    while cur <= now_local:
        hours.append(cur)
        counts.append(hourly_counts.get(cur, 0))
        cur = cur + timedelta(hours=1)

    # Plot
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(hours, counts, width=0.03)
    ax.set_title('Attività bot ultime 24 ore')
    ax.set_xlabel('Ora')
    ax.set_ylabel('Eventi')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d-%H:%M'))
    fig.autofmt_xdate(rotation=45)

    bio = io.BytesIO()
    plt.tight_layout()
    fig.savefig(bio, format='png')
    plt.close(fig)
    bio.seek(0)

    summary = (
        f"*Statistiche ultime 24 ore\\:*\n\n"
        f"_👥 Gruppi attivi\\: {len(groups_active)}_\n"
        f"_🆕 Partite avviate\\: {count_trombola}_\n"
        f"_🏧 Estrazioni\\: {count_estrai}_\n"
        f"_🆘 Errori rilevati: {count_errors}_\n"
    )

    # Telegram ha un limite di ~1024 caratteri per caption; tronchiamo se necessario
    if len(summary) > 1000:
        summary = summary[:997] + '...'

    try:
        await context.bot.send_photo(chat_id=chat.id, photo=bio, caption=summary, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        # Se l'invio fallisce, invia un messaggio di testo come fallback (escaped)
        try:
            await context.bot.send_message(chat_id=chat.id, text=summary, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception:
            logger.error(f"Errore inviando il grafico o il caption: {e}")


async def logactivity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra attività del bot (ultimi 7 giorni).

    Output testuale (private, solo founder): barre orarie su intervalli 2h e attività giornaliera.
    """
    user_id = update.effective_user.id
    if user_id != OWNER_USER_ID:
        return

    chat = update.effective_chat
    if getattr(chat, 'type', None) != 'private':
        return

    now_local = datetime.now().astimezone()
    start_dt = now_local - timedelta(days=7)

    # Recupera tutti i log e filtra per l'intervallo
    all_logs = _fetch_all_logs_from_firebase()
    recent = []
    for entry in all_logs:
        ts = entry.get('timestamp')
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts).astimezone()
        except Exception:
            continue
        if dt >= start_dt and dt <= now_local:
            recent.append((dt, entry))

    # Per contare una partita: cerchiamo, per ogni gruppo, la sequenza
    # `/trombola` seguita da `/estrai`. Ogni coppia corrisponde a 1 partita.
    # Raggruppiamo i log per chat_id e li ordiniamo temporalmente.
    by_group = {}
    for dt, entry in recent:
        gid = entry.get('chat_id') or entry.get('group_id')
        if not gid:
            continue
        by_group.setdefault(gid, []).append((dt, entry))

    matched_games = []  # lista di datetime (usiamo il timestamp dell'/estrai)
    for gid, entries in by_group.items():
        # ordina per timestamp
        entries.sort(key=lambda x: x[0])
        i = 0
        n = len(entries)
        while i < n:
            dt_i, e_i = entries[i]
            cmd_i = e_i.get('command')
            if cmd_i == '/trombola':
                # cerca un /estrai dopo i
                j = i + 1
                found = False
                while j < n:
                    dt_j, e_j = entries[j]
                    if e_j.get('command') == '/estrai':
                        # conto una partita usando il timestamp dell'estrazione
                        matched_games.append(dt_j)
                        i = j + 1
                        found = True
                        break
                    j += 1
                if not found:
                    # nessuna estrazione successiva trovata, avanziamo di 1
                    i += 1
            else:
                i += 1

    # Ora abbiamo tutti i timestamp delle partite concluse (basate su /estrai)
    # Buckets orari 2h: 0-2,2-4,...,22-24
    buckets = [(i, i+2) for i in range(0, 24, 2)]
    bucket_counts = {i: 0 for i in range(len(buckets))}

    # Weekly counts Mon-Sun
    weekday_counts = {i: 0 for i in range(7)}

    for dt in matched_games:
        h = dt.hour
        bi = h // 2
        bucket_counts[bi] = bucket_counts.get(bi, 0) + 1
        weekday_counts[dt.weekday()] = weekday_counts.get(dt.weekday(), 0) + 1

    # Genera grafici: (1) attività per giorno della settimana, (2) attività per fasce orarie (2h)
    weekday_labels = ['Lun','Mar','Mer','Gio','Ven','Sab','Dom']
    weekday_vals = [weekday_counts.get(i, 0) for i in range(7)]

    hour_labels = [f"{s:02d}–{e:02d}" for (s, e) in buckets]
    hour_vals = [bucket_counts.get(i, 0) for i in range(len(buckets))]

    try:
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 7), constrained_layout=True)

        # Grafico per giorni della settimana
        ax1.bar(weekday_labels, weekday_vals, color='tab:blue')
        ax1.set_title('Attività per giorno (ultimi 7 giorni)')
        ax1.set_ylabel('Partite')

        # Grafico per fasce orarie (2h)
        ax2.bar(hour_labels, hour_vals, color='tab:orange')
        ax2.set_title('Attività per fascia oraria (2h)')
        ax2.set_ylabel('Partite')
        ax2.set_xlabel('Fascia oraria')

        plt.setp(ax1.get_xticklabels(), rotation=0)
        plt.setp(ax2.get_xticklabels(), rotation=45)

        bio = io.BytesIO()
        fig.savefig(bio, format='png')
        plt.close(fig)
        bio.seek(0)

        caption = f"_🔙  Attività rilevata\\: {sum(weekday_vals)} partite negli ultimi 7 giorni_"
        await context.bot.send_photo(chat_id=chat.id, photo=bio, caption=caption, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        logger.error(f"Errore generando o inviando i grafici /logactivity: {e}")


async def logclean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Elimina i log più vecchi di N giorni. Uso: /logclean <days>

    Solo founder, solo in privato. Restituisce il numero di log rimossi
    e una stima della memoria liberata in MB.
    """
    user_id = update.effective_user.id
    if user_id != OWNER_USER_ID:
        return

    chat = update.effective_chat
    if getattr(chat, 'type', None) != 'private':
        return

    args = context.args
    if not args:
        await context.bot.send_message(chat_id=chat.id, text="Uso: /logclean <giorni> (es. /logclean 30)")
        return

    try:
        days = int(args[0])
        if days < 0:
            raise ValueError()
    except Exception:
        await context.bot.send_message(chat_id=chat.id, text="Parametro invalido: inserisci un numero di giorni positivo.")
        return

    now_local = datetime.now().astimezone()
    cutoff = now_local - timedelta(days=days)

    total_deleted = 0
    total_bytes = 0

    group_ids = _get_all_group_ids()
    for gid in group_ids:
        ref = db.reference(f"logs/{gid}")
        data = ref.get() or {}
        if not isinstance(data, dict):
            continue
        for push_id, entry in list(data.items()):
            ts = entry.get('timestamp')
            delete_it = False
            if not ts:
                delete_it = True
            else:
                try:
                    dt = datetime.fromisoformat(ts).astimezone()
                    if dt < cutoff:
                        delete_it = True
                except Exception:
                    delete_it = True

            if delete_it:
                try:
                    # calcola dimensione stimata
                    try:
                        j = json.dumps(entry, ensure_ascii=False)
                        size = len(j.encode('utf-8'))
                    except Exception:
                        size = 0
                    # elimina
                    try:
                        ref.child(push_id).set(None)
                    except Exception:
                        try:
                            ref.child(push_id).delete()
                        except Exception:
                            # fallback set None
                            ref.child(push_id).set(None)
                    total_deleted += 1
                    total_bytes += size
                except Exception as e:
                    logger.error(f"Errore eliminando log {push_id} in {gid}: {e}")

    mb_saved = total_bytes / (1024 * 1024)
    mb_saved_str = f"{mb_saved:.2f} MB" if mb_saved >= 0.01 else "<0.01 MB"

    await context.bot.send_message(chat_id=chat.id, text=f"*🗑 Eliminati {total_deleted} log\\.*\n_🔋 Memoria stimata liberata\\: {mb_saved_str}_", parse_mode=ParseMode.MARKDOWN_V2)


# --------------------------------------------------------------------
# HELPER PER RECUPERARE (O CREARE) UN LINK DI INVITO AL GRUPPO
# --------------------------------------------------------------------
_group_link_cache = {}
_group_link_ttl = 60 * 60  # 1 hour


async def _make_group_link(bot, chat_id: int) -> str:
    # cache
    now_ts = asyncio.get_event_loop().time()
    cached = _group_link_cache.get(chat_id)
    if cached and (now_ts - cached[1]) < _group_link_ttl:
        return cached[0]

    invite = None
    try:
        chat: Chat = await bot.get_chat(chat_id)
        invite = getattr(chat, 'invite_link', None)
    except Exception as e:
        logging.debug(f"[make_group_link] get_chat fallito: {e}")

    if not invite:
        try:
            invite = await bot.export_chat_invite_link(chat_id)
        except Exception as e:
            logging.debug(f"[make_group_link] export_chat_invite_link fallito: {e}")
            invite = None

    # store in cache even if None to avoid repeated failing calls
    _group_link_cache[chat_id] = (invite, now_ts)
    return invite
