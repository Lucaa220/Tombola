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
import os.path
import sys

load_dotenv()

# Importa i tuoi moduli locali
from comandi import start_game, button, estrai, stop_game, start, reset_classifica, regole
from game_instance import get_game
from variabili import is_admin, get_chat_id_or_thread, load_group_settings, save_group_settings, find_group, on_bot_added
from log import send_logs_by_group, handle_all_commands

# Configura il logging su stdout
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

logger.addHandler(handler)
logger.setLevel(logging.INFO)

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
        logger.warning(f"Tentativo di estrazione automatica in un gruppo senza partita attiva: {chat_id}")
        return

    if mode == 'auto':
        logger.info(f"Avvio estrazione automatica per chat {chat_id}.")
        await estrai(None, context)  # Chiama la funzione di estrazione senza controllare admin
    else:
        logger.info(f"Estratto numero in modalità manuale per chat {chat_id}, modalità attuale: {mode}.")

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

    text = "*📱 Benvenuto nel pannello di controllo!*\n\n_📲 Da dove vuoi iniziare la configurazione?_"
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
    text = ("_🆗 Ah quindi vuoi permettere a tutti di poter toccare i comandi\\? E va bene, a tuo rischio e pericolo\\. Premi si se vuoi che "
            "tutti, non solo gli admin, possano avviare, estrarre ed interrompere\\. Premi no se vuoi che il potere rimanga nelle mani di pochi\\:_")
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
    text = ("_🆗 Questo è il posto giusto se vuoi mettere un po' di pepe alle tue partite, attiva i bonus e i malus se vuoi che "
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

    file_classifiche = os.path.join(os.path.dirname(__file__), "classifiche.json")
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
    logger.info(f"Callback data ricevuto: {action}")
    if action.startswith('set_') or action in ['menu_estrazione', 'menu_admin', 'menu_premi', 'menu_bonus', 'back_to_main_menu', 'close_settings', 'reset_premi']:
        await settings_button(update, context)
    else:
        await button(update, context)

async def webhook_handler(request):
    try:
        update_data = await request.json()
        logger.info("Aggiornamento ricevuto: %s", update_data)
        update = update.de_json(update_data, application.bot)
        asyncio.create_task(applicatio.process_update(update))
    except Exception as e:
        logger.error("Errore nel Webhook Handler: %s", e)
    return web.Response(text="OK")
    
async def health_check(request):
    # Aggiungi un controllo più completo qui
    try:
        # Verifica se il bot è online
        me = await application.bot.get_me()
        return web.Response(text=f"Bot {me.username} attivo!")
    except Exception as e:
        logger.error(f"Errore nel health check: {e}")
        return web.Response(status=500, text="Bot non disponibile")
        
# Configurazione del server web per webhook
async def setup_webapp():
    # Creazione dell'app web
    app = web.Application()
    
    # Aggiungi route per webhook, controllo salute e root
    app.router.add_post('/webhook', webhook_handler)
    app.router.add_get('/health', health_check)
    app.router.add_get('/', health_check)  # Aggiungi questa linea

    return app
    
async def self_ping():
    while True:
        try:
            logger.info("Self-ping per mantenere il servizio attivo")
            # Puoi anche eseguire operazioni di manutenzione qui
            await asyncio.sleep(14 * 60)  # 14 minuti (sotto i 15 min di Render)
        except Exception as e:
            logger.error(f"Errore nel self-ping: {e}")

async def main():
    # Configurazione del bot
    global application
    global TOKEN
    
    logger.info("Configurazione del bot...")
    TOKEN = os.getenv('TOKEN')
    WEBHOOK_URL = os.getenv('WEBHOOK_URL', f'https://tombola.onrender.com/webhook')
    PORT = int(os.getenv('PORT', 10000))
    
    # Creazione dell'applicazione
    application = Application.builder().token(TOKEN).build()
    
    # Registrazione degli handler
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("trombola", start_game))
    application.add_handler(CommandHandler("estrai", estrai))
    application.add_handler(CommandHandler("stop", stop_game))
    application.add_handler(CommandHandler("classifiga", classifica))
    application.add_handler(CommandHandler("azzera", reset_classifica))
    application.add_handler(CommandHandler("impostami", settings_command))
    application.add_handler(CommandHandler("trombolatori", numero_giocatori))
    application.add_handler(CommandHandler("trova", find_group))
    application.add_handler(CommandHandler("log", send_logs_by_group))
    application.add_handler(CommandHandler("regolo", regole))
    application.add_handler(MessageHandler(filters.COMMAND, handle_all_commands))
    application.add_handler(CallbackQueryHandler(combined_button_handler))
    application.add_handler(ChatMemberHandler(on_bot_added, ChatMemberHandler.MY_CHAT_MEMBER))
    
    # Impostazione del webhook
    await application.bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Webhook impostato su {WEBHOOK_URL}")
    
    # Configurazione e avvio del server web
    app = await setup_webapp()
    
    # Creazione e avvio server
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    
    logger.info(f"Avvio del server web sulla porta {PORT}...")
    await site.start()
    
    # Mantieni il processo attivo
    logger.info("Bot avviato con webhook, in attesa di richieste...")
    
    # Rimani in ascolto
    while True:
        await asyncio.sleep(3600)  # Controlla ogni ora

    asyncio.create_task(self_ping())

if __name__ == '__main__':
    asyncio.run(main())
