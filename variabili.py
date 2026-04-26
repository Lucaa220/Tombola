from telegram import Update, Chat
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackContext
import logging
import os
import asyncio
import time
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()

chat_id_global = None
thread_id_global = None
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

premi_default = {"ambo": 5, "terno": 10, "quaterna": 15, "cinquina": 20, "tombola": 50}

from firebase_client import (
    load_group_settings_from_firebase,   
    save_group_settings_to_firebase     
)

def get_chat_id_or_thread(update: Update):
    chat_id = update.effective_chat.id
    thread_id = None
    
    if update.effective_message.is_topic_message:
        thread_id = update.effective_message.message_thread_id
    
    return chat_id, thread_id


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
                _chat_cache.pop(key, None)
    try:
        chat = await bot.get_chat(chat_id=chat_id)
        async with _chat_cache_lock:
            _chat_cache[key] = (chat, now)
        return chat
    except Exception as e:
        logger.error(f"cached_get_chat: errore ottenendo chat {chat_id}: {e}")
        raise

def get_admin_limitation(chat_id):
    settings = load_group_settings_from_firebase(chat_id)

    chat_id_str = str(chat_id)
    if chat_id_str not in settings:
        settings[chat_id_str] = {'extraction_mode': 'manual', 'limita_admin': True}
        save_group_settings_to_firebase(chat_id, settings) 
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
        value = getattr(permissions, attr, None)
        if value is not None:
            message += f"• *{label}:* {'✅' if value else '❌'}\n"
    return message

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
    "harry_potter": {
        104: "CAACAgIAAxkBAAE_7LZpU5bDar1npSTkGJlqp0ygTJm4GAACIDgAAnkR-UlJfPy0gvKZvjgE",
        666: "CAACAgIAAxkBAAE_7KhpU5ZYdl6gCPJJbWRWlZr58sKBjgACoTwAAo4TIUnVBy3VTBB29TgE",
        110: "CAACAgIAAxkBAAE_7LJpU5apvV5L8q71JtUyu4PPamjkVQACnx8AAlHF6Ur3ThPuK03feDgE",
        404: "CAACAgIAAxkBAAE_7KxpU5aQzYOCUEa48D86zDeBMPiyKwACzh4AAmVK6Eq3dJbJGEtjGDgE",
        "final": "CAACAgQAAxkBAAE_zK1pT63xXtFOFDAa_ekPN4o7-kMi8AACDAEAAr77Uw45cDSvFffnFjYE"
    },
    "marvel": {
        104: "CAACAgQAAxkBAAFBPXhpdyvZ65rskI4TkqOczsXHGkUU9gAC0B4AAmPCuFOCAAFWFHRHotQ4BA",
        666: "CAACAgQAAxkBAAFBPXVpdyvZxwRJ9fjYf0yoNrjsR9UhHgACYxsAAuZ-uVNse9UD8uL_HzgE",
        110: "CAACAgQAAxkBAAFBPXdpdyvZrX1DM-mdBS_h7Ptvy1AoCAACmxgAAjvOuVNkI3y9RcGeAzgE",
        404: "CAACAgQAAxkBAAFBPXZpdyvZ7sRdSnFNAaujDbicjmi-5wACJx0AAlMHuFOaB05GebevQTgE",
        "final": "CAACAgQAAxkBAAFBPXRpdyvZMx-YAwUz7h7G1LOaRwtnKQACLxgAAkYpuVNu6DW7nmqblzgE"
    },
    "barbie": {
        104: "CAACAgQAAxkBAAFH5dJp6jDT9BBEZI3o_Ehq1HZs7I2w_wACExwAAi5gSFMYVq6JEudVWjsE",
        666: "CAACAgQAAxkBAAFH5dRp6jDTYiOl7vMS3pRWUc8r49aSbQAC7RkAAn4pSFPvbPuqaLtIHjsE",
        110: "CAACAgQAAxkBAAFH5dNp6jDTJEZ7EG1BITvXSkI0Rg9fpgACLhoAAuBFUVOzFuQWZFKKpjsE",
        404: "CAACAgQAAxkBAAFH5dVp6jDT6pbRWG02KGnVtaukoyQRDgAC6RoAAroZSVM3SZwdsDzeQDsE",
        "final": "CAACAgQAAxkBAAFH5dZp6jDTjgZDvaEbxgv4tZ0Zd1HHoQACFCAAAt0fSFOUQalpZnSHCTsE"
    },
    "calcio": {
        104: "CAACAgIAAxkBAAFH5fNp6jHb7Y35wQSo1eE4GsUtAAE1a8EAAgFUAAJIiBhKfAZwVe4F0yg7BA",
        666: "CAACAgIAAxkBAAFH5fJp6jHb0PgLH1p0xZmQPzvBXAABBw8AAn9GAAIx2vlIucLxm0TUenM7BA",
        110: "CAACAgIAAxkBAAFH5fFp6jHbvLHs5KGyNoXEvSK-DP74jQACKEcAAjhg-UlDgpPK0uCR6DsE",
        404: "CAACAgIAAxkBAAFH5fRp6jHbz5A9KJ74R9Z49OsMIBz1wwACQUMAAlGVIEqV-lHkjfHgNDsE",
        "final": "CAACAgIAAxkBAAFH5fVp6jHblM5xskxKoIL20iwGX1fQRwAC3kkAAoXZIEq-rAZQv3QLzTsE"
    }

}

def get_sticker_for_number(number, tema: str = 'normale'):
    stickers_for_tema = THEME_STICKERS.get(tema, THEME_STICKERS.get('normale', {}))
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


THEME_SETTINGS = {
    "normale": {
        "stickers_enabled": True
    },
    "harry_potter": {
        "stickers_enabled": True
    },
    "marvel": {
        "stickers_enabled": True
    },
    "barbie": {
        "stickers_enabled": True
    },
    "calcio": {
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
    },
    "marvel": {
        "104": True,
        "110": True,
        "666": True,
        "404": True,
        "Tombolino": True
    },
    "barbie": {
        "104": True,
        "110": True,
        "666": True,
        "404": True,
        "Tombolino": True
    },
    "calcio": {
        "104": True,
        "110": True,
        "666": True,
        "404": True,
        "Tombolino": True
    }
}


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
                feats[k] = bool(feats.get(k, False))

_validate_theme_features()

def get_default_feature_states(tema: str = 'normale'):
    defaults = THEME_FEATURES.get(tema)
    if defaults is None:
        defaults = THEME_FEATURES.get('normale', {})
    return dict(defaults)


THEME_ANNOUNCEMENT_PHOTOS = {
    "normale": "normale.png",
    "harry_potter": "harry.png",
    "marvel": "marvel.png",
    "barbie": "barbie.png",
    "calcio": "calcio.png"
}

def get_announcement_photo(tema: str = 'normale'):
    filename = THEME_ANNOUNCEMENT_PHOTOS.get(tema) or THEME_ANNOUNCEMENT_PHOTOS.get('normale')
    if not filename:
        return None
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(base_dir, filename)
    if os.path.exists(full_path):
        return full_path
    return None
