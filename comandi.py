import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
import telegram
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from game_instance import get_game
# MODIFICA: import delle funzioni Firebase al posto di JSONBin
from firebase_client import (
    load_classifica_from_firebase,    # in luogo di load_classifica_from_json
    save_classifica_to_firebase       # in luogo di save_classifica_to_json
)
from variabili import get_chat_id_or_thread, is_admin
# MODIFICA: rimuovere load_group_settings e sostituire con Firebase
from firebase_client import load_group_settings_from_firebase
from variabili import get_sticker_for_number, premi_default
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
    # MODIFICA: carica la classifica da Firebase anziché JSONBin
    game.overall_scores = load_classifica_from_firebase(chat_id)

    # MODIFICA: carica impostazioni di gruppo da Firebase
    group_settings = load_group_settings_from_firebase(chat_id)
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

    print(f"ID gruppo: {chat_id}, Thread: {thread_id}, Nome: {group_name}, Link: {group_link}")
    game.reset_game()
    print("Gioco resettato!")

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

    if query.data == 'join_game':
        async with game.join_lock:
            if user_id in game.players_in_game:
                await query.answer("Sei già iscritto alla partita!", show_alert=True)
                return

            if not game.game_active:
                await query.answer(
                    "🚫 Non ci sono partite in corso. "
                    "Aspetta che ne inizi una nuova per poterti unire!",
                    show_alert=True
                )
                return

            if game.extraction_started:
                await query.answer(
                    "🚫 La partita è già iniziata, non puoi unirti ora. "
                    "Aspetta la prossima partita!",
                    show_alert=True
                )
                return

            # Ora proviamo ad aggiungere il giocatore
            added = game.add_player(user_id)
            if not added:
                # Se add_player ritorna False (es. era già dentro o estrazione partita),
                # rispondi con un alert generico
                await query.answer("🔜 Non puoi unirti alla partita ora.", show_alert=True)
                return

            # Se l'aggiunta ha avuto successo, registriamo l'username
            if update.effective_user.username:
                game.usernames[user_id] = update.effective_user.username
            else:
                game.usernames[user_id] = update.effective_user.full_name

            # Generiamo la cartella e la inviamo in privato
            cartella = game.players[user_id]
            formatted_cartella = game.format_cartella(cartella)

            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"*🏁 Sei ufficialmente nella partita del gruppo {group_text}, "
                        f"ecco la tua cartella\\:*\n\n{formatted_cartella}"
                    ),
                    parse_mode=ParseMode.MARKDOWN_V2,
                    disable_web_page_preview=True
                )
            except Exception:
                # Se l'invio in privato fallisce, inviamo un messaggio d'errore
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Non riesco a inviarti la cartella in privato. "
                         "Assicurati di aver avviato il bot.",
                    parse_mode=ParseMode.MARKDOWN
                )

            # Annuncio nel gruppo che l'utente si è unito
            await context.bot.send_message(
                chat_id=group_chat_id,
                text=f"*_👤 @{escape_markdown(username, version=2)} si è unito alla partita\\!_*",
                message_thread_id=thread_id,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            return  # Esco dalla callback “join_game”

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
    """Recupera il link del gruppo in modo asincrono."""
    try:
        chat = await context.bot.get_chat(group_chat_id)
        return f"https://t.me/{chat.username}" if chat.username else await context.bot.export_chat_invite_link(group_chat_id)
    except Exception:
        return None


async def send_cartella_to_user(user_id, game, group_text, context):
    """Invia la cartella al giocatore in privato."""
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
    """Mostra la cartella del giocatore."""
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
    await log_interaction(user_id, username, chat_id, "/estrai", group_name)
    
    # ─── 1) Verifica permessi (solo admin possono estrarre) ─────────────────────────────────
    if update and not await is_admin(update, context):
        if update.message:
            await update.message.reply_text("🚫 Solo gli amministratori possono estrarre i numeri manualmente.")
        return

    # ─── 2) Ottieni chat_id e thread_id ─────────────────────────────────────────────────────
    if update:
        chat_id, thread_id = get_chat_id_or_thread(update)
    elif context.job:
        chat_id = context.job.chat_id
        game_temp = get_game(chat_id)
        thread_id = game_temp.thread_id
    else:
        logger.error("[estrai] Impossibile determinare chat_id per l'estrazione.")
        return

    game = get_game(chat_id)
    if not game or not game.game_active:
        if update and update.message:
            await context.bot.send_message(
                chat_id=chat_id,
                text="🚫 Assicurati di aver iniziato una partita prima.",
                message_thread_id=thread_id
            )
        return

    # ─── 3) Se l'estrazione non è partita, iniziala ─────────────────────────────────────────
    if not game.extraction_started:
        game.start_extraction()
        logger.info(f"[estrai] Avviata estrazione per chat_id={chat_id}")

    # ─── 4) Carica impostazioni di gruppo da Firebase ─────────────────────────────────────
    group_settings = load_group_settings_from_firebase(chat_id).get(str(chat_id), {})
    feature_states = group_settings.get("bonus_malus_settings", {
        "104": True, "110": True, "666": True, "404": True, "Tombolino": True
    })
    mode = group_settings.get('extraction_mode', 'manual')

    # ─── 5) Prepara la tastiera per “🔎 Vedi Cartella” ─────────────────────────────────────
    keyboard_buttons = [
        [InlineKeyboardButton("🔎 Vedi Cartella", callback_data='mostra_cartella')]
    ]
    reply_markup_keyboard = InlineKeyboardMarkup(keyboard_buttons)

    # ─────────────────────────────────────────────────────────────────────────────────────────
    # Funzione interna: invia un DM a un giocatore se ha il numero e verifica vincite parziali
    # ─────────────────────────────────────────────────────────────────────────────────────────
    async def dm_if_present(user_id: int, number_drawn: int, current_game_instance, bot_context):
        name = current_game_instance.usernames.get(user_id)
        if not name:
            try:
                member = await bot_context.bot.get_chat_member(current_game_instance.chat_id, user_id)
                name = member.user.username or member.user.full_name or f"Utente_{user_id}"
            except Exception as e:
                logger.error(f"[dm_if_present] Errore nel recuperare membro {user_id} per chat {current_game_instance.chat_id}: {e}")
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
                logger.error(f"[dm_if_present] Errore nell'invio DM a {user_id} ({escaped_name_for_log}): {e}")

            await current_game_instance.check_winner(user_id, name, bot_context)

    # ─────────────────────────────────────────────────────────────────────────────────────────
    # Funzione interna: aggiorna in parallelo tutti i giocatori
    # ─────────────────────────────────────────────────────────────────────────────────────────
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
                    logger.error(f"[update_all_players_dm] Errore in dm_if_present per user {player_id_involved}: {err_or_res}")
        else:
            logger.info(f"[update_all_players_dm] Nessun giocatore a cui inviare DM per il numero {number_drawn} in chat {current_game_instance.chat_id}.")

    # ─────────────────────────────────────────────────────────────────────────────────────────
    # Funzione interna: ciclo di estrazione
    # ─────────────────────────────────────────────────────────────────────────────────────────
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

                    effective_update_for_end = update if update else type(
                        'obj', (object,), {
                            'effective_chat': type('obj', (object,), {'id': game.chat_id}),
                            'effective_message': type('obj', (object,), {'is_topic_message': bool(game.thread_id), 'message_thread_id': game.thread_id}),
                            'effective_user': None
                        }
                    )()
                    await end_game(effective_update_for_end, context)
                break

            # Annuncio numero estratto
            try:
                msg = await context.bot.send_message(
                    chat_id=game.chat_id,
                    text=f"_📤 È stato estratto il numero **{current_number_val:02}**_",
                    reply_markup=reply_markup_keyboard,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    message_thread_id=game.thread_id
                )
                # Salvo il message_id per cancellazione futura
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
                logger.info(f"Numero {current_number_val} reinserito nel sacchetto a causa di errore annuncio.")
                continue
            except Exception as e:
                logger.error(f"[extract_loop] Errore nell'invio messaggio numero {current_number_val}: {e}")

            # ─── GESTIONE BONUS/MALUS DOPO ANNUNCIO ────────────────────────────────────────────────
            if current_number_val in [110, 666, 104, 404]:
                # Controlla se il bonus/malus è attivo per questo numero
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
                        # 1) invia il messaggio scritto del bonus/malus
                        try:
                            msg_bonus = await context.bot.send_message(
                                chat_id=game.chat_id,
                                text=message_special_text,
                                parse_mode=ParseMode.MARKDOWN_V2,
                                message_thread_id=game.thread_id
                            )
                        except Exception as e:
                            logger.error(f"[extract_loop] Errore invio bonus/malus per numero {current_number_val} a chat {game.chat_id}: {e}")

                        # 2) invia subito dopo lo sticker corrispondente
                        sticker_id = get_sticker_for_number(current_number_val)
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

            # Invia sticker per numeri speciali 69 e 90 DOPO l'annuncio del numero
            if current_number_val in [69, 90]:
                sticker_special = get_sticker_for_number(current_number_val)
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

            # Aggiorna cartelle e verifica vincite parziali
            if game.players_in_game:
                try:
                    await update_all_players_dm_and_check_minor_wins(game, current_number_val, context)
                except Exception as e:
                    logger.error(f"[extract_loop] Errore in update_all_players_dm_and_check_minor_wins per numero {current_number_val}: {e}")
            else:
                logger.info(f"[extract_loop] Nessun giocatore in partita per il numero {current_number_val} in chat {game.chat_id}, salto aggiornamento cartelle.")

            if mode == 'auto':
                await asyncio.sleep(1)

            # Verifica Tombola (fine partita)
            partita_terminata_da_tombola = False
            if game.game_active:
                try:
                    partita_terminata_da_tombola = await game.check_for_tombola(context)
                except Exception as e:
                    logger.error(f"[extract_loop] Errore in game.check_for_tombola: {e}")
                    partita_terminata_da_tombola = True

            if partita_terminata_da_tombola:
                logger.info(f"[extract_loop] Partita terminata da check_for_tombola per chat_id={game.chat_id}.")
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
    if not game.game_interrupted:
        game.update_overall_scores()
        await send_final_rankings(update, context)  # Pubblica la classifica solo qui
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Punti non conteggiati perché la partita è stata interrotta.",
            message_thread_id=thread_id
        )

    group_settings = load_group_settings_from_firebase(chat_id).get(str(chat_id), {})
    delete_flag = group_settings.get('delete_numbers_on_end', False)
    if delete_flag:
        for msg_id in game.number_message_ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception as e:
                # Potrebbe essere già stato cancellato o non accessibile
                logger.warning(f"[end_game] Impossibile cancellare msg {msg_id} in chat {chat_id}: {e}")
    
    game.reset_game()
    game.stop_game()


