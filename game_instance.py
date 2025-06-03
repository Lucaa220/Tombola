import random
from telegram import Update
from telegram.ext import ContextTypes
import asyncio
from variabili import chat_id_global, thread_id_global, JSONBIN_API_KEY, CLASSIFICA_BIN_ID, load_group_settings, premi_default
import logging
import json
import os
from telegram.constants import ParseMode
import requests
from telegram.helpers import escape_markdown
import telegram

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

JSONBIN_BASE_URL = "https://api.jsonbin.io/v3/b"


def load_classifica_from_json(group_id: int) -> dict:
    url = f"{JSONBIN_BASE_URL}/{CLASSIFICA_BIN_ID}/latest"
    headers = {
        "X-Master-Key": JSONBIN_API_KEY,
    }

    try:
        resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        data = resp.json().get("record", {})
        return data.get(str(group_id), {})
    except requests.HTTPError as e:
        logger.error(f"JSONBin load error (HTTP): {e}")
    except Exception as e:
        logger.error(f"JSONBin load error: {e}")

    return {}


def save_classifica_to_json(group_id: int, scores: dict) -> None:
    url_latest = f"{JSONBIN_BASE_URL}/{CLASSIFICA_BIN_ID}/latest"
    url = f"{JSONBIN_BASE_URL}/{CLASSIFICA_BIN_ID}"
    headers = {
        "X-Master-Key": JSONBIN_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.get(url_latest, headers=headers)
        resp.raise_for_status()
        all_records = resp.json().get("record", {})
    except Exception as e:
        logger.warning(f"JSONBin pre-load warning, inizializzo bin vuoto: {e}")
        all_records = {}

    all_records[str(group_id)] = scores

    try:
        resp = requests.put(url, headers=headers, json=all_records)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"JSONBin save error: {e}")


