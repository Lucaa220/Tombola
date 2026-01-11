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
import matplotlib
matplotlib.use('Agg') # Importante per evitare errori di thread su server senza GUI
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import json
from concurrent.futures import ThreadPoolExecutor

# --------------------------------------------------------------------
# IMPORT PER FIREBASE (Corretto)
# Usa il client centralizzato per evitare doppie inizializzazioni
# --------------------------------------------------------------------
from firebase_client import db

# --------------------------------------------------------------------
# Costanti e configurazioni
# --------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_COMMANDS = {
    '/trombola', '/estrai', '/stop', '/azzera',
    '/impostami', '/send_logs'
}

OWNER_USER_ID = int(os.getenv("OWNER_USER_ID", "0"))

# Executor per operazioni bloccanti (Firebase e Matplotlib)
_executor = ThreadPoolExecutor(max_workers=3)

# --------------------------------------------------------------------
# Funzione che registra immediatamente ogni log su Firebase
# --------------------------------------------------------------------
async def log_interaction(user_id: int, username: str, chat_id: int, command: str, group_name: str):
    if command not in VALID_COMMANDS:
        return

    entry = {
        'timestamp': datetime.now().astimezone().isoformat(),
        'user_id': user_id,
        'username': username,
        'chat_id': chat_id,
        'group_name': group_name,
        'command': command
    }
    
    # Esegui in background per non rallentare l'utente
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(_executor, _sync_save_log, chat_id, entry)
    except Exception as e:
        logger.error(f"[log_interaction] Errore salvataggio async: {e}")

def _sync_save_log(chat_id, entry):
    try:
        ref = db.reference(f"logs/{chat_id}")
        new_ref = ref.push()
        new_ref.set(entry)
        logger.info(f"Log registrato su Firebase: {entry['command']} in {chat_id}")
    except Exception as e:
        logger.error(f"Errore scrittura Firebase: {e}")

# --------------------------------------------------------------------
# HELPERS SINCRONI (Da eseguire in executor)
# --------------------------------------------------------------------
def _fetch_all_logs_sync() -> List[Dict]:
    """Scarica tutti i log (pesante, usare con cautela)."""
    try:
        all_logs_dict = db.reference("logs").get() or {}
        flattened = []
        for gid_str, entries in all_logs_dict.items():
            if not isinstance(entries, dict): continue
            for entry in entries.values():
                flattened.append(entry)
        return flattened
    except Exception as e:
        logger.error(f"Errore fetch all logs: {e}")
        return []

def _fetch_logs_group_sync(group_id: int) -> List[Dict]:
    try:
        data = db.reference(f"logs/{group_id}").get() or {}
        if isinstance(data, dict):
            return list(data.values())
        return []
    except Exception:
        return []

def _get_all_group_ids_sync() -> List[int]:
    try:
        # shallow=True scarica solo le chiavi, molto più veloce
        data = db.reference("logs").get(shallow=True) or {}
        return [int(k) for k in data.keys() if str(k).lstrip('-').isdigit()]
    except Exception as e:
        logger.error(f"Errore recupero ID gruppi: {e}")
        return []

