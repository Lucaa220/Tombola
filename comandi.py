import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import telegram
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from game_instance import get_game
# MODIFICA: import delle funzioni Firebase al posto di JSONBin
from firebase_client import (
    load_classifica_from_firebase,    # in luogo di load_classifica_from_json
    save_classifica_to_firebase,      # in luogo di save_classifica_to_json
    add_log_entry
)
from variabili import get_chat_id_or_thread, is_admin, get_default_feature_states
# MODIFICA: rimuovere load_group_settings e sostituire con Firebase
from firebase_client import load_group_settings_from_firebase
from variabili import get_sticker_for_number, get_final_sticker, premi_default, get_announcement_photo
import asyncio
import json
import os
from log import log_interaction
from datetime import datetime
from firebase_admin import db
from utils import safe_escape_markdown as esc
from asyncio.log import logger
from messages import get_testo_tematizzato

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name
    chat_id, thread_id = get_chat_id_or_thread(update)
    group_name = update.message.chat.title or "il gruppo"
    await log_interaction(user_id, username, chat_id, "/trombola", group_name)

    if not await is_admin(update, context):
        group_settings = load_group_settings_from_firebase(chat_id)
        tema = group_settings.get(str(chat_id), {}).get('tema', 'normale')
        text = get_testo_tematizzato('solo_admin', tema)
        await update.message.reply_text(text)
        return

    game = get_game(chat_id)
    game.set_chat_id(chat_id)
    game.set_thread_id(thread_id)
    game.overall_scores = load_classifica_from_firebase(chat_id)
    group_settings = load_group_settings_from_firebase(chat_id)
    custom_scores = group_settings.get(str(chat_id), {}).get("premi")
    if custom_scores:
        game.custom_scores = custom_scores
    else:
        game.custom_scores = premi_default.copy()

    if update.message.chat.username:
        group_link = f"https://t.me/{update.message.chat.username}"
    else:
        try:
            group_link = await context.bot.export_chat_invite_link(chat_id)
        except Exception as e:
            group_link = None

    print(f"ID gruppo: {chat_id}, Thread: {thread_id}, Nome: {group_name}, Link: {group_link}")

    if not game.game_active:
        game.reset_game()
        print("Gioco resettato!")
    else:
        logger.info(f"Start requested but game already active in chat {chat_id}; skip reset.")

    keyboard = [
        [InlineKeyboardButton("➕ Unisciti", callback_data='join_game')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    tema = group_settings.get(str(chat_id), {}).get('tema', 'normale') # Recupero tema per annuncio
    # Prepare caption from template and attempt to send theme-specific announcement photo
    caption = get_testo_tematizzato('annuncio_partita', tema)
    photo_path = get_announcement_photo(tema)
    if photo_path and os.path.exists(photo_path):
        try:
            f = open(photo_path, 'rb')
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=f,
                caption=caption,
                reply_markup=reply_markup,
                message_thread_id=thread_id,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            try:
                f.close()
            except Exception:
                pass
        except Exception as e:
            # Fallback to plain message if photo send fails
            await context.bot.send_message(
                chat_id=chat_id,
                text=caption,
                reply_markup=reply_markup,
                message_thread_id=thread_id,
                parse_mode=ParseMode.MARKDOWN_V2
            )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=reply_markup,
            message_thread_id=thread_id,
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id, _ = get_chat_id_or_thread(update)  # Aggiunto per tema, assumendo contesto gruppo se possibile
    group_settings = load_group_settings_from_firebase(chat_id)
    tema = group_settings.get(str(chat_id), {}).get('tema', 'normale')

    if context.args:
        command_argument = context.args[0]
        if command_argument.startswith("join_game_"):
            try:
                group_id = int(command_argument.split("_", 2)[2])
            except Exception as e:
                await update.message.reply_text("Parametro non valido.")
                return

            try:
                member_status = await context.bot.get_chat_member(group_id, user_id)
                # MODIFICA QUI: Aggiunto 'restricted' per permettere l'ingresso a utenti con limitazioni
                if member_status.status not in ['member', 'administrator', 'creator', 'restricted']:
                    text = get_testo_tematizzato('join_non_autorizzato', tema)
                    await update.message.reply_text(text)
                    logger.info(f"Tentativo di join non autorizzato: User {user_id} per gruppo {group_id}")
                    return
            except telegram.error.BadRequest as e:
                if "User_not_participant" in str(e):
                    text = get_testo_tematizzato('non_membro_gruppo', tema)
                    await update.message.reply_text(text)
                    return
                else:
                    raise

            try:
                chat = await context.bot.get_chat(group_id)
                group_name = chat.title or "Gruppo Sconosciuto"
                if chat.username:
                    group_link = f"https://t.me/{chat.username}"
                else:
                    group_link = await context.bot.export_chat_invite_link(group_id)
            except Exception as e:
                group_name = f"con ID {group_id}"
                group_link = None

            group_text = f"[{group_name}]({group_link})" if group_link else group_name

            game = get_game(group_id)
            if not game.game_active:
                text = get_testo_tematizzato('partita_non_attiva', tema)
                await update.message.reply_text(text)
                return

            if game.extraction_started:
                text = get_testo_tematizzato('partita_iniziata', tema)
                await update.message.reply_text(text)
                return

            if game.players.get(user_id):
                return
            else:
                if await game.add_player(user_id):
                    if update.effective_user.username:
                        game.usernames[user_id] = update.effective_user.username
                    else:
                        game.usernames[user_id] = update.effective_user.full_name

                    # Se il tema è Harry Potter, assegna casualmente una casata e memorizzala
                    assigned_house = None
                    if tema == 'harry_potter':
                        if not getattr(game, 'user_houses', None):
                            game.user_houses = {}
                        assigned_house = game.user_houses.get(user_id)
                        if not assigned_house:
                            houses = ['Grifondoro', 'Serpeverde', 'Corvonero', 'Tassorosso']
                            assigned_house = random.choice(houses)
                            game.user_houses[user_id] = assigned_house
                            # Persistiamo la casata assegnata nelle impostazioni del gruppo
                            try:
                                conf = load_group_settings_from_firebase(group_id) or {}
                                conf_user_houses = conf.get('user_houses', {})
                                conf_user_houses[str(user_id)] = assigned_house
                                conf['user_houses'] = conf_user_houses
                                from firebase_client import save_group_settings_to_firebase
                                save_group_settings_to_firebase(group_id, conf)
                            except Exception:
                                pass

                    cartella = game.players[user_id]
                    formatted_cartella = game.format_cartella(cartella)
                    escaped_cartella = esc(formatted_cartella)
                    # Invia la cartella in privato usando la funzione centralizzata (gestisce fallback)
                    await send_cartella_to_user(user_id, game, group_text, context, tema, assigned_house=assigned_house)

                    if tema == 'harry_potter':
                        if user_id not in getattr(game, 'announced_smistamento_users', set()):
                            # preferiamo @username se disponibile
                            if update.effective_user.username:
                                mention = f"@{update.effective_user.username}"
                            else:
                                mention = esc(update.effective_user.full_name)
                            house_disp = assigned_house or "Casata Sconosciuta"
                            group_msg = f"*_🎩 {mention} è salito sulla sua Nimbus 2000 per la casa {house_disp}\\!_*"
                            try:
                                await context.bot.send_message(
                                    chat_id=group_id,
                                    text=group_msg,
                                    parse_mode=ParseMode.MARKDOWN_V2,
                                    message_thread_id=game.thread_id if game.thread_id else None
                                )
                            except Exception:
                                # fallback al template se il formato diretto dovesse fallire
                                escaped_username = esc(update.effective_user.username or update.effective_user.full_name)
                                text_annuncio = get_testo_tematizzato('annuncio_smistamento', tema, escaped_username=escaped_username, house=house_disp)
                                await context.bot.send_message(chat_id=group_id, text=text_annuncio, parse_mode=ParseMode.MARKDOWN_V2, message_thread_id=game.thread_id if game.thread_id else None)
                            game.announced_smistamento_users.add(user_id)
                    else:
                        if user_id not in getattr(game, 'announced_join_users', set()):
                            escaped_username = esc(update.effective_user.username or update.effective_user.full_name)
                            text_annuncio = get_testo_tematizzato('annuncio_unione', tema, escaped_username=escaped_username)
                            await context.bot.send_message(
                                chat_id=group_id,
                                text=text_annuncio,
                                parse_mode=ParseMode.MARKDOWN_V2,
                                message_thread_id=game.thread_id if game.thread_id else None
                            )
                            game.announced_join_users.add(user_id)
                else:
                    text = get_testo_tematizzato('non_unito_ora', tema)
                    await update.message.reply_text(text)
            return
    group_link = "https://t.me/monopolygoscambioitailtopcontest"
    nickname = update.effective_user.full_name or update.effective_user.username
    escaped_nickname = esc(nickname)
    escaped_username = esc(update.effective_user.username)
    text = get_testo_tematizzato('benvenuto', tema, escaped_nickname=escaped_nickname, escaped_username=escaped_username, group_link=group_link)
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True
    )
    
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    user_id = user.id
    username = user.username or user.full_name
    group_chat_id = query.message.chat.id
    thread_id = getattr(query.message, "message_thread_id", None)
    group_name = query.message.chat.title or "Gruppo Sconosciuto"
    escaped_group_name = esc(group_name)
    group_link = await get_group_link(context, group_chat_id)
    group_text = f"[{escaped_group_name}]({group_link})" if group_link else escaped_group_name

    game = get_game(group_chat_id)
    await log_interaction(user_id, username, group_chat_id, query.data, group_name)

    group_settings = load_group_settings_from_firebase(group_chat_id)
    tema = group_settings.get(str(group_chat_id), {}).get('tema', 'normale') 
    logger.info(f"Tema corrente: {tema}")

    if query.data == 'join_game':
        logger.debug(f"Processando join_game per user {user_id} in chat {group_chat_id}")
        if user_id in game.players_in_game:
            text = get_testo_tematizzato('gia_unito', tema)
            await query.answer(text, show_alert=True)
            return

        if not game.game_active:
            text = get_testo_tematizzato('partita_non_attiva', tema)
            await query.answer(text, show_alert=True)
            return

        if game.extraction_started:
            text = get_testo_tematizzato('partita_iniziata', tema)
            await query.answer(text, show_alert=True)
            return

        try:
            member_status = await context.bot.get_chat_member(group_chat_id, user_id)
            # MODIFICA QUI: Aggiunto 'restricted' per permettere l'ingresso a utenti con limitazioni
            if member_status.status not in ['member', 'administrator', 'creator', 'restricted']:
                text = get_testo_tematizzato('non_membro_gruppo', tema)
                await query.answer(text, show_alert=True)
                logger.info(f"Tentativo di join non autorizzato via bottone: User {user_id} per gruppo {group_chat_id}")
                return
        except telegram.error.BadRequest as e:
            if "User_not_participant" in str(e):
                text = get_testo_tematizzato('non_membro_gruppo', tema)
                await query.answer(text, show_alert=True)
                return
            else:
                raise

        added = await game.add_player(user_id)
        if not added:
            text = get_testo_tematizzato('non_unito_ora', tema)
            await query.answer(text, show_alert=True)
            return

        if update.effective_user.username:
            game.usernames[user_id] = update.effective_user.username
        else:
            game.usernames[user_id] = update.effective_user.full_name

        cartella = game.players[user_id]
        formatted_cartella = game.format_cartella(cartella)
        # Se il tema è Harry Potter, assegna una casata se necessario
        assigned_house = None
        if tema == 'harry_potter':
            if not getattr(game, 'user_houses', None):
                game.user_houses = {}
            assigned_house = game.user_houses.get(user_id)
            if not assigned_house:
                houses = ['🦁 Grifondoro', '🐍 Serpeverde', '🦅 Corvonero', '🦡 Tassorosso']
                assigned_house = random.choice(houses)
                game.user_houses[user_id] = assigned_house
                # Persist the assigned house into Firebase group settings
                try:
                    conf = load_group_settings_from_firebase(group_chat_id) or {}
                    conf_user_houses = conf.get('user_houses', {})
                    conf_user_houses[str(user_id)] = assigned_house
                    conf['user_houses'] = conf_user_houses
                    from firebase_client import save_group_settings_to_firebase
                    save_group_settings_to_firebase(group_chat_id, conf)
                except Exception:
                    pass

            # Usa la funzione centralizzata per inviare la cartella in DM (gestisce fallback)
            await send_cartella_to_user(user_id, game, group_text, context, tema, assigned_house=assigned_house)

            # Invia UNICO annuncio nel gruppo
            if tema == 'harry_potter':
                if update.effective_user.username:
                    user = esc(update.effective_user.username)
                    mention = f"@{user}"
                else:
                    mention = esc(update.effective_user.full_name)
                house_disp = assigned_house or "Casata Sconosciuta"
                group_msg = f"*_🎩 {mention} è salito sulla sua Nimbus 2000 per la casa {house_disp}\\!_*"
                # Only announce smistamento once per user
                if user_id not in getattr(game, 'announced_smistamento_users', set()):
                    try:
                        await context.bot.send_message(chat_id=group_chat_id, text=group_msg, message_thread_id=thread_id, parse_mode=ParseMode.MARKDOWN_V2)
                    except Exception:
                        escape_username = esc(username)
                        text_annuncio = get_testo_tematizzato('annuncio_smistamento', tema, escaped_username=escape_username, house=house_disp)
                        await context.bot.send_message(chat_id=group_chat_id, text=text_annuncio, message_thread_id=thread_id, parse_mode=ParseMode.MARKDOWN_V2)
                    game.announced_smistamento_users.add(user_id)
        elif tema == 'marvel':
            # Inizializza il dizionario se non esiste
            if not getattr(game, 'user_houses', None):
                game.user_houses = {}
            
            assigned_house = game.user_houses.get(user_id)
            
            # Se l'utente non ha ancora un team, assegnane uno
            if not assigned_house:
                # Lista dei Team Marvel
                marvel_teams = [ "Iron Man 🦾", "Captain America 🛡️", "Thor 🔨", "Hulk 💪", "Black Widow 🕷️", "Hawkeye 🏹", "Vision 🤖",
                                "Scarlet Witch 🔮", "Falcon 🦅", "Winter Soldier 🥷", "Ant-Man 🐜", "Wasp 🐝", "Captain Marvel ✨", "War Machine 🛡️",
                                "Spider-Man 🕸️", "Miles Morales 🕷️", "Spider-Gwen 🕸️", "Black Panther 🐆", "Doctor Strange 🪄", "Wong 🧙", "Shang-Chi 🥋",
                                "She-Hulk 🟢", "Moon Knight 🌙", "Blade 🗡️", "Ghost Rider 🔥", "Silver Surfer 🪐", "Adam Warlock 🌟", "Hercules 🏺",
                                "Sentry ⚡", "Punisher 💀", "Daredevil 👨‍🦯", "Jessica Jones 🕵️‍♀️", "Luke Cage 🛡️", "Iron Fist 🥋", "Elektra 🗡️",
                                "Black Cat 🐈‍⬛", "Mister Fantastic 🧠", "Invisible Woman 🫧", "Human Torch 🔥", "Thing 🪨", "Professor X 🧠", "Cyclops 👁️",
                                "Jean Grey 🔥", "Wolverine 🐾", "Storm ⛈️", "Beast 🧪", "Rogue 🦋", "Gambit ♠️", "Nightcrawler 💨",
                                "Colossus 🧱", "Iceman ❄️", "Jubilee 🎆", "Kitty Pryde 🪄", "Psylocke 🔪", "Magneto 🧲", "Star-Lord 🎧",
                                "Gamora 🗡️", "Drax 💪", "Rocket 🦝", "Groot 🌳", "Mantis 🐛", "Nebula 🤖", "Yondu 🎶",
                                "Okoye 🗡️", "Shuri 🧠", "Ms. Marvel 🧕", "Captain Britain 🇬🇧", "Squirrel Girl 🐿️", "Moon Girl 🧠", "Devil Dinosaur 🦖",
                                "Cloak ⚫", "Dagger ⚪", "Wiccan ✨", "Speed ⚡", "Kate Bishop 🏹", "Echo 🦻", "America Chavez ⭐",
                                "Quasar 🌌", "Beta Ray Bill 🐎", "Silk 🕸️"
                            ]

                assigned_house = random.choice(marvel_teams)
                
                game.user_houses[user_id] = assigned_house
                
                # Salvataggio su Firebase
                try:
                    conf = load_group_settings_from_firebase(group_chat_id) or {}
                    conf_user_houses = conf.get('user_houses', {})
                    conf_user_houses[str(user_id)] = assigned_house
                    conf['user_houses'] = conf_user_houses
                    from firebase_client import save_group_settings_to_firebase
                    save_group_settings_to_firebase(group_chat_id, conf)
                except Exception:
                    pass

            # Invia la cartella in DM
            await send_cartella_to_user(user_id, game, group_text, context, tema, assigned_house=assigned_house)

            # Annuncio nel gruppo
            if tema == 'marvel':
                if update.effective_user.username:
                    user = esc(update.effective_user.username)
                    mention = f"@{user}"
                else:
                    mention = esc(update.effective_user.full_name)
                
                team_disp = assigned_house or "Team Sconosciuto"
                
                # Messaggio tematizzato Marvel
                group_msg = f"*_🧬 {mention} è stato reclutato da Nick Fury nel team di {team_disp}\\!_*"
                
                # Controlla se l'annuncio è già stato fatto per questo utente
                if user_id not in getattr(game, 'announced_smistamento_users', set()):
                    try:
                        await context.bot.send_message(chat_id=group_chat_id, text=group_msg, message_thread_id=thread_id, parse_mode=ParseMode.MARKDOWN_V2)
                    except Exception:
                        # Fallback in caso di errore (uso generico o template)
                        pass
                    
                    # Aggiunge l'utente al set degli annunciati
                    game.announced_smistamento_users.add(user_id)
        else:
            if update.effective_user.username:
                user = esc(update.effective_user.username)
                escape_username = f"@{user}"
            else:
                escape_username = esc(update.effective_user.full_name)
            # Only announce normal join once per user
            if user_id not in getattr(game, 'announced_join_users', set()):
                await context.bot.send_message(
                    chat_id=group_chat_id,
                    text=get_testo_tematizzato('annuncio_unione', tema, username=escape_username),
                    message_thread_id=thread_id,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
                game.announced_join_users.add(user_id)
            
            await send_cartella_to_user(user_id, game, group_text, context, tema, assigned_house=assigned_house)

        await query.answer()  
        return  

    elif query.data == 'draw_number':
        await estrai(update, context)
        await query.answer(get_testo_tematizzato('numero_estratto', tema, default="Numero estratto!")) # Aggiunto default per retrocompatibilità
        return

    elif query.data == 'stop_game':
        await stop_game(update, context)
        # Potresti voler usare un messaggio tematizzato anche qui
        await query.answer(get_testo_tematizzato('partita_interrotta', tema, default="Partita interrotta!")) # Aggiunto default per retrocompatibilità
        return

    elif query.data == 'mostra_cartella':
        await show_cartella(user_id, game, query, tema) # Passo il tema a show_cartella
        return

    else:
        logger.warning(f"Azione non gestita in button: {query.data}")
        await query.answer()
        
async def get_group_link(context, group_chat_id):
    try:
        chat = await context.bot.get_chat(group_chat_id)
        return f"https://t.me/{chat.username}" if chat.username else await context.bot.export_chat_invite_link(group_chat_id)
    except Exception:
        return None

async def send_cartella_to_user(user_id, game, group_text, context, tema, assigned_house=None): # Aggiunto parametro tema e assigned_house
    cartella = game.players[user_id]
    formatted_cartella = game.format_cartella(cartella)
    escaped_cartella = esc(formatted_cartella)
    try:
        if assigned_house:
            try:
                house_escaped = esc(str(assigned_house))
            except Exception:
                house_escaped = str(assigned_house)
            text_cartella = get_testo_tematizzato('messaggio_cartella', tema, group_text=group_text, escaped_cartella=escaped_cartella, house=house_escaped)
        else:
            text_cartella = get_testo_tematizzato('messaggio_cartella', tema, group_text=group_text, escaped_cartella=escaped_cartella)
        await context.bot.send_message(
            chat_id=user_id,
            text=text_cartella,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True
        )
    except Exception:
        logger.error(f"Errore invio cartella in privato a {user_id}; invio fallback in gruppo {game.chat_id}")
        try:
            bot_info = await context.bot.get_me()
            bot_username = bot_info.username if getattr(bot_info, 'username', None) else None
            bot_link = f"https://t.me/{bot_username}" if bot_username else None
            button = InlineKeyboardMarkup([[InlineKeyboardButton("Apri chat privata", url=bot_link)]]) if bot_link else None
            user_display = game.usernames.get(user_id) or f"Utente_{user_id}"
            escape_user = esc(user_display)
            fallback_text = get_testo_tematizzato('errore_invio_cartella', tema) + f" @{escape_user}"
            await context.bot.send_message(
                chat_id=game.chat_id,
                text=fallback_text,
                reply_markup=button,
                message_thread_id=game.thread_id,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception as e:
            logger.error(f"Errore nel fallback invio cartella al gruppo {game.chat_id}: {e}")

async def show_cartella(user_id, game, query, tema): # Aggiunto parametro tema
    """Mostra la cartella del giocatore."""
    if user_id not in game.players:
        await query.answer(get_testo_tematizzato('non_in_partita', tema), show_alert=True)
    else:
        cartella = game.players[user_id]
        formatted_cartella = game.format_cartella(cartella)
        # Usa un nuovo messaggio tematizzato per la cartella nell'alert
        alert_text = get_testo_tematizzato('mostra_cartella_alert', tema, formatted_cartella=formatted_cartella)
        # Tronca se necessario
        if len(alert_text) > 200:
            alert_text = alert_text[:197] + "..."
        await query.answer(text=alert_text, show_alert=True)

async def estrai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name
    chat_id, thread_id = get_chat_id_or_thread(update)
    group_name = update.message.chat.title or "il gruppo"
    await log_interaction(user_id, username, chat_id, "/estrai", group_name)

    # Recupero tema per messaggi interni alla funzione estrai
    group_settings = load_group_settings_from_firebase(chat_id)
    tema = group_settings.get(str(chat_id), {}).get('tema', 'normale')

    if update and not await is_admin(update, context):
        if update.message:
            await update.message.reply_text(get_testo_tematizzato('estrazione_solo_admin', tema))
        return

    if update:
        chat_id, thread_id = get_chat_id_or_thread(update)
    elif context.job:
        chat_id = context.job.chat_id
        game_temp = get_game(chat_id)
        thread_id = game_temp.thread_id
    else:
        return

    game = get_game(chat_id)
    if not game or not game.game_active:
        if update and update.message:
            await context.bot.send_message(
                chat_id=chat_id,
                text=get_testo_tematizzato('nessuna_partita_attiva_per_estrazione', tema),
                message_thread_id=thread_id
            )
        return

    if not game.extraction_started:
        game.start_extraction()

    # Recupero settings per modalità estrazione e bonus/malus
    group_settings = load_group_settings_from_firebase(chat_id).get(str(chat_id), {})
    # parti: default tema-based, poi override con le impostazioni di gruppo
    theme_defaults = get_default_feature_states(tema)
    group_overrides = group_settings.get("bonus_malus_settings", {})
    # union di chiavi
    all_keys = set(theme_defaults.keys()) | set(group_overrides.keys())
    feature_states = {k: group_overrides.get(k, theme_defaults.get(k, False)) for k in all_keys}
    mode = group_settings.get('extraction_mode', 'manual')

    keyboard_buttons = [
        [InlineKeyboardButton("🔎 Vedi Cartella", callback_data='mostra_cartella')]
    ]
    reply_markup_keyboard = InlineKeyboardMarkup(keyboard_buttons)

    async def dm_if_present(user_id: int, number_drawn: int, current_game_instance, bot_context):
        name = current_game_instance.usernames.get(user_id)
        if not name:
            try:
                member = await bot_context.bot.get_chat_member(current_game_instance.chat_id, user_id)
                name = member.user.username or member.user.full_name or f"Utente_{user_id}"
            except Exception as e:
                name = f"Utente_{user_id}"
            current_game_instance.usernames[user_id] = name

        escaped_name_for_log = esc(name)
        updated = current_game_instance.update_cartella(user_id, number_drawn)
        if updated:
            cart_text = current_game_instance.format_cartella(current_game_instance.players[user_id])
            escaped_cart_text = esc(cart_text)
            try:
                # Usa messaggio tematizzato per la DM quando si ha il numero
                text_avuto_numero = get_testo_tematizzato('numero_avuto_dm', tema, number_drawn=number_drawn, escaped_cart_text=escaped_cart_text)
                await bot_context.bot.send_message(
                    chat_id=user_id,
                    text=text_avuto_numero,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            except Exception as e:
                logger.error(f"[dm_if_present] Errore nell'invio DM a {user_id} ({escaped_name_for_log}): {e}")

            await current_game_instance.check_winner(user_id, name, bot_context) # Passo tema anche a check_winner se necessario

    async def update_all_players_dm_and_check_minor_wins(current_game_instance, number_drawn, bot_context):
        # Filtra solo i giocatori che hanno effettivamente il numero
        players_to_notify = []
        for uid in current_game_instance.players_in_game:
            players_to_notify.append(uid)

        if not players_to_notify:
            return

        # Elabora a blocchi di 10 utenti per volta
        chunk_size = 25
        for i in range(0, len(players_to_notify), chunk_size):
            chunk = players_to_notify[i:i + chunk_size]
            tasks = [
                asyncio.create_task(dm_if_present(uid, number_drawn, current_game_instance, bot_context))
                for uid in chunk
            ]
            
            # Esegui il blocco e gestisci errori
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for res_idx, err_or_res in enumerate(results):
                if isinstance(err_or_res, Exception):
                    uid_err = chunk[res_idx]
                    logger.error(f"Errore DM per {uid_err}: {err_or_res}")

            # Pausa anti-flood tra i blocchi (solo se ce ne sono altri)
            if i + chunk_size < len(players_to_notify):
                await asyncio.sleep(0.5)

    async def extract_loop():
        nonlocal game, feature_states, mode
        run_once = (mode == 'manual')
        while game.game_active:
            current_number_val = None
            try:
                current_number_val = await game.draw_number(context)
            except telegram.error.RetryAfter as e:
                await asyncio.sleep(e.retry_after)
                continue
            except Exception as e:
                break

            if current_number_val is None:
                if game.game_active:
                    try:
                        await context.bot.send_message(
                            chat_id=game.chat_id,
                            text=get_testo_tematizzato('tutti_numeri_estratti', tema),
                            message_thread_id=game.thread_id
                        )
                    except telegram.error.RetryAfter as e:
                        await asyncio.sleep(e.retry_after)
                    except Exception as e:
                        logger.error(f"[extract] Errore nell'invio messaggio fine numeri: {e}")

                    effective_update_for_end = update if update else type(
                        'obj', (object,), {
                            'effective_chat': type('obj', (object,), {'id': game.chat_id}),
                            'effective_message': type('obj', (object,), {'is_topic_message': bool(game.thread_id), 'message_thread_id': game.thread_id}),
                            'effective_user': None
                        }
                    )()
                    await end_game(effective_update_for_end, context)
                break

            # Invia messaggio dell'estrazione
            try:
                text_numero_estratto = get_testo_tematizzato('numero_estratto_annuncio', tema, current_number_val=current_number_val)
                msg = await context.bot.send_message(
                    chat_id=game.chat_id,
                    text=text_numero_estratto,
                    reply_markup=reply_markup_keyboard,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    message_thread_id=game.thread_id
                )
                game.number_message_ids.append(msg.message_id)
            except telegram.error.RetryAfter as e:
                logger.warning(f"[extract_loop] Flood control su annuncio numero {current_number_val}: attendo {e.retry_after}s…")
                await asyncio.sleep(e.retry_after)
                if current_number_val in game.numeri_estratti:
                    try:
                        game.numeri_estratti.pop()
                    except IndexError:
                        pass
                game.numeri_tombola.insert(0, current_number_val)
                continue
            except Exception as e:
                logger.error(f"[extract_loop] Errore nell'invio messaggio numero {current_number_val}: {e}")

            # Gestione Bonus/Malus
            if current_number_val in [110, 666, 104, 404]:
                if feature_states.get(str(current_number_val), True):
                    player_id_affected = random.choice(list(game.players_in_game))
                    try:
                        member = await context.bot.get_chat_member(game.chat_id, player_id_affected)
                        raw_name = member.user.username or member.user.full_name or f"Utente_{player_id_affected}"
                        user_affected_escaped_name = esc(raw_name)
                    except Exception:
                        user_affected_escaped_name = esc(f"Utente_{player_id_affected}")

                    punti_val = random.randint(1, 49)
                    message_special_text = ""

                    if current_number_val == 110:
                        game.add_score(player_id_affected, punti_val)
                        message_special_text = get_testo_tematizzato('bonus_110', tema, user_affected_escaped_name=user_affected_escaped_name, punti_val=punti_val)
                    elif current_number_val == 666:
                        game.add_score(player_id_affected, -punti_val)
                        message_special_text = get_testo_tematizzato('malus_666', tema, user_affected_escaped_name=user_affected_escaped_name, punti_val=punti_val)
                    elif current_number_val == 104:
                        game.add_score(player_id_affected, punti_val)
                        message_special_text = get_testo_tematizzato('bonus_104', tema, user_affected_escaped_name=user_affected_escaped_name, punti_val=punti_val)
                    elif current_number_val == 404:
                        game.add_score(player_id_affected, -punti_val)
                        message_special_text = get_testo_tematizzato('malus_404', tema, user_affected_escaped_name=user_affected_escaped_name, punti_val=punti_val)

                    if message_special_text:
                        try:
                            msg_bonus = await context.bot.send_message(
                                chat_id=game.chat_id,
                                text=message_special_text,
                                parse_mode=ParseMode.MARKDOWN_V2,
                                message_thread_id=game.thread_id
                            )
                        except Exception as e:
                            logger.error(f"[extract_loop] Errore invio bonus/malus per numero {current_number_val} a chat {game.chat_id}: {e}")

                    sticker_id = get_sticker_for_number(current_number_val, tema)
                    if sticker_id:
                        try:
                            msg_sticker = await context.bot.send_sticker(
                                chat_id=game.chat_id,
                                sticker=sticker_id,
                                message_thread_id=game.thread_id
                            )
                            game.number_message_ids.append(msg_sticker.message_id)
                        except Exception as e:
                            logger.error(f"[extract_loop] Errore invio sticker bonus/malus {current_number_val} a chat {game.chat_id}: {e}")

            # Invio sticker speciali per 69 e 90 (saltare se tema == 'harry_potter')
            if current_number_val in [69, 90] and tema not in ['harry_potter', 'marvel']:
                sticker_special = get_sticker_for_number(current_number_val, tema)
                if sticker_special:
                    try:
                        msg_special = await context.bot.send_sticker(
                            chat_id=game.chat_id,
                            sticker=sticker_special,
                            message_thread_id=game.thread_id
                        )
                        game.number_message_ids.append(msg_special.message_id)
                    except Exception as e:
                        logger.error(f"[extract_loop] Errore sticker {current_number_val} (post-annuncio) per chat {game.chat_id}: {e}")

            # Aggiorna cartelle e controlla vincitori minori
            if game.players_in_game:
                try:
                    await update_all_players_dm_and_check_minor_wins(game, current_number_val, context)
                except Exception as e:
                    logger.error(f"[extract_loop] Errore in update_all_players_dm_and_check_minor_wins per numero {current_number_val}: {e}")
            else:
                logger.info(f"[extract_loop] Nessun giocatore in partita per il numero {current_number_val} in chat {game.chat_id}, salto aggiornamento cartelle.")

            if mode == 'auto':
                await asyncio.sleep(1)

            partita_terminata_da_tombola = False
            if game.game_active:
                try:
                    partita_terminata_da_tombola = await game.check_for_tombola(context)
                except Exception as e:
                    logger.error(f"[extract_loop] Errore in game.check_for_tombola: {e}")
                    partita_terminata_da_tombola = True

            if partita_terminata_da_tombola:
                effective_update_for_end = update if update else type(
                    'obj', (object,), {
                        'effective_chat': type('obj', (object,), {'id': game.chat_id}),
                        'effective_message': type('obj', (object,), {'is_topic_message': bool(game.thread_id), 'message_thread_id': game.thread_id}),
                        'effective_user': None
                    }
                )()
                await end_game(effective_update_for_end, context)
                break

            if run_once:
                break

        if not game.game_active and not run_once:
            logger.info(f"[extract_loop] Uscita dal loop di estrazione per chat_id={game.chat_id} perché game.game_active è False.")

    if mode == 'auto':
        if not game.extraction_task or game.extraction_task.done():
            game.extraction_task = asyncio.create_task(extract_loop())
    else:
        await extract_loop()

async def auto_extraction_loop(update, context, game, chat_id, thread_id, extract_and_update_func):
    while game.game_active and not game.game_interrupted:
        extracted = await extract_and_update_func()
        if not extracted or game.game_interrupted:
            break
        await asyncio.sleep(3)

async def end_game(update, context):
    chat_id, thread_id = get_chat_id_or_thread(update)
    game = get_game(chat_id)
    # Se ci sono punteggi nella partita corrente, proviamo ad aggiornare la classifica overall.
    try:
        if game.current_game_scores:
            game.update_overall_scores()
    except Exception as e:
        logger.error(f"Errore aggiornando la classifica overall al termine partita in chat {chat_id}: {e}")

    # Aggiungiamo una voce di log che indica la conclusione della partita
    try:
        entry = {
            'timestamp': datetime.now().astimezone().isoformat(),
            'command': 'game_end',
            'chat_id': chat_id
        }
        try:
            add_log_entry(chat_id, entry)
        except Exception:
            # fallback diretto su DB se add_log_entry non riesce
            ref = db.reference(f"logs/{chat_id}")
            new_ref = ref.push()
            new_ref.set(entry)
    except Exception:
        pass

    # Invia la classifica overall anche se la partita è stata interrotta;
    # manteniamo il messaggio di interruzione se il gioco è stato segnato come interrotto.
    try:
        await send_final_rankings(update, context)
    except Exception as e:
        logger.error(f"Errore inviando la classifica finale in chat {chat_id}: {e}")

    if game.game_interrupted:
        group_settings = load_group_settings_from_firebase(chat_id)
        tema = group_settings.get(str(chat_id), {}).get('tema', 'normale') # Recupero tema per messaggio interruzione
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=get_testo_tematizzato('partita_interrotta_no_punti', tema),
                message_thread_id=thread_id
            )
        except Exception as e:
            logger.error(f"Errore inviando messaggio interruzione in chat {chat_id}: {e}")

    # Eliminazione messaggi numeri se impostato
    group_settings = load_group_settings_from_firebase(chat_id).get(str(chat_id), {})
    delete_flag = group_settings.get('delete_numbers_on_end', False)
    if delete_flag:
        for msg_id in game.number_message_ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception as e:
                logger.warning(f"[end_game] Impossibile cancellare msg {msg_id} in chat {chat_id}: {e}")

    game.reset_game()
    game.stop_game()

import json
import os

async def send_final_rankings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, thread_id = get_chat_id_or_thread(update)
    group_settings = load_group_settings_from_firebase(chat_id)
    tema = group_settings.get(str(chat_id), {}).get('tema', 'normale')
    sticker_file_id = get_final_sticker(tema) or "CAACAgQAAxkBAAEt32Rm8Z_GRtaOFHzCVCFePFCU0rk1-wACNQEAAubEtwzIljz_HVKktzYE"

    classifica_gruppo = load_classifica_from_firebase(chat_id)
    if not classifica_gruppo:
        group_settings = load_group_settings_from_firebase(chat_id)
        tema = group_settings.get(str(chat_id), {}).get('tema', 'normale') # Recupero tema per messaggio classifica vuota
        await context.bot.send_message(
            chat_id=chat_id,
            text=get_testo_tematizzato('nessuna_classifica', tema),
            message_thread_id=thread_id,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    ordinata = sorted(classifica_gruppo.items(), key=lambda item: item[1], reverse=True)
    lines = []
    for idx, (user_id_str, punti) in enumerate(ordinata, start=1):
        if punti == 0:
            continue
        try:
            user_id_int = int(user_id_str)
            info = await context.bot.get_chat(user_id_int)
            nome = info.username or info.first_name
        except Exception:
            nome = f"utente_{user_id_str}"
        raw_line = f"{idx}. @{nome}: {punti} punti\n"
        lines.append(esc(raw_line))

    if not lines:
        group_settings = load_group_settings_from_firebase(chat_id)
        tema = group_settings.get(str(chat_id), {}).get('tema', 'normale') # Recupero tema per messaggio classifica vuota (anche se i punti sono 0)
        await context.bot.send_message(
            chat_id=chat_id,
            text=get_testo_tematizzato('nessuna_classifica', tema),
            message_thread_id=thread_id,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    testo = get_testo_tematizzato('classifica_finale', tema, lines="".join(lines))
    await context.bot.send_message(chat_id=chat_id, text=testo, message_thread_id=thread_id, parse_mode=ParseMode.MARKDOWN_V2)
    await context.bot.send_sticker(chat_id=chat_id, sticker=sticker_file_id, message_thread_id=thread_id)

async def stop_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name
    chat_id, thread_id = get_chat_id_or_thread(update)
    group_name = update.message.chat.title or "il gruppo"
    await log_interaction(user_id, username, chat_id, "/stop", group_name)

    if not await is_admin(update, context):
        group_settings = load_group_settings_from_firebase(chat_id)
        tema = group_settings.get(str(chat_id), {}).get('tema', 'normale') # Recupero tema per messaggio admin
        await update.message.reply_text(get_testo_tematizzato('stop_solo_admin', tema))
        return

    chat_id, thread_id = get_chat_id_or_thread(update)
    game = get_game(chat_id)
    game.stop_game(interrupted=True)

    group_settings = load_group_settings_from_firebase(chat_id)
    tema = group_settings.get(str(chat_id), {}).get('tema', 'normale') # Recupero tema per messaggio interruzione
    await context.bot.send_message(
        chat_id=chat_id,
        text=get_testo_tematizzato('messaggio_stop', tema),
        message_thread_id=thread_id,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    game.current_game_scores.clear()

async def reset_classifica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name
    chat_id, thread_id = get_chat_id_or_thread(update)
    group_name = update.message.chat.title or "il gruppo"
    await log_interaction(user_id, username, chat_id, "/azzera", group_name)

    if not await is_admin(update, context):
        group_settings = load_group_settings_from_firebase(chat_id)
        tema = group_settings.get(str(chat_id), {}).get('tema', 'normale') # Recupero tema per messaggio admin
        await update.message.reply_text(get_testo_tematizzato('reset_classifica_solo_admin', tema))
        return

    save_classifica_to_firebase(chat_id, {})
    group_settings = load_group_settings_from_firebase(chat_id)
    tema = group_settings.get(str(chat_id), {}).get('tema', 'normale') # Recupero tema per messaggio reset
    await update.message.reply_text(
        get_testo_tematizzato('messaggio_reset_classifica', tema),
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def regole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_origin = update.effective_chat.id
    username = update.effective_user.username or update.effective_user.first_name or str(user_id)
    escaped_username = esc(username)

    raw_conf = load_group_settings_from_firebase(chat_origin) or {}
    conf = raw_conf.get(str(chat_origin), {})
    custom_premi = conf.get("premi", premi_default)

    # Recupero tema per i messaggi di regole
    tema = conf.get('tema', 'normale')

    keyboard = [
        [InlineKeyboardButton("🌐 Comandi",    callback_data=f"rule_comandi|{chat_origin}"),
         InlineKeyboardButton("🆒 Partecipare", callback_data=f"rule_unirsi|{chat_origin}")],
        [InlineKeyboardButton("🔁 Estrazione", callback_data=f"rule_estrazione|{chat_origin}"),
         InlineKeyboardButton("🏆 Punteggi",    callback_data=f"rule_punteggi|{chat_origin}")],
        [InlineKeyboardButton("☯️ Bonus/Malus", callback_data=f"rule_bonus_malus|{chat_origin}")],
        [InlineKeyboardButton("❌ Chiudi",       callback_data=f"rule_close|{chat_origin}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=get_testo_tematizzato('regole_introduzione', tema),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        await update.message.reply_text(
            get_testo_tematizzato('errore_invio_regole_privato', tema, escaped_username=escaped_username),
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    # Se il comando è stato eseguito in un gruppo (chat_origin != user_id), invia nel gruppo
    try:
        chat_id_origin, thread_id = get_chat_id_or_thread(update)
    except Exception:
        chat_id_origin = getattr(update.effective_chat, 'id', None)
        thread_id = None

    if chat_id_origin is not None and chat_id_origin != user_id:
        texto = get_testo_tematizzato('messaggio_invio_regole_privato', tema, escaped_username=escaped_username)
        try:
            await context.bot.send_message(
                chat_id=chat_id_origin,
                text=texto,
                parse_mode=ParseMode.MARKDOWN_V2,
                message_thread_id=thread_id
            )
        except Exception:
            # Primo fallback: invia il testo con escape sicuro (dovrebbe risolvere problemi MarkdownV2)
            try:
                await context.bot.send_message(
                    chat_id=chat_id_origin,
                    text=esc(texto),
                    parse_mode=ParseMode.MARKDOWN_V2,
                    message_thread_id=thread_id
                )
            except Exception:
                # Secondo fallback: prova a rispondere nella chat originale (se disponibile)
                try:
                    if update.message:
                        await update.message.reply_text(
                            esc(texto),
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                except Exception:
                    # Ultimo fallback: invia senza parse_mode come testo semplice
                    try:
                        await context.bot.send_message(
                            chat_id=chat_id_origin,
                            text=esc(texto),
                            message_thread_id=thread_id,
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                    except Exception:
                        pass

    try:
        await update.message.delete()
    except Exception:
        pass

async def rule_section_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('|')
    action = data[0].split('_', 1)[1]  # es. "comandi", "unirsi", etc.
    chat_origin = data[1] if len(data) > 1 else None
    user_id = query.from_user.id

    # Determina l'ID del gruppo di origine: preferiamo il valore passato nel callback (chat_origin)
    try:
        chat_id = int(chat_origin) if chat_origin is not None else getattr(query.message.chat, 'id', None)
    except Exception:
        chat_id = getattr(query.message.chat, 'id', None)

    group_settings = load_group_settings_from_firebase(chat_id) if chat_id is not None else {}
    tema = group_settings.get(str(chat_id), {}).get('tema', 'normale')

    if action == 'back':
        # Torna al menu principale: usiamo lo stesso testo e la stessa tastiera di `regole()`
        text_to_send = get_testo_tematizzato('regole_introduzione', tema)

        keyboard = [
               [InlineKeyboardButton("🌐 Comandi", callback_data=f"rule_comandi|{chat_origin}"),
                   InlineKeyboardButton("🆒 Partecipare", callback_data=f"rule_unirsi|{chat_origin}" )],
                  [InlineKeyboardButton("🔁 Estrazione", callback_data=f"rule_estrazione|{chat_origin}"),
                   InlineKeyboardButton("🏆 Punteggi", callback_data=f"rule_punteggi|{chat_origin}")],
                  [InlineKeyboardButton("☯️ Bonus/Malus", callback_data=f"rule_bonus_malus|{chat_origin}" )],
                  [InlineKeyboardButton("❌ Chiudi", callback_data=f"rule_close|{chat_origin}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.message.edit_text(
                text_to_send,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True
            )
        except Exception:
            await query.answer("Errore interno. Riprova.", show_alert=True)
            await context.bot.send_message(
                chat_id=user_id,
                text=text_to_send,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        return

    if action == 'close':
        await query.message.delete()
        return

    section_key = action  # es. "comandi", "unirsi", etc.

    # Sezione speciale: punteggi -> inseriamo i valori dei premi dal gruppo
    if section_key == 'punteggi':
        group_title = None
        group_link = None
        try:
            if chat_id:
                chat_obj = await context.bot.get_chat(chat_id)
                group_title = chat_obj.title or str(chat_id)
                if getattr(chat_obj, 'username', None):
                    group_link = f"https://t.me/{chat_obj.username}"
                else:
                    try:
                        group_link = await context.bot.export_chat_invite_link(chat_id)
                    except Exception:
                        group_link = None
        except Exception:
            group_title = None
            group_link = None

        if group_title:
            escaped_title = esc(group_title)
            header = f"[{escaped_title}]({group_link})" if group_link else f"{escaped_title}"
        else:
            header = ""

        raw_conf = load_group_settings_from_firebase(chat_id) or {}
        conf = raw_conf.get(str(chat_id), {})
        premi_dict = conf.get("premi", premi_default)
        val_tombolino = premi_dict.get("tombola", 50) // 2

        text_to_send = get_testo_tematizzato(
            'regole_punteggi',
            tema,
            header=header,
            premi_ambo=premi_dict.get('ambo', 5),
            premi_terno=premi_dict.get('terno', 10),
            premi_quaterna=premi_dict.get('quaterna', 15),
            premi_cinquina=premi_dict.get('cinquina', 20),
            premi_tombola=premi_dict.get('tombola', 50),
            premi_tombolino=val_tombolino
        )
        # Pulsanti di ritorno/chiudi anche per la sezione punteggi
        back_button = [
            [InlineKeyboardButton("🔙 Indietro", callback_data=f"rule_back|{chat_origin}"), InlineKeyboardButton("❌ Chiudi", callback_data=f"rule_close|{chat_origin}")]
        ]
    else:
        # Usa messaggio tematizzato generico se esiste, altrimenti quello specifico
        text_to_send = get_testo_tematizzato(f'regole_{section_key}', tema, default=_RULES_SECTIONS.get(section_key, "Testo non trovato."))

        back_button = [
            [InlineKeyboardButton("🔙 Indietro", callback_data=f"rule_back|{chat_origin}"), InlineKeyboardButton("❌ Chiudi",       callback_data=f"rule_close|{chat_origin}")]
        ]
    reply_markup = InlineKeyboardMarkup(back_button)

    try:
        await query.message.edit_text(
            text_to_send,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        await query.answer("Errore interno. Riprova.", show_alert=True)
        await context.bot.send_message(
            chat_id=user_id,
            text=text_to_send,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )

_RULES_SECTIONS = {
    "comandi": (
        "*🌐 Comandi\\:*\n"
        "_🛃 Qui trovi fondamentalmente tutti i comandi del bot, alcuni utilizzabili solo dai moderatori altri accessibili a tutti, "
        "vediamone una rapida spiegazione\\:_\n"
        "*1️⃣ /trombola*\n"
        "_Il comando principale, di default lo possono usare solo i moderatori e ti permette di avviare una partita\\._\n"
        "*2️⃣ /impostami*\n"
        "_Con questo comando puoi decidere come e cosa cambiare all'interno del gruppo, non voglio dilungarmi troppo, provalo nel gruppo, "
        "se sei moderatore, e sperimenta tu stesso\\._\n"
        "*3️⃣ /classifiga*\n"
        "_No non è un errore di battitura, si chiama davvero così il comando, intuibilmente ti permette di visualizzare la classifica del "
        "gruppo, ovviamente se sei moderatore\\._\n"
        "*4️⃣ /azzera*\n"
        "_Anche per questo di default devi essere un moderatore, anche perchè resetta totalmente la classifica del gruppo, maneggiare con cura\\._\n"
        "*5️⃣ /stop*\n"
        "_Se per qualunque motivo \\(ad esempio perchè non hai messo nemmeno un numero\\) volessi interrompere la partita, beh con questo "
        "comando puoi farlo, ah se sei moderatore\\._\n"
        "*6️⃣ /estrai*\n"
        "_Che partita di tombola sarebbe se i numeri non venissero estratti, d'altronde c'è da fare solo questo, quindi moderatore sta a te, "
        "usa questo comando e dai inizio alla partita e che vinca il migliore\\._\n"
        "*7️⃣ /trombolatori*\n"
        "_Se per caso ti interessa sapere quante persone stanno tromb\\.\\.\\. volevo dire partecipando alla partita usa questo comando, "
        "ah e questo possono usarlo tutti\\._"
    ),
    "unirsi": (
        "*🆒 Partecipare\\:*\n"
        "_🆗 Ora, probabilmente ti starai chiedendo, bello tutto eh, ma come faccio a partecipare alla partita? Nulla di più semplice, "
        "quando un moderatore avrà iniziato una partita col comando /trombola \\(non usarlo qui non funzionerà\\) comparirà un bottone come "
        "questo '➕ Unisciti' cliccaci sopra e riceverai la cartella in questa chat e il gioco è fatto\\. Ora non ti resta che sperare che "
        "escano i tuoi numeri\\._"
    ),
    "estrazione": (
        "*🔁 Estrazione\\:*\n"
        "_🔀 Come nella più classica delle tombole i numeri vanno da 1 a 90, una volta estratto il primo numero voi non dovrete fare niente "
        "se non accertarvi dei numeri che escono e che vi vengono in automatico segnati dal bot\\. Il vero lavoro ce l'ha il moderatore che deve "
        "estrarre i numeri ma se va a darsi un'occhiata alle impostazioni anche per lui sarà una passeggiata\\._"
    ),
    "bonus_malus": (
        "*☯️ Bonus/Malus\\:*\n"
        "_🏧 Se non vi piace la monotonia e volete rendere piu interessante le classifica, allora dovete assolutamente leggervi cosa fanno "
        "questi bonus/malus e correre ad avvisare il vostro admin di fiducia di attivarli\\:_\n"
        "_🔽 Ciascuno di questi numeri è stato aggiunto al sacchetto ed una volta estratto potrà aggiungervi o togliervi  un numero "
        "randomico di punti \\(da 1 a 49\\)\\. No non vi compariranno in cartella, il fortunato o sfortunato verrà scelto a caso tra tutti "
        "quelli in partita\\._\n"
        "*1️⃣ {bonus_104_name}*\n"
        "_Spero non siate per il politically correct, nel caso ci dispiace \\(non è vero\\)\\._\n"
        "*2️⃣ {malus_666_name}*\n"
        "_Se siete fan sfegatati di Dio vi consiglio di disattivarlo dalle impostazioni\\._\n"
        "*3️⃣ {bonus_110_name}*\n"
        "_Un po' come per la laurea, vi diamo la lode ma il valore di essa non dipende da noi\. O se preferite come lo stato, vi diamo il "
        "110\\% di quanto avete speso\._\n"
        "*4️⃣ {malus_404_name}*\n"
        "_Error 404 Not Found\\. Impossibile caricare il testo del Malus\._\n"
        "_⏸️ Pensavate davvero avessimo finito qui\\? Pff non ci conoscete bene, per gli amanti della tombola abbiamo anche introdotto "
        "un extra\\:_\n"
        "*5️⃣ Tombolino*\n"
        "_Spero lo conosciate nel caso ve lo spiego brevemente\\. Se attivato dalle impostazioni un altro utente avrà la possibilità di "
        "fare tombola\\. Fondamentalmente viene premiato il secondo giocatore a farla, ma ovviamente non con gli stessi punti della prima\\._"
    )
}
