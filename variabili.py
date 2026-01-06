from telegram import Update, Chat
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackContext
import logging
import os
import asyncio
import time
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
# OWNER_USER_ID ora viene preso esclusivamente da variabile d'ambiente opzionale.
# Se non impostata, rimane None (caller deve gestire l'assenza).
owner_env = os.getenv('OWNER_USER_ID')
try:
    OWNER_USER_ID = int(owner_env) if owner_env is not None else None
except Exception:
    logger.warning('OWNER_USER_ID non è un intero valido; impostato a None')
    OWNER_USER_ID = None

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


# ----------------------------
# Async cached get_chat
# ----------------------------
# semplice cache in-memory per evitare chiamate ripetute a get_chat
_chat_cache = {}
_chat_cache_lock = asyncio.Lock()
_chat_cache_ttl = int(os.getenv('CHAT_CACHE_TTL', '300'))

async def cached_get_chat(bot, chat_id):
    key = str(chat_id)
    now = time.time()
    async with _chat_cache_lock:
        entry = _chat_cache.get(key)
        if entry:
            chat_obj, ts = entry
            if now - ts < _chat_cache_ttl:
                return chat_obj
            else:
                # scaduto
                _chat_cache.pop(key, None)
    # fuori dal lock chiamata reale
    try:
        chat = await bot.get_chat(chat_id=chat_id)
        async with _chat_cache_lock:
            _chat_cache[key] = (chat, now)
        return chat
    except Exception as e:
        logger.error(f"cached_get_chat: errore ottenendo chat {chat_id}: {e}")
        raise

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

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, _ = get_chat_id_or_thread(update)
    
    if not get_admin_limitation(chat_id):
        return True

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
        chat: Chat = await cached_get_chat(context.bot, group_id)
        
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
    # Mappa etichetta -> attributo Permissions
    mapping = [
        ("Invio di messaggi", 'can_send_messages'),
        ("Invio di messaggi multimediali", 'can_send_media_messages'),
        ("Invio di foto", 'can_send_photos'),
        ("Invio di video", 'can_send_videos'),
        ("Invio di note vocali", 'can_send_voice_notes'),
        ("Invio di video note", 'can_send_video_notes'),
        ("Invio di audio", 'can_send_audios'),
        ("Invio di documenti", 'can_send_documents'),
        ("Invio di sondaggi", 'can_send_polls'),
        ("Aggiunta di anteprime", 'can_add_web_page_previews'),
        ("Invio di altri messaggi", 'can_send_other_messages'),
        ("Modifica informazioni", 'can_change_info'),
        ("Invito utenti", 'can_invite_users'),
        ("Fissare messaggi", 'can_pin_messages'),
        ("Gestione argomenti", 'can_manage_topics'),
    ]

    message = "🔹 *Chat Permissions:*\n\n"
    for label, attr in mapping:
        # usa getattr in modo sicuro; se l'attributo non esiste, ottiene None
        value = getattr(permissions, attr, None)
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

# Supporto sticker per tema: mappa tema -> (numero -> sticker_file_id), più uno sticker finale opzionale
THEME_STICKERS = {
    "normale": {
        69: "CAACAgQAAxkBAAEty5Vm7TKgxrKxsvhU824Vk7x2CEND3wACegcAAj2RqFBz3KLfy83lqTYE",
        90: "CAACAgEAAxkBAAEt32Vm8Z_GSXsHJiUjkcuuFKbOn6-C5QAC5gUAAknjsAjqSIl2V50ugDYE",
        104: "CAACAgQAAxkBAAExyBZnsMNjcmrjrNQpNTTiJDhIuaqLEAACLhcAAsNrSVEvCd8T5g72HDYE",
        666: "CAACAgQAAxkBAAEx-sBnuLFsYCU3q7RM7U0-kKNSkEHAhgACXAADIPteF9q_7MKC2ERiNgQ",
        110: "CAACAgQAAxkBAAE1oqxoOXr1BaVGLmjQ6UfsbRTTcVOgtQACJwoAArybIFHOnHbz_EYnizYE",
        404: "CAACAgQAAxkBAAE1oq5oOXsd4KgUBf_Zprzwu8ewEMVqmAACowwAAkwu8FPV9fZm6lrXPDYE",
        "final": "CAACAgQAAxkBAAEt32Rm8Z_GRtaOFHzCVCFePFCU0rk1-wACNQEAAubEtwzIljz_HVKktzYE"
    },
    # Esempio di tema alternativo (puoi aggiungere sticker diversi per tema)
    "harry_potter": {
        69: "CAACAgQAAxkBAAEty5Vm7TKgxrKxsvhU824Vk7x2CEND3wACegcAAj2RqFBz3KLfy83lqTYE",
        90: "CAACAgEAAxkBAAEt32Vm8Z_GSXsHJiUjkcuuFKbOn6",
        104: "CAACAgIAAxkBAAE_7LZpU5bDar1npSTkGJlqp0ygTJm4GAACIDgAAnkR-UlJfPy0gvKZvjgE",
        666: "CAACAgIAAxkBAAE_7KhpU5ZYdl6gCPJJbWRWlZr58sKBjgACoTwAAo4TIUnVBy3VTBB29TgE",
        110: "CAACAgIAAxkBAAE_7LJpU5apvV5L8q71JtUyu4PPamjkVQACnx8AAlHF6Ur3ThPuK03feDgE",
        404: "CAACAgIAAxkBAAE_7KxpU5aQzYOCUEa48D86zDeBMPiyKwACzh4AAmVK6Eq3dJbJGEtjGDgE",
        "final": "CAACAgQAAxkBAAE_zK1pT63xXtFOFDAa_ekPN4o7-kMi8AACDAEAAr77Uw45cDSvFffnFjYE"
    }
}

