from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ChatMemberHandler
import os
import logging
from telegram.constants import ParseMode
import asyncio
from aiohttp import web
from dotenv import load_dotenv
import json

if os.name == 'nt':
    from asyncio import WindowsProactorEventLoopPolicy
    asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())
    logging.info("Using Windows ProactorEventLoop")
else:
    try:
        import uvloop
        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logging.info("Using uvloop EventLoopPolicy")
    except ImportError:
        logging.info("uvloop non disponibile, uso asyncio di default")


# Importa i tuoi moduli locali
from comandi import start_game, button, estrai, stop_game, start, reset_classifica, regole  # Assicurati che questi siano corretti
from game_instance import get_game  # Assicurati che questo sia corretto
from variabili import is_admin, get_chat_id_or_thread, load_group_settings, save_group_settings, find_group, on_bot_added  # Assicurati che questi siano corretti
from log import send_logs_by_group # Assicurati che questi siano corretti

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

# Impostazioni logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Dizionario premi di default
premi_default = {"ambo": 5, "terno": 10, "quaterna": 15, "cinquina": 20, "tombola": 50}

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

async def show_bonus_menu(query, chat_id, settings):
    bonus_enabled = settings.get(str(chat_id), {}).get("bonus_malus", True)  # Default True se non presente
    keyboard = [
        [InlineKeyboardButton(f"Attivo {'✅' if bonus_enabled else ''}", callback_data='set_bonus_on'),
         InlineKeyboardButton(f"Disattivo {'✅' if not bonus_enabled else ''}", callback_data='set_bonus_off')],
        [InlineKeyboardButton("🔙 Indietro", callback_data='back_to_main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = ("_🆗 Questo è il posto giusto se vuoi mettere un po’ di pepe alle tue partite, attiva i bonus e i malus se vuoi che "
            "la classifica sia un pochino più combattuta, se invece sei un tradizionalista, tieni l'opzione disattivata\\:_")
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        if "Message is not modified" not in str(e):
            raise e

async def settings_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id, _ = get_chat_id_or_thread(update)
    settings = load_group_settings()
    if str(chat_id) not in settings:
        settings[str(chat_id)] = {}

    action = query.data
    logger.info(f"settings_button: {action}")

    if action == 'menu_estrazione':
        await show_extraction_menu(query, chat_id, settings)
    elif action == 'menu_admin':
        await show_admin_menu(query, chat_id, settings)
    elif action == 'menu_premi':
        await show_premi_menu(query, chat_id, settings)
    elif action == 'menu_bonus':
        await show_bonus_menu(query, chat_id, settings)
    elif action == 'set_manual':
        settings[str(chat_id)]['extraction_mode'] = 'manual'
        save_group_settings(settings)
        await show_extraction_menu(query, chat_id, settings)
    elif action == 'set_auto':
        settings[str(chat_id)]['extraction_mode'] = 'auto'
        save_group_settings(settings)
        await show_extraction_menu(query, chat_id, settings)
    elif action == 'set_limita_admin_yes':
        settings[str(chat_id)]['limita_admin'] = True
        save_group_settings(settings)
        await show_admin_menu(query, chat_id, settings)
    elif action == 'set_limita_admin_no':
        settings[str(chat_id)]['limita_admin'] = False
        save_group_settings(settings)
        await show_admin_menu(query, chat_id, settings)
    elif action.startswith("set_premio_"):
        parts = action.split("_")
        premio = parts[2]
        change = int(parts[3])
        if "premi" not in settings[str(chat_id)]:
            settings[str(chat_id)]["premi"] = premi_default.copy()
        settings[str(chat_id)]["premi"][premio] = max(0, settings[str(chat_id)]["premi"].get(premio, 0) + change)
        save_group_settings(settings)
        await show_premi_menu(query, chat_id, settings)
    elif action == "reset_premi":
        settings[str(chat_id)]["premi"] = premi_default.copy()
        save_group_settings(settings)
        await show_premi_menu(query, chat_id, settings)
    elif action == 'set_bonus_on':
        settings[str(chat_id)]["bonus_malus"] = True
        save_group_settings(settings)
        await show_bonus_menu(query, chat_id, settings)
    elif action == 'set_bonus_off':
        settings[str(chat_id)]["bonus_malus"] = False
        save_group_settings(settings)
        await show_bonus_menu(query, chat_id, settings)
    elif action == 'back_to_main_menu':
        await settings_command(update, context)
    elif action == 'close_settings':
        try:
            await query.message.delete()
            await query.answer()
        except Exception as e:
            logger.error(f"Errore eliminazione messaggio: {e}")
            await query.answer("Errore nel chiudere il menu.")
    else:
        await query.answer()

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

    file_classifiche = "classifiche.json"
    if not os.path.exists(file_classifiche):
        await context.bot.send_message(chat_id=chat_id, text="📊 Nessuna classifica disponibile", message_thread_id=thread_id)
        return

    try:
        with open(file_classifiche, "r", encoding="utf-8") as f:
            classifiche = json.load(f)
    except json.JSONDecodeError:
        logger.error(f"Errore nella decodifica del file JSON delle classifiche.")
        await context.bot.send_message(chat_id=chat_id, text="⚠️ Errore nel leggere il file della classifica.", message_thread_id=thread_id)
        return

    group_id = str(chat_id)
    if group_id in classifiche:
        classifica_gruppo = classifiche[group_id]
        classifica_ordinata = sorted(classifica_gruppo.items(), key=lambda item: item[1], reverse=True)
        classifica_text = []
        for posizione, (user_id, punteggio) in enumerate(classifica_ordinata):
            if punteggio == 0:
                continue
            try:
                user_info = await context.bot.get_chat(user_id)
                username = user_info.username or user_info.first_name
            except Exception:
                username = f"utente_{user_id}"
            classifica_text.append(f"{posizione + 1}. @{username}: {punteggio} punti")
        if classifica_text:
            classifica_text = "\n".join(classifica_text)
            await context.bot.send_message(chat_id=chat_id, text=f"🏆 Classifica:\n\n{classifica_text}", message_thread_id=thread_id)
        else:
            await context.bot.send_message(chat_id=chat_id, text="📊 Nessuna classifica disponibile.", message_thread_id=thread_id)
    else:
        await context.bot.send_message(chat_id=chat_id, text="📊 Nessuna classifica disponibile.", message_thread_id=thread_id)

async def combined_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = query.data
    user = query.from_user
    username = user.username if user.username else user.full_name # Usa username se disponibile, altrimenti il nome completo
    user_id = user.id

    logger.info(f"Callback data '{action}' ricevuto da utente: {username} (ID: {user_id})")
    
    if action.startswith('set_') or action in ['menu_estrazione', 'menu_admin', 'menu_premi', 'menu_bonus', 'back_to_main_menu', 'close_settings', 'reset_premi']:
        await settings_button(update, context)
    else:
        await button(update, context)

async def health_check(request):
    try:
        me = await app.bot.get_me()
        return web.Response(text=f"Bot @{me.username} attivo!")
    except Exception as e:
        logger.error(f"Health check fallito: {e}")
        return web.Response(status=500, text="Bot non disponibile")

async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    asyncio.create_task(app.process_update(update))
    return web.Response(text='OK')

async def self_ping():
    while True:
        await asyncio.sleep(14 * 60)
        try:
            await app.bot.get_updates(offset=-1, timeout=1)
        except Exception as e:
            logger.error(f"Self-ping fallito: {e}")

async def start_webserver():
    webapp = web.Application()
    webapp.router.add_get('/', health_check)
    webapp.router.add_get('/health', health_check)
    webapp.router.add_post('/webhook', handle_webhook)
    runner = web.AppRunner(webapp)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"Webserver avviato su porta {PORT}")

async def main():
    global app, PORT
    load_dotenv()
    TOKEN = os.getenv('TOKEN')
    WEBHOOK_URL = os.getenv('WEBHOOK_URL')  # e.g. https://domain.com/webhook
    PORT = int(os.getenv('PORT', '8443'))

    # Istanzia bot
    builder = Application.builder().token(TOKEN)
    app = builder.build()

    # Aggiungi handler
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('trombola', start_game))
    app.add_handler(CommandHandler('estrai', estrai))
    app.add_handler(CommandHandler('stop', stop_game))
    app.add_handler(CommandHandler('impostami', settings_command))
    app.add_handler(CommandHandler('trombolatori', numero_giocatori))
    app.add_handler(CommandHandler('classifica', classifica))
    app.add_handler(CommandHandler('azzera', reset_classifica := settings_command))
    app.add_handler(CommandHandler('regole', regole))
    app.add_handler(CommandHandler('trova', find_group))
    app.add_handler(CommandHandler('log', send_logs_by_group))

    # CallbackQuery: settings prima, poi button
    app.add_handler(CallbackQueryHandler(settings_button, pattern='^(menu_|set_|back_to_main_menu|close_settings|reset_premi)'))
    app.add_handler(CallbackQueryHandler(button))

    app.add_handler(ChatMemberHandler(on_bot_added, ChatMemberHandler.MY_CHAT_MEMBER))

    # Imposta webhook Telegram
    await app.initialize()
    await app.bot.set_webhook(WEBHOOK_URL)
    await app.start()
    logger.info(f"Webhook impostato su {WEBHOOK_URL}")

    # Avvia webserver e self-ping
    await asyncio.gather(start_webserver(), self_ping())

if __name__ == '__main__':
    asyncio.run(main())