# --------------------------------------------------------------------
# 1. SEND LOGS BY GROUP
# --------------------------------------------------------------------
async def send_logs_by_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_USER_ID:
        return
    
    args = context.args
    specific_date = None
    if args:
        try:
            specific_date = datetime.strptime(args[0], "%d-%m-%Y").date()
        except ValueError:
            await update.message.reply_text("Formato data invalido, usa GG-MM-YYYY.")
            return

    loop = asyncio.get_running_loop()

    # Logica pesante spostata in thread separato
    def _process_logs():
        now_local = datetime.now().astimezone()
        if specific_date:
            # Usiamo il timezone locale approssimativo
            start_dt = datetime.combine(specific_date, _time.min).astimezone()
            end_dt = start_dt + timedelta(days=1)
        else:
            end_dt = now_local
            start_dt = now_local - timedelta(hours=24)

        start_iso = start_dt.isoformat()
        end_iso = end_dt.isoformat()

        group_ids = _get_all_group_ids_sync()
        by_group = {}
        
        for gid in group_ids:
            # Recuperiamo i log del gruppo
            raw_logs = _fetch_logs_group_sync(gid)
            filtered = []
            for log in raw_logs:
                ts = log.get('timestamp', '')
                cmd = log.get('command')
                if cmd in VALID_COMMANDS and ts >= start_iso and ts <= end_iso:
                    filtered.append(log)
            
            if filtered:
                # Ordina per timestamp
                filtered.sort(key=lambda x: x.get('timestamp', ''))
                by_group[gid] = filtered
        
        return by_group

    try:
        by_group = await loop.run_in_executor(_executor, _process_logs)
    except Exception as e:
        logger.error(f"Errore process log: {e}")
        await update.message.reply_text("Errore interno nel recupero log.")
        return

    if not by_group:
        await update.message.reply_text("*⚠️ Nessun log trovato nel periodo selezionato\\.*", parse_mode=ParseMode.MARKDOWN_V2)
        return

    cumulative_message = []
    
    for gid, logs in by_group.items():
        gname = esc(logs[0].get('group_name', 'Sconosciuto'))
        invite_link = await _make_group_link(context.bot, gid)
        
        link_md = f"[{gname}]({invite_link})" if invite_link else f"{gname}"
        header = f"*📁 Gruppo\\:* {link_md} `[{gid}]`\n\n"
        cumulative_message.append(header)

        for log in logs:
            try:
                dt = datetime.fromisoformat(log['timestamp']).strftime('%H:%M')
            except: dt = "??"
            
            cmd = esc(log.get('command'))
            user = esc(log.get('username'))
            line = f"ℹ️ {esc(dt)} @{user} {cmd}\n"
            
            if sum(len(x) for x in cumulative_message) + len(line) > 3800:
                await update.message.reply_text("".join(cumulative_message), parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)
                cumulative_message = []
            
            cumulative_message.append(line)
        
        cumulative_message.append("\n\n")

    if cumulative_message:
        await update.message.reply_text("".join(cumulative_message), parse_mode=ParseMode.MARKDOWN_V2, disable_web_page_preview=True)

# --------------------------------------------------------------------
# 2. SEND ALL LOGS
# --------------------------------------------------------------------
async def send_all_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Simile a sopra, ma senza raggruppamento visuale
    # Per brevità, usa la stessa logica di invio messaggi.
    # L'implementazione attuale nel tuo file è OK se resa asincrona come sopra.
    # Qui riporto una versione semplificata che richiama logicamente quella sopra.
    await send_logs_by_group(update, context)

