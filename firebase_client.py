import os
import json
import logging
import tempfile
import time
from functools import wraps
import firebase_admin
from firebase_admin import credentials, db, exceptions

# Logger setup
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def check_firebase_initialized():
    if not firebase_admin._apps:
        raise RuntimeError("Firebase non inizializzato. Controlla credenziali.")

def _masked_path(p: str) -> str:
    # Non rivelare il path completo nei log: mostra solo il nome file
    try:
        return os.path.basename(p)
    except Exception:
        return "[service-account]"


# Legge l'env e ricava un path al file di credenziali
raw_env = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
if not raw_env:
    raise RuntimeError(
        "Devi impostare GOOGLE_APPLICATION_CREDENTIALS con il percorso o il contenuto JSON del Service Account."
    )

SERVICE_ACCOUNT_PATH = None
_temp_sa_file = None

raw_env_stripped = raw_env.strip()
if os.path.isfile(raw_env_stripped):
    SERVICE_ACCOUNT_PATH = raw_env_stripped
else:
    # Proviamo a interpretarlo come JSON (contenuto direttamente nella env)
    try:
        sa_content = json.loads(raw_env_stripped)
        # Scriviamo in file temporaneo con permessi ristretti
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(sa_content, tf)
        tf.flush()
        tf.close()
        _temp_sa_file = tf.name
        SERVICE_ACCOUNT_PATH = sa_content
    except json.JSONDecodeError:
        # Non è né un file né un JSON valido
        raise RuntimeError(
            "La variabile GOOGLE_APPLICATION_CREDENTIALS non è valida: fornisci un percorso al file JSON o il contenuto JSON stesso."
        )

# Preleva URL database e valida generica (ma senza esporre valori sensibili nei log)
DATABASE_URL = os.getenv("FIREBASE_DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "Devi impostare FIREBASE_DATABASE_URL con l'URL del tuo Realtime Database Firebase."
    )

if not (DATABASE_URL.startswith("https://") and ("firebaseio" in DATABASE_URL or "firebasedatabase" in DATABASE_URL)):
    logger.warning("FIREBASE_DATABASE_URL sembra non essere un URL Realtime Database standard; controlla la configurazione.")

# Inizializza Firebase Admin usando il path al file di service account
if not firebase_admin._apps:
    try:
        cred = credentials.Certificate
        firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})
        logger.info("✅ Firebase Admin inizializzato correttamente.")
    except Exception as e:
        logger.error("❌ Errore inizializzazione Firebase Admin (vedere dettaglio eccezione)")
        raise

# --------------------------------------------------------------------
# 2. CLASSIFICA (punti)
# --------------------------------------------------------------------
def _retry_on_firebase_error(max_retries: int = 3, base_delay: float = 0.5, backoff: float = 2.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions.FirebaseError as e:
                    attempt += 1
                    if attempt > max_retries:
                        logger.error(f"Firebase error after {max_retries} retries: {e}")
                        raise
                    delay = base_delay * (backoff ** (attempt - 1))
                    logger.warning(f"Firebase error, retrying in {delay:.1f}s (attempt {attempt}/{max_retries})")
                    time.sleep(delay)
        return wrapper
    return decorator


@_retry_on_firebase_error()
def load_classifica_from_firebase(group_id: int) -> dict:
    check_firebase_initialized()
    ref = db.reference(f"classifiche/{group_id}")
    data = ref.get()
    return data if isinstance(data, dict) else {}


@_retry_on_firebase_error()
def save_classifica_to_firebase(group_id: int, scores: dict) -> None:
    check_firebase_initialized()
    ref = db.reference(f"classifiche/{group_id}")
    ref.set(scores or {})
    logger.info(f"Classifica per group_id={group_id} salvata correttamente.")

# --------------------------------------------------------------------
# 3. IMPOSTAZIONI DI GRUPPO
# --------------------------------------------------------------------
@_retry_on_firebase_error()
def load_all_group_settings_from_firebase() -> dict:
    check_firebase_initialized()
    ref = db.reference("group_settings")
    data = ref.get()
    return data if isinstance(data, dict) else {}


@_retry_on_firebase_error()
def load_group_settings_from_firebase(group_id: int) -> dict:
    check_firebase_initialized()
    ref = db.reference(f"group_settings/{group_id}")
    data = ref.get()
    return data if isinstance(data, dict) else {}


@_retry_on_firebase_error()
def save_group_settings_to_firebase(group_id: int, settings: dict) -> None:
    check_firebase_initialized()
    ref = db.reference(f"group_settings/{group_id}")
    ref.set(settings or {})
    logger.info(f"Group settings per group_id={group_id} salvate correttamente.")


@_retry_on_firebase_error()
def save_all_group_settings_to_firebase(all_settings: dict) -> None:
    check_firebase_initialized()
    ref = db.reference("group_settings")
    ref.set(all_settings or {})
    logger.info("Tutte le impostazioni di gruppo salvate correttamente.")

# --------------------------------------------------------------------
# 4. LOG DELLE INTERAZIONI
# --------------------------------------------------------------------
@_retry_on_firebase_error()
def add_log_entry(group_id: int, entry: dict) -> None:
    check_firebase_initialized()
    ref = db.reference(f"logs/{group_id}")
    new_ref = ref.push()
    new_ref.set(entry)
    # Non loggare l'intero entry payload per non esporre dati sensibili
    logger.info(f"Log entry aggiunta per group_id={group_id}") 
