import json
from telegram.constants import ParseMode
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

LOG_FILE = "interaction_log.json"
FOUNDER_ID = 547260823
BOT_USERNAME = "@Tombola2_Bot"

giorni = {
    0: "lunedì",
    1: "martedì",
    2: "mercoledì",
    3: "giovedì",
    4: "venerdì",
    5: "sabato",
    6: "domenica",
}

mesi = {
    1: "gennaio",
    2: "febbraio",
    3: "marzo",
    4: "aprile",
    5: "maggio",
    6: "giugno",
    7: "luglio",
    8: "agosto",
    9: "settembre",
    10: "ottobre",
    11: "novembre",
    12: "dicembre",
}

# Funzione per pulire il file di log: conserva solo le entry degli ultimi 7 giorni
def cleanup_logs():
    try:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return

    new_lines = []
    cutoff = datetime.now() - timedelta(days=7)
    for line in lines:
        try:
            entry = json.loads(line)
            entry_time = datetime.fromisoformat(entry["timestamp"])
            if entry_time >= cutoff:
                new_lines.append(line)
        except Exception:
            continue
    with open(LOG_FILE, "w") as f:
        f.writelines(new_lines)

# Funzione per loggare l'interazione (solo i comandi del bot vengono registrati)
def log_interaction(user_id, username, chat_id, command, group_name):
    cleanup_logs()
    log_entry = {
        "user_id": user_id,
        "username": username,
        "chat_id": chat_id,
        "group_name": group_name,
        "command": command,
        "timestamp": str(datetime.now())
    }
    with open(LOG_FILE, "a") as log_file:
        json.dump(log_entry, log_file)
        log_file.write("\n")

def split_text(text, max_length=4096):
    return [text[i:i + max_length] for i in range(0, len(text), max_length)]

async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name
    chat_id = update.effective_chat.id
    group_name = update.effective_chat.title

    # Comandi ammessi
    allowed_commands = ["/trombola", "/stop", "/estrai"]

    # Se è un messaggio con un comando
    if update.message and update.message.text:
        # Prendi la prima parola (il comando) e normalizzala (rimuovendo eventuale bot mention e in lowercase)
        command_full = update.message.text.split()[0]
        command_normalized = command_full.split('@')[0].lower()
        if command_normalized in allowed_commands:
            log_interaction(user_id, username, chat_id, update.message.text, group_name)

    # Se è un callback di un bottone inline (si registra comunque)
    elif update.callback_query:
        callback_data = update.callback_query.data
        log_interaction(user_id, username, chat_id, f"Bottone: {callback_data}", group_name)

async def send_logs_by_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        await update.message.reply_text("Questo comando può essere usato solo in chat privata.")
        return

    # Ottieni la data specificata come argomento, se presente
    args = context.args
    if args:
        try:
            specified_date = datetime.strptime(args[0], "%d-%m-%Y").date()
        except ValueError:
            await update.message.reply_text("⚠️ Formato data non valido. Usa il formato: /log DD-MM-YYYY")
            return
    else:
        specified_date = None

    # Ottieni i log raggruppati per ogni gruppo, filtrato per la data specificata o ultime 24 ore
    grouped_logs = get_recent_group_logs(hours=24, specific_date=specified_date)

    if grouped_logs:
        for group_id, group_logs in grouped_logs.items():
            group_name = group_logs[0].get("group_name", None)
            if group_name == "Gruppo Sconosciuto":
                continue

            log_text = f"📜 Log del Gruppo {group_name} (ultime 24h):\n\n" if not specified_date else f"📜 Log del Gruppo {group_name} ({specified_date}):\n\n"
            logs_by_date = {}

            # Raggruppa i log per data
            for log in group_logs:
                timestamp = datetime.fromisoformat(log['timestamp'])
                date_key = timestamp.date()
                if date_key not in logs_by_date:
                    logs_by_date[date_key] = []
                logs_by_date[date_key].append(log)

            for date, logs in sorted(logs_by_date.items()):
                if specified_date and date != specified_date:
                    continue

                giorno_settimana = giorni[date.weekday()]
                giorno = date.day
                mese = mesi[date.month]
                anno = date.year

                log_text += f"\n📅 {giorno_settimana}, {giorno} {mese} {anno}:\n\n"
                for log in logs:
                    formatted_time = datetime.fromisoformat(log['timestamp']).strftime("%H:%M:%S")
                    log_text += f"  🕒 {formatted_time} - @{log['username']} ha usato: {log['command']}\n"

            # Invia il log suddiviso in parti se necessario
            for text_part in split_text(log_text):
                await update.message.reply_text(text_part)

    else:
        await update.message.reply_text("⚠️ Nessun log disponibile per i gruppi conosciuti nelle ultime 24 ore.")

def get_recent_group_logs(hours=24, specific_date=None):
    logs_by_group = {}
    cutoff_time = datetime.now() - timedelta(hours=hours)
    try:
        with open(LOG_FILE, "r") as log_file:
            for line in log_file:
                log_entry = json.loads(line.strip())
                log_time = datetime.fromisoformat(log_entry["timestamp"])

                # Se è stata specificata una data, filtra per quella, altrimenti usa il cutoff delle 24 ore
                if specific_date:
                    if log_time.date() != specific_date:
                        continue
                elif log_time < cutoff_time:
                    continue

                chat_id = log_entry["chat_id"]
                if chat_id not in logs_by_group:
                    logs_by_group[chat_id] = []
                logs_by_group[chat_id].append(log_entry)
    except Exception as e:
        print(f"Errore nella lettura del file log: {e}")
    return logs_by_group

# Funzione per collegare il tracking dei comandi a tutti i comandi usati nel gruppo
async def handle_all_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await track_command(update, context)
