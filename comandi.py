import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import telegram
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from game_instance import get_game, load_classifica_from_json, save_classifica_to_json
from variabili import get_chat_id_or_thread, is_admin, load_group_settings, get_sticker_for_number
import asyncio
import json
import os
from log import log_interaction
from telegram.helpers import escape_markdown
from asyncio.log import logger

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name
    chat_id, thread_id = get_chat_id_or_thread(update)
    group_name = update.message.chat.title or "il gruppo"
    await log_interaction(user_id, username, chat_id, "/trombola", group_name)

    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Solo gli amministratori possono avviare il gioco.")
        return

    game = get_game(chat_id)
    game.set_chat_id(chat_id)
    game.set_thread_id(thread_id)
    game.overall_scores = load_classifica_from_json(chat_id)

    group_settings = load_group_settings()
    custom_scores = group_settings.get(str(chat_id), {}).get("premi")
    if custom_scores:
        game.custom_scores = custom_scores
    else:
        game.custom_scores = {
            "ambo": 5,
            "terno": 10,
            "quaterna": 15,
            "cinquina": 20,
            "tombola": 50
        }

    # Recupera (se disponibile) il link del gruppo
    if update.message.chat.username:
        group_link = f"https://t.me/{update.message.chat.username}"
    else:
        try:
            group_link = await context.bot.export_chat_invite_link(chat_id)
        except Exception as e:
            group_link = None

    game.reset_game()

    # Definisci i pulsanti per la gestione della partita
    keyboard = [
        [InlineKeyboardButton("➕ Unisciti", callback_data='join_game')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=chat_id,
        text="*🆕 Partita di tombola cominciata\\!*\n\n"
            "_🔽 Premi 'Unisciti' per entrare, ma prima accertati di aver avviato il bot_\n\n"
            "_🔜 Moderatore quando sei pronto avvia la partita con il comando /estrai  se poi vorrai interromperla usa /stop "
            "e che vinca il migliore\\! Per qualunque dubbio usate /regolo per ricevere le regole_",
        reply_markup=reply_markup,
        message_thread_id=thread_id,
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.args:
        command_argument = context.args[0]
        if command_argument.startswith("join_game_"):
            try:
                group_id = int(command_argument.split("_", 2)[2])
            except Exception as e:
                await update.message.reply_text("Parametro non valido.")
                return
            # Recupera info del gruppo per ottenere nome e link
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
                await update.message.reply_text("🚫 Non ci sono partite in corso in questo gruppo.")
                return
            if game.extraction_started:
                await update.message.reply_text("🚫 La partita è già iniziata, non puoi unirti ora. Aspetta la prossima partita!")
                return

            # Se l'utente è già iscritto, non invio alcun messaggio
            if game.players.get(user_id):
                return
            else:
                if game.add_player(user_id):
                    if update.effective_user.username:
                       game.usernames[user_id] = update.effective_user.username
                    else:
                      game.usernames[user_id] = update.effective_user.full_name

                    cartella = game.players[user_id]
                    formatted_cartella = game.format_cartella(cartella)
                    await context.bot.send_message(
                        chat_id=group_id,
                        text=f"*🏁 Sei ufficialmente nella partita del gruppo {group_text}, ecco la tua cartella\\:*\n\n{formatted_cartella}",
                        parse_mode=ParseMode.MARKDOWN_V2,
                        disable_web_page_preview=True
                    )
                else:
                    await update.message.reply_text("🔜 Non puoi unirti alla partita ora.")
            return

    group_link = "https://t.me/monopolygoscambioitailtopcontest"
    nickname = update.effective_user.full_name or update.effective_user.username
    escaped_nickname = escape_markdown(nickname, version=2)
    escaped_username = escape_markdown(update.effective_user.username, version=2)
    await update.message.reply_text(
        f"*Benvenuto [{escaped_nickname}](https://t.me/{escaped_username})*\\!\n\n"
        f"Questo è il bot ufficiale di [Monopoly Go Contest e Regali]({group_link}), "
        "aggiungilo liberamente nel tuo gruppo e gioca a Tombola con i tuoi amici\\. "
        "Utilizzando il comando /impostami potrai gestire al meglio le impostazioni, con /trombola invece darai inizio alla partita e che vinca il migliore, o meglio, il più fortunato\\.\n\n"
        "_Buona Trombolata_",
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
    escaped_group_name = escape_markdown(group_name, version=2)

    # Recupera il link del gruppo in modo asincrono
    group_link = await get_group_link(context, group_chat_id)

    group_text = f"[{escaped_group_name}]({group_link})" if group_link else escaped_group_name
    game = get_game(group_chat_id)

    await log_interaction(user_id, username, group_chat_id, query.data, group_name)

    # Gestione della richiesta di unirsi al gioco
    if query.data == 'join_game':
        # Controllo se l'utente è già iscritto
        if user_id in game.players_in_game:
            await query.answer("Sei già iscritto alla partita!", show_alert=True)
            return

        # Verifica stato della partita
        if not game.game_active:
            await query.answer("🚫 Non ci sono partite in corso. Aspetta che ne inizi una nuova per poterti unire!", show_alert=True)
            return
        if game.extraction_started:
            await query.answer("🚫 La partita è già iniziata, non puoi unirti ora. Aspetta la prossima partita!", show_alert=True)
            return

        # Registra username e aggiungi giocatore
        game.usernames[user_id] = username
        game.add_player(user_id)

        # Invia la cartella in privato
        await send_cartella_to_user(user_id, game, group_text, context)

        # Annuncio nel gruppo
        await context.bot.send_message(
            chat_id=group_chat_id,
            text=f"*_👤 @{escape_markdown(username, version=2)} si è unito alla partita\\!_*",
            message_thread_id=thread_id,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    # Gestione di altri comandi
    elif query.data == 'draw_number':
        await estrai(update, context)
        await query.answer("Numero estratto!")
        return

    elif query.data == 'stop_game':
        await stop_game(update, context)
        await query.answer("Partita interrotta!")
        return

    elif query.data == 'mostra_cartella':
        await show_cartella(user_id, game, query)
        return
    
    else:
        await query.answer()

async def get_group_link(context, group_chat_id):
    try:
        chat = await context.bot.get_chat(group_chat_id)
        return f"https://t.me/{chat.username}" if chat.username else await context.bot.export_chat_invite_link(group_chat_id)
    except Exception:
        return None

async def send_cartella_to_user(user_id, game, group_text, context):
    cartella = game.players[user_id]
    formatted_cartella = game.format_cartella(cartella)
    escaped_cartella = escape_markdown(formatted_cartella, version=2)

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"*🏁 Sei ufficialmente nella partita del gruppo {group_text}, ecco la tua cartella\\:*"
                 f"\n\n{escaped_cartella}",
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True
        )
    except Exception:
        await context.bot.send_message(
            chat_id=user_id,
            text="Non riesco a inviarti la cartella in privato. Assicurati di aver avviato il bot.",
            parse_mode=ParseMode.MARKDOWN
        )

async def show_cartella(user_id, game, query):
    if user_id not in game.players:
        await query.answer("⛔️ Non sei in partita!", show_alert=True)
    else:
        cartella = game.players[user_id]
        formatted_cartella = game.format_cartella(cartella)
        alert_text = f"La tua cartella:\n\n{formatted_cartella}"
        if len(alert_text) > 200:
            alert_text = alert_text[:197] + "..."
        await query.answer(text=alert_text, show_alert=True)

async def estrai(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update and not await is_admin(update, context):
        if update.message:
            await update.message.reply_text("🚫 Solo gli amministratori possono estrarre i numeri manualmente.")
        return

    if update:
        chat_id, thread_id = get_chat_id_or_thread(update)
    elif context.job:
        chat_id = context.job.chat_id
        game_temp = get_game(chat_id)
        thread_id = game_temp.thread_id

    game = get_game(chat_id)
    if not game or not game.game_active:
        if update and update.message:
             await context.bot.send_message(
                chat_id=chat_id,
                text="🚫 Assicurati di aver iniziato una partita prima.",
                message_thread_id=thread_id
            )
        return

    if not game.extraction_started:
        game.start_extraction()

    group_settings = load_group_settings().get(str(chat_id), {})
    feature_states = group_settings.get("bonus_malus_settings", {
        "104": True, "110": True, "666": True, "404": True, "Tombolino": True
    })
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
        
        escaped_name_for_log = escape_markdown(name, version=2)

        updated = current_game_instance.update_cartella(user_id, number_drawn)
        if updated:
            cart_text = current_game_instance.format_cartella(current_game_instance.players[user_id])
            escaped_cart_text = escape_markdown(cart_text, version=2)
            try:
                await bot_context.bot.send_message(
                    chat_id=user_id,
                    text=f"*🔒 Avevi il numero {number_drawn:02}\\!*\n\n{escaped_cart_text}",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            except Exception as e:
                try:
                    escaped_name_for_group_message = escape_markdown(name, version=2)
                    await bot_context.bot.send_message(
                        chat_id=current_game_instance.chat_id,
                        text=f"⚠️ @{escaped_name_for_group_message}, non riesco a inviarti la cartella in privato per il numero {number_drawn:02}\\. Controlla di aver avviato il bot e le impostazioni di privacy\\.",
                        parse_mode=ParseMode.MARKDOWN_V2,
                        message_thread_id=current_game_instance.thread_id
                    )
                except Exception as group_msg_e:
                    logger.error(f"[dm_if_present] Errore invio messaggio di fallback nel gruppo {current_game_instance.chat_id}: {group_msg_e}")

            await current_game_instance.check_winner(user_id, name, bot_context)

    async def update_all_players_dm_and_check_minor_wins(current_game_instance, number_drawn, bot_context):
        tasks = [
            asyncio.create_task(dm_if_present(uid, number_drawn, current_game_instance, bot_context))
            for uid in current_game_instance.players_in_game
        ]
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res_idx, err_or_res in enumerate(results):
                if isinstance(err_or_res, Exception):
                    player_id_involved = list(current_game_instance.players_in_game)[res_idx]

    async def extract_loop():
        nonlocal game, feature_states, mode
        
        run_once = (mode == 'manual')

        while game.game_active:
            current_number_val = None
            try:
                current_number_val = await game.draw_number(context)
            except telegram.error.RetryAfter as e:
                logger.warning(f"[extract_loop] Flood control in draw_number, attendo {e.retry_after}s…")
                await asyncio.sleep(e.retry_after)
                continue
            except Exception as e:
                logger.error(f"[extract_loop] Errore in draw_number: {e}")
                break

            if current_number_val is None:
                if game.game_active:
                    logger.info(f"[extract_loop] Sacchetto vuoto per chat_id={game.chat_id}. Partita terminata.")
                    try:
                        await context.bot.send_message(
                            chat_id=game.chat_id,
                            text="⚠️ Tutti i numeri sono stati estratti. Il gioco è finito!",
                            message_thread_id=game.thread_id
                        )
                    except telegram.error.RetryAfter as e:
                        logger.warning(f"[extract_loop] Flood control su messaggio fine numeri: attendo {e.retry_after}s…")
                        await asyncio.sleep(e.retry_after)
                    except Exception as e:
                        logger.error(f"[extract_loop] Errore nell'invio messaggio fine numeri: {e}")
                    
                    effective_update_for_end = update if update else type('obj', (object,), {'effective_chat': type('obj', (object,), {'id': game.chat_id}), 'effective_message': type('obj', (object,), {'is_topic_message': bool(game.thread_id), 'message_thread_id': game.thread_id}), 'effective_user': None})()
                    await end_game(effective_update_for_end, context)
                break

            # Annuncio numero estratto
            try:
                await context.bot.send_message(
                    chat_id=game.chat_id,
                    text=f"_📤 È stato estratto il numero **{current_number_val:02}**_",
                    reply_markup=reply_markup_keyboard,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    message_thread_id=game.thread_id
                )
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

            if current_number_val in [110, 666, 104, 404]:
                if feature_states.get(str(current_number_val), True):
                    player_id_affected = random.choice(list(game.players_in_game))
                    try:
                        member = await context.bot.get_chat_member(game.chat_id, player_id_affected)
                        raw_name = member.user.username or member.user.full_name or f"Utente_{player_id_affected}"
                        user_affected_escaped_name = escape_markdown(raw_name, version=2)
                    except Exception:
                        user_affected_escaped_name = escape_markdown(f"Utente_{player_id_affected}", version=2)

                    punti_val = random.randint(1, 49)
                    message_special_text = ""

                    if current_number_val == 110:
                        game.add_score(player_id_affected, punti_val)
                        message_special_text = f"*🧑‍🎓 Numero 110 estratto\\!*\n\n_🆒 @{user_affected_escaped_name} ha guadagnato {punti_val} punti_"
                    elif current_number_val == 666:
                        game.add_score(player_id_affected, -punti_val)
                        message_special_text = f"*🛐 Numero 666 estratto\\!*\n\n_🆒 @{user_affected_escaped_name} ha perso {punti_val} punti_"
                    elif current_number_val == 104:
                        game.add_score(player_id_affected, punti_val)
                        message_special_text = f"*♿️ Numero 104 estratto\\!*\n\n_🆒 @{user_affected_escaped_name} ha guadagnato {punti_val} punti_"
                    elif current_number_val == 404:
                        game.add_score(player_id_affected, -punti_val)
                        message_special_text = f"*🆘 Numero 404 estratto\\!*\n\n_🆒 @{user_affected_escaped_name} ha perso {punti_val} punti_"

                    if message_special_text:
                        try:
                            await context.bot.send_message(
                                chat_id=game.chat_id,
                                text=message_special_text,
                                parse_mode=ParseMode.MARKDOWN_V2,
                                message_thread_id=game.thread_id
                            )
                        except Exception as e:
                            logger.error(f"[extract_loop] Errore invio bonus/malus per numero {current_number_val} a chat {game.chat_id}: {e}")

                        sticker_file_id = get_sticker_for_number(current_number_val)
                        if sticker_file_id:
                            try:
                                await context.bot.send_sticker(
                                    chat_id=game.chat_id,
                                    sticker=sticker_file_id,
                                    message_thread_id=game.thread_id
                                )
                            except Exception as e:
                                logger.error(f"[extract_loop] Errore invio sticker bonus/malus {current_number_val} a chat {game.chat_id}: {e}")

            if current_number_val in [69, 90]:
                sticker_file_id = get_sticker_for_number(current_number_val)
                if sticker_file_id:
                    try:
                        await context.bot.send_sticker(
                            chat_id=game.chat_id,
                            sticker=sticker_file_id,
                            message_thread_id=game.thread_id
                        )
                    except Exception as e:
                        logger.error(f"[extract_loop] Errore sticker {current_number_val} (post-annuncio) per chat {game.chat_id}: {e}")

            # Aggiorna cartelle e verifica vincite parziali
            if game.players_in_game:
                try:
                    await update_all_players_dm_and_check_minor_wins(game, current_number_val, context)
                except Exception as e:
                    logger.error(f"[extract_loop] Errore in update_all_players_dm_and_check_minor_wins per numero {current_number_val}: {e}")

            if mode == 'auto':
                 await asyncio.sleep(1.5)

            partita_terminata_da_tombola = False
            if game.game_active:
                try:
                    partita_terminata_da_tombola = await game.check_for_tombola(context)
                except Exception as e:
                    logger.error(f"[extract_loop] Errore in game.check_for_tombola: {e}")
                    partita_terminata_da_tombola = True

            if partita_terminata_da_tombola:
                effective_update_for_end = update if update else type('obj', (object,), {'effective_chat': type('obj', (object,), {'id': game.chat_id}), 'effective_message': type('obj', (object,), {'is_topic_message': bool(game.thread_id), 'message_thread_id': game.thread_id}), 'effective_user': None})()
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
    if not game.game_interrupted:
        game.update_overall_scores()
        await send_final_rankings(update, context)  # Pubblica la classifica solo qui
    else:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ Punti non conteggiati perché la partita è stata interrotta.", message_thread_id=thread_id)
    game.reset_game()
    game.stop_game()

import json
import os

async def send_final_rankings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, thread_id = get_chat_id_or_thread(update)
    sticker_file_id = "CAACAgQAAxkBAAEt32Rm8Z_GRtaOFHzCVCFePFCU0rk1-wACNQEAAubEtwzIljz_HVKktzYE"

    # Carica la classifica dal bin
    classifica_gruppo = load_classifica_from_json(chat_id)

    if not classifica_gruppo:
        await context.bot.send_message(
            chat_id=chat_id,
            text="*📊 Nessuna classifica disponibile\\.*",
            message_thread_id=thread_id,
            parse_mode=ParseMode.MARKDOWN_V2
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

    if not lines:
        await context.bot.send_message(
            chat_id=chat_id,
            text="*📊 Nessuna classifica disponibile\\.*",
            message_thread_id=thread_id,
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return

    testo = "🏆 Classifica finale:\n\n" + "\n".join(lines)
    await context.bot.send_message(chat_id=chat_id, text=testo, message_thread_id=thread_id)
    await context.bot.send_sticker(chat_id=chat_id, sticker=sticker_file_id, message_thread_id=thread_id)

async def stop_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Solo gli amministratori possono interrompere il gioco.")
        return
    chat_id, thread_id = get_chat_id_or_thread(update)
    game = get_game(chat_id)
    game.stop_game(interrupted=True)
    await context.bot.send_message(
        chat_id=chat_id,
        text="*🔚 Il gioco è stato interrotto*",
        message_thread_id=thread_id,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    game.current_game_scores.clear()

async def reset_classifica(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, thread_id = get_chat_id_or_thread(update)

    if not await is_admin(update, context):
        await update.message.reply_text("🚫 Solo gli amministratori possono resettare la classifica.")
        return

    save_classifica_to_json(chat_id, {})

    await update.message.reply_text(
        "_🚾 Complimenti hai scartato tutti i punteggi\\._",
        parse_mode=ParseMode.MARKDOWN_V2
    )

async def regole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or str(user_id)
    escaped_username = escape_markdown(username, version=2)
    group_settings = load_group_settings()
    group_id = str(update.effective_chat.id)
    scores = group_settings.get(group_id, {}).get("premi", {
        "ambo": 5,
        "terno": 10,
        "quaterna": 15,
        "cinquina": 20,
        "tombola": 50
    })

    rules_text = (
        "_*📜 REGOLAMENTO\\:*_\n\n"
        "_⚙️ Comandi\\:_\n\n"
        "\\- */trombola*\nAvvia la partita \\(solo in gruppo e di default per gli admin\\);\n"
        "\\- */classifiga*\nVisualizza la classifica del gruppo \\(solo in gruppo e di default per gli admin\\);\n"
        "\\- */azzera*\nAzzerare la classifica \\(solo in gruppo e di default per gli admin\\);\n"
        "\\- */stop*\nInterrompe la partita in corso \\(solo in gruppo e di default per gli admin\\);\n"
        "\\- */trombolatori*\nVisualizza il numero di partecipanti in partita;\n"
        "\\- */estrai*\nEstrae i numeri \\(solo in gruppo e di default per gli admin\\);\n"
        "\\- */impostami*\nGestisce le impostazioni del bot, include la possibilità di modificare i permessi, il tipo di estrazione, "
        "i punteggi e l'attivazione o meno dei bonus e malus\\.\n\n"
        "_➡️ Unirsi alla partita\\:_\n\n"
        "Premi il bottone 'Unisciti' per ricevere in privato la tua cartella\\.\n\n"
        "_🔢 Estrazione\\:_\n\n"
        "I numeri vengono estratti da 1 a 90, sono inoltre presenti due numeri extra che aggiungono o tolgono punti\\.\n\n"
        f"_🏆 Punteggi\\:_\n\n"
        f"\\- {scores.get('ambo')} punti per *ambo*;\n"
        f"\\- {scores.get('terno')} punti per *terno*;\n"
        f"\\- {scores.get('quaterna')} punti per *quaterna*;\n"
        f"\\- {scores.get('cinquina')} punti per *cinquina*;\n"
        f"\\- {scores.get('tombola')} punti per *tombola*;\n\n"
        "Inoltre, sono previsti i seguenti bonus e malus\\:\n"
        "\\- All'estrazione del numero 110 viene assegnato un punteggio casuale \\(da 1 a 49\\) a un utente casuale;\n"
        "\\- All'estrazione del numero 666 vengono rimossi punti casuali \\(da 1 a 49\\) a un utente casuale\\.\n"
    )
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=rules_text,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        await update.message.reply_text(
            "Non posso inviarti le regole in privato. Assicurati di aver avviato una chat con me.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        await update.message.reply_text(f"_📩 @{escaped_username} ti ho inviato le regole in chat privata\\!_", parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        pass

    try:
        await update.message.delete()
    except Exception as e:
        pass
