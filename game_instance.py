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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

JSONBIN_BASE_URL = "https://api.jsonbin.io/v3/b"

def load_classifica_from_json(group_id: int) -> dict:
    """
    Carica tutte le classifiche dal bin e restituisce solo quella per `group_id`.
    Se il bin non esiste o c'è un errore, restituisce {}.
    """
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

    return {}  # Restituisce un dizionario vuoto in caso di errore

def save_classifica_to_json(group_id: int, scores: dict) -> None:
    """
    Carica il contenuto attuale del bin, aggiorna la voce per `group_id` e riscrive il record.
    Se il bin non esiste, lo inizializza.
    """
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
    # Scarica il dict solo del gruppo
    classifica = load_classifica_from_json(group_id)

    # Aggiorna il punteggio
    classifica[str(user_id)] = classifica.get(str(user_id), 0) + points

    # Salva TUTTO il bin aggiornando solo questo gruppo
    save_classifica_to_json(group_id, classifica)


class TombolaGame:
    def __init__(self):
        self.players = {}  # Giocatori e le loro cartelle
        self.numeri_estratti = []  # Numeri già estratti
        # Include numeri da 1 a 90, bonus 110 e malus 666
        self.numeri_tombola = list(range(1, 91)) + [110, 666, 104, 404]
        random.shuffle(self.numeri_tombola)  # Mischia i numeri
        self.winners = {'ambo': None, 'terno': None, 'quaterna': None, 'cinquina': None, 'tombola': None}  # Per tracciare le vittorie
        self.game_active = True  # Stato del gioco
        self.current_game_scores = {}  # Punteggi per la partita corrente
        self.overall_scores = {}  # Punteggi generali
        self.usernames = {}  # Dizionario per i nomi utente
        self.players_in_game = set()
        self.extraction_started = False
        self.game_interrupted = False
        self.chat_id = None
        self.thread_id = None  # Per gestire i thread dei messaggi
        self.tombole_fatte = 0

    def set_chat_id(self, chat_id):
        self.chat_id = chat_id
        self.load_scores_from_file()

    def set_thread_id(self, thread_id):
        self.thread_id = thread_id

    def add_player(self, user_id):
        if self.extraction_started:
            return False

        if user_id in self.players_in_game:
            return False  # L'utente è già in partita

        if user_id not in self.players:
            # Genera 15 numeri unici per la cartella
            numeri_cartella = random.sample(range(1, 91), 15)
            self.current_game_scores[user_id] = 0  # Inizializza il punteggio del giocatore per la partita corrente
            # Divide i numeri in 3 righe da 5 numeri ciascuna
            cartella = [
                {num: False for num in sorted(numeri_cartella[0:5])},   # Prima riga
                {num: False for num in sorted(numeri_cartella[5:10])},  # Seconda riga
                {num: False for num in sorted(numeri_cartella[10:15])}  # Terza riga
            ]
            self.players[user_id] = cartella
            self.players_in_game.add(user_id)
            return True
        return False

    def start_extraction(self):
        self.extraction_started = True

    async def draw_number(self, context: ContextTypes.DEFAULT_TYPE = None):
        # 1) Prendi lo stato di tutti i bonus/malus
        group_conf = load_group_settings().get(str(self.chat_id), {})
        feature_states = group_conf.get("bonus_malus_settings", {
            "104": True,
            "110": True,
            "666": True,
            "404": True,
            "Tombolino": True
        })

        # 2) Estrai il prossimo valore valido
        number = None
        while self.numeri_tombola and self.game_active:
            candidate = self.numeri_tombola.pop(0)
            key = str(candidate) if str(candidate) in feature_states else None

            # Se è “Tombolino” lo gestirai altrove, qui lasciamo passare
            if candidate == "Tombolino":
                key = "Tombolino"

            # Se è una feature definita e disabilitata, salta
            if key and not feature_states.get(key, True):
                continue

            # Altrimenti lo prendi
            number = candidate
            break

        if number is None:
            return None

        # 3) Registra l’estratto
        self.numeri_estratti.append(number)

        # 4) Applica logica speciali solo se abilitati
        if number == 110 and feature_states.get("110", True):
            if self.players_in_game:
                player = random.choice(list(self.players_in_game))
                punti = random.randint(1, 49)
                self.add_score(player, punti)
                if context:
                    try:
                        member = await context.bot.get_chat_member(self.chat_id, player)
                        uname = member.user.username or member.user.first_name or str(player)
                    except:
                        uname = str(player)
                    await context.bot.send_message(
                        chat_id=self.chat_id,
                        text=(
                            f"*🧑‍🎓 Numero 110 estratto\\!*\n\n"
                            f"_🆒 @{uname} ha guadagnato {punti} punti_"
                        ),
                        message_thread_id=self.thread_id,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
            else:
                logger.warning("110 estratto ma non ci sono giocatori.")
        
        elif number == 666 and feature_states.get("666", True):
            if self.players_in_game:
                player = random.choice(list(self.players_in_game))
                punti = random.randint(1, 49)
                self.add_score(player, -punti)
                if context:
                    try:
                        member = await context.bot.get_chat_member(self.chat_id, player)
                        uname = member.user.username or member.user.first_name or str(player)
                    except:
                        uname = str(player)
                    await context.bot.send_message(
                        chat_id=self.chat_id,
                        text=(
                            f"*🛐 Numero 666 estratto\\!*\n\n"
                            f"_🆒 @{uname} ha perso {punti} punti_"
                        ),
                        message_thread_id=self.thread_id,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
            else:
                logger.warning("666 estratto ma non ci sono giocatori.")

        elif number == 104 and feature_states.get("104", True):
            if self.players_in_game:
                player = random.choice(list(self.players_in_game))
                punti = random.randint(1, 49)
                self.add_score(player, punti)
                if context:
                    try:
                        member = await context.bot.get_chat_member(self.chat_id, player)
                        uname = member.user.username or member.user.first_name or str(player)
                    except:
                        uname = str(player)
                    await context.bot.send_message(
                        chat_id=self.chat_id,
                        text=(
                            f"*♿️ Numero 104 estratto\\!*\n\n"
                            f"_🆒 @{uname} ha guadagnato {punti} punti_"
                        ),
                        message_thread_id=self.thread_id,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
            else:
                logger.warning("104 estratto ma non ci sono giocatori.")    

        elif number == 404 and feature_states.get("404", True):
            if self.players_in_game:
                player = random.choice(list(self.players_in_game))
                punti = random.randint(1, 49)
                self.add_score(player, -punti)
                if context:
                    try:
                        member = await context.bot.get_chat_member(self.chat_id, player)
                        uname = member.user.username or member.user.first_name or str(player)
                    except:
                        uname = str(player)
                    await context.bot.send_message(
                        chat_id=self.chat_id,
                        text=(
                            f"*🆘 Numero 404 estratto\\!*\n\n"
                            f"_🆒 @{uname} ha perso {punti} punti_"
                        ),
                        message_thread_id=self.thread_id,
                        parse_mode=ParseMode.MARKDOWN_V2
                    )
            else:
                logger.warning("404 estratto ma non ci sono giocatori.")
        
        return number
    
    async def check_for_tombola(self, context: ContextTypes.DEFAULT_TYPE):
        group_conf = load_group_settings().get(str(self.chat_id), {})
        tombolino_active = group_conf.get("bonus_malus_settings", {}).get("Tombolino", False)
        premi = group_conf.get("premi", premi_default)

        for user_id, cartella in self.players.items():
            if cartella.is_complete(self.numeri_estratti):
                self.tombole_fatte += 1

                base = premi.get("tombola", premi_default["tombola"])

                if tombolino_active:
                    if self.tombole_fatte == 1:
                        await context.bot.send_message(
                            chat_id=self.chat_id,
                            text=(f"_@{await self._username(user_id)} ha fatto tombola\\._"),
                            parse_mode=ParseMode.MARKDOWN_V2,
                            message_thread_id=self.thread_id
                        )
                        return False  

                    punti = base // 2
                    await context.bot.send_message(
                        chat_id=self.chat_id,
                        text=(f"_@{await self._username(user_id)} ha fatto tombolino e la partita è terminata\\._"),
                        parse_mode=ParseMode.MARKDOWN_V2,
                        message_thread_id=self.thread_id
                    )
                    self.add_score(user_id, punti)
                    self.game_active = False
                    return True

                else:
                    await context.bot.send_message(
                        chat_id=self.chat_id,
                        text=(f"_@{await self._username(user_id)} ha fatto tombola\\._"),
                        parse_mode=ParseMode.MARKDOWN_V2,
                        message_thread_id=self.thread_id
                    )
                    return False  

        return False

    async def check_winner(self, user_id, username, context: ContextTypes.DEFAULT_TYPE):
        scores = getattr(self, "custom_scores", {
            "ambo": 5,
            "terno": 10,
            "quaterna": 15,
            "cinquina": 20,
            "tombola": 50
        })

        player_cartella = self.players.get(user_id, [])
        if not player_cartella:
            logger.warning(f"Nessuna cartella trovata per l'utente {user_id}.")
            return None

        for i, riga in enumerate(player_cartella):
            matched_numbers = sum(is_marked for is_marked in riga.values())
            if matched_numbers in [2, 3, 4, 5]:
                prize_type = ['ambo', 'terno', 'quaterna', 'cinquina'][matched_numbers - 2]
                if self.winners[prize_type] is None:
                    self.winners[prize_type] = user_id
                    points = scores.get(prize_type, 0)
                    self.add_score(user_id, points)
                    asyncio.create_task(self.announce_winner(prize_type.capitalize(), username, context))
                    return prize_type

        if all(is_marked for riga in player_cartella for is_marked in riga.values()) and self.winners['tombola'] is None:
            self.winners['tombola'] = user_id
            self.add_score(user_id, scores.get("tombola", 50))
            await context.bot.send_message(
                chat_id=self.chat_id,
                text=f"_🏆 @{username} ha fatto tombola e la partita è terminata\\!_",
                parse_mode=ParseMode.MARKDOWN_V2,
                message_thread_id=self.thread_id
            )
            asyncio.create_task(self.update_overall_scores())
            self.stop_game(interrupted=False)
            return "tombola e la partita è terminata"

        return None

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
        return False  # Restituisce False se il numero non è stato trovato

    def interrupt_game(self):
        if self.game_active:
            self.stop_game(interrupted=True)
            print("Il gioco è stato interrotto manualmente.")
        else:
            print("Nessun gioco attivo da interrompere.")

    def update_overall_scores(self):
        """
        Per ogni user_id in self.current_game_scores,
        incrementa il suo punteggio sul bin usando update_player_score,
        poi ricarica self.overall_scores e resetta current_game_scores.
        """
        if self.game_interrupted or not self.chat_id:
            logger.warning("Partita interrotta o chat_id non impostato, punteggi non aggiornati.")
            return

        # Usa l'helper che aggiorna un singolo utente sul bin
        for user_id, punti in self.current_game_scores.items():
            update_player_score(self.chat_id, user_id, punti)

        # Ricarica i punteggi complessivi dal bin
        # (questa chiamata ti restituisce solo il dict {user_id: punti} per questo gruppo)
        self.overall_scores = load_classifica_from_json(self.chat_id)

        # Pulisci i punteggi di partita
        self.current_game_scores.clear()

    def save_scores_to_file(self):
        filename = "classifiche.json"
        try:
            if os.path.exists(filename):
                with open(filename, 'r') as file:
                    all_scores = json.load(file)
            else:
                all_scores = {}

            all_scores[str(self.chat_id)] = self.overall_scores

            with open(filename, 'w') as file:
                json.dump(all_scores, file, indent=4)
        except Exception as e:
            logger.error(f"Errore durante il salvataggio dei punteggi: {e}")

    def load_scores_from_file(self):
        try:
            all_scores = load_classifica_from_json("classifiche.json")
            self.overall_scores = all_scores.get(str(self.chat_id), {})
        except Exception as e:
            logger.error(f"Errore durante il caricamento dei punteggi: {e}")
            self.overall_scores = {}

    def stop_game(self, interrupted=False):
        self.game_active = False
        self.game_interrupted = interrupted

        if not interrupted:
            self.update_overall_scores()
            print("Il gioco è stato completato e i punteggi sono stati aggiornati.")
        else:
            print("Il gioco è stato interrotto, i punteggi della partita corrente non verranno conteggiati.")

    def reset_game(self):
        saved_overall_scores = self.overall_scores.copy()
        self.players = {}
        self.numeri_estratti = []
        self.numeri_tombola = list(range(1, 91)) + [110, 666, 404, 104]
        random.shuffle(self.numeri_tombola)
        self.winners = {'ambo': None, 'terno': None, 'quaterna': None, 'cinquina': None, 'tombola': None}
        self.game_active = True
        self.extraction_started = False
        self.players_in_game = set()
        self.current_game_scores = {}
        self.overall_scores = saved_overall_scores
        self.game_interrupted = False
        self.tombole_fatte = 0

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

    async def announce_winner(self, prize_type, username, context: ContextTypes.DEFAULT_TYPE):
        if not self.chat_id or not self.thread_id:
            logger.error("Chat ID o Thread ID non sono definiti!")
            return
        if self.game_interrupted:
            print(f"Annuncio del premio {prize_type} non effettuato perché il gioco è stato interrotto.")

    def save_scores_to_file(self, filename="classifiche.json"):
        try:
            with open(filename, 'w') as file:
                json.dump(self.overall_scores, file)
            print("Punteggi salvati correttamente.")
        except IOError as e:
            print(f"Errore durante il salvataggio dei punteggi: {e}")

    def load_scores_from_file(self, filename="classifiche.json"):
        try:
            with open(filename, 'r') as file:
                self.overall_scores = json.load(file)
            print("Punteggi caricati correttamente.")
        except FileNotFoundError:
            print(f"File {filename} non trovato, nessun punteggio da caricare.")
            self.overall_scores = {}
        except json.JSONDecodeError as e:
            print(f"Errore nella lettura del file JSON: {e}")
            self.overall_scores = {}
        except IOError as e:
            print(f"Errore durante il caricamento dei punteggi: {e}")

# Dizionario per gestire le istanze di gioco per ogni chat
games = {}

def get_game(chat_id):
    if chat_id not in games:
        game = TombolaGame()
        game.set_chat_id(chat_id)
        games[chat_id] = game
    return games[chat_id]
