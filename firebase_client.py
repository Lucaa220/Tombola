import os
import firebase_admin
from firebase_admin import credentials, db, exceptions
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --------------------------------------------------------------------
# 1. Configurazione iniziale Firebase Admin
# --------------------------------------------------------------------
SERVICE_ACCOUNT_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if not SERVICE_ACCOUNT_PATH:
    raise RuntimeError(
        "Devi impostare GOOGLE_APPLICATION_CREDENTIALS con il percorso al file JSON del Service Account."
    )

DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "Devi impostare FIREBASE_DATABASE_URL con l'URL del tuo Realtime Database Firebase."
    )

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
        firebase_admin.initialize_app(cred, {
            "databaseURL": DATABASE_URL
        })
        logger.info("Firebase Admin inizializzato correttamente.")
    except Exception as e:
        logger.error(f"Errore inizializzazione Firebase Admin: {e}")
        raise

# --------------------------------------------------------------------
# 2. CLASSIFICA (punti)
# --------------------------------------------------------------------
def load_classifica_from_firebase(group_id: int) -> dict:
    """
    Legge la classifica per il group_id dal nodo /classifiche/{group_id}.
    Restituisce un dict {utente: punteggio, ...} oppure {} se non esiste.
    """
    try:
        ref = db.reference(f"classifiche/{group_id}")
        data = ref.get()
        return data if isinstance(data, dict) else {}
    except exceptions.FirebaseError as e:
        logger.error(f"Firebase load_classifica error: {e}")
        return {}

def save_classifica_to_firebase(group_id: int, scores: dict) -> None:
    """
    Salva (o sovrascrive) il dict scores in /classifiche/{group_id}.
    """
    try:
        # Scores deve essere un dict piatto { "user_id": punti, ... }
        ref = db.reference(f"classifiche/{group_id}")
        ref.set(scores or {})
        logger.info(f"Classifica per group_id={group_id} salvata correttamente.")
    except exceptions.FirebaseError as e:
        logger.error(f"Firebase save_classifica error: {e}")


# --------------------------------------------------------------------
# 3. IMPOSTAZIONI DI GRUPPO
# --------------------------------------------------------------------
def load_all_group_settings_from_firebase() -> dict:
    try:
        ref = db.reference("group_settings")
        data = ref.get()
        return data if isinstance(data, dict) else {}
    except exceptions.FirebaseError as e:
        logger.error(f"Firebase load_all_group_settings error: {e}")
        return {}

def load_group_settings_from_firebase(group_id: int) -> dict:
    try:
        ref = db.reference(f"group_settings/{group_id}")
        data = ref.get()
        return data if isinstance(data, dict) else {}
    except exceptions.FirebaseError as e:
        logger.error(f"Firebase load_group_settings error: {e}")
        return {}

def save_group_settings_to_firebase(group_id: int, settings: dict) -> None:
    try:
        ref = db.reference(f"group_settings/{group_id}")
        ref.set(settings or {})
        logger.info(f"Group settings per group_id={group_id} salvate correttamente.")
    except exceptions.FirebaseError as e:
        logger.error(f"Firebase save_group_settings error: {e}")

def save_all_group_settings_to_firebase(all_settings: dict) -> None:
    try:
        ref = db.reference("group_settings")
        ref.set(all_settings or {})
        logger.info("Tutte le impostazioni di gruppo salvate correttamente.")
    except exceptions.FirebaseError as e:
        logger.error(f"Firebase save_all_group_settings error: {e}")


# --------------------------------------------------------------------
# 4. LOG DELLE INTERAZIONI
# --------------------------------------------------------------------
def add_log_entry(group_id: int, entry: dict) -> None:
    try:
        ref = db.reference(f"logs/{group_id}")
        new_ref = ref.push()
        new_ref.set(entry)
        logger.info(f"Log entry aggiunta per group_id={group_id}: {entry}")
    except exceptions.FirebaseError as e:
        logger.error(f"Firebase add_log_entry error: {e}")
