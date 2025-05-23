from telegram import Update
from telegram.ext import ContextTypes, CallbackContext
import logging
import json
import os
from telegram.constants import ParseMode
from pathlib import Path
from datetime import datetime
from github import Github

# Impostazioni logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Variabili globali per chat_id e thread_id
chat_id_global = None
thread_id_global = None
SETTINGS_FILE = Path(__file__).parent / "group_settings.json"
OWNER_USER_ID = "547260823"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = "Lucaa220/Tombola"
REMOTE_PATH = "classifiche.json"

def push_json_to_github(local_json_path: str, commit_message: str = None):
    with open(local_json_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    gh = Github(GITHUB_TOKEN)
    repo = gh.get_repo(REPO_NAME)
    
    try:
        contents = repo.get_contents(REMOTE_PATH)
        sha = contents.sha
    except Exception as e:
        sha = None
    
    if not commit_message:
        commit_message = f"Aggiorno stato bot — {datetime.utcnow().isoformat()}Z"
    
    repo.update_file(
        path=REMOTE_PATH,
        message=commit_message,
        content=content,
        sha=sha,
        branch="main"  # o un’altra branch a tua scelta
    )
    print(f"✅ {REMOTE_PATH} aggiornato su GitHub")

def load_group_settings():
    if not SETTINGS_FILE.exists():
        return {}
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError:
        logger.error("Corrupted settings file, loading empty settings.")
        return {}


def save_group_settings(settings):
    """Salva le impostazioni dei gruppi nel file group_settings.json e le pusha su GitHub."""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
            json.dump(settings, file, ensure_ascii=False, indent=4)
        logger.info(f"Settings salvati correttamente in {SETTINGS_FILE}.")
    except Exception as e:
        logger.error(f"Errore durante il salvataggio delle impostazioni: {e}")
        return

    # Push su GitHub
    try:
        push_json_to_github(
            local_json_path=str(SETTINGS_FILE),
            commit_message="Aggiorno impostazioni — " + datetime.utcnow().isoformat() + "Z"
        )
        logger.info("✅ Impostazioni aggiornate anche su GitHub.")
    except Exception as e:
        logger.error(f"Errore nel push delle impostazioni su GitHub: {e}")

# Funzione per ottenere chat_id e thread_id se applicabile
def get_chat_id_or_thread(update: Update):
    chat_id = update.effective_chat.id  # Ottiene l'ID della chat corrente
    thread_id = None  # Imposta di default il thread ID come None
    
    # Se la chat ha thread, ottieni il thread ID
    if update.effective_message.is_topic_message:
        thread_id = update.effective_message.message_thread_id
    
    return chat_id, thread_id

# Aggiungi una chiave per la limitazione degli amministratori
def get_admin_limitation(chat_id):
    settings = load_group_settings()

    if str(chat_id) not in settings:
        settings[str(chat_id)] = {'extraction_mode': 'manual', 'limita_admin': True}  # Impostazione predefinita: limita admin
        save_group_settings(settings)
    else:
        pass
    return settings[str(chat_id)].get('limita_admin', True)


# Verifica se la limitazione degli admin è disattivata per la chat corrente
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, _ = get_chat_id_or_thread(update)
    
    # Controlla se la limitazione admin è disabilitata
    if not get_admin_limitation(chat_id):
        return True  # Se non ci sono limitazioni, tutti possono eseguire il comando

    # Altrimenti, controlla se l'utente è un admin
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    return chat_member.status in ['administrator', 'creator']


from telegram import Chat
from telegram.constants import ParseMode

async def find_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("Devi fornire un ID di gruppo, ad esempio: /findgroup -1001234567890")
        return

    group_id = context.args[0]
    
    try:
        # Recupera le informazioni del gruppo tramite l'ID specificato
        chat: Chat = await context.bot.get_chat(chat_id=group_id)
        
        # Costruzione del messaggio
        messaggio = "📢 *Informazioni sul Gruppo*\n\n"
        
        # Sezione dettagli generali
        messaggio += "*Dettagli:*\n"
        messaggio += f"• *ID:* `{chat.id}`\n"
        messaggio += f"• *Tipo:* {chat.type}\n"
        if chat.title:
            messaggio += f"• *Titolo:* {chat.title}\n"
        if chat.username:
            messaggio += f"• *Username:* @{chat.username}\n"
        if chat.description:
            messaggio += f"• *Descrizione:* {chat.description}\n"
        if hasattr(chat, 'bio') and chat.bio:
            messaggio += f"• *Bio:* {chat.bio}\n"
        messaggio += "\n"
        
        # Sezione impostazioni aggiuntive
        messaggio += "*Impostazioni:*\n"
        if chat.invite_link:
            messaggio += f"• *Invite Link:* {chat.invite_link}\n"
        if hasattr(chat, 'pinned_message') and chat.pinned_message:
            messaggio += f"• *Messaggio fissato:* ID {chat.pinned_message.message_id}\n"
        if hasattr(chat, 'slow_mode_delay') and chat.slow_mode_delay:
            messaggio += f"• *Slow Mode:* {chat.slow_mode_delay} sec\n"
        if hasattr(chat, 'sticker_set_name') and chat.sticker_set_name:
            messaggio += f"• *Sticker Set:* {chat.sticker_set_name}\n"
        if hasattr(chat, 'linked_chat_id') and chat.linked_chat_id:
            messaggio += f"• *Linked Chat ID:* {chat.linked_chat_id}\n"
        if hasattr(chat, 'location') and chat.location:
            messaggio += f"• *Location:* lat {chat.location.latitude}, lon {chat.location.longitude}\n"
        messaggio += "\n"
        
        # Sezione permessi
        if hasattr(chat, 'permissions') and chat.permissions:
            messaggio += "*Permessi del Gruppo:*\n"
            messaggio += format_chat_permissions(chat.permissions)
        
        # Se il gruppo ha una foto, prova a inviarla come allegato
        if chat.photo:
            try:
                await update.message.reply_photo(
                    photo=chat.photo.big_file_id,
                    caption=messaggio,
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Errore nell'invio della foto: {e}. Invio il messaggio come testo.")
                await update.message.reply_text(messaggio, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(messaggio, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Errore nel trovare il gruppo con ID {group_id}: {e}")
        await update.message.reply_text("Errore: il gruppo non è stato trovato o non posso accedervi.")

def format_chat_permissions(permissions):
    # Costruiamo una lista di tuple (etichetta, valore booleano)
    fields = [
        ("Invio di messaggi", permissions.can_send_messages),
        ("Invio di messaggi multimediali", permissions.api_kwargs.get('can_send_media_messages', None) if hasattr(permissions, 'api_kwargs') else None),
        ("Invio di foto", permissions.can_send_photos),
        ("Invio di video", permissions.can_send_videos),
        ("Invio di note vocali", permissions.can_send_voice_notes),
        ("Invio di video note", permissions.can_send_video_notes),
        ("Invio di audio", permissions.can_send_audios),
        ("Invio di documenti", permissions.can_send_documents),
        ("Invio di sondaggi", permissions.can_send_polls),
        ("Aggiunta di anteprime", permissions.can_add_web_page_previews),
        ("Invio di altri messaggi", permissions.can_send_other_messages),
        ("Modifica informazioni", permissions.can_change_info),
        ("Invito utenti", permissions.can_invite_users),
        ("Fissare messaggi", permissions.can_pin_messages),
        ("Gestione argomenti", permissions.can_manage_topics),
    ]
    
    # Costruiamo il messaggio formattato
    message = "🔹 *Chat Permissions:*\n\n"
    for label, value in fields:
        # Salta i campi che risultano None (non disponibili)
        if value is not None:
            message += f"• *{label}:* {'✅' if value else '❌'}\n"
    return message

async def on_bot_added(update: Update, context: CallbackContext):
    chat = update.effective_chat
    my_chat_member = update.my_chat_member

    # Verifica che il bot sia stato appena aggiunto come membro del gruppo
    if my_chat_member.old_chat_member.status != "member" and my_chat_member.new_chat_member.status == "member":
        # Ottieni il numero di membri con 'await'
        try:
            membri = await chat.get_member_count()
        except Exception as e:
            membri = "Sconosciuto"
            logger.error(f"Errore ottenendo il numero di membri: {e}")

        # Prepara le informazioni del gruppo
        gruppo_info = (
            f"📢 Il bot è stato aggiunto a un nuovo gruppo!\n\n"
            f"🔹 Nome del gruppo: {chat.title}\n"
            f"🔹 ID del gruppo: {chat.id}\n"
            f"🔹 Tipo: {chat.type}\n"
            f"🔹 Membri: {membri}"
        )

        # Invia il messaggio al proprietario
        try:
            await context.bot.send_message(chat_id=OWNER_USER_ID, text=gruppo_info)
        except Exception as e:
            logger.error(f"Errore nell'invio del messaggio: {e}")
