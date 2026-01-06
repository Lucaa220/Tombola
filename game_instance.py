import random
from telegram import Update
from telegram.ext import ContextTypes
import asyncio
from variabili import chat_id_global, thread_id_global, premi_default  # MODIFICA: manterremo load_group_settings solo se usato altrove
import logging
import json
import os
from telegram.constants import ParseMode
import telegram
from telegram.helpers import escape_markdown
from firebase_client import (
    load_classifica_from_firebase,    # in luogo di load_classifica_from_json
    save_classifica_to_firebase,      # in luogo di save_classifica_to_json
    load_group_settings_from_firebase # in luogo di load_group_settings (JSONBin)
)
from messages import get_testo_tematizzato

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def update_player_score(group_id: int, user_id: int, points: int) -> None:
    """
    Carica la classifica corrente da Firebase, aggiorna i punti del giocatore e
    salva nuovamente su Firebase.
    """
    classifica = load_classifica_from_firebase(group_id)
    # Chiavi utente come stringa, incrementa i punti
    classifica[str(user_id)] = classifica.get(str(user_id), 0) + points
    save_classifica_to_firebase(group_id, classifica)


class TombolaGame:
    def __init__(self):
        self.players = {}
        self.numeri_estratti = []
        self.numeri_tombola = list(range(1, 91)) + [110, 666, 104, 404]
        random.shuffle(self.numeri_tombola)
        # Un solo vincitore per ciascun premio
        self.winners = {'ambo': None, 'terno': None, 'quaterna': None, 'cinquina': None}
        self.tombola_winner = None  # Primo vincitore tombola
        self.game_active = True
        self.current_game_scores = {}
        self.overall_scores = {}
        self.usernames = {}
        self.user_houses = {}
        # Track which users have already had their join/sorting announced in the group
        self.announced_join_users = set()
        self.announced_smistamento_users = set()
        self.players_in_game = set()
        self.extraction_started = False
        self.game_interrupted = False
        self.chat_id = None
        self.thread_id = None
        self.tombole_fatte = 0
        self.custom_scores = premi_default.copy()
        self.extraction_task = None
        self.number_message_ids = []
        self.join_lock = asyncio.Lock()
        self.draw_lock = asyncio.Lock()
        # cache per le impostazioni di gruppo (popolato da set_chat_id)
        self.group_settings_cache = None
        self.group_settings_ts = 0
        self._group_settings_ttl = 30  # secondi



    def set_chat_id(self, chat_id):
        self.chat_id = chat_id
        # Carica e cachea le impostazioni del gruppo al settaggio della chat
        try:
            conf = load_group_settings_from_firebase(chat_id) or {}
            # load_group_settings_from_firebase returns a dict keyed by chat_id (string) in our client
            self.group_settings_cache = conf.get(str(chat_id), conf) if isinstance(conf, dict) else {}
            self.group_settings_ts = asyncio.get_event_loop().time()
            # Aggiorna punteggi personalizzati se presenti
            custom_scores = self.group_settings_cache.get('premi')
            if custom_scores:
                self.custom_scores = custom_scores
        except Exception:
            # Fallisce silenziosamente e lascia i valori di default
            self.group_settings_cache = {}

    def set_thread_id(self, thread_id):
        self.thread_id = thread_id

    async def add_player(self, user_id: int) -> bool:
        async with self.join_lock:
            if self.extraction_started:
                return False
            if user_id in self.players_in_game:
                return False

            # Crea la cartella impostando 15 numeri casuali
            if user_id not in self.players:
                numeri_cartella = random.sample(range(1, 91), 15)
                self.current_game_scores[user_id] = 0
                cartella = [
                    {num: False for num in sorted(numeri_cartella[0:5])},
                    {num: False for num in sorted(numeri_cartella[5:10])},
                    {num: False for num in sorted(numeri_cartella[10:15])}
                ]
                self.players[user_id] = cartella
                self.players_in_game.add(user_id)
                return True

            return False

    def start_extraction(self):
        self.extraction_started = True

    async def draw_number(self, context: ContextTypes.DEFAULT_TYPE = None):
        if not self.game_active:
            logger.warning(f"Tentativo di estrarre numero ma gioco non attivo in chat {self.chat_id}")
            return None
        async with self.draw_lock:
            # Protegge la selezione e la modifica della lista dei numeri
            if not self.game_active:
                logger.warning(f"Tentativo di estrarre numero ma gioco non attivo (inside lock) in chat {self.chat_id}")
                return None

            # Ottieni impostazioni di gruppo dalla cache se valida, altrimenti ricarica
            now = asyncio.get_event_loop().time()
            if self.group_settings_cache and (now - self.group_settings_ts) < self._group_settings_ttl:
                group_conf = self.group_settings_cache
            else:
                try:
                    loaded = load_group_settings_from_firebase(self.chat_id) or {}
                    group_conf = loaded.get(str(self.chat_id), loaded) if isinstance(loaded, dict) else {}
                    self.group_settings_cache = group_conf
                    self.group_settings_ts = now
                except Exception:
                    group_conf = {}
            feature_states = group_conf.get("bonus_malus_settings", {
                "104": True, "110": True, "666": True, "404": True, "Tombolino": True
            })

            selected_number = None
            idx_to_pop = -1

            for candidate_num in list(self.numeri_tombola):
                key = str(candidate_num)
                is_special_feature = key in feature_states

                if is_special_feature and not feature_states.get(key, True):
                    continue

                selected_number = candidate_num
                try:
                    idx_to_pop = self.numeri_tombola.index(candidate_num)
                except ValueError:
                    continue
                break

            if idx_to_pop != -1:
                try:
                    self.numeri_tombola.pop(idx_to_pop)
                except Exception:
                    pass
            elif not self.numeri_tombola and selected_number is None:
                self.game_active = False
                return None

            if selected_number is None:
                logger.info(f"Nessun numero valido rimasto da estrarre secondo le impostazioni per la chat {self.chat_id}.")
                if not self.numeri_tombola:
                    self.game_active = False
                return None

            # Applica numero estratto: aggiorna cartelle e controlla vincitori
            self.numeri_estratti.append(selected_number)

            for uid in list(self.players_in_game):
                self.update_cartella(uid, selected_number)

            await self.check_all_winners(context)

            return selected_number

    async def check_all_winners(self, context: ContextTypes.DEFAULT_TYPE):
        if not self.game_active or self.game_interrupted:
            return

        scores = self.custom_scores
        candidati = {'ambo': [], 'terno': [], 'quaterna': [], 'cinquina': []}

        for user_id, cartella in self.players.items():
            if user_id not in self.players_in_game:
                continue

            for riga in cartella:
                marcati_nella_riga = sum(1 for _, marked in riga.items() if marked)

                if marcati_nella_riga == 2 and self.winners['ambo'] is None:
                    candidati['ambo'].append(user_id)
                if marcati_nella_riga == 3 and self.winners['terno'] is None:
                    candidati['terno'].append(user_id)
                if marcati_nella_riga == 4 and self.winners['quaterna'] is None:
                    candidati['quaterna'].append(user_id)
                if marcati_nella_riga == 5 and self.winners['cinquina'] is None:
                    candidati['cinquina'].append(user_id)

        for premio, lista_utenti in candidati.items():
            if lista_utenti and self.winners[premio] is None:
                vincitore = random.choice(lista_utenti)
                self.winners[premio] = vincitore
                punti_assegnati = scores.get(premio, 0)
                self.add_score(vincitore, punti_assegnati)

                raw_username = self.usernames.get(vincitore, f"Utente_{vincitore}")
                escaped = escape_markdown(raw_username, version=2)

                premio_lower = premio  # oppure premio.lower()
                text_annuncio = f"_🏆 @{escaped} ha fatto {premio_lower}\\!_"

                await context.bot.send_message(
                    chat_id=self.chat_id,
                    text=text_annuncio,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    message_thread_id=self.thread_id
                )

    async def check_for_tombola(self, context: ContextTypes.DEFAULT_TYPE) -> bool:
            if not self.game_active:
                return True

            group_conf = load_group_settings_from_firebase(self.chat_id).get(str(self.chat_id), {})
            tombolino_active = group_conf.get("bonus_malus_settings", {}).get("Tombolino", False)
            tombola_points = self.custom_scores.get("tombola", premi_default["tombola"])

            group_settings = load_group_settings_from_firebase(self.chat_id)
            tema = group_settings.get(str(self.chat_id), {}).get('tema', 'normale')

            for user_id, cartella in self.players.items():
                if user_id not in self.players_in_game:
                    continue

                if self.tombola_winner is not None and user_id == self.tombola_winner:
                    continue

                is_tombola = all(marked for riga in cartella for _, marked in riga.items())
                if not is_tombola:
                    continue

                if self.tombola_winner is None:
                    self.tombola_winner = user_id
                    self.tombole_fatte += 1
                    raw_username = self.usernames.get(user_id, f"Utente_{user_id}")
                    escaped_username = escape_markdown(raw_username, version=2)

                    if tombolino_active:
                        points_awarded = tombola_points
                        extra = ", la partita prosegue per il tombolino"
                        game_should_end = False
                    elif tombolino_active and len(self.players_in_game) == 1:
                        points_awarded = tombola_points
                        extra = " e la partita è terminata"
                        game_should_end = True
                    else:
                        points_awarded = tombola_points
                        extra = " e la partita è terminata\\."
                        game_should_end = True

                    announcement_text = get_testo_tematizzato('tombola_prima', tema, escaped_username=escaped_username, extra=extra)

                    self.add_score(user_id, points_awarded)
                    try:
                        await context.bot.send_message(
                            chat_id=self.chat_id,
                            text=announcement_text,
                            parse_mode=ParseMode.MARKDOWN_V2,
                            message_thread_id=self.thread_id
                        )
                    except Exception as e:
                        logger.error(
                            f"Errore nell'annunciare la prima tombola per {raw_username} in chat {self.chat_id}: {e}"
                        )

                    if game_should_end:
                        self.game_active = False
                        return True
                    else:
                        return False  

                self.tombole_fatte += 1
                raw_username = self.usernames.get(user_id, f"Utente_{user_id}")
                escaped_username = escape_markdown(raw_username, version=2)
                points_awarded = tombola_points // 2
                announcement_text = get_testo_tematizzato('tombolino', tema, escaped_username=escaped_username)
                game_should_end = True

                self.add_score(user_id, points_awarded)
                logger.info(
                    f"Tombolino per {raw_username} (ID: {user_id}) in chat {self.chat_id}. "
                    f"Tombole fatte: {self.tombole_fatte}. Punti: {points_awarded}"
                )

                try:
                    await context.bot.send_message(
                        chat_id=self.chat_id,
                        text=announcement_text,
                        parse_mode=ParseMode.MARKDOWN_V2,
                        message_thread_id=self.thread_id
                    )
                except Exception as e:
                    logger.error(
                        f"Errore nell'annunciare il tombolino per {raw_username} in chat {self.chat_id}: {e}"
                    )

                if game_should_end:
                    self.game_active = False
                    return True

            return False

    async def check_winner(self, user_id, username_raw, context: ContextTypes.DEFAULT_TYPE):
        if not self.game_active or self.game_interrupted:
            return

        player_cartella = self.players.get(user_id)
        if not player_cartella:
            return

        scores = self.custom_scores

        for riga in player_cartella:
            numeri_marcati_in_riga = sum(1 for _, marked_val in riga.items() if marked_val)

            if numeri_marcati_in_riga == 2 and self.winners['ambo'] is None:
                self.winners['ambo'] = user_id
                punti_assegnati = scores.get('ambo', 0)
                self.add_score(user_id, punti_assegnati)
                await self.announce_winner("ambo", username_raw, punti_assegnati, context)
                return

            if numeri_marcati_in_riga == 3 and self.winners['terno'] is None:
                self.winners['terno'] = user_id
                punti_assegnati = scores.get('terno', 0)
                self.add_score(user_id, punti_assegnati)
                await self.announce_winner("terno", username_raw, punti_assegnati, context)
                return

            if numeri_marcati_in_riga == 4 and self.winners['quaterna'] is None:
                self.winners['quaterna'] = user_id
                punti_assegnati = scores.get('quaterna', 0)
                self.add_score(user_id, punti_assegnati)
                await self.announce_winner("quaterna", username_raw, punti_assegnati, context)
                return

            if numeri_marcati_in_riga == 5 and self.winners['cinquina'] is None:
                self.winners['cinquina'] = user_id
                punti_assegnati = scores.get('cinquina', 0)
                self.add_score(user_id, punti_assegnati)
                await self.announce_winner("cinquina", username_raw, punti_assegnati, context)
                return

    def add_score(self, user_id, points):
        if user_id in self.current_game_scores:
            self.current_game_scores[user_id] += points
        else:
            self.current_game_scores[user_id] = points

    def get_scores(self):
        return sorted(self.current_game_scores.items(), key=lambda x: x[1], reverse=True)

    def format_cartella(self, cartella):
        formatted_cartella = ""
        for riga in cartella:
            formatted_row = []
            for num, is_marked in riga.items():
                if is_marked:
                    formatted_row.append("✖️")
                else:
                    formatted_row.append(f"{num:02}")
            formatted_cartella += "  ".join(formatted_row) + "\n"
        return formatted_cartella

    def update_cartella(self, user_id, number):
        if user_id in self.players:
            for riga in self.players[user_id]:
                if number in riga:
                    riga[number] = True
                    return True
        return False

    def interrupt_game(self):
        if self.game_active:
            self.stop_game(interrupted=True)

    def update_overall_scores(self):
        """
        Aggiorna la classifica complessiva in Firebase sommando i punteggi
        della partita corrente. Poi ricarica la classifica overall da Firebase.
        """
        if self.game_interrupted or not self.chat_id:
            return

        for user_id, punti in self.current_game_scores.items():
            update_player_score(self.chat_id, user_id, punti)

        # Ricarica la classifica overall da Firebase
        self.overall_scores = load_classifica_from_firebase(self.chat_id)
        self.current_game_scores.clear()

    def stop_game(self, interrupted=False):
        self.game_active = False
        self.game_interrupted = interrupted

        if not interrupted:
            self.update_overall_scores()

    def reset_game(self):
        logger.info(f"Reset game state for chat {self.chat_id} (Thread: {self.thread_id})...")
        self.players = {}
        self.numeri_estratti = []
        self.numeri_tombola = list(range(1, 91)) + [110, 666, 104, 404]
        random.shuffle(self.numeri_tombola)
        self.winners = {'ambo': None, 'terno': None, 'quaterna': None, 'cinquina': None}
        self.tombola_winner = None
        self.game_active = True
        self.extraction_started = False
        self.players_in_game = set()
        self.current_game_scores = {}
        self.game_interrupted = False
        self.tombole_fatte = 0
        self.user_houses = {} 

        self.announced_join_users = set()
        self.announced_smistamento_users = set()

        if self.extraction_task and not self.extraction_task.done():
            try:
                self.extraction_task.cancel()
            except Exception:
                pass
        self.extraction_task = None
        self.number_message_ids.clear()

    async def get_username(self, user: Update.effective_user):
        user_id = user.id
        if user_id not in self.usernames:
            self.usernames[user_id] = user.username or user.first_name or str(user_id)
        return self.usernames[user_id]

    async def get_current_game_classifica(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        classifica = []
        for user_id, score in self.current_game_scores.items():
            if score > 0:
                user = await context.bot.get_chat_member(update.effective_chat.id, user_id)
                username = await self.get_username(user.user)
                classifica.append((username, score))
        return sorted(classifica, key=lambda x: x[1], reverse=True)

    async def get_overall_classifica(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        classifica_overall = []
        for user_id, score in self.overall_scores.items():
            if score > 0:
                user = await context.bot.get_chat_member(update.effective_chat.id, user_id)
                username = await self.get_username(user.user)
                classifica_overall.append((username, score))
        return sorted(classifica_overall, key=lambda x: x[1], reverse=True)
    async def announce_winner(self, prize_type_str: str, username_raw: str, points: int, context: ContextTypes.DEFAULT_TYPE):
        if not self.game_active or self.game_interrupted:
            return
        if not self.chat_id:
            return

        escaped_username = escape_markdown(username_raw, version=2)

        group_settings = load_group_settings_from_firebase(self.chat_id)
        tema = group_settings.get(str(self.chat_id), {}).get('tema', 'normale')
        message_text = get_testo_tematizzato('vincitore_premio', tema, escaped=escaped_username, premio_lower=prize_type_str.lower())

        try:
            await context.bot.send_message(
                chat_id=self.chat_id,
                text=message_text,
                parse_mode=ParseMode.MARKDOWN_V2,
                message_thread_id=self.thread_id
            )
        except telegram.error.RetryAfter as e:
            logger.warning(f"Flood control durante annuncio {prize_type_str} per {username_raw}: attendo {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            try:
                await context.bot.send_message(
                    chat_id=self.chat_id,
                    text=message_text,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    message_thread_id=self.thread_id
                )
            except Exception as e_retry:
                logger.error(f"Errore nel riprovare ad annunciare {prize_type_str} per {username_raw}: {e_retry}")
        except Exception as e:
            logger.error(f"Errore generico nell'annunciare {prize_type_str} per {escaped_username} in chat {self.chat_id}: {e}")

# Gestione istanze di gioco per chat
games = {}


def get_game(chat_id):
    if chat_id not in games:
        game = TombolaGame()
        game.set_chat_id(chat_id)
        games[chat_id] = game
    return games[chat_id]
