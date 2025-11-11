import os
import logging
import asyncio
from aiohttp import web
from dotenv import load_dotenv
import argparse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# --------------------------------------------------------------------
# 1. Caricamento variabili ambiente
# --------------------------------------------------------------------
load_dotenv()

TOKEN = os.getenv('TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # es. "https://<tuo-servizio>.onrender.com/webhook"
PORT = int(os.getenv('PORT', '8443'))

# --------------------------------------------------------------------
# 2. Impostazioni bonus/malus (rimangono invariate)
# --------------------------------------------------------------------
_ALL_BONUS_FEATURES = {
    "104": "104",
    "110": "110",
    "666": "666",
    "404": "404",
    "Tombolino": "Tombolino"
}
_DEFAULT_BONUS_STATES = {key: True for key in _ALL_BONUS_FEATURES}  # Default: tutte attive

# --------------------------------------------------------------------
# 3. Logger
# --------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

application = None
# --------------------------------------------------------------------
# 4. Cache informazioni chat (rimane invariate)
# --------------------------------------------------------------------
_chat_info_cache: dict[int, dict] = {}
_cache_ttl = 3600

async def get_cached_chat(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    now = asyncio.get_event_loop().time()
    entry = _chat_info_cache.get(chat_id)
    if entry and now - entry['ts'] < _cache_ttl:
        return entry['info']
    try:
        info = await context.bot.get_chat(chat_id)
        _chat_info_cache[chat_id] = {'info': info, 'ts': now}
        return info
    except Exception:
        return None

# --------------------------------------------------------------------
# 5. Import dei moduli locali e di Firebase
# --------------------------------------------------------------------
from comandi import start_game, button, estrai, stop_game, start, reset_classifica, regole, rule_section_callback
from game_instance import get_game
# --- RIMOSSE importazioni su JSONBin: load_classifica_from_json, load_group_settings, save_group_settings ---
# MODIFICA: import delle nuove funzioni Firebase
from firebase_client import (
    load_classifica_from_firebase,
    save_classifica_to_firebase,
    load_group_settings_from_firebase,
    save_group_settings_to_firebase,
)
from variabili import is_admin, get_chat_id_or_thread, find_group, on_bot_added, premi_default
from log import send_all_logs, send_logs_by_group

# --------------------------------------------------------------------
# 6. Funzione per estrazione automatica (invariata, tranne che si usa get_extraction_mode che a sua volta usa Firebase)
# --------------------------------------------------------------------
async def auto_extract(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    mode = get_extraction_mode(chat_id)

    game = get_game(chat_id)
    if not game.game_active:
        return

    if mode == 'auto':
        await estrai(None, context)

# --------------------------------------------------------------------
# 7. Comando /impostami (invariato)
# --------------------------------------------------------------------
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name
    chat_id, thread_id = get_chat_id_or_thread(update)
    
    # 1) Controllo permessi: solo admin possono aprire il pannello
    if not await is_admin(update, context):
        # Se sono in callback, uso update.callback_query.message
        if update.callback_query:
            await update.callback_query.answer("🚫 Solo gli amministratori possono modificare le impostazioni.", show_alert=True)
        else:
            await update.message.reply_text("🚫 Solo gli amministratori possono modificare le impostazioni.")
        return

    # 2) Costruisco la tastiera principale
    keyboard = [
        [
            InlineKeyboardButton("🔁 Estrazione", callback_data='menu_estrazione'),
            InlineKeyboardButton("🛂 Admin", callback_data='menu_admin')
        ],
        [
            InlineKeyboardButton("💰 Premi", callback_data='menu_premi'),
            InlineKeyboardButton("☯️ Bonus/Malus", callback_data='menu_bonus')
        ],
        [
            InlineKeyboardButton("🗑️ Elimina Numeri", callback_data='menu_delete'),
        ],
        [
            InlineKeyboardButton("❌ Chiudi", callback_data='close_settings')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "*📱 Pannello di Controllo*\n\n_📲 Scegli quale sezione vuoi configurare_"

    # 3) Se siamo in callback, edito il testo del messaggio esistente
    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
        except Exception as e:
            logger.error(f"[settings_command] Errore edit_message_text: {e}")
    else:
        # Siamo stati invocati da comando testuale
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)

# --------------------------------------------------------------------
# 8. Funzioni per mostrare i vari sotto‐menu (invariate, tranne il caricamento di “settings” da Firebase)
# --------------------------------------------------------------------
async def show_extraction_menu(query, chat_id_str, settings):
    current_mode = settings.get(chat_id_str, {}).get('extraction_mode', 'manual')
    keyboard = [
        [
            InlineKeyboardButton(
                f"Manuale {'✅' if current_mode == 'manual' else ''}",
                callback_data='set_manual'
            ),
            InlineKeyboardButton(
                f"Automatica {'✅' if current_mode == 'auto' else ''}",
                callback_data='set_auto'
            )
        ],
        [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        "_🆗 Saggia scelta cominciare da qui, puoi decidere se rendere l'estrazione automatica, "
        "con un numero nuovo senza dover premere nulla, oppure se proprio ti piace cliccare i bottoni, "
        "tenerla manuale\\:_"
    )
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)

async def show_admin_menu(query, chat_id_str, settings):
    limita_admin = settings.get(chat_id_str, {}).get('limita_admin', True)
    keyboard = [
        [
            InlineKeyboardButton(f"Sì {'✅' if limita_admin else ''}", callback_data='set_limita_admin_yes'),
            InlineKeyboardButton(f"No {'✅' if not limita_admin else ''}", callback_data='set_limita_admin_no')
        ],
        [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        "_🆗 Ah quindi vuoi permettere a tutti di poter toccare i comandi\\? E va bene, a tuo rischio e pericolo\\._ "
        "Premi no se vuoi che tutti, non solo gli admin, possano avviare, estrarre ed interrompere\\._ "
        "Premi si se vuoi che il potere rimanga nelle mani di pochi\\:_"
    )
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)

async def show_premi_menu(query, chat_id_str, settings):
    _PREMIO_ORDER = ["ambo", "terno", "quaterna", "cinquina", "tombola"]
    premi = settings.get(chat_id_str, {}).get("premi", premi_default)

    keyboard = []
    for premio in _PREMIO_ORDER:
        valore = premi.get(premio, premi_default.get(premio, 0))
        # Riga con etichetta
        keyboard.append([
            InlineKeyboardButton(f"{premio.capitalize()}: {valore}💰", callback_data="none"),
        ])
        # Riga con bottoni di modifica
        keyboard.append([
            InlineKeyboardButton("➖1", callback_data=f"set_premio_{premio}_-1"),
            InlineKeyboardButton("➕1", callback_data=f"set_premio_{premio}_+1"),
            InlineKeyboardButton("➖10", callback_data=f"set_premio_{premio}_-10"),
            InlineKeyboardButton("➕10", callback_data=f"set_premio_{premio}_+10"),
        ])

    keyboard.append([InlineKeyboardButton("🔄 Reset Punti", callback_data="reset_premi")])
    keyboard.append([InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main_menu')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        "_🆗 Eccoci, dove avviene la magia, il cuore di tutto\\: *i punteggi*\\. "
        "Dai ad ogni premio il punteggio che ritieni corretto e lascia che l'estrazione faccia il suo corso\\:_"
    )
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise e

async def show_bonus_menu(query, chat_id_str: str, settings: dict):
    group_conf = settings.setdefault(chat_id_str, {})  # str() è ridondante se chat_id_str è già stringa
    feature_states = group_conf.setdefault("bonus_malus_settings", _DEFAULT_BONUS_STATES.copy())
    for key, default_value in _DEFAULT_BONUS_STATES.items():
        if key not in feature_states:
            feature_states[key] = default_value

    keyboard = []
    ordered_feature_keys = ["110", "104", "666", "404", "Tombolino"]
    for key in ordered_feature_keys:
        if key in _ALL_BONUS_FEATURES:
            label = _ALL_BONUS_FEATURES[key]
            active = feature_states.get(key)
            btn_active_text = f"{'Si ✅' if active else 'Si '}"
            btn_inactive_text = f"{'No ❌' if not active else 'No '}"
            keyboard.append([
                InlineKeyboardButton(btn_active_text, callback_data=f"toggle_feature_{key}_active"),
                InlineKeyboardButton(label, callback_data="none"),
                InlineKeyboardButton(btn_inactive_text, callback_data=f"toggle_feature_{key}_inactive")
            ])

    keyboard.append([InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        "_🆗 Eccoci, nella sezione che ti permette di mettere un po' di pepe alla tua partita, attiva o disattiva i bonus/malus singolarmente "
        "e rendi la classifica altalenante e ricca di emozioni\\. Se vuoi maggiori informazioni digita /regolo per riceverle in privato\\._"
    )
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Errore in show_bonus_menu: {e}")

async def show_delete_menu(query, chat_id_str: str, settings: dict):
    delete_flag = settings.get(str(chat_id_str), {}).get('delete_numbers_on_end', False)
    keyboard = [
        [
            InlineKeyboardButton(f"Sì {'✅' if delete_flag else ''}", callback_data='set_delete_yes'),
            InlineKeyboardButton(f"No {'✅' if not delete_flag else ''}", callback_data='set_delete_no')
        ],
        [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        "_🆗 Se vuoi fare un po' di pulizia di messaggi sei nel posto giusto, qui potrai abilitare il bot ad eliminare i messaggi dei numeri "
        "estratti, questi verranno cancellati al termine della partita\\. Premi 'si' se vuoi che vengano cancellati, se preferisci che rimangano "
        "seleziona 'no'_"
    )
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise e

async def settings_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id_obj, _ = get_chat_id_or_thread(update)
    chat_id_str = str(chat_id_obj)

    settings = load_group_settings_from_firebase(chat_id_obj)
    if chat_id_str not in settings:
        settings[chat_id_str] = {}

    action = query.data
    logger.info(f"[settings_button] Azione '{action}' per chat {chat_id_str}")

    if action == 'menu_estrazione':
        await show_extraction_menu(query, chat_id_str, settings)
        return
    if action == 'menu_admin':
        await show_admin_menu(query, chat_id_str, settings)
        return
    if action == 'menu_premi':
        await show_premi_menu(query, chat_id_str, settings)
        return
    if action == 'menu_bonus':
        await show_bonus_menu(query, chat_id_str, settings)
        return
    if action == 'menu_delete':
        await show_delete_menu(query, chat_id_str, settings)
        return

    if action == 'set_manual':
        settings[chat_id_str]['extraction_mode'] = 'manual'
        save_group_settings_to_firebase(chat_id_obj, settings)
        await show_extraction_menu(query, chat_id_str, settings)
        return
    if action == 'set_auto':
        settings[chat_id_str]['extraction_mode'] = 'auto'
        save_group_settings_to_firebase(chat_id_obj, settings)
        await show_extraction_menu(query, chat_id_str, settings)
        return

    if action == 'set_limita_admin_yes':
        settings[chat_id_str]['limita_admin'] = True
        save_group_settings_to_firebase(chat_id_obj, settings)
        await show_admin_menu(query, chat_id_str, settings)
        return
    if action == 'set_limita_admin_no':
        settings[chat_id_str]['limita_admin'] = False
        save_group_settings_to_firebase(chat_id_obj, settings)
        await show_admin_menu(query, chat_id_str, settings)
        return

    if action.startswith("set_premio_"):
        parts = action.split("_")
        premio_key = parts[2]
        change = int(parts[3])
        current_premi = settings[chat_id_str].setdefault("premi", {})
        if not current_premi:
            from variabili import premi_default
            current_premi.update(premi_default)
        current_premi[premio_key] = max(0, current_premi.get(premio_key, 0) + change)
        save_group_settings_to_firebase(chat_id_obj, settings)
        await show_premi_menu(query, chat_id_str, settings)
        return
    if action == "reset_premi":
        from variabili import premi_default
        settings[chat_id_str]["premi"] = premi_default.copy()
        save_group_settings_to_firebase(chat_id_obj, settings)
        await show_premi_menu(query, chat_id_str, settings)
        return

    if action.startswith("toggle_feature_"):
        parts = action.split("_")
        feature_key = parts[2]
        desired_state_str = parts[3]  # 'active' o 'inactive'
        bonus_map = settings[chat_id_str].setdefault("bonus_malus_settings", {})
        from variabili import _DEFAULT_BONUS_STATES
        for k, v in _DEFAULT_BONUS_STATES.items():
            bonus_map.setdefault(k, v)
        bonus_map[feature_key] = (desired_state_str == "active")
        save_group_settings_to_firebase(chat_id_obj, settings)
        await show_bonus_menu(query, chat_id_str, settings)
        return

    if action == 'set_delete_yes':
        settings[chat_id_str]['delete_numbers_on_end'] = True
        save_group_settings_to_firebase(chat_id_obj, settings)
        await show_delete_menu(query, chat_id_str, settings)
        return
    if action == 'set_delete_no':
        settings[chat_id_str]['delete_numbers_on_end'] = False
        save_group_settings_to_firebase(chat_id_obj, settings)
        await show_delete_menu(query, chat_id_str, settings)
        return

    if action == 'back_to_main_menu':
        await settings_command(update, context)
        return

    if action == 'close_settings':
        try:
            await query.message.delete()
        except Exception as e:
            logger.error(f"Errore chiusura menu: {e}")
            await query.answer("Impossibile chiudere il menu.", show_alert=True)
        return

    logger.warning(f"[settings_button] Azione non gestita: {action} per chat {chat_id_str}")

def get_extraction_mode(chat_id):
    settings = load_group_settings_from_firebase(chat_id)
    chat_id_str = str(chat_id)

    if chat_id_str not in settings:
        settings[chat_id_str] = {'extraction_mode': 'manual'}
        save_group_settings_to_firebase(chat_id, settings)

    if 'extraction_mode' not in settings[chat_id_str]:
        settings[chat_id_str]['extraction_mode'] = 'manual'
        save_group_settings_to_firebase(chat_id, settings)

    return settings[chat_id_str]['extraction_mode']

async def numero_giocatori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, _ = get_chat_id_or_thread(update)
    game = get_game(chat_id)
    if not game.game_active:
        await update.message.reply_text("🚫 Non ci sono partite in corso al momento.")
        return
    numero_giocatori_attivi = len(game.players)
    if numero_giocatori_attivi == 0:
        await update.message.reply_text(
            "*🤷‍♂️ Nessuno si è unito alla partita ancora\\!*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
    else:
        await update.message.reply_text(
            f"*👥 Utenti in partita\\: {numero_giocatori_attivi}*",
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def classifica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, thread_id = get_chat_id_or_thread(update)

    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Solo gli amministratori possono vedere la classifica.")
        return

    classifica_gruppo = load_classifica_from_firebase(chat_id)

    if not classifica_gruppo:
        await context.bot.send_message(
            chat_id=chat_id,
            text="📊 Nessuna classifica disponibile.",
            message_thread_id=thread_id
        )
        return

    ordinata = sorted(classifica_gruppo.items(), key=lambda item: item[1], reverse=True)
    lines = []
    for idx, (user_id_str, punti) in enumerate(ordinata, start=1):
        try:
            user_id_int = int(user_id_str)
        except ValueError:
            user_id_int = None

        if punti == 0 or user_id_int is None:
            continue

        try:
            info = await context.bot.get_chat(user_id_int)
            nome = info.username or info.first_name
        except:
            nome = f"utente_{user_id_str}"
        lines.append(f"{idx}. @{nome}: {punti} punti")

    if lines:
        testo = "🏆 Classifica:\n\n" + "\n".join(lines)
        await context.bot.send_message(chat_id=chat_id, text=testo, message_thread_id=thread_id)
    else:
        await context.bot.send_message(chat_id=chat_id, text="📊 Nessuna classifica disponibile.", message_thread_id=thread_id)

async def combined_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    # Risponde subito così Telegram non va in timeout
    try:
        await query.answer()
    except:
        pass

    data = query.data
    logger.info(f"[CALLBACK] data = {data}")

    # ✅ Menù / impostazioni
    if (
        data.startswith("menu_") or
        data.startswith("set_") or
        data.startswith("toggle_feature_") or
        data in ("back_to_main_menu", "close_settings", "reset_premi")
    ):
        logger.info("[ROUTER] → settings_button")
        return await settings_button(update, context)

    # ✅ Regole
    if data.startswith("rule_"):
        logger.info("[ROUTER] → rule_section_callback")
        return await rule_section_callback(update, context)

    # ✅ Default: gioco
    logger.info("[ROUTER] → button")
    return await button(update, context)

async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK")


# ============================
# WEBHOOK HANDLER
# ============================
async def handle_webhook(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        logger.info(f"[WEBHOOK] Update ricevuto")
    except Exception as e:
        logger.error(f"[WEBHOOK] Errore nel parse del JSON: {e}")
        return web.Response(status=400, text="Invalid JSON")

    try:
        update = Update.de_json(data, application.bot)

        # ✅ IMPORTANTE: usare AWAIT, non create_task
        await application.process_update(update)

    except Exception as e:
        logger.exception(f"[WEBHOOK] Errore process_update: {e}")
        return web.Response(status=500)

    return web.Response(text="OK")


# ============================
# WEB SERVER
# ============================
async def start_webserver() -> None:
    load_dotenv()
    PORT = int(os.getenv("PORT", "8443"))

    webapp = web.Application()
    webapp.router.add_get("/", health_check)
    webapp.router.add_get("/health", health_check)
    webapp.router.add_post("/webhook", handle_webhook)

    runner = web.AppRunner(webapp)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logger.info(f"[WEBHOOK] Server avviato su 0.0.0.0:{PORT}")


# ============================
# MAIN
# ============================
async def main() -> None:
    load_dotenv()
    TOKEN = os.getenv("TOKEN")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")

    if not TOKEN or not WEBHOOK_URL:
        logger.error("❌ Le variabili d'ambiente TOKEN e WEBHOOK_URL devono essere definite.")
        return

    webhook_full = f"{WEBHOOK_URL}"

    global application
    application = Application.builder().token(TOKEN).build()

    # =====================================================
    # ✅ COMMAND HANDLER
    # =====================================================
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("trombola", start_game))
    application.add_handler(CommandHandler("estrai", estrai))
    application.add_handler(CommandHandler("stop", stop_game))
    application.add_handler(CommandHandler("impostami", settings_command))
    application.add_handler(CommandHandler("trombolatori", numero_giocatori))
    application.add_handler(CommandHandler("classifiga", classifica))
    application.add_handler(CommandHandler("azzera", reset_classifica))
    application.add_handler(CommandHandler("regolo", regole))
    application.add_handler(CommandHandler("trova", find_group))
    application.add_handler(CommandHandler("log", send_all_logs))
    application.add_handler(CommandHandler("logruppo", send_logs_by_group))

    # =====================================================
    # ✅ UNICO CALLBACK QUERY ROUTER
    # =====================================================
    application.add_handler(CallbackQueryHandler(combined_button_handler))

    # =====================================================
    # ✅ BOT CHAT STATUS
    # =====================================================
    application.add_handler(ChatMemberHandler(on_bot_added, ChatMemberHandler.MY_CHAT_MEMBER))

    # =====================================================
    # ✅ START
    # =====================================================
    await application.initialize()

    # ✅ Webhook
    try:
        ok = await application.bot.set_webhook(webhook_full)
        logger.info(f"✅ Webhook impostato: {webhook_full} -> {ok}")
    except Exception as e:
        logger.exception(f"❌ Errore setWebhook: {e}")

    # ✅ Info webhook
    try:
        info = await application.bot.get_webhook_info()
        logger.info(
            f"ℹ️ Webhook info:\n"
            f" URL = {info.url}\n"
            f" Pending = {info.pending_update_count}\n"
            f" LastError = {info.last_error_message}"
        )
    except Exception as e:
        logger.error(f"❌ Errore getWebhookInfo: {e}")

    # ✅ Start webserver
    await start_webserver()

    logger.info("✅ Bot avviato e in ascolto degli update")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