def update_player_score(group_id: int, user_id: int, points: int) -> None:
    classifica = load_classifica_from_json(group_id)
    classifica[str(user_id)] = classifica.get(str(user_id), 0) + points
    save_classifica_to_json(group_id, classifica)


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
        self.players_in_game = set()
        self.extraction_started = False
        self.game_interrupted = False
        self.chat_id = None
        self.thread_id = None
        self.tombole_fatte = 0
        self.custom_scores = premi_default.copy()
        self.extraction_task = None

    def set_chat_id(self, chat_id):
        self.chat_id = chat_id

    def set_thread_id(self, thread_id):
        self.thread_id = thread_id

    def add_player(self, user_id):
        if self.extraction_started:
            return False

        if user_id in self.players_in_game:
            return False

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

        group_conf = load_group_settings().get(str(self.chat_id), {})
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
                logger.error(f"Numero candidato {candidate_num} non trovato in self.numeri_tombola durante estrazione.")
                continue
            break

        if idx_to_pop != -1:
            self.numeri_tombola.pop(idx_to_pop)
        elif not self.numeri_tombola and selected_number is None:
            logger.info(f"Sacchetto numeri vuoto per la chat {self.chat_id}.")
            self.game_active = False
            return None

        if selected_number is None:
            logger.info(f"Nessun numero valido rimasto da estrarre secondo le impostazioni per la chat {self.chat_id}.")
            if not self.numeri_tombola:
                self.game_active = False
            return None

        self.numeri_estratti.append(selected_number)
        logger.info(f"Numero estratto: {selected_number} in chat {self.chat_id}. Numeri rimasti: {len(self.numeri_tombola)}")

        # 1) Marco il numero sui cartelloni di TUTTI i giocatori
        for uid in list(self.players_in_game):
            self.update_cartella(uid, selected_number)

        # 2) Controllo collettivo dei vincitori per ogni premio (solo primo a farlo)
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
                premio_cap = premio.capitalize()

                text_annuncio = f"_🏆 @{escaped} ha fatto {premio_cap}\\!_"
                await context.bot.send_message(
                    chat_id=self.chat_id,
                    text=text_annuncio,
                    parse_mode=ParseMode.MARKDOWN_V2,
                    message_thread_id=self.thread_id
                )

    async def check_for_tombola(self, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Verifica se qualcuno ha fatto tombola o tombolino.
        - Alla prima tombola: assegna a quel giocatore il premio tombola e imposta self.tombola_winner.
        - Al secondo round (tombolino): ignora il giocatore self.tombola_winner e assegna tombolino al primo differente.
        """
        if not self.game_active:
            return True

        group_conf = load_group_settings().get(str(self.chat_id), {})
        tombolino_active = group_conf.get("bonus_malus_settings", {}).get("Tombolino", False)
        tombola_points = self.custom_scores.get("tombola", premi_default["tombola"])

        for user_id, cartella in self.players.items():
            if user_id not in self.players_in_game:
                continue

            # Se è già il vincitore della prima tombola, ignoralo per il tombolino
            if self.tombola_winner is not None and user_id == self.tombola_winner:
                continue

            is_tombola = all(marked for riga in cartella for _, marked in riga.items())
            if not is_tombola:
                continue

            # Se non c'è ancora un vincitore di tombola, questo è il primo
            if self.tombola_winner is None:
                self.tombola_winner = user_id
                self.tombole_fatte += 1
                raw_username = self.usernames.get(user_id, f"Utente_{user_id}")
                escaped_username = escape_markdown(raw_username, version=2)

                # Primo round di tombola
                if tombolino_active:
                    points_awarded = tombola_points
                    announcement_text = (
                        f"_🏆 @{escaped_username} ha fatto tombola, la partita prosegue per il tombolino_"
                    )
                    game_should_end = False
                else:
                    points_awarded = tombola_points
                    announcement_text = (
                        f"_🏆 @{escaped_username} ha fatto tombola e la partita è terminata\\._"
                    )
                    game_should_end = True

                self.add_score(user_id, points_awarded)
                logger.info(
                    f"Tombola per {raw_username} (ID: {user_id}) in chat {self.chat_id}. "
                    f"Tombole fatte: {self.tombole_fatte}. Tombolino: {tombolino_active}. Punti: {points_awarded}"
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
                        f"Errore nell'annunciare la prima tombola per {raw_username} in chat {self.chat_id}: {e}"
                    )

                if game_should_end:
                    self.game_active = False
                    return True
                else:
                    return False  # Continua per far giocare gli altri al tombolino

            # Se qui, significa che self.tombola_winner è già impostato: stiamo cercando il tombolino
            # Questo user_id non è equal al primo vincitore, e ha la cartella piena => è il vincitore del tombolino
            self.tombole_fatte += 1
            raw_username = self.usernames.get(user_id, f"Utente_{user_id}")
            escaped_username = escape_markdown(raw_username, version=2)
            points_awarded = tombola_points // 2
            announcement_text = (
                f"_🏆 @{escaped_username} ha fatto tombolino e la partita è terminata\\._"
            )
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
            logger.warning(f"Nessuna cartella trovata per l'utente {user_id} ({username_raw}) in check_winner.")
            return

        scores = self.custom_scores

        for riga in player_cartella:
            numeri_marcati_in_riga = sum(1 for _, marked_val in riga.items() if marked_val)

            # Ambo
            if numeri_marcati_in_riga == 2 and self.winners['ambo'] is None:
                self.winners['ambo'] = user_id
                punti_assegnati = scores.get('ambo', 0)
                self.add_score(user_id, punti_assegnati)
                logger.info(f"Ambo per {username_raw} (ID: {user_id}) in chat {self.chat_id}. Punti: {punti_assegnati}")
                await self.announce_winner("Ambo", username_raw, punti_assegnati, context)
                return

            # Terno
            if numeri_marcati_in_riga == 3 and self.winners['terno'] is None:
                self.winners['terno'] = user_id
                punti_assegnati = scores.get('terno', 0)
                self.add_score(user_id, punti_assegnati)
                logger.info(f"Terno per {username_raw} (ID: {user_id}) in chat {self.chat_id}. Punti: {punti_assegnati}")
                await self.announce_winner("Terno", username_raw, punti_assegnati, context)
                return

            # Quaterna
            if numeri_marcati_in_riga == 4 and self.winners['quaterna'] is None:
                self.winners['quaterna'] = user_id
                punti_assegnati = scores.get('quaterna', 0)
                self.add_score(user_id, punti_assegnati)
                logger.info(f"Quaterna per {username_raw} (ID: {user_id}) in chat {self.chat_id}. Punti: {punti_assegnati}")
                await self.announce_winner("Quaterna", username_raw, punti_assegnati, context)
                return

            # Cinquina
            if numeri_marcati_in_riga == 5 and self.winners['cinquina'] is None:
                self.winners['cinquina'] = user_id
                punti_assegnati = scores.get('cinquina', 0)
                self.add_score(user_id, punti_assegnati)
                logger.info(f"Cinquina per {username_raw} (ID: {user_id}) in chat {self.chat_id}. Punti: {punti_assegnati}")
                await self.announce_winner("Cinquina", username_raw, punti_assegnati, context)
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
        logger.warning(f"Numero {number} non trovato nella cartella dell'utente {user_id}.")
        return False

    def interrupt_game(self):
        if self.game_active:
            self.stop_game(interrupted=True)
            print("Il gioco è stato interrotto manualmente.")
        else:
            print("Nessun gioco attivo da interrompere.")

    def update_overall_scores(self):
        if self.game_interrupted or not self.chat_id:
            logger.warning("Partita interrotta o chat_id non impostato, punteggi non aggiornati.")
            return

        for user_id, punti in self.current_game_scores.items():
            update_player_score(self.chat_id, user_id, punti)

        self.overall_scores = load_classifica_from_json(self.chat_id)
        self.current_game_scores.clear()

    def stop_game(self, interrupted=False):
        self.game_active = False
        self.game_interrupted = interrupted

        if not interrupted:
            self.update_overall_scores()
            print("Il gioco è stato completato e i punteggi sono stati aggiornati.")
        else:
            print("Il gioco è stato interrotto, i punteggi della partita corrente non verranno conteggiati.")

    def reset_game(self):
        logger.info(f"Reset game state for chat {self.chat_id} (Thread: {self.thread_id})...")
        self.players = {}
        self.numeri_estratti = []
        self.numeri_tombola = list(range(1, 91)) + [110, 666, 104, 404]
        random.shuffle(self.numeri_tombola)
        # Ripristina vincitori e tombola_winner a None
        self.winners = {'ambo': None, 'terno': None, 'quaterna': None, 'cinquina': None}
        self.tombola_winner = None
        self.game_active = True
        self.extraction_started = False
        self.players_in_game = set()
        self.current_game_scores = {}
        self.game_interrupted = False
        self.tombole_fatte = 0

        if self.extraction_task and not self.extraction_task.done():
            try:
                self.extraction_task.cancel()
            except Exception:
                pass
        self.extraction_task = None

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
                print(f"User ID: {user_id}, Username: {username}, Current Game Score: {score}")
                classifica.append((username, score))
        return sorted(classifica, key=lambda x: x[1], reverse=True)

    async def get_overall_classifica(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        classifica_overall = []
        for user_id, score in self.overall_scores.items():
            if score > 0:
                user = await context.bot.get_chat_member(update.effective_chat.id, user_id)
                username = await self.get_username(user.user)
                print(f"User ID: {user_id}, Username: {username}, Overall Score: {score}")
                classifica_overall.append((username, score))
        return sorted(classifica_overall, key=lambda x: x[1], reverse=True)

    async def announce_winner(self, prize_type_str: str, username_raw: str, points: int, context: ContextTypes.DEFAULT_TYPE):
        if not self.game_active or self.game_interrupted:
            return
        if not self.chat_id:
            logger.error(f"Impossibile annunciare {prize_type_str} per {username_raw}: chat_id non definito.")
            return

        escaped_username = escape_markdown(username_raw, version=2)

        message_text = f"_🏆 @{escaped_username} ha fatto {prize_type_str}\\!_"

        try:
            await context.bot.send_message(
                chat_id=self.chat_id,
                text=message_text,
                parse_mode=ParseMode.MARKDOWN_V2,
                message_thread_id=self.thread_id
            )
            logger.info(f"Annunciato: {prize_type_str} per {username_raw} in chat {self.chat_id}")
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


games = {}


def get_game(chat_id):
    if chat_id not in games:
        game = TombolaGame()
        game.set_chat_id(chat_id)
        games[chat_id] = game
    return games[chat_id]
