import random
from telegram import Update
from telegram.ext import ContextTypes
import asyncio
from variabili import chat_id_global, thread_id_global
import logging
import json
import os
from telegram.constants import ParseMode

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def load_classifica_from_json(filename):
    try:
        with open(filename, 'r') as json_file:
            all_scores = json.load(json_file)
        return all_scores
    except Exception as e:
        logger.error(f"Errore durante il caricamento della classifica dal file {filename}: {e}")
        return {}

def save_classifica_to_json(filename, all_scores):
    try:
        with open(filename, 'w') as json_file:
            json.dump(all_scores, json_file, indent=4)
        logger.info(f"Classifiche salvate correttamente nel file {filename}.")
    except Exception as e:
        logger.error(f"Errore durante il salvataggio delle classifiche nel file {filename}: {e}")

def update_player_score(group_id: int, user_id: int, score: int) -> None:
    logger.info(f"Aggiornamento punteggio per gruppo {group_id}, utente {user_id}, punteggio {score}")
    classifica = load_classifica_from_json(group_id)
    logger.info(f"Classifica prima dell'aggiornamento: {classifica}")

    if str(user_id) in classifica:
        classifica[str(user_id)] += score
    else:
        classifica[str(user_id)] = score

    logger.info(f"Classifica dopo l'aggiornamento: {classifica}")
    save_classifica_to_json(group_id, classifica)
    logger.info(f"Punteggio aggiornato per l'utente {user_id} nel gruppo {group_id}: {score} punti")