def get_sticker_for_number(number, tema: str = 'normale'):
    stickers_for_tema = THEME_STICKERS.get(tema, THEME_STICKERS.get('normale', {}))
    # Se il tema disabilita gli sticker, restituisci None
    theme_settings = THEME_SETTINGS.get(tema, THEME_SETTINGS.get('normale', {}))
    if not theme_settings.get('stickers_enabled', True):
        return None
    return stickers_for_tema.get(number)

def get_final_sticker(tema: str = 'normale'):
    theme_settings = THEME_SETTINGS.get(tema, THEME_SETTINGS.get('normale', {}))
    if not theme_settings.get('stickers_enabled', True):
        return None
    stickers_for_tema = THEME_STICKERS.get(tema, THEME_STICKERS.get('normale', {}))
    return stickers_for_tema.get('final')


# Impostazioni per tema: abilitazione sticker e feature disponibili per tema
THEME_SETTINGS = {
    "normale": {
        "stickers_enabled": True
    },
    "harry_potter": {
        "stickers_enabled": True
    }
}

THEME_FEATURES = {
    "normale": {
        "104": True,
        "110": True,
        "666": True,
        "404": True,
        "Tombolino": True
    },
    "harry_potter": {
        "104": True,
        "110": True,
        "666": True,
        "404": True,
        "Tombolino": True
    }
}


# Validazione di THEME_FEATURES: rimuove chiavi non riconosciute e normalizza i valori a bool
VALID_FEATURE_KEYS = set(_ALL_BONUS_FEATURES.keys())

def _validate_theme_features():
    for tema, feats in list(THEME_FEATURES.items()):
        if not isinstance(feats, dict):
            logger.warning(f"THEME_FEATURES: valore per tema '{tema}' non è dict; verrà sostituito con dict vuoto")
            THEME_FEATURES[tema] = {}
            continue
        for k in list(feats.keys()):
            if k not in VALID_FEATURE_KEYS:
                logger.warning(f"THEME_FEATURES: rimosso feature non valida '{k}' dal tema '{tema}'")
                feats.pop(k, None)
            else:
                # Normalizza a bool
                feats[k] = bool(feats.get(k, False))

# Esegui validazione al caricamento del modulo
_validate_theme_features()

def get_default_feature_states(tema: str = 'normale'):
    """Restituisce un dizionario con lo stato (True/False) delle feature per il tema.

    La funzione ritorna mapping con chiavi stringa per ogni feature nota.
    """
    defaults = THEME_FEATURES.get(tema)
    if defaults is None:
        # se tema sconosciuto, usa normale
        defaults = THEME_FEATURES.get('normale', {})
    return dict(defaults)


# Mappa tema -> nome file immagine per l'annuncio della partita.
# I file devono trovarsi nella stessa cartella del progetto (lo stesso folder di questi file .py).
THEME_ANNOUNCEMENT_PHOTOS = {
    "normale": "normale.png",
    "harry_potter": "harry.png",
}

def get_announcement_photo(tema: str = 'normale'):
    """Ritorna il percorso assoluto del file immagine per l'annuncio del tema, o None se non esiste.

    Usa i nomi definiti in `THEME_ANNOUNCEMENT_PHOTOS` localizzati nella cartella del progetto.
    """
    filename = THEME_ANNOUNCEMENT_PHOTOS.get(tema) or THEME_ANNOUNCEMENT_PHOTOS.get('normale')
    if not filename:
        return None
    # Cartella del progetto (dove risiedono i file .py principali)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(base_dir, filename)
    if os.path.exists(full_path):
        return full_path
    return None
