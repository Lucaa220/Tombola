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
            text="Non riesco a inviarti la cartella in privato. Assicurati di aver avviato una chat con me.",
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
    # Solo admin possono estrarre
    if not await is_admin(update, context):
        return

    chat_id, thread_id = get_chat_id_or_thread(update)
    game = get_game(chat_id)
    
    if not game.game_active:
        await context.bot.send_message(
            chat_id=chat_id,
            text="🚫 Assicurati di aver iniziato una partita prima.",
            message_thread_id=thread_id
        )
        return

    # Avvia estrazione se non già partita
    if not game.extraction_started:
        game.start_extraction()

    # Carica impostazioni di gruppo
    group_settings = load_group_settings().get(str(chat_id), {})
    mode = group_settings.get('extraction_mode', 'manual')
    tombolino_enabled = group_settings.get("bonus_malus_settings", {}).get("Tombolino", True)

    # Pulsante per vedere la cartella
    keyboard = [[InlineKeyboardButton("🔎 Vedi Cartella", callback_data='mostra_cartella')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    async def update_player(user_id: int, number: int):
        # Mantieni la logica di update_player già esistente
        name = game.usernames.get(user_id)
        if not name:
            try:
                member = await context.bot.get_chat_member(chat_id, user_id)
                name = member.user.username or member.user.full_name or f"Utente_{user_id}"
            except Exception as e:
                logger.error(f"Errore nel recuperare il membro: {e}")
                name = f"Utente_{user_id}"
            game.usernames[user_id] = name

        # Aggiorna la cartella e invia DM se trovato numero
        updated = game.update_cartella(user_id, number)
        if updated:
            cart_text = game.format_cartella(game.players[user_id])
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"*🔒 Avevi il numero {number:02}\\!*\n\n{cart_text}",
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            except Exception as e:
                logger.error(f"Errore nell'invio del messaggio al giocatore {user_id}: {e}")

        # Controlla vincitore (tombola/tombolino)
        result = await game.check_winner(user_id, name, context)
        if result:
            escaped = escape_markdown(name, version=2)
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"_🏆 @{escaped} ha fatto {result}\\!_",
                message_thread_id=thread_id,
                parse_mode=ParseMode.MARKDOWN_V2
            )
            if result.endswith("la partita è terminata"):
                await end_game(update, context)

    async def extract_loop():
        """Estrae numeri fino a chiusura partita, gestendo flood control e aggiornamenti."""
        while game.game_active:
            try:
                number = await game.draw_number(context)
            except telegram.error.RetryAfter as e:
                logger.warning(f"Flood control exceeded, attendo {e.retry_after} secondi...")
                await asyncio.sleep(e.retry_after)
                continue
            except Exception as e:
                logger.error(f"Errore durante l'estrazione del numero: {e}")
                break

            if number is None:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text="Tutti i numeri sono stati estratti. Il gioco è finito!",
                        message_thread_id=thread_id
                    )
                except telegram.error.RetryAfter as e:
                    logger.warning(f"Flood control exceeded su messaggio finale, attendo {e.retry_after} secondi...")
                    await asyncio.sleep(e.retry_after)
                    continue
                except Exception as e:
                    logger.error(f"Errore nell'invio del messaggio finale: {e}")
                await end_game(update, context)
                break

            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"_📤 È stato estratto il numero **{number:02}**_",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    message_thread_id=thread_id
                )
            except telegram.error.RetryAfter as e:
                logger.warning(f"Flood control exceeded su annuncio numero, attendo {e.retry_after} secondi...")
                await asyncio.sleep(e.retry_after)
                continue
            except Exception as e:
                logger.error(f"Errore nell'invio del messaggio estrazione: {e}")

            # Ritardo tra le estrazioni per prevenire flood (es. 1 secondo)
            await asyncio.sleep(1)

            # Invia sticker se numero speciale
            if number in [69, 90, 104, 666, 110, 404]:
                sticker = get_sticker_for_number(number)
                try:
                    await context.bot.send_sticker(chat_id=chat_id, sticker=sticker, message_thread_id=thread_id)
                except Exception as e:
                    logger.error(f"Errore nell'invio sticker per numero {number}: {e}")

            # Aggiornamento parallelo di tutti i giocatori
            try:
                await update_all_players(game.players, number)
            except Exception as e:
                logger.error(f"Errore durante update_all_players: {e}")

    async def update_all_players(players, number):
        tasks = [asyncio.create_task(update_player(uid, number)) for uid in players]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for err in results:
            if isinstance(err, Exception):
                logger.error(f"Errore in update_player: {err}")

    # Avvia il loop di estrazione in base alla modalità
    if mode == 'auto':
        # In background per non bloccare l'handler
        asyncio.create_task(extract_loop())
    else:
        # Modalità manuale: esegue subito fino a fine
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
        await send_final_rankings(update, context)
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
