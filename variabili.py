from telegram import Update, Chat
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackContext
import logging
import os
from dotenv import load_dotenv

# --------------------------------------------------------------------
# 1. Impostazioni logger e caricamento variabili d’ambiente
# --------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()

# --------------------------------------------------------------------
# 2. Variabili globali preesistenti
# --------------------------------------------------------------------
chat_id_global = None
thread_id_global = None
OWNER_USER_ID = "547260823"

_ALL_BONUS_FEATURES = {
    "104": "104",
    "110": "110",
    "666": "666",
    "404": "404",
    "Tombolino": "Tombolino"
}

_DEFAULT_BONUS_STATES = {key: True for key in _ALL_BONUS_FEATURES}

# Dizionario premi di default (rimane invariato)
premi_default = {"ambo": 5, "terno": 10, "quaterna": 15, "cinquina": 20, "tombola": 50}

# --------------------------------------------------------------------
# 4. Import delle funzioni Firebase (invece di JSONBin)
# --------------------------------------------------------------------
from firebase_client import (
    load_group_settings_from_firebase,   # MODIFICA
    save_group_settings_to_firebase     # MODIFICA
)

# --------------------------------------------------------------------
# 5. Funzione per ottenere chat_id e thread_id se applicabile
# --------------------------------------------------------------------
def get_chat_id_or_thread(update: Update):
    chat_id = update.effective_chat.id
    thread_id = None
    
    if update.effective_message.is_topic_message:
        thread_id = update.effective_message.message_thread_id
    
    return chat_id, thread_id

# --------------------------------------------------------------------
# 6. Funzione per ottenere la limitazione degli admin usando Firebase
# --------------------------------------------------------------------
def get_admin_limitation(chat_id):
    """
    Carica da Firebase le impostazioni del gruppo specificato e
    restituisce lo stato di 'limita_admin' (default True).
    Se la voce non esiste, la crea con valori di default.
    """
    # MODIFICA: carica le impostazioni INTERE usando Firebase
    settings = load_group_settings_from_firebase(chat_id)

    chat_id_str = str(chat_id)
    if chat_id_str not in settings:
        # Se non esiste, inizializzo con extraction_mode manual e limita_admin True
        settings[chat_id_str] = {'extraction_mode': 'manual', 'limita_admin': True}
        save_group_settings_to_firebase(chat_id, settings)  # MODIFICA
        return True
    else:
        stato = settings[chat_id_str].get('limita_admin', True)
        logger.info(f"Stato corrente della limitazione admin per chat {chat_id}: {stato}")
        return stato

# --------------------------------------------------------------------
# 7. Verifica se l’utente è admin (o se la limitazione è disattivata)
# --------------------------------------------------------------------
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, _ = get_chat_id_or_thread(update)
    
    if not get_admin_limitation(chat_id):
        # Se la limitazione è disattivata, tutti possono eseguire
        return True

    # Altrimenti controllo lo status Telegram
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(chat_id, user_id)
    return chat_member.status in ['administrator', 'creator']

# --------------------------------------------------------------------
# 8. Comando /find_group (rimasto invariato, non tocca Firebase o JSONBin)
# --------------------------------------------------------------------
async def find_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text(
            "Devi fornire un ID di gruppo, ad esempio: /findgroup -1001234567890"
        )
        return

    group_id = context.args[0]
    
    try:
        chat: Chat = await context.bot.get_chat(chat_id=group_id)
        
        messaggio = "📢 *Informazioni sul Gruppo*\n\n"
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
        
        if hasattr(chat, 'permissions') and chat.permissions:
            messaggio += "*Permessi del Gruppo:*\n"
            messaggio += format_chat_permissions(chat.permissions)
        
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
        await update.message.reply_text(
            "Errore: il gruppo non è stato trovato o non posso accedervi."
        )

def format_chat_permissions(permissions):
    fields = [
        ("Invio di messaggi", permissions.can_send_messages),
        ("Invio di messaggi multimediali", 
         permissions.api_kwargs.get('can_send_media_messages', None) 
         if hasattr(permissions, 'api_kwargs') else None),
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
    
    message = "🔹 *Chat Permissions:*\n\n"
    for label, value in fields:
        if value is not None:
            message += f"• *{label}:* {'✅' if value else '❌'}\n"
    return message

# --------------------------------------------------------------------
# 9. Handler che notifica l’owner quando il bot viene aggiunto a un gruppo (invariato)
# --------------------------------------------------------------------
async def on_bot_added(update: Update, context: CallbackContext):
    chat = update.effective_chat
    my_chat_member = update.my_chat_member

    if (
        my_chat_member.old_chat_member.status != "member"
        and my_chat_member.new_chat_member.status == "member"
    ):
        try:
            membri = await chat.get_member_count()
        except Exception as e:
            membri = "Sconosciuto"
            logger.error(f"Errore ottenendo il numero di membri: {e}")

        gruppo_info = (
            f"📢 Il bot è stato aggiunto a un nuovo gruppo!\n\n"
            f"🔹 Nome del gruppo: {chat.title}\n"
            f"🔹 ID del gruppo: {chat.id}\n"
            f"🔹 Tipo: {chat.type}\n"
            f"🔹 Membri: {membri}"
        )

        try:
            await context.bot.send_message(chat_id=OWNER_USER_ID, text=gruppo_info)
            logger.info(f"Informazioni inviate al proprietario: {OWNER_USER_ID}")
        except Exception as e:
            logger.error(f"Errore nell'invio del messaggio: {e}")

# --------------------------------------------------------------------
# 10. Funzione per ottenere sticker in base al numero (invaria)
# --------------------------------------------------------------------
def get_sticker_for_number(number):
    stickers = {
        69: "CAACAgQAAxkBAAEty5Vm7TKgxrKxsvhU824Vk7x2CEND3wACegcAAj2RqFBz3KLfy83lqTYE",
        90: "CAACAgEAAxkBAAEt32Vm8Z_GSXsHJiUjkcuuFKbOn6-C5QAC5gUAAknjsAjqSIl2V50ugDYE",
        104: "CAACAgQAAxkBAAExyBZnsMNjcmrjrNQpNTTiJDhIuaqLEAACLhcAAsNrSVEvCd8T5g72HDYE",
        666: "CAACAgQAAxkBAAEx-sBnuLFsYCU3q7RM7U0-kKNSkEHAhgACXAADIPteF9q_7MKC2ERiNgQ",
        110: "CAACAgQAAxkBAAE1oqxoOXr1BaVGLmjQ6UfsbRTTcVOgtQACJwoAArybIFHOnHbz_EYnizYE",
        404: "CAACAgQAAxkBAAE1oq5oOXsd4KgUBf_Zprzwu8ewEMVqmAACowwAAkwu8FPV9fZm6lrXPDYE"
    }
    return stickers.get(number)