class TombolaGame:
    def __init__(self):
        self.players = {}  # Giocatori e le loro cartelle
        self.numeri_estratti = []  # Numeri già estratti
        # Include numeri da 1 a 90, bonus 104 e malus 666
        self.numeri_tombola = list(range(1, 91)) + [104, 666]
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
        # Carica le impostazioni di gruppo per verificare se bonus/malus sono abilitati (default True)
        from variabili import load_group_settings  # Import locale per evitare cicli di importazione
        group_settings = load_group_settings()
        bonus_malus_enabled = group_settings.get(str(self.chat_id), {}).get("bonus_malus", True)

        # Se i bonus/malus sono disattivati, ignoriamo i numeri 104 e 666
        number = None
        while self.numeri_tombola and self.game_active:
            potential = self.numeri_tombola.pop(0)
            if not bonus_malus_enabled and potential in [104, 666]:
                logger.info(f"Numero {potential} estratto ma bonus/malus disabilitati: salto il numero.")
                continue
            number = potential
            break

        if number is not None:
            self.numeri_estratti.append(number)
            # Gestione bonus e malus: questi blocchi verranno eseguiti solo se i bonus/malus sono abilitati
            if number == 104 and bonus_malus_enabled:
                if self.players_in_game:
                    random_player = random.choice(list(self.players_in_game))
                    bonus_points = random.randint(1, 49)
                    self.add_score(random_player, bonus_points)
                    logger.info(f"Numero 104 estratto! Al giocatore {random_player} sono stati assegnati {bonus_points} punti bonus.")
                    if context is not None:
                        try:
                            chat_member = await context.bot.get_chat_member(self.chat_id, random_player)
                            username = chat_member.user.username or chat_member.user.first_name or str(random_player)
                        except Exception:
                            username = str(random_player)
                        await context.bot.send_message(
                            chat_id=self.chat_id,
                            text=f"*♿️ Numero 104 estratto\\!*\n\n_🆒 @{username} ha guadagnato {bonus_points} punti_",
                            message_thread_id=self.thread_id,
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                else:
                    logger.warning("Numero 104 estratto ma non ci sono giocatori in partita.")
            elif number == 666 and bonus_malus_enabled:
                if self.players_in_game:
                    random_player = random.choice(list(self.players_in_game))
                    malus_points = random.randint(1, 49)
                    self.add_score(random_player, -malus_points)
                    logger.info(f"Numero 666 estratto! Al giocatore {random_player} sono stati rimossi {malus_points} punti malus.")
                    if context is not None:
                        try:
                            chat_member = await context.bot.get_chat_member(self.chat_id, random_player)
                            username = chat_member.user.username or chat_member.user.first_name or str(random_player)
                        except Exception:
                            username = str(random_player)
                        await context.bot.send_message(
                            chat_id=self.chat_id,
                            text=f"*🛐 Numero 666 estratto\\!*\n\n_🆒 @{username} ha perso {malus_points} punti_",
                            message_thread_id=self.thread_id,
                            parse_mode=ParseMode.MARKDOWN_V2
                        )
                else:
                    logger.warning("Numero 666 estratto ma non ci sono giocatori in partita.")
            return number
        return None

    def check_winner(self, user_id, username, context: ContextTypes.DEFAULT_TYPE):
        # Preleva i punteggi personalizzati se presenti, altrimenti usa i valori di default
        scores = getattr(self, "custom_scores", {
            "ambo": 5,
            "terno": 10,
            "quaterna": 15,
            "cinquina": 20,
            "tombola": 50
        })

        player_cartella = self.players.get(user_id, [])
        for i, riga in enumerate(player_cartella):
            # Conta i numeri "segnati" in ogni riga
            matched_numbers = sum(is_marked for is_marked in riga.values())
            # Se la riga ha 2, 3, 4 o 5 numeri segnati...
            if matched_numbers in [2, 3, 4, 5]:
                # Mappa il numero di numeri segnati al tipo di premio:
                prize_type = ['ambo', 'terno', 'quaterna', 'cinquina'][matched_numbers - 2]
                if self.winners[prize_type] is None:
                    self.winners[prize_type] = user_id
                    # Assegna i punti usando il valore definito in "scores"
                    points = scores.get(prize_type, 0)
                    self.add_score(user_id, points)
                    asyncio.create_task(self.announce_winner(prize_type.capitalize(), username, context))
                    return prize_type

        # Se il giocatore ha segnato tutti i numeri e non è stata ancora assegnata la tombola
        if all(is_marked for riga in player_cartella for is_marked in riga.values()) and self.winners['tombola'] is None:
            self.winners['tombola'] = user_id
            self.add_score(user_id, scores.get("tombola", 50))
            self.update_overall_scores()
            self.stop_game(interrupted=False)
            asyncio.create_task(self.announce_winner("Tombola", username, context))
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

        all_scores = load_classifica_from_json("classifiche.json")
        group_scores = all_scores.get(str(self.chat_id), {})

        for user_id, score in self.current_game_scores.items():
            user_id_str = str(user_id)
            group_scores[user_id_str] = group_scores.get(user_id_str, 0) + score

        all_scores[str(self.chat_id)] = group_scores
        save_classifica_to_json("classifiche.json", all_scores)
        logger.info(f"Punteggi aggiornati per il gruppo {self.chat_id}")

        self.overall_scores = group_scores
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
            logger.info(f"Punteggi salvati correttamente per il gruppo {self.chat_id}")
        except Exception as e:
            logger.error(f"Errore durante il salvataggio dei punteggi: {e}")

    def load_scores_from_file(self):
        try:
            all_scores = load_classifica_from_json("classifiche.json")
            self.overall_scores = all_scores.get(str(self.chat_id), {})
            logger.info(f"Punteggi caricati correttamente per il gruppo {self.chat_id}")
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
        self.numeri_tombola = list(range(1, 91)) + [104, 666]
        random.shuffle(self.numeri_tombola)
        self.winners = {'ambo': None, 'terno': None, 'quaterna': None, 'cinquina': None, 'tombola': None}
        self.game_active = True
        self.extraction_started = False
        self.players_in_game = set()
        self.current_game_scores = {}
        self.overall_scores = saved_overall_scores
        if self.game_interrupted:
            print("Gioco resettato. Poiché il gioco è stato interrotto, i punteggi della partita corrente sono stati cancellati.")
        self.game_interrupted = False
        print("Gioco resettato mantenendo i punteggi generali.")

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