import json
import os


async def send_final_rankings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id, thread_id = get_chat_id_or_thread(update)
    sticker_file_id = "CAACAgQAAxkBAAEt32Rm8Z_GRtaOFHzCVCFePFCU0rk1-wACNQEAAubEtwzIljz_HVKktzYE"

    # MODIFICA: carica la classifica finale da Firebase
    classifica_gruppo = load_classifica_from_firebase(chat_id)

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
    for idx, (user_id_str, punti) in enumerate(ordinata, start=1):
        if punti == 0:
            continue
        try:
            user_id_int = int(user_id_str)
            info = await context.bot.get_chat(user_id_int)
            nome = info.username or info.first_name
        except:
            nome = f"utente_{user_id_str}"
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

    # MODIFICA: resetta la classifica su Firebase
    save_classifica_to_firebase(chat_id, {})

    await update.message.reply_text(
        "_🚾 Complimenti hai scartato tutti i punteggi\\._",
        parse_mode=ParseMode.MARKDOWN_V2
    )


async def regole(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_origin = update.effective_chat.id
    username = update.effective_user.username or update.effective_user.first_name or str(user_id)
    escaped_username = escape_markdown(username, version=2)

    raw_conf = load_group_settings_from_firebase(chat_origin) or {}
    conf = raw_conf.get(str(chat_origin), {})
    custom_premi = conf.get("premi", premi_default)

    # Tastiera del menu principale
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
            text=(
                "*_ℹ️ REGOLAMENTO\\:_*\n\n"
                "_👋 Benvenuto nel regolamento, qui potrai navigare grazie ai bottoni tra le varie sezioni_ "
                "_per scoprire ogni angolo di questo bot\\._\n\n"
                "_✍️ Per qualunque informazione rimaniamo a disposizione su @AssistenzaTombola2\\_Bot\\._ "
                "_Non esitare a contattarci se ci sono problemi\\._\n\n"
            ),
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )
    except Exception as e:
        await update.message.reply_text(
            f"_📭 @{escaped_username} non riesco a inviarti le regole in privato\\._\n"
            "*Vai su @Tombola2_Bot e premi 'Avvia'*",
            parse_mode=ParseMode.MARKDOWN_V2
        )
        return
    try:
        await update.message.reply_text(
            f"_📬 @{escaped_username} ti ho inviato le regole in privato\\._",
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

    user_id = query.from_user.id
    data = query.data
    try:
        section_part, group_id_str = data.split("|", 1)
    except ValueError:
        return

    section_key = section_part.replace("rule_", "")
    try:
        chat_origin = int(group_id_str)
    except ValueError:
        chat_origin = None

    if section_key == "close":
        try:
            await query.message.delete()
        except Exception:
            pass
        return
    
    # 1. Gestione pulsante “🔙 Indietro”
    if section_key == "back" and chat_origin is not None:
        keyboard = [
            [InlineKeyboardButton("🌐 Comandi",    callback_data=f"rule_comandi|{chat_origin}"),
             InlineKeyboardButton("🆒 Partecipare", callback_data=f"rule_unirsi|{chat_origin}")],
            [InlineKeyboardButton("🔁 Estrazione", callback_data=f"rule_estrazione|{chat_origin}"),
             InlineKeyboardButton("🏆 Punteggi",    callback_data=f"rule_punteggi|{chat_origin}")],
            [InlineKeyboardButton("☯️ Bonus/Malus", callback_data=f"rule_bonus_malus|{chat_origin}")],
            [InlineKeyboardButton("❌ Chiudi",       callback_data=f"rule_close|{chat_origin}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        main_text = (
            "*_ℹ️ REGOLAMENTO\\:_*\n\n"
            "_👋 Benvenuto nel regolamento, qui potrai navigare grazie ai bottoni tra le varie sezioni_ "
            "_per scoprire ogni angolo di questo bot\\._\n\n"
            "_✍️ Per qualunque informazione rimaniamo a disposizione su @AssistenzaTombola2\\_Bot\\._ "
            "_Non esitare a contattarci se ci sono problemi\\._\n\n"
        )
        try:
            await query.message.edit_text(
                main_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        except Exception:
            await context.bot.send_message(
                chat_id=user_id,
                text=main_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        return

    # 2. Gestione sezione “punteggi” (non è in _RULES_SECTIONS, quindi la gestiamo a parte)
    if section_key == "punteggi" and chat_origin is not None:
        # Recupero titolo e link del gruppo
        group_title = None
        group_link = None
        try:
            chat_obj = await context.bot.get_chat(chat_origin)
            group_title = chat_obj.title or str(chat_origin)
            if chat_obj.username:
                group_link = f"https://t.me/{chat_obj.username}"
            else:
                try:
                    group_link = await context.bot.export_chat_invite_link(chat_origin)
                except Exception:
                    group_link = None
        except Exception:
            group_title = None
            group_link = None

        if group_title:
            escaped_title = escape_markdown(group_title, version=2)
            if group_link:
                header = f"[{escaped_title}]({group_link})"
            else:
                header = f"{escaped_title}"
        else:
            header = ""

        raw_conf = load_group_settings_from_firebase(chat_origin) or {}
        conf = raw_conf.get(str(chat_origin), {})
        premi_dict = conf.get("premi", premi_default)
        val_tombolino = premi_dict.get("tombola", 50) // 2

        text_to_send = (
            "*🏆 Punteggi\\:*\n\n"
            "_🔢 Il cuore della classifica risiede qui, ogni gruppo ha la possibilità di personalizzare i punteggi tramite il comando "
            f"apposito che vedi spiegato nella sezione di riferimento, ma questi sono quelli attualmente in uso nel gruppo {header}\\:_\n\n"
            f"1️⃣ *AMBO* vale {premi_dict.get('ambo', 5)} punti\n"
            f"2️⃣ *TERNO* vale {premi_dict.get('terno', 10)} punti\n"
            f"3️⃣ *QUATERNA* vale {premi_dict.get('quaterna', 15)} punti\n"
            f"4️⃣ *CINQUINA* vale {premi_dict.get('cinquina', 20)} punti\n"
            f"5️⃣ *TOMBOLA* vale {premi_dict.get('tombola', 50)} punti\n\n"
            "_🔽 Inoltre, se attivo nel vostro gruppo:_\n\n"
            f"6️⃣ *TOMBOLINO* vale {val_tombolino} punti\n"
        )

        # Pulsante “🔙 Indietro”
        back_button = [
            [InlineKeyboardButton("🔙 Indietro", callback_data=f"rule_back|{chat_origin}"), InlineKeyboardButton("❌ Chiudi",       callback_data=f"rule_close|{chat_origin}")]
        ]
        reply_markup = InlineKeyboardMarkup(back_button)

        # Provo a modificare il messaggio originale; se fallisce, mando un nuovo messaggio
        try:
            await query.message.edit_text(
                text_to_send,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True
            )
        except Exception:
            await context.bot.send_message(
                chat_id=user_id,
                text=text_to_send,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN_V2
            )
        return

    # 3. Controllo che la sezione sia tra quelle statiche (_RULES_SECTIONS)
    if section_key not in _RULES_SECTIONS:
        return

    # 4. Se sono arrivato fino a qui, la sezione è una chiave valida di _RULES_SECTIONS.
    text_to_send = _RULES_SECTIONS[section_key]

    # Pulsante “🔙 Indietro” anche per le sezioni statiche
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
    except Exception:
        await context.bot.send_message(
            chat_id=user_id,
            text=text_to_send,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN_V2
        )


_RULES_SECTIONS = {
    "comandi": (
        "*🌐 Comandi\\:*\n\n"
        "_🛃 Qui trovi fondamentalmente tutti i comandi del bot, alcuni utilizzabili solo dai moderatori altri accessibili a tutti, "
        "vediamone una rapida spiegazione\\:_\n\n"
        "*1️⃣ /trombola*\n"
        "_Il comando principale, di default lo possono usare solo i moderatori e ti permette di avviare una partita\\._\n\n"
        "*2️⃣ /impostami*\n"
        "_Con questo comando puoi decidere come e cosa cambiare all'interno del gruppo, non voglio dilungarmi troppo, provalo nel gruppo, "
        "se sei moderatore, e sperimenta tu stesso\\._\n\n"
        "*3️⃣ /classifiga*\n"
        "_No non è un errore di battitura, si chiama davvero così il comando, intuibilmente ti permette di visualizzare la classifica del "
        "gruppo, ovviamente se sei moderatore\\._\n\n"
        "*4️⃣ /azzera*\n"
        "_Anche per questo di default devi essere un moderatore, anche perchè resetta totalmente la classifica del gruppo, maneggiare con cura\\._\n\n"
        "*5️⃣ /stop*\n"
        "_Se per qualunque motivo \\(ad esempio perchè non hai messo nemmeno un numero\\) volessi interrompere la partita, beh con questo "
        "comando puoi farlo, ah se sei moderatore\\._\n\n"
        "*6️⃣ /estrai*\n"
        "_Che partita di tombola sarebbe se i numeri non venissero estratti, d'altronde c'è da fare solo questo, quindi moderatore sta a te, "
        "usa questo comando e dai inizio alla partita e che vinca il migliore\\._\n\n"
        "*7️⃣ /trombolatori*\n"
        "_Se per caso ti interessa sapere quante persone stanno tromb\\.\\.\\. volevo dire partecipando alla partita usa questo comando, "
        "ah e questo possono usarlo tutti\\._"
    ),
    "unirsi": (
        "*🆒 Partecipare\\:*\n\n"
        "_🆗 Ora, probabilmente ti starai chiedendo, bello tutto eh, ma come faccio a partecipare alla partita? Nulla di più semplice, "
        "quando un moderatore avrà iniziato una partita col comando /trombola \\(non usarlo qui non funzionerà\\) comparirà un bottone come "
        "questo '➕ Unisciti' cliccaci sopra e riceverai la cartella in questa chat e il gioco è fatto\\. Ora non ti resta che sperare che "
        "escano i tuoi numeri\\._"
    ),
    "estrazione": (
        "*🔁 Estrazione\\:*\n\n"
        "_🔀 Come nella più classica delle tombole i numeri vanno da 1 a 90, una volta estratto il primo numero voi non dovrete fare niente "
        "se non accertarvi dei numeri che escono e che vi vengono in automatico segnati dal bot\\. Il vero lavoro ce l'ha il moderatore che deve "
        "estrarre i numeri ma se va a darsi un'occhiata alle impostazioni anche per lui sarà una passeggiata\\._"
    ),
    "bonus_malus": (
        "*☯️ Bonus/Malus\\:*\n\n"
        "_🏧 Se non vi piace la monotonia e volete rendere piu interessante le classifica, allora dovete assolutamente leggervi cosa fanno "
        "questi bonus/malus e correre ad avvisare il vostro admin di fiducia di attivarli\\:_\n\n"
        "_🔽 Ciascuno di questi numeri è stato aggiunto al sacchetto ed una volta estratto potrà aggiungervi o togliervi  un numero "
        "randomico di punti \\(da 1 a 49\\)\\. No non vi compariranno in cartella, il fortunato o sfortunato verrà scelto a caso tra tutti "
        "quelli in partita\\._\n\n"
        "*1️⃣ Bonus 104*\n"
        "_Spero non siate per il politically correct, nel caso ci dispiace \\(non è vero\\)\\._\n\n"
        "*2️⃣ Malus 666*\n"
        "_Se siete fan sfegatati di Dio vi consiglio di disattivarlo dalle impostazioni\\._\n\n"
        "*2️⃣ Bonus 110*\n"
        "_Un po' come per la laurea, vi diamo la lode ma il valore di essa non dipende da noi\\. O se preferite come lo stato, vi diamo il "
        "110\\% di quanto avete speso\\._\n\n"
        "*2️⃣ Malus 404*\n"
        "_Error 404 Not Found\\. Impossibile caricare il testo del Malus\\._\n\n"
        "_⏸️ Pensavate davvero avessimo finito qui\\? Pff non ci conoscete bene, per gli amanti della tombola abbiamo anche introdotto "
        "un extra\\:_\n\n"
        "*5️⃣ Tombolino*\n"
        "_Spero lo conosciate nel caso ve lo spiego brevemente\\. Se attivato dalle impostazioni un altro utente avrà la possibilità di "
        "fare tombola\\. Fondamentalmente viene premiato il secondo giocatore a farla, ma ovviamente non con gli stessi punti della prima\\._"
    )
}
