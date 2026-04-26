import random
from telegram.ext import ContextTypes
import logging

logger = logging.getLogger(__name__)

# Struttura dati semplice: numero -> lista di file_id sticker
# I file_id sono placeholder - vanno sostituiti con ID reali di sticker Telegram
ICONIC_STICKERS = {
    10: ["CAACAgQAAxkBAAFIB9tp7IBc_6R6Dp1rk4svD2ryUFkuAgACnh4AAq9rWFNKE1MVMRPPJTsE", #Ronaldinho
        "CAACAgQAAxkBAAFIB9xp7IBckeWsmBZ0nVR015vj1N1wvgACoR4AAq9rWFNaUgy-rjlghzsE", #Maradona
        "CAACAgQAAxkBAAFIB91p7IBc54TxlaxHQO_xqkC52FRQKQACox4AAq9rWFMSGHipVtzMfTsE", #Baggio
        "CAACAgQAAxkBAAFIB95p7IBch5pjxEYVFrCqaqk9_GRkhwACpB4AAq9rWFMlSTEtYThMfzsE", #Morfeo
        "CAACAgQAAxkBAAFIB99p7IBcRKuEJRC3BovTvPvOfhC5FgACpR4AAq9rWFPYVVpXtHy-vTsE", #AnsuFati
        "CAACAgQAAxkBAAFIB-Bp7IBcuuYcawgOTmYCKF-4nU9v5QACph4AAq9rWFOtUsyjySy3qzsE", #Leao
        "CAACAgQAAxkBAAFIB-Fp7IBcPFENEK5UN_4bFYQgCrrP9AACpx4AAq9rWFPrOQcJYgxyYTsE", #NicoPaz
        "CAACAgQAAxkBAAFIB-Jp7IBc-wLZ0CjWjXFDdX4Qj32gewACqR4AAq9rWFP0sDzkWt3j5TsE", #Nakamura
        "CAACAgQAAxkBAAFIB-Np7IBckyUmYIIMIMWNhCRTYtGTugACqh4AAq9rWFMx_-boPzniPzsE", #Vannucchi
        "CAACAgQAAxkBAAFIB-Rp7IBcKkencNstxiDhETdoczC3fwACqx4AAq9rWFP6owcCdk56DjsE", #Nakata
        "CAACAgQAAxkBAAFIB-Vp7IBchs947iqER7zewL6YhW9_ZwACrB4AAq9rWFNi4GCLSASSVDsE", #Ronaldo
        "CAACAgQAAxkBAAFIB-Zp7IBcsNwRxgNJDDaMz6ZRp_lRZAACrR4AAq9rWFNExqLTEN3oezsE", #Lautaro
        "CAACAgQAAxkBAAFIB-dp7IBcI4ASza0z15XoI81s3eQ4CgACrh4AAq9rWFMdGJ30S67zIjsE", #Neymar
        "CAACAgQAAxkBAAFIB-hp7IBcvzLSAAEO1iOOVT632jQu4rUAAq8eAAKva1hTWRA54sDShdA7BA", #Lupatelli
        "CAACAgQAAxkBAAFIB-lp7IBcc3Rv7o8cQMT1TOJgjzna1QACsB4AAq9rWFMGL0teuXDN1DsE", #Totti
        "CAACAgQAAxkBAAFIB-pp7IBcIczq9STcWK3_9Hm6_GHBgQACsh4AAq9rWFMZKBr6YzuNZzsE", #Mbappe
        "CAACAgQAAxkBAAFIB-tp7IBcbnaVVuFUZ2vCKd6jy9KlLQACsx4AAq9rWFMatniDYvwX7zsE", #Laporte
        "CAACAgQAAxkBAAFIB-xp7IBc-8lwh5mQ7EDnVvGnZOpuBwACth4AAq9rWFNFzc1ru4CP3zsE", #Eusebio
        "CAACAgQAAxkBAAFIB-1p7IBc_rY8gwsSeikGWxUPi4vstwACtx4AAq9rWFNwxcYkwv2GdDsE", #Zico
        "CAACAgQAAxkBAAFIB-5p7IBccyTRteP2AVzFfg8JQhpPCQACuB4AAq9rWFOLZLp2sHV0hDsE", #Pele
        "CAACAgQAAxkBAAFIB-9p7IBcGfuOKGm2Rahz41-Ty0LrXQACuR4AAq9rWFMSazZULastIDsE", #Osvaldo
        "CAACAgQAAxkBAAFIB_Bp7IBcqtG9AygYtksoCPWnGayJTQACvR4AAq9rWFPIJvgC2r3mrDsE", #Del Piero
        ],
    7: ["CAACAgQAAxkBAAFIG-Fp7dmEMYNV2DJPb0XJ8qmMJElY1gACtB4AAq9rWFNJUVrjIbLJhzsE" #Nani
    ],
    5: ["CAACAgQAAxkBAAFIG-Np7dmypCau-fuoShY9-mUKUYjhqwACtR4AAq9rWFMCy-_ZLLZwwjsE" #Sensi
        ]
}

# Probabilità di attivazione dell'evento (0-100)
ICONIC_PROBABILITY = 100  # 100% di probabilità


async def trigger_iconic_sticker_event(
    chat_id: int,
    thread_id: int,
    number_drawn: int,
    tema: str,
    context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """
    Invia uno sticker iconico se il numero corrisponde.
    
    Args:
        chat_id: ID della chat dove inviare lo sticker
        thread_id: ID del thread (per i gruppi con topic)
        number_drawn: Numero estratto
        tema: Tema attivo
        context: Contesto del bot
        
    Returns:
        True se lo sticker è stato inviato, False altrimenti
    """
    
    # Attiva solo nel tema "calcio"
    if tema != "calcio":
        return False
    
    # Verifica se il numero è tra quelli iconici
    if number_drawn not in ICONIC_STICKERS:
        return False
    
    # Applica la probabilità
    if random.randint(1, 100) > ICONIC_PROBABILITY:
        return False
    
    try:
        # Seleziona uno sticker casuale
        stickers_list = ICONIC_STICKERS[number_drawn]
        selected_sticker = random.choice(stickers_list)
        
        # Invia lo sticker
        await context.bot.send_sticker(
            chat_id=chat_id,
            sticker=selected_sticker,
            message_thread_id=thread_id
        )
        
        return True
    
    except Exception as e:
        logger.warning(
            f"[iconic_stickers] Errore nell'invio dello sticker per numero {number_drawn} "
            f"in chat {chat_id}: {e}"
        )
        # Se lo sticker fallisce, il gioco continua normalmente
        return False