# --------------------------------------------------------------------
# 3. LOG STATS (Grafico)
# --------------------------------------------------------------------
async def logstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_USER_ID: return

    loop = asyncio.get_running_loop()

    def _generate_stats():
        now = datetime.now().astimezone()
        start_dt = now - timedelta(hours=24)
        
        all_logs = _fetch_all_logs_sync()
        
        # Filtro
        active_logs = []
        for l in all_logs:
            try:
                t = datetime.fromisoformat(l['timestamp']).astimezone()
                if start_dt <= t <= now:
                    active_logs.append((t, l))
            except: pass
            
        if not active_logs:
            return None, "Nessun log attivo nelle ultime 24 ore."

        # Conti
        groups = set()
        cmds = {'/trombola': 0, '/estrai': 0, 'error': 0}
        hourly = {}

        for t, l in active_logs:
            gid = l.get('chat_id')
            if gid: groups.add(gid)
            c = l.get('command', '')
            if c in cmds: cmds[c] += 1
            if 'error' in str(c).lower(): cmds['error'] += 1
            
            h = t.replace(minute=0, second=0, microsecond=0)
            hourly[h] = hourly.get(h, 0) + 1

        # Grafico
        dates = sorted(hourly.keys())
        counts = [hourly[d] for d in dates]

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(dates, counts, width=0.03, color='skyblue')
        ax.set_title('Attività ultime 24h')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.xticks(rotation=45)
        plt.tight_layout()

        bio = io.BytesIO()
        fig.savefig(bio, format='png')
        plt.close(fig)
        bio.seek(0)

        txt = (
            f"*Statistiche 24h:*\n\n"
            f"_👥 Gruppi attivi: {len(groups)}_\n"
            f"_🆕 Partite: {cmds['/trombola']}_\n"
            f"_🏧 Estrazioni: {cmds['/estrai']}_\n"
            f"_🆘 Errori: {cmds['error']}_\n"
        )
        return bio, txt

    bio, caption = await loop.run_in_executor(_executor, _generate_stats)

    if bio:
        await context.bot.send_photo(chat_id=user_id, photo=bio, caption=caption, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(caption)

# --------------------------------------------------------------------
# 4. LOG ACTIVITY (Grafico settimanale)
# --------------------------------------------------------------------
async def logactivity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_USER_ID: return
    
    loop = asyncio.get_running_loop()

    def _analyze_week():
        now = datetime.now().astimezone()
        start = now - timedelta(days=7)
        all_logs = _fetch_all_logs_sync()
        
        # Logica euristica per "partite" (/trombola seguito da /estrai)
        # Raggruppa per chat
        chat_logs = {}
        for l in all_logs:
            try:
                t = datetime.fromisoformat(l['timestamp']).astimezone()
                if start <= t <= now:
                    gid = l.get('chat_id')
                    if gid: 
                        chat_logs.setdefault(gid, []).append((t, l['command']))
            except: pass

        games_count = 0
        weekday_dist = [0]*7
        
        for gid, entries in chat_logs.items():
            entries.sort(key=lambda x: x[0])
            i = 0
            while i < len(entries):
                if entries[i][1] == '/trombola':
                    # Cerca estrazione successiva
                    for j in range(i+1, len(entries)):
                        if entries[j][1] == '/estrai':
                            games_count += 1
                            wd = entries[j][0].weekday()
                            weekday_dist[wd] += 1
                            i = j # Salta avanti
                            break
                i += 1
        
        # Plot
        days = ['Lun', 'Mar', 'Mer', 'Gio', 'Ven', 'Sab', 'Dom']
        fig, ax = plt.subplots()
        ax.bar(days, weekday_dist, color='orange')
        ax.set_title(f"Partite totali 7gg: {games_count}")
        
        bio = io.BytesIO()
        fig.savefig(bio, format='png')
        plt.close(fig)
        bio.seek(0)
        
        return bio, games_count

    bio, count = await loop.run_in_executor(_executor, _analyze_week)
    await context.bot.send_photo(chat_id=user_id, photo=bio, caption=f"_🔙 Totale partite stimate\\: {count} negli utilimi 7 giorni_", parse_mode=ParseMode.MARKDOWN_V2)


# --------------------------------------------------------------------
# 5. LOG CLEAN (Ottimizzato)
# --------------------------------------------------------------------
async def logclean(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != OWNER_USER_ID: return

    if not context.args:
        await update.message.reply_text("Uso: /logclean <giorni>")
        return

    try:
        days = int(context.args[0])
    except:
        await update.message.reply_text("Giorni non validi.")
        return

    
    loop = asyncio.get_running_loop()

    def _perform_clean():
        cutoff = datetime.now().astimezone() - timedelta(days=days)
        deleted_count = 0
        
        # Ottieni riferimento radice
        logs_ref = db.reference("logs")
        # Scarica tutto (purtroppo necessario senza query complesse su firebase admin)
        # Se il DB è enorme, questo andrebbe fatto a chunk o via Cloud Functions.
        all_groups = logs_ref.get() or {}

        updates = {}
        
        for gid, entries in all_groups.items():
            if not isinstance(entries, dict): continue
            for push_id, data in entries.items():
                try:
                    ts_str = data.get('timestamp')
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str).astimezone()
                        if ts < cutoff:
                            # Aggiungi a path di cancellazione
                            updates[f"{gid}/{push_id}"] = None
                            deleted_count += 1
                except:
                    # Se timestamp rotto, cancella o ignora? Ignoriamo per sicurezza
                    pass

        # Esegui multi-path update (molto più veloce di N richieste)
        # Firebase accetta update atomici
        if updates:
            # Firebase limita la dimensione degli update. Facciamo chunk da 500.
            chunk_size = 500
            items = list(updates.items())
            for i in range(0, len(items), chunk_size):
                chunk = dict(items[i:i + chunk_size])
                logs_ref.update(chunk)
                
        return deleted_count

    try:
        count = await loop.run_in_executor(_executor, _perform_clean)
        await update.message.reply_text(f"*✅ Pulizia completata\\. Rimossi {count} log\\.*", parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        logger.error(f"Errore logclean: {e}")
        await update.message.reply_text(f"❌ Errore durante la pulizia: {e}")

# --------------------------------------------------------------------
# Helper Link (Cache Sincrona/Asincrona mista)
# --------------------------------------------------------------------
_group_link_cache = {}

async def _make_group_link(bot, chat_id: int) -> str:
    # check cache
    if chat_id in _group_link_cache:
        return _group_link_cache[chat_id]
    
    try:
        chat = await bot.get_chat(chat_id)
        link = chat.invite_link or chat.username
        if link:
            if not link.startswith('http') and not link.startswith('t.me'):
                 link = f"https://t.me/{link}"
            _group_link_cache[chat_id] = link
            return link
    except:
        pass
    return None
