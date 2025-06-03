from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ChatMemberHandler
import os
import logging
from telegram.constants import ParseMode
import asyncio
from aiohttp import web
from dotenv import load_dotenv
import argparse

# Configurazione dell'ambiente
load_dotenv()
TOKEN = os.getenv('TOKEN')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # e.g. https://domain.com/webhook
PORT = int(os.getenv('PORT', '8443'))

_ALL_BONUS_FEATURES = {
    "104": "104", 
    "110": "110", 
    "666": "666", 
    "404": "404", 
    "Tombolino": "Tombolino"
}
_DEFAULT_BONUS_STATES = {key: True for key in _ALL_BONUS_FEATURES} # Default: tutte attive

# Impostazioni logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cache per le informazioni della chat
_chat_info_cache: dict[int, dict] = {}
_cache_ttl = 3600

# Importa i tuoi moduli locali
from comandi import start_game, button, estrai, stop_game, start, reset_classifica, regole
from game_instance import get_game, load_classifica_from_json
from variabili import is_admin, get_chat_id_or_thread, load_group_settings, save_group_settings, find_group, on_bot_added, premi_default
from log import send_all_logs, send_logs_by_group

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

# Funzione per l'estrazione automatica
async def auto_extract(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    mode = get_extraction_mode(chat_id)

    game = get_game(chat_id)
    if not game.game_active:  # Evita di estrarre se la partita non è attiva
        return

    if mode == 'auto':
        await estrai(None, context)  # Chiama la funzione di estrazione senza controllare admin

# Comando impostazioni con menu a bottoni
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name
    chat_id = update.effective_chat.id
    logger.info(f"Il comando /impostami è stato usato da @{username} (ID: {user_id}).")

    message = update.message if update.message else update.callback_query.message

    if not await is_admin(update, context):
        await message.reply_text("🚫 Solo gli amministratori possono modificare le impostazioni.")
        return

    # Tastiera con quattro pulsanti: Estrazione, Admin, Premi, Bonus/Malus, Chiudi
    keyboard = [
        [InlineKeyboardButton("🔁 Estrazione", callback_data='menu_estrazione'),
         InlineKeyboardButton("🛂 Admin", callback_data='menu_admin')],
        [InlineKeyboardButton("💰 Premi", callback_data='menu_premi'),
         InlineKeyboardButton("☯️ Bonus/Malus", callback_data='menu_bonus')],
        [InlineKeyboardButton("❌ Chiudi", callback_data='close_settings')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = "*📱 Benvenuto nel pannello di controllo\\!*\n\n_📲 Da dove vuoi iniziare la configurazione\\?_"
    if update.callback_query:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)

# Funzioni per mostrare i vari menu
async def show_extraction_menu(query, chat_id, settings):
    current_mode = settings.get(str(chat_id), {}).get('extraction_mode', 'manual')
    keyboard = [
        [InlineKeyboardButton(f"Manuale {'✅' if current_mode == 'manual' else ''}", callback_data='set_manual'),
         InlineKeyboardButton(f"Automatica {'✅' if current_mode == 'auto' else ''}", callback_data='set_auto')],
        [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = ("_🆗 Saggia scelta cominciare da qui, puoi decidere se rendere l'estrazione automatica, con un numero nuovo senza dover "
            "premere nulla, oppure se proprio ti piace cliccare i bottoni, tenerla manuale\\:_")
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)

async def show_admin_menu(query, chat_id, settings):
    limita_admin = settings.get(str(chat_id), {}).get('limita_admin', True)
    keyboard = [
        [InlineKeyboardButton(f"Sì {'✅' if limita_admin else ''}", callback_data='set_limita_admin_yes'),
         InlineKeyboardButton(f"No {'✅' if not limita_admin else ''}", callback_data='set_limita_admin_no')],
        [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = ("_🆗 Ah quindi vuoi permettere a tutti di poter toccare i comandi\\? E va bene, a tuo rischio e pericolo\\. Premi no se vuoi che "
            "tutti, non solo gli admin, possano avviare, estrarre ed interrompere\\. Premi si se vuoi che il potere rimanga nelle mani di pochi\\:_")
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)

async def show_premi_menu(query, chat_id, settings):
    premi = settings.get(str(chat_id), {}).get("premi", premi_default)
    keyboard = []
    for premio, valore in premi.items():
        keyboard.append([
            InlineKeyboardButton(f"{premio.capitalize()}: {valore}💰", callback_data="none"),
        ])
        keyboard.append([
            InlineKeyboardButton("➖1", callback_data=f"set_premio_{premio}_-1"),
            InlineKeyboardButton("➕1", callback_data=f"set_premio_{premio}_+1"),
            InlineKeyboardButton("➖10", callback_data=f"set_premio_{premio}_-10"),
            InlineKeyboardButton("➕10", callback_data=f"set_premio_{premio}_+10"),
        ])
    keyboard.append([InlineKeyboardButton("🔄 Reset Punti", callback_data="reset_premi")])
    keyboard.append([InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = ("_🆗 Eccoci, dove avviene la magia, il cuore di tutto\\: *i punteggi*\\. Dai ad ogni premio il punteggio che ritieni corretto e "
            "lascia che l'estrazione faccia il suo corso\\:_")
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise e

async def show_bonus_menu(query, chat_id_str: str, settings: dict):
    group_conf = settings.setdefault(str(chat_id_str), {}) # str() è ridondante se chat_id_str è già stringa
    # Inizializza 'bonus_malus_settings' se non esiste, usando _DEFAULT_BONUS_STATES
    feature_states = group_conf.setdefault("bonus_malus_settings", _DEFAULT_BONUS_STATES.copy())

    # Assicura che tutte le feature definite in _ALL_BONUS_FEATURES abbiano uno stato
    # Se una nuova feature è in _ALL_BONUS_FEATURES ma non in feature_states, usa il suo default
    for key, default_value in _DEFAULT_BONUS_STATES.items():
        if key not in feature_states:
            feature_states[key] = default_value

    keyboard = []
    # Ordine di visualizzazione consistente per le feature
    ordered_feature_keys = ["110", "104", "666", "404", "Tombolino"] 

    for key in ordered_feature_keys:
        if key in _ALL_BONUS_FEATURES: # Processa solo le feature definite
            label = _ALL_BONUS_FEATURES[key] # Prende il nome/label della feature
            active = feature_states.get(key) # Lo stato dovrebbe esistere dopo il loop di inizializzazione sopra

            btn_active_text = f"Attivo {'✅' if active else ''}" # Testo del bottone "Attivo"
            btn_inactive_text = f"Non Attivo {'❌' if not active else ''}" # Testo del bottone "Non Attivo"
            
            keyboard.append([
                InlineKeyboardButton(btn_active_text, callback_data=f"toggle_feature_{key}_active"),
                InlineKeyboardButton(label, callback_data="none"), # Bottone etichetta, non interagibile
                InlineKeyboardButton(btn_inactive_text, callback_data=f"toggle_feature_{key}_inactive")
            ])

    keyboard.append([InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main_menu')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        "_🆗 Qui puoi attivare o disattivare ogni bonus/malus singolarmente: "
        "tocca il pulsante per cambiare lo stato\\.\n\n"
        "Attivo: ✅ · Non Attivo: ❌\\:_" # Legenda originale
    )
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        if "Message is not modified" not in str(e): logger.error(f"Errore in show_bonus_menu: {e}")


async def settings_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Rispondi subito alla callback
    
    chat_id_obj, _ = get_chat_id_or_thread(update) # Ottiene chat_id come intero
    chat_id_str = str(chat_id_obj) # Converti in stringa per usarlo come chiave nei dizionari

    settings = load_group_settings() # Carica tutte le impostazioni da JSONBin
    
    # Assicura che esista una voce per questa chat_id_str in settings
    # Se non esiste, verrà creata la prima volta che si accede a una sotto-chiave con setdefault
    # o quando si salva. È buona norma inizializzarla subito.
    if chat_id_str not in settings:
        settings[chat_id_str] = {} # Inizializza come dizionario vuoto se non esiste

    action = query.data
    logger.info(f"settings_button: Azione '{action}' per chat ID '{chat_id_str}'")

    # --- Mantenimento della logica esistente per le altre azioni ---
    if action == 'menu_estrazione':
        await show_extraction_menu(query, chat_id_str, settings)
    elif action == 'menu_admin':
        await show_admin_menu(query, chat_id_str, settings)
    elif action == 'menu_premi':
        await show_premi_menu(query, chat_id_str, settings)
    elif action == 'menu_bonus':
        await show_bonus_menu(query, chat_id_str, settings) # Chiama la funzione corretta
    elif action == 'set_manual':
        settings[chat_id_str].setdefault('extraction_mode', 'manual') # Usa setdefault per sicurezza
        settings[chat_id_str]['extraction_mode'] = 'manual'
        save_group_settings(settings)
        await show_extraction_menu(query, chat_id_str, settings)
    elif action == 'set_auto':
        settings[chat_id_str].setdefault('extraction_mode', 'manual')
        settings[chat_id_str]['extraction_mode'] = 'auto'
        save_group_settings(settings)
        await show_extraction_menu(query, chat_id_str, settings)
    elif action == 'set_limita_admin_yes':
        settings[chat_id_str].setdefault('limita_admin', True)
        settings[chat_id_str]['limita_admin'] = True
        save_group_settings(settings)
        await show_admin_menu(query, chat_id_str, settings)
    elif action == 'set_limita_admin_no':
        settings[chat_id_str].setdefault('limita_admin', True)
        settings[chat_id_str]['limita_admin'] = False
        save_group_settings(settings)
        await show_admin_menu(query, chat_id_str, settings)
    elif action.startswith("set_premio_"):
        parts = action.split("_")
        premio_key = parts[2]
        change = int(parts[3])
        
        # Assicura che 'premi' esista e usa premi_default se necessario
        current_premi = settings[chat_id_str].setdefault("premi", premi_default.copy())
        current_premi[premio_key] = max(0, current_premi.get(premio_key, 0) + change)
        
        save_group_settings(settings)
        await show_premi_menu(query, chat_id_str, settings)
    elif action == "reset_premi":
        settings[chat_id_str]["premi"] = premi_default.copy() # Resetta ai default globali
        save_group_settings(settings)
        await show_premi_menu(query, chat_id_str, settings)
    # --- Fine mantenimento logica esistente ---

    elif action.startswith("toggle_feature_"):
        parts = action.split("_") # Es: "toggle_feature_Tombolino_active"
        feature_key = parts[2]    # Es: "Tombolino"
        desired_state_str = parts[3] # Es: "active" o "inactive"
        
        logger.info(f"Richiesta modifica feature: '{feature_key}' a stato '{desired_state_str}' per chat {chat_id_str}")

        # Assicura che 'bonus_malus_settings' esista per la chat, usando i default globali se necessario
        bonus_malus_map = settings[chat_id_str].setdefault("bonus_malus_settings", _DEFAULT_BONUS_STATES.copy())

        # Assicura che tutte le feature definite in _ALL_BONUS_FEATURES abbiano uno stato iniziale
        # Questo è importante se _DEFAULT_BONUS_STATES non è stato usato prima per questa chat
        for key, default_value in _DEFAULT_BONUS_STATES.items():
            if key not in bonus_malus_map:
                bonus_malus_map[key] = default_value
        
        if feature_key in bonus_malus_map: # Verifica che la feature_key sia valida
            new_state = True if desired_state_str == "active" else False
            bonus_malus_map[feature_key] = new_state
            logger.info(f"Feature '{feature_key}' per chat {chat_id_str} impostata a {new_state}")
        else:
            logger.warning(f"Tentativo di modificare feature sconosciuta: '{feature_key}' per chat {chat_id_str}")

        save_group_settings(settings) # Salva l'intero oggetto settings
        await show_bonus_menu(query, chat_id_str, settings) # Ricarica e mostra il menu aggiornato

    elif action == 'back_to_main_menu':
        # Richiama la funzione settings_command per mostrare il menu principale
        # Passa l'update originale, così settings_command può estrarre i dati necessari
        # Non è necessario creare una nuova tastiera qui, settings_command lo farà.
        # Nota: query.message deve essere disponibile per edit_text in settings_command se chiamato da callback
        await settings_command(update, context) 

    elif action == 'close_settings':
        try:
            await query.message.delete()
            # query.answer() è già stato chiamato all'inizio
        except Exception as e:
            logger.error(f"Errore durante l'eliminazione del messaggio delle impostazioni: {e}")
            # Potresti voler inviare un avviso se l'eliminazione fallisce
            await query.answer("Impossibile chiudere il menu.", show_alert=True) 
    else:
        logger.warning(f"Azione non gestita in settings_button: '{action}' per chat {chat_id_str}")
        # query.answer() è già stato chiamato.

def get_extraction_mode(chat_id):
    settings = load_group_settings()
    if str(chat_id) not in settings:
        settings[str(chat_id)] = {'extraction_mode': 'manual'}
        save_group_settings(settings)
    if 'extraction_mode' not in settings[str(chat_id)]:
        settings[str(chat_id)]['extraction_mode'] = 'manual'
        save_group_settings(settings)
    return settings[str(chat_id)]['extraction_mode']

async def numero_giocatori(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, _ = get_chat_id_or_thread(update)
    game = get_game(chat_id)
    if not game.game_active:
        await update.message.reply_text("🚫 Non ci sono partite in corso al momento.")
        return
    numero_giocatori_attivi = len(game.players)
    if numero_giocatori_attivi == 0:
        await update.message.reply_text("*🤷‍♂️ Nessuno si è unito alla partita ancora\\!*", parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await update.message.reply_text(f"*👥 Utenti in partita\\: {numero_giocatori_attivi}*", parse_mode=ParseMode.MARKDOWN_V2)

async def classifica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, thread_id = get_chat_id_or_thread(update)

    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Solo gli amministratori possono vedere la classifica.")
        return

    # Carica dal bin
    classifica_gruppo = load_classifica_from_json(chat_id)

    if not classifica_gruppo:
        await context.bot.send_message(
            chat_id=chat_id,
            text="📊 Nessuna classifica disponibile.",
            message_thread_id=thread_id
        )
        return

    # Ordina e formatta
    ordinata = sorted(classifica_gruppo.items(), key=lambda item: item[1], reverse=True)
    lines = []
    for idx, (user_id, punti) in enumerate(ordinata, start=1):
        if punti == 0:
            continue
        try:
            info = await context.bot.get_chat(user_id)
            nome = info.username or info.first_name
        except:
            nome = f"utente_{user_id}"
        lines.append(f"{idx}. @{nome}: {punti} punti")

    if lines:
        testo = "🏆 Classifica:\n\n" + "\n".join(lines)
        await context.bot.send_message(chat_id=chat_id, text=testo, message_thread_id=thread_id)
    else:
        await context.bot.send_message(chat_id=chat_id, text="📊 Nessuna classifica disponibile.", message_thread_id=thread_id)

async def combined_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = query.data
    user = query.from_user
    username = user.username or user.full_name
    user_id = user.id

    logger.info(f"Callback data '{action}' ricevuto da utente: {username} (ID: {user_id})")

    # Tutti i comandi di configurazione settings vanno in settings_button
    settings_actions = (
        action.startswith('menu_'),
        action.startswith('set_'),
        action.startswith('toggle_feature_'),
        action in ('back_to_main_menu', 'close_settings', 'reset_premi')
    )

    if any(settings_actions):
        await settings_button(update, context)
    else:
        # Tutto il resto (draw_number, mostra_cartella, bonus/malus specifici, ecc.)
        await button(update, context)

async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def handle_webhook(request: web.Request) -> web.Response:
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"Errore nel parse del JSON: {e}")
        return web.Response(status=400, text="Invalid JSON")

    # Converte il JSON in un oggetto Update di python-telegram-bot
    update = Update.de_json(data, application.bot)

    # Lanciato come task separato per non bloccare subito la risposta HTTP
    asyncio.create_task(application.process_update(update))

    return web.Response(text="OK")


async def start_webserver() -> None:
    load_dotenv()
    # Render (oppure tu) imposta la variabile d'ambiente PORT al valore che serve (es. 8443)
    PORT = int(os.getenv('PORT', '8443'))

    webapp = web.Application()
    webapp.router.add_get('/', health_check)        # root → health
    webapp.router.add_get('/health', health_check)  # health check endpoint
    webapp.router.add_post('/webhook', handle_webhook)

    runner = web.AppRunner(webapp)
    await runner.setup()

    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

    logger.info(f"Webserver avviato su 0.0.0.0:{PORT}")


async def main() -> None:
    load_dotenv()
    TOKEN = os.getenv('TOKEN')
    WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # es. "https://<tuo-servizio>.onrender.com/webhook"

    if not TOKEN or not WEBHOOK_URL:
        logger.error("Le variabili d'ambiente TOKEN e WEBHOOK_URL devono essere definite.")
        return

    # Creazione dell’Application (builder)
    global application
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('trombola', start_game))
    application.add_handler(CommandHandler('estrai', estrai))
    application.add_handler(CommandHandler('stop', stop_game))
    application.add_handler(CommandHandler('impostami', settings_command))
    application.add_handler(CommandHandler('trombolatori', numero_giocatori))
    application.add_handler(CommandHandler('classifiga', classifica))
    application.add_handler(CommandHandler('azzera', reset_classifica))
    application.add_handler(CommandHandler('regolo', regole))
    application.add_handler(CommandHandler('trova', find_group))
    application.add_handler(CommandHandler('log', send_all_logs))
    application.add_handler(CommandHandler('logruppo', send_logs_by_group))

    application.add_handler(
        CallbackQueryHandler(
            settings_button,
            pattern=r'^(menu_|set_|toggle_feature_|back_to_main_menu|close_settings|reset_premi)'
        )
    )
    application.add_handler(CallbackQueryHandler(button))

    application.add_handler(ChatMemberHandler(on_bot_added, ChatMemberHandler.MY_CHAT_MEMBER))

    # Inizializza il bot (scarica offset, settaggi interni, ecc.)
    await application.initialize()

    # Imposta il webhook su Telegram (fa la chiamata a setWebhook)
    await application.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook impostato su: {WEBHOOK_URL}")

    # Avvia il webserver aiohttp in background (apre socket su PORT)
    await start_webserver()

    # Mantieni il processo vivo (non terminare main)
    # Questo asyncio.Event rimarrà in attesa infinita, tenendo il container vivo
    await asyncio.Event().wait()


if __name__ == '__main__':
    asyncio.run(main())
