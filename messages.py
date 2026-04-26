from asyncio.log import logger
from collections import defaultdict
from telegram.helpers import escape_markdown

THEME_BONUS_NAMES = {
    "normale": {
        "bonus_110_name": "Bonus 110",
        "malus_666_name": "Malus 666",
        "bonus_104_name": "Bonus 104",
        "malus_404_name": "Malus 404",
        "tombolino_name": "Tombolino",
    },
    "harry_potter": {
        "bonus_110_name": "Salvio Hexia",
        "malus_666_name": "Oppugno",
        "bonus_104_name": "Protego",
        "malus_404_name": "Depulso",
        "tombolino_name": "Tombolino Magico",
    },
    "marvel": {
        "bonus_110_name": "Scudo di Captain America",
        "malus_666_name": "Gemme del Potere",
        "bonus_104_name": "Martello di Thor",
        "malus_404_name": "Multiverso",
        "tombolino_name": "Tombolino Marvel",
    },
    "barbie": {
        "bonus_110_name": "Barbie Icon Moment",
        "malus_666_name": "Fashion Disaster",
        "bonus_104_name": "Glow Up Glam",
        "malus_404_name": "Closet Chaos",
        "tombolino_name": "Barbie Rising Star",
    },
    "calcio": {
        "bonus_110_name": "Gol spettacolare",
        "malus_666_name": "Autogol clamoroso",
        "bonus_104_name": "Parata miracolosa",
        "malus_404_name": "Fuorigioco ingenuo",
        "tombolino_name": "Secondo classificato"
    }
}

def get_feature_name(feature_key: str, tema: str = 'normale') -> str:
    mapping = {
        '110': 'bonus_110_name',
        '104': 'bonus_104_name',
        '666': 'malus_666_name',
        '404': 'malus_404_name',
        'Tombolino': 'tombolino_name'
    }
    theme_names = THEME_BONUS_NAMES.get(tema, THEME_BONUS_NAMES.get('normale', {}))
    return theme_names.get(mapping.get(feature_key, feature_key), mapping.get(feature_key, feature_key))
def get_testo_tematizzato(chiave: str, tema: str = "normale", **kwargs) -> str:
    testi = {
        "normale": {
            "solo_admin": "🚫 Solo gli amministratori possono avviare la partita.",
            "annuncio_partita":(
                        "*🆕 Partita di tombola cominciata\\!*\n\n"
                        "_🔽 Premi 'Unisciti' per entrare, ma prima accertati di aver avviato il bot_\n\n"
                        "_🔜 Moderatore quando sei pronto avvia la partita con il comando /estrai  se poi vorrai interromperla usa /stop "
                        "e che vinca il migliore\\! Per qualunque dubbio usate /regolo per ricevere le regole_"
                        ),
            "join_non_autorizzato": "🚫 Non puoi unirti alla partita.",
            "non_membro_gruppo": "🚫 Non sei membro del gruppo.",
            "partita_non_attiva": "🚫 Non ci sono partite in corso in questo gruppo.",
            "partita_iniziata": "🚫 La partita è già iniziata, non puoi unirti ora. Aspetta la prossima partita!",
            "unito_partita": "*🏁 Sei ufficialmente nella partita del gruppo {group_text}, ecco la tua cartella\\:*\n\n{escaped_cartella}",
            "non_unito_ora": "🔜 Non puoi unirti alla partita ora.",
            "benvenuto": (
                        "*Benvenuto [{escaped_nickname}](https://t.me/{escaped_username})*\\!\n\n"
                        "Questo è il bot ufficiale di [Monopoly Go Contest e Regali]({group_link}), "
                        "aggiungilo liberamente nel tuo gruppo e gioca a Tombola con i tuoi amici\\. "
                        "Utilizzando il comando /impostami potrai gestire al meglio le impostazioni, con /trombola invece darai inizio alla partita e che vinca il migliore, o meglio, il più fortunato\\.\n\n"
                        "_Buona Trombolata_"
                        ),
            
            "gia_unito":"Sei già iscritto alla partita!",
            "annuncio_unione":"*_👤 {username} si è unito alla partita\\!_*",
            "numero_estratto":"Numero estratto!",
            "partita_interrotta":"Partita interrotta!",
            "errore_invio_cartella":"Non riesco a inviarti la cartella in privato. Assicurati di aver avviato il bot.",
            "non_in_partita":"⛔️ Non sei in partita!",
            "numero_estratto_annuncio":"_📤 È stato estratto il numero **{current_number_val:02}**_",
            "stop_solo_admin": "🚫 Solo gli amministratori possono interrompere il gioco.",
            "messaggio_stop": "*⚠️ Il gioco è stato interrotto*",
            "messaggio_cartella": "*🏁 Sei ufficialmente nella partita del gruppo {group_text}, ecco la tua cartella\\:*\n\n{escaped_cartella}",
            "mostra_cartella_alert":"La tua cartella:\n\n{formatted_cartella}",
            "estrazione_solo_admin":"🚫 Solo gli amministratori possono estrarre i numeri manualmente.",
            "nessuna_partita_attiva_per_estrazione":"🚫 Assicurati di aver iniziato una partita prima.",
            "numero_avuto_dm":"*🔒 Avevi il numero {number_drawn:02}\\!*\n\n{escaped_cart_text}",
            "tutti_numeri_estratti":"⚠️ Tutti i numeri sono stati estratti. Il gioco è finito!",
            "bonus_110":"*🧑‍🎓 {bonus_110_name} estratto\\!*\n\n_🆒 @{user_affected_escaped_name} ha guadagnato {punti_val} punti_",
            "malus_666":"*🛐 {malus_666_name} estratto\\!*\n\n_🆒 @{user_affected_escaped_name} ha perso {punti_val} punti_",
            "bonus_104":"*♿️ {bonus_104_name} estratto\\!*\n\n_🆒 @{user_affected_escaped_name} ha guadagnato {punti_val} punti_",
            "malus_404":"*🆘 {malus_404_name} estratto\\!*\n\n_🆒 @{user_affected_escaped_name} ha perso {punti_val} punti_",
            "partita_interrotta_no_punti":"⚠️ Punti non conteggiati perché la partita è stata interrotta.",
            "nessuna_classifica":"*📊 Nessuna classifica disponibile\\.*",
            "classifica_finale":"🏆 Classifica finale:\n\n" + "{lines}",
            "reset_classifica_solo_admin":"🚫 Solo gli amministratori possono resettare la classifica.",
            "messaggio_reset_classifica":"_🚾 Complimenti hai scartato tutti i punteggi\\._",
            "tombola_prima": "_🏆 @{escaped_username} ha fatto tombola{extra}_",
            "tombolino": "_🏆 @{escaped_username} ha fatto tombolino\\!_",
            "regole_introduzione":(
                        "*_ℹ️ REGOLAMENTO\\:_*\n\n"
                        "_👋 Benvenuto nel regolamento, qui potrai navigare grazie ai bottoni tra le varie sezioni_ "
                        "_per scoprire ogni angolo di questo bot\\._\n\n"
                        "_✍️ Per qualunque informazione rimaniamo a disposizione su @AssistenzaTombola2\\_Bot\\._ "
                        "_Non esitare a contattarci se ci sono problemi\\._\n\n"
                    ),
            "errore_invio_regole_privato": (
                        "_📭 @{escaped_username} non riesco a inviarti le regole in privato\\._\n"
                        "*Vai su @Tombola2_Bot e premi 'Avvia'*" 
                    ),
            "messaggio_invio_regole_privato":"_📬 @{escaped_username} ti ho inviato le regole in privato\\._",
            "regole_punteggi":(
                        "*🏆 Punteggi\\:*\n\n"
                        "_🔢 Il cuore della classifica risiede qui, ogni gruppo ha la possibilità di personalizzare i punteggi tramite il comando "
                        "apposito che vedi spiegato nella sezione di riferimento, ma questi sono quelli attualmente in uso nel gruppo {header}\\:_\n\n"
                        "1️⃣ *AMBO* vale {premi_ambo} punti\n"
                        "2️⃣ *TERNO* vale {premi_terno} punti\n"
                        "3️⃣ *QUATERNA* vale {premi_quaterna} punti\n"
                        "4️⃣ *CINQUINA* vale {premi_cinquina} punti\n"
                        "5️⃣ *TOMBOLA* vale {premi_tombola} punti\n\n"
                        "_🔽 Inoltre, se attivo nel vostro gruppo\\:_\n\n"
                        "6️⃣ *TOMBOLINO* vale {premi_tombolino} punti\n"
                    ),
                    
            "regole_comandi": (
                "*🌐 Comandi\\:*\n\n"
                "_🛃 Qui trovi fondamentalmente tutti i comandi del bot, alcuni utilizzabili solo dai moderatori altri accessibili a tutti, "
                "vediamone una rapida spiegazione\\:_\n\n"
                "*1️⃣ /trombola*\n"
                "_Il comando principale, di default lo possono usare solo i moderatori e ti permette di avviare una partita\\._\n"
                "*2️⃣ /impostami*\n"
                "_Con questo comando puoi decidere come e cosa cambiare all'interno del gruppo, non voglio dilungarmi troppo, provalo nel gruppo, "
                "se sei moderatore, e sperimenta tu stesso\\._\n"
                "*3️⃣ /classifiga*\n"
                "_No non è un errore di battitura, si chiama davvero così il comando, intuibilmente ti permette di visualizzare la classifica del "
                "gruppo, ovviamente se sei moderatore\\._\n"
                "*4️⃣ /azzera*\n"
                "_Anche per questo di default devi essere un moderatore, anche perchè resetta totalmente la classifica del gruppo, maneggiare con cura\\._\n"
                "*5️⃣ /stop*\n"
                "_Se per qualunque motivo \\(ad esempio perchè non hai messo nemmeno un numero\\) volessi interrompere la partita, beh con questo "
                "comando puoi farlo, ah se sei moderatore\\._\n"
                "*6️⃣ /estrai*\n"
                "_Che partita di tombola sarebbe se i numeri non venissero estratti, d'altronde c'è da fare solo questo, quindi moderatore sta a te, "
                "usa questo comando e dai inizio alla partita e che vinca il migliore\\._\n"
                "*7️⃣ /trombolatori*\n"
                "_Se per caso ti interessa sapere quante persone stanno tromb\\.\\.\\. volevo dire partecipando alla partita usa questo comando, "
                "ah e questo possono usarlo tutti\\._"
            ),
            "regole_unirsi": (
                "*🆒 Partecipare\\:*\n\n"
                "_🆗 Ora, probabilmente ti starai chiedendo, bello tutto eh, ma come faccio a partecipare alla partita? Nulla di più semplice, "
                "quando un moderatore avrà iniziato una partita col comando /trombola \\(non usarlo qui non funzionerà\\) comparirà un bottone come "
                "questo '➕ Unisciti' cliccaci sopra e riceverai la cartella in questa chat e il gioco è fatto\\. Ora non ti resta che sperare che "
                "escano i tuoi numeri\\._"
            ),
            "regole_estrazione": (
                "*🔁 Estrazione\\:*\n\n"
                "_🔀 Come nella più classica delle tombole i numeri vanno da 1 a 90, una volta estratto il primo numero voi non dovrete fare niente "
                "se non accertarvi dei numeri che escono e che vi vengono in automatico segnati dal bot\\. Il vero lavoro ce l'ha il moderatore che deve "
                "estrarre i numeri ma se va a darsi un'occhiata alle impostazioni anche per lui sarà una passeggiata\\._"
            ),
            "regole_bonus_malus": (
                "*☯️ Bonus/Malus\\:*\n\n"
                "_🏧 Se non vi piace la monotonia e volete rendere piu interessante le classifica, allora dovete assolutamente leggervi cosa fanno "
                "questi bonus/malus e correre ad avvisare il vostro admin di fiducia di attivarli\\:_\n"
                "_🔽 Ciascuno di questi numeri è stato aggiunto al sacchetto ed una volta estratto potrà aggiungervi o togliervi  un numero "
                "randomico di punti \\(da 1 a 49\\)\\. No non vi compariranno in cartella, il fortunato o sfortunato verrà scelto a caso tra tutti "
                "quelli in partita\\._\n\n"
                "*1️⃣ {bonus_104_name}*\n"
                "_Spero non siate per il politically correct, nel caso ci dispiace \\(non è vero\\)\\._\n\n"
                "*2️⃣ {malus_666_name}*\n"
                "_Se siete fan sfegatati di Dio vi consiglio di disattivarlo dalle impostazioni\\._\n\n"
                "*3️⃣ {bonus_110_name}*\n"
                "_Un po' come per la laurea, vi diamo la lode ma il valore di essa non dipende da noi\\. O se preferite come lo stato, vi diamo il "
                "110\\% di quanto avete speso\\._\n\n"
                "*2️⃣ {malus_404_name}*\n"
                "_Error 404 Not Found\\. Impossibile caricare il testo del Malus\\._\n\n"
                "_⏸️ Pensavate davvero avessimo finito qui\\? Pff non ci conoscete bene, per gli amanti della tombola abbiamo anche introdotto "
                "un extra\\:_\n"
                "*5️⃣ Tombolino*\n"
                "_Spero lo conosciate nel caso ve lo spiego brevemente\\. Se attivato dalle impostazioni un altro utente avrà la possibilità di "
                "fare tombola\\. Fondamentalmente viene premiato il secondo giocatore a farla, ma ovviamente non con gli stessi punti della prima\\._"
            ),
            "regole_punteggi":(
                        "*🏆 Punteggi\\:*\n\n"
                        "_🔢 Il cuore della classifica risiede qui, ogni gruppo ha la possibilità di personalizzare i punteggi tramite il comando apposito che vedi spiegato nella sezione "
                        "di riferimento, ma questi sono quelli attualmente in uso nel gruppo {header}\\:_\n\n"
                        "1️⃣ *AMBO* vale {premi_ambo} punti\n"
                        "2️⃣ *TERNO* vale {premi_terno} punti\n"
                        "3️⃣ *QUATERNA* vale {premi_quaterna} punti\n"
                        "4️⃣ *CINQUINA* vale {premi_cinquina} punti\n"
                        "5️⃣ *TOMBOLA* vale {premi_tombola} punti\n\n"
                        "_🔽 Inoltre, se attivo nel vostro gruppo\\:_\n\n"
                        "6️⃣ *TOMBOLINO* vale {premi_tombolino} punti\n"
            ),
            "impostazioni_solo_admin": "🚫 Solo gli amministratori possono modificare le impostazioni.",
            "pannello_controllo": "*📱 Pannello di Controllo*\n\n_📲 Scegli quale sezione vuoi configurare_",
            "descrizione_estrazione": (
                "_🆗 Saggia scelta cominciare da qui, puoi decidere se rendere l'estrazione automatica, "
                "con un numero nuovo senza dover premere nulla, oppure se proprio ti piace cliccare i bottoni, "
                "tenerla manuale\\:_"
            ),
            "errore_aggiornamento_menu":"Errore interno durante l'aggiornamento. Riprova.",
            "descrizione_admin": (
                "_🆗 Ah quindi vuoi permettere a tutti di poter toccare i comandi\\? E va bene, a tuo rischio e pericolo\\._ "
                "Premi no se vuoi che tutti, non solo gli admin, possano avviare, estrarre ed interrompere\\._ "
                "Premi si se vuoi che il potere rimanga nelle mani di pochi\\:_"
            ),
            "descrizione_premi":(
                "_🆗 Eccoci, dove avviene la magia, il cuore di tutto\\: *i punteggi*\\. "
                "Dai ad ogni premio il punteggio che ritieni corretto e lascia che l'estrazione faccia il suo corso\\:_"
            ),
            "descrizione_bonus_malus":(
                "_🆗 Eccoci, nella sezione che ti permette di mettere un po' di pepe alla tua partita, attiva o disattiva i bonus/malus singolarmente "
                "e rendi la classifica altalenante e ricca di emozioni\\. Se vuoi maggiori informazioni digita /regolo per riceverle in privato\\._"
            ),
            "descrizione_elimina_numeri":(
                "_🆗 Se vuoi fare un po' di pulizia di messaggi sei nel posto giusto, qui potrai abilitare il bot ad eliminare i messaggi dei numeri "
                "estratti, questi verranno cancellati al termine della partita\\. Premi 'si' se vuoi che vengano cancellati, se preferisci che rimangano "
                "seleziona 'no'_"
            ),
            "descrizione_tema":(
                "_🆗 Eccoci nella sezione che più personalizza e caratterizza ogni gruppo\\: i temi✨\\.\n"
                "Qui avrai la possibilità di decidere quale tema caratterizzerà la tombola\\. Mi raccomando, scegli saggiamente\\:_"
            ),
            "nessuna_partita_attiva_per_giocatori":"🚫 Non ci sono partite in corso al momento.",
            "nessun_giocatore_unito":"*🤷‍♂️ Nessuno si è unito alla partita ancora\\!*",
            "numero_giocatori_attivi":"*👥 Utenti in partita\\: {count}*",
            "nessuna_classifica_disponibile":"*📊 Nessuna classifica disponibile\\.*",
            "testo_classifica": "🏆 Classifica finale:\n\n" + "{lines}",
            "vincitore_ambo": "_🏆 @{escaped} ha fatto ambo\\!_",
            "vincitore_terno": "_🏆 @{escaped} ha fatto terno\\!_",
            "vincitore_quaterna": "_🏆 @{escaped} ha fatto quaterna\\!_",
            "vincitore_cinquina": "_🏆 @{escaped} ha fatto cinquina\\!_",
        },
        "harry_potter": {
            "solo_admin": "🚫 Solo i Capitani di Squadra possono dare il via al match.",
            "annuncio_partita": (
                "*⚡ Partita di Quidditch iniziata\\!*\n\n"
                "_🧹 Afferra la tua Nimbus 2000 e unisciti alla sfida\\! Attenzione al Boccino d'Oro nascosto tra gli incantesimi_\n\n"
                "_🧙 Capitano, quando sei pronto a rivelare i numeri con /estrai\\! Per interrompere il match usa /stop\\. "
                "Che vinca la Casa più meritevole\\! Per le regole complete, consulta il Manuale del Giocatore con /regolo\\._"
            ),
            "join_non_autorizzato": "🚫 La tua bacchetta non è registrata negli archivi di Hogwarts!",
            "non_membro_gruppo": "🚫 Non sei iscritto al Registro degli Studenti di questa scuola di magia.",
            "partita_non_attiva": "🚫 La bacheca del Quidditch non mostra alcun match in programma.",
            "partita_iniziata": "🚫 Le scope sono già in volo! Dovrai attendere il prossimo torneo tra le Case.",
            "unito_partita": "*🧹 Sei ufficialmente in sella alla tua scopa per la Casa {house}\\! Ecco la tua Mappa Incantata\\:*\n\n{escaped_cartella}\n\n",
            "non_unito_ora": "🔜 Il Portiere ha chiuso le porte dello spogliatoio\\!",
            "benvenuto": (
                "*Benvenuto, {escaped_nickname}\\!*\n\n"
                "Questo è il Portolano Ufficiale delle Partite Magiche di Hogwarts, "
                "dove le Case si sfidano a colpi di incantesimi e strategie\\. Usa /impostami per configurare la tua squadra, "
                "poi lancia /trombola per dare inizio allo scontro aereo\\! _Ricorda\\: chi cattura il Boccino vince per la sua Casa\\.\\.\\._"
            ),
            "gia_unito": "🧹 Sei già in volo\\! La tua scopa non può esistere in due punti contemporaneamente\\.",
            "annuncio_smistamento": "*_🎩 {escaped_username} è salito sulla sua Nimbus 2000 per la casa {house}\\!_*",
            "numero_estratto": "✨ *REVELIO NUMERUS!*",
            "partita_interrotta": "*🌩️ MATCH INTERROTTO DAL PRESIDE!*",
            "errore_invio_cartella": "🦉 Il tuo Gufo non è riuscito a consegnare la Mappa Incantata. Hai stretto il Patto Magico con il bot?",
            "non_in_partita": "⛔️ La tua scopa è ancora nel deposito! Unisciti al match prima di giocare.",
            "numero_estratto_annuncio": "_✨ Revelio\\! **{current_number_val:02}** appare tra le nuvole\\!_",
            "stop_solo_admin": "🚫 Solo i Capitani possono invocare l'incantesimo *'Finite Incantatem'* per fermare il match.",
            "messaggio_stop": "*☁️ Tutte le scope atterrano d'urgenza\\. Il match è sospeso\\.*",
            "messaggio_cartella": "*🧹 Benvenuto in campo per {group_text}, Cavaliere di {house}\\! Ecco la tua Mappa Incantata\\:*\n\n{escaped_cartella}\n\n",
            "mostra_cartella_alert": "✨ La tua Mappa Incantata:\n\n{formatted_cartella}",
            "estrazione_solo_admin": "🚫 Solo i Capitani possono pronunciare *'Numerus Revelio'*.",
            "nessuna_partita_attiva_per_estrazione": "🚫 Il Campo da Quidditch è vuoto! Avvia un match prima di rivelare numeri.",
            "numero_avuto_dm": "*⚡ La tua bacchetta vibra\\! Appare il numero {number_drawn:02} nella tua Mappa Incantata\\!*\n\n{escaped_cart_text}",
            "tutti_numeri_estratti": "⚡ *TUTTI GLI INCANTESIMI SONO STATI LANCIATI!* Il Boccino è stato catturato - match concluso!",
            # Bonus/Malus trasformati in effetti magici
            "bonus_110": "*🛡️ {bonus_110_name}\\!*\n\n_🤸 @{user_affected_escaped_name} ha deviato il bolide con un incantesimo di protezione\\! La magia ribalta la sfortuna in fortuna, e guadagna {punti_val} punti\\._",
            "malus_666": "*🪨 {malus_666_name}\\!*\n\n_☄️ @{user_affected_escaped_name} è stato colpito da un bolide lanciato come per magia oscura\\! L’incantesimo ha richiamato il Bolide dritto contro di lui\\.\\.\\. Perde {punti_val} punti\\._",
            "bonus_104": "*🛡️ {bonus_104_name}\\!*\n\n_⛔️ @{user_affected_escaped_name} alza uno scudo magico davanti agli Anelli\\! Il tiro avversario rimbalza via, difesa perfetta\\! Guadagna {punti_val} punti\\._",
            "malus_404": "*🌀 {malus_404_name}\\!*\n\n_☄️ Mentre @{user_affected_escaped_name} sorvegliava gli Anelli, un colpo di bacchetta ha respinto il Bludger\\.\\.\\. ma nella direzione sbagliata\\! Il Bolide è tornato indietro e lo ha centrato\\. Perde {punti_val} punti\\._",
            "partita_interrotta_no_punti": "⚡ *Nessun punto assegnato* Il match è stato interrotto dal Preside\\!",
            "nessuna_classifica": "*🏆 La Coppa delle Case è ancora chiusa nella bacheca\\!*",
            "classifica_finale": "*🏆 Classifica Coppa delle Case\\:*\n\n{lines}",
            "reset_classifica_solo_admin": "🚫 Solo il Preside può cancellare i punti con la Pergamena dei Ricordi Dimenticati.",
            "messaggio_reset_classifica": "_✨ Con un colpo di bacchetta, tutti i punti tornano a zero\\!_",
            # Sezione Regolamento
            "regole_introduzione": (
                "*_📚 MANUALE DEL GIOCATORE DI QUIDDITCH_*\n\n"
                "_📜 Questo antico tomo contiene tutte le regole del torneo\\. Naviga tra le sezioni con i pulsanti qui sotto\\._\n\n"
                "_🦉 Per chiarimenti, consulta il Gufo delle Regole su @AssistenzaTombola2\\_Bot\\._"
            ),
            "errore_invio_regole_privato": (
                "_🦉 @{escaped_username}, il tuo Gufo è stato fermato da un Dissennatore\\!_\n"
                "*Vai su @Tombola2_Bot e incanta il bot per riceverle\\.*"
            ),
            "messaggio_invio_regole_privato": "_📬 @{escaped_username}, il tuo Manuale del Giocatore è stato recapitato da un Gufo\\!_",
            "regole_punteggi": (
                "🏆✨ *Coppa delle Case di Hogwarts* ✨🏆\n\n"
                "_Ogni Casa ottiene punti grazie a imprese degne dei migliori maghi e streghe:_\n\n"
                "🪄 *AMBO* assegna {premi_ambo} punti per un Incantesimo Riuscito\n"
                "📜 *TERNO* assegna {premi_terno} punti per una Formula Antica\n"
                "⚡ *QUATERNA* assegna {premi_quaterna} punti per Magia Avanzata\n"
                "🔮 *CINQUINA* assegna {premi_cinquina} punti per un Sortilegio Magistrale\n"
                "🏆 *TOMBOLA* assegna {premi_tombola} punti per un’Impresa Degna di Hogwarts\n\n"
                "_⬇️ Se la Magia Antica è attiva nel Castello\\:_\n\n"
                "🧙‍♂️ *TOMBOLINO* assegna {premi_tombolino} punti bonus assegnati dai Professori\n"
            ),
            # Pannello di controllo trasformato in Ufficio del Preside
            "pannello_controllo": "*🏰 Ufficio del Preside*\n\n_📜 Seleziona quale incantesimo configurare\\:_",
            "descrizione_estrazione": (
                "_🦉 Saggio come Silente\\! Puoi scegliere se rivelare gli incantesimi automaticamente "
                "\\(le scope volano da sole\\) o manualmente \\(solo i Capitani controllano il gioco\\)\\:_"
            ),
            "descrizione_admin": (
                "_⚠️ Attenzione\\! Alcuni incantesimi sono riservati ai maghi più esperti\\. "
                "Con Sì, solo Professori e Capitani delle Case potranno usarli\\. "
                "Con No, tutti gli studenti di Hogwarts avranno accesso\\._"
            ),
            "descrizione_premi": (
                "_💎 Benvenuto nella Stanza dei Punteggi, dove ogni Casa lotta per la gloria\\! "
                "Assegna i punti come desideri per le imprese più eroiche\\:_"
            ),
            "descrizione_bonus_malus": (
                "_🔮 Attenzione\\! Questi incantesimi possono cambiare le sorti del match\\. "
                "Attivali per rendere la sfida epica come la battaglia di Hogwarts\\:_"
            ),
            "descrizione_elimina_numeri": (
                "_🧹 Vuoi che i ricordi di questo match svaniscano come polvere di Fumo\\? "
                "Abilita la cancellazione automatica dei messaggi alla fine del gioco\\._"
            ),
            "descrizione_tema": (
                "_✨ Ogni scuola di magia ha il suo stile\\! Scegli il tema che meglio rappresenta la tua Casa "
                "tra quelli disponibili nel Libro dei Misteri\\:_"
            ),
            "regole_comandi": (
                "*🪄 Comandi Magici\\:*\n\n"
                "_📚 Benvenuto nel Ministero della Trombola\\! Qui troverai tutti gli incantesimi segreti del tuo fedele elfo domestico\\-bot\\. "
                "Alcuni sono riservati ai Prescelti \\(leggi\\: i Professori\\), altri a tutti i maghi in gara\\. Ecco il tuo manuale del perfetto stregone\\:_\n\n"
                "*1️⃣ /trombola*\n"
                "_L’Incantesimo Fondamentale\\! Solo i Professori possono lanciarlo per convocare il Grande Gioco della Trombola\\. "
                "Attenzione\\: non è un semplice _Accio Cartella_, richiede autorità magica\\._\n"
                "*2️⃣ /impostami*\n"
                "_Un vero coltellino svizzero magico\\! Se sei un Professore, puoi modellare le regole del gioco come un vero Silente\\. "
                "Vuoi attivare i Doloris della Sfortuna\\? O forse la Benedizione di Grifondoro\\? Provalo e scopri i segreti nascosti\\._\n"
                "*3️⃣ /classifiga*\n"
                "_No, non è un guasto della Bacchetta Parlante\\! Si chiama proprio così\\: la Classifiga\\. "
                "Mostra la classifica magica del gruppo\\. Solo chi indossa il Cappello Parlante \\(ovvero i Professori\\) può consultarla\\._\n"
                "*4️⃣ /azzera*\n"
                "_Attenzione\\: questo è un _Obliviate_ di massa\\! Cancellare la classifica equivale a ricominciare da zero\\. "
                "Usalo solo se sei un Professore e hai il permesso di Albus in persona\\._\n"
                "*5️⃣ /stop*\n"
                "_Hai lanciato un _Confundo_ invece di un numero\\? La partita è fuori controllo\\? Nessun problema\\! "
                "Con questo incantesimo \\(riservato ai Professori\\) puoi fermare il caos prima che diventi un Babbano\\._\n"
                "*6️⃣ /estrai*\n"
                "_Il cuore pulsante della Trombola\\! Ogni numero estratto è come una piuma di fenice che danza nell'aria\\. "
                "Professori, è il vostro turno\\: estraete i numeri con dignità e che la Fortuna vi sia propizia\\._\n"
                "*7️⃣ /trombolatori*\n"
                "_Chi sono i coraggiosi maghi in gara\\? Usa questo incantesimo e lo scoprirai\\! "
                "Funziona per tutti\\: anche i Babbani curiosi possono sapere chi sta sfidando il destino\\._"
            ),

            "regole_unirsi": (
                "*🌀 Partecipare\\:*\n\n"
                "_🪄 Il Grande Gioco sta per iniziare\\! Ma come unirsi\\? Semplice\\: quando un Professore lancia /trombola, "
                "apparirà un pulsante magico\\: '➕ Unisciti al Torneo'\\. Cliccalo e, come per magia, riceverai la tua Cartella Incantata "
                "direttamente in questa chat\\. Ora non ti resta che sperare che la Fortuna ti sorrida più di quanto faccia Piton\\._"
            ),

            "regole_estrazione": (
                "*✨ Estrazione Magica\\:*\n\n"
                "_🔮 I numeri vanno da 1 a 90, proprio come i gradini della Torre di Astronomia\\. "
                "Non devi fare nulla\\: il tuo fedele elfo domestico \\(il bot\\) segnerà automaticamente i numeri usciti sulla tua cartella\\. "
                "Il vero lavoro spetta al Professore\\: lui deve estrarre i numeri con la bacchetta ben salda\\. "
                "Ma se ha già studiato il Manuale delle Impostazioni, sarà più facile di un _Wingardium Leviosa_\\._"
            ),
            "regole_bonus_malus": (
                "*⚡ Incantesimi Segreti\\: Bonus & Malus\\!*\n\n"
                "_🦉 Attenzione, maghi\\! Questa non è una partita qualsiasi\\: è un vero duello a mezz’aria, degno del Torneo Tremaghi\\. "
                "Abbiamo infuso il sacchetto dei numeri con magia imprevedibile\\: alcuni numeri, se estratti, scateneranno incantesimi casuali su un giocatore a caso\\!_\n"
                "_✨ Potresti guadagnare fino a 49 punti\\.\\.\\. o vederteli svanire come polvere di Fiducio\\! "
                "E ricorda\\: questi numeri *non compaiono sulla tua cartella*\\. La sorte li lancia come un Bludger invisibile\\.\\.\\. e colpisce chi "
                "meno se lo aspetta\\._\n\n"
                "*1️⃣ {bonus_104_name}*\n"
                "_Guarda\\! Il nostro Portiere ha alzato uno scudo magico proprio in tempo\\! "
                "Protego ha respinto il tiro avversario e la Casa guadagna punti preziosi\\. "
                "Speriamo tu non sia di Serpeverde\\.\\.\\. altrimenti il cuore ti si spezza come una bacchetta di salice\\._\n\n"
                "*2️⃣ {malus_666_name}*\n"
                "_Un’ombra si allunga sul campo, qualcuno ha sussurrato un incantesimo oscuro\\. "
                "Oppugno ha richiamato un Bolide dritto contro un giocatore\\! "
                "Se non chiami Voldemort per nome forse non succede, ma ormai è troppo tardi\\._\n\n"
                "*3️⃣ {bonus_110_name}*\n"
                "_Salvio Hexia\\! Un antico scudo ha deviato il Bolide maledetto e la magia si è ribaltata in fortuna\\! "
                "La tua Casa non solo si salva, ma guadagna il 110\\% di gloria \\— come la lode in una laurea di Alchimia\\. "
                "Il Ministero non lo ammetterà mai, ma oggi la burocrazia è dalla tua parte\\._\n\n"
                "*4️⃣ {malus_404_name}*\n"
                "_Depulso\\! Hai provato a respingere il Bludger ma la bacchetta ha avuto un’idea diversa\\. "
                "Errore 404\\: Giocatore non trovato\\! \\(Scherzo\\: sei ancora lì, ma pieno di lividi\\)\\. "
                "La Casa perde punti\\.\\.\\. e forse anche un po’ di dignità in volo\\._\n\n"
                "_🧙‍♂️ Ma aspetta\\! Il gioco non finisce qui… Per i veri campioni del cielo, c’è un premio segreto\\:_\n"
                "*5️⃣ Trombolino*\n"
                "_Il cugino dimenticato della Trombola\\! Se attivato, premia il *secondo mago* che completa la cartella\\. "
                "Non vince la Coppa Tremaghi… ma una borsa di Galeoni magici sì\\! Perché anche il secondo posto merita un applauso da Grifondoro\\._"
            ),
            "numero_giocatori_attivi": "*🧹 Giocatori in volo\\: {count}*",
            "testo_classifica": "*🏆 Classifica Coppa delle Case\\:*\n\n{lines}",
            "classifica_finale": "*🏆 Classifica Coppa delle Case\\:*\n\n{lines}",
            "nessuna_classifica_disponibile": "*📜 La Pergamena dei Punteggi è vuota\\!*",
            "vincitore_ambo": "_🏆 @{escaped} ha distrutto il Diario di Tom Riddle e fa ambo\\!_",
            "vincitore_terno": "_🏆 @{escaped} ha distrutto l'Anello di Marvoli Gaunt e fa terno\\!_",
            "vincitore_quaterna": "_🏆 @{escaped} ha distrutto il Medaglione Serpeverde e fa quaterna\\!_",
            "vincitore_cinquina": "_🏆 @{escaped}  ha distrutto la Coppa di Tassorosso e il Diadema di Corvonero e fa cinquina\\!_",
            "tombola_prima": "_🏆 @{escaped_username} distrugge tutti gli Horcrux guadagnandosi, oltre alla tombola, il duello finale con ColuiCheNonDeveEssereNominato{extra}_",
            "tombolino": "_🏆 @{escaped_username} credeva che uccidendo Nagini potesse uccidere finalmente Lord Voldemort, ma la pietra filosofale fa risorgere Harry e distrugge i sogni di gloria, ma almeno conquista il tombolino\\!_",
        },
        "marvel": {
            "solo_admin": "🔒 Accesso negato. Livello di sicurezza S.H.I.E.L.D. insufficiente.",
            "annuncio_partita": (
                "*🚨 INIZIATIVA AVENGERS ATTIVATA\\!*\n\n"
                "_🕸️ Premi 'Unisciti' per entrare in squadra, ma assicurati che J\\.A\\.R\\.V\\.I\\.S\\. \\(il bot\\) sia online_\n\n"
                "_🕶️ Direttore Fury, quando la squadra è schierata avvia la missione con /estrai\\. Se devi abbandonare usa /stop "
                "e che vinca il Vendicatore più forte\\! Usa /regolo per consultare il database\\._"
            ),
            "join_non_autorizzato": "🚧 Accesso bloccato dalla Damage Control.",
            "non_membro_gruppo": "🕵️ Non sei nei file dello S.H.I.E.L.D.",
            "partita_non_attiva": "💤 Nessuna minaccia livello Avengers rilevata.",
            "partita_iniziata": "⏳ Portale temporale chiuso. Missione già operativa, attendi la prossima variante!",
            "unito_partita": "*🦾 Armatura indossata nel settore {group_text}, ecco il tuo HUD tattico\\:*\n\n{escaped_cartella}",
            "non_unito_ora": "🚀 Il Quinjet è già decollato\\.",
            "benvenuto": (
                "*Benvenuto alla Stark Tower [{escaped_nickname}](https://t.me/{escaped_username})*\\!\n\n"
                "Questo è il protocollo ufficiale di [Monopoly Go Contest e Regali]({group_link})\\. "
                "Integralo nel tuo sistema e gioca con gli altri eroi\\. "
                "Usa /impostami per calibrare i sistemi, e /trombola per scatenare il Ragnarok\\.\\.\\. ehm, la partita\\.\n\n"
                "_🅰️vengers Uniti\\!_"
            ),
            "gia_unito": "📝 Sei già negli Accordi di Sokovia!",
            "annuncio_smistamento": "*_🧬 {mention} è stato reclutato da Nick Fury nel team di {team_disp}\\!_*",
            "numero_estratto": "🔮 Nuova visione dal futuro!",
            "partita_interrotta": "💥 Missione compromessa!",
            "errore_invio_cartella": "🤖 Errore di connessione con J.A.R.V.I.S. Assicurati di aver avviato il bot.",
            "non_in_partita": "⛔️ Civile, allontanati dalla zona di scontro!",
            "numero_estratto_annuncio": "_⚛️ Reattore Arc al 100\\%\\. Numero estratto\\: **{current_number_val:02}**_",
            "stop_solo_admin": "🛡️ Solo il Consiglio può revocare la missione.",
            "messaggio_stop": "*🫰 Thanos ha schioccato le dita\\: gioco polverizzato*",
            "messaggio_cartella": "*🦾 Sistemi online nel gruppo {group_text}, ecco i codici\\:*\n\n{escaped_cartella}",
            "mostra_cartella_alert": "Il tuo equipaggiamento Mark-85:\n\n{formatted_cartella}",
            "estrazione_solo_admin": "🧤 Solo chi ha le Gemme può manipolare la realtà (estrarre).",
            "nessuna_partita_attiva_per_estrazione": "🧊 Sistemi congelati come Cap nel ghiaccio. Avvia prima una partita.",
            "numero_avuto_dm": "*🎯 Colpo a segno\\! Avevi il numero {number_drawn:02}\\!*\n\n{escaped_cart_text}",
            "tutti_numeri_estratti": "🏁 Endgame. Tutte le timeline sono state esplorate.",
            "bonus_110": "*🛡️ {bonus_110_name}\\!*\n\n_🇺🇸 @{user_affected_escaped_name} alza il braccio appena in tempo\\! Il disco di Vibranio assorbe completamente l'impatto nemico e restituisce il colpo con un rimbombo metallico\\! Guadagna {punti_val} punti\\._",
            "malus_666": "*🔮 {malus_666_name}\\!*\n\n_⚡ @{user_affected_escaped_name} ha provato a brandire il Guanto dell'Infinito, ma il potere è troppo grande per un solo mortale\\! L'energia cosmica brucia attraverso l'armatura\\.\\.\\. Perde {punti_val} punti\\._",
            "bonus_104": "*🌩️ {bonus_104_name}\\!*\n\n_🔨 Il cielo si oscura e @{user_affected_escaped_name} tende la mano\\.\\.\\. Mjolnir risponde alla chiamata\\! La prova è superata: è degno del potere di Thor\\! Un fulmine colpisce il campo e gli conferisce {punti_val} punti\\._",
            "malus_404": "*🌀 {malus_404_name}\\!*\n\n_😵‍💫 Un incantesimo sbagliato apre una frattura nella realtà\\! @{user_affected_escaped_name} viene risucchiato in una timeline alternativa dove non ha mai giocato a Tombola\\. Prima di riuscire a tornare nel presente, perde {punti_val} punti\\._",            "partita_interrotta_no_punti": "🌫️ Punti svaniti nel Regno Quantico.",
            "nessuna_classifica": "*💾 Nessun dato negli archivi Stark\\.*",
            "classifica_finale": "🏆 Hall of Armor \\(Classifica\\)\\:\n\n" + "{lines}",
            "reset_classifica_solo_admin": "💂‍♂️ Solo Odin può riscrivere la storia.",
            "messaggio_reset_classifica": "_🧹 Protocollo 'Clean Slate' eseguito\\: memoria cancellata\\._",
            "regole_introduzione": (
                "*_ℹ️ DATABASE S\\.H\\.I\\.E\\.L\\.D\\.\\:_*\n\n"
                "_👋 Salve recluta\\. Accedi ai dossier segreti tramite i bottoni qui sotto_ "
                "_per comprendere la tecnologia aliena di questo bot\\._\n\n"
                "_📡 Per comunicazioni criptate rivolgiti a @AssistenzaTombola2\\_Bot\\._ "
                "_Chiama i rinforzi se rilevi bug nel sistema\\._\n\n"
            ),
            "errore_invio_regole_privato": (
                "_📭 @{escaped_username} frequenza criptata non raggiungibile\\._\n"
                "*Vai su @Tombola2_Bot e premi 'Avvia' per aprire il canale*"
            ),
            "messaggio_invio_regole_privato": "_📂 @{escaped_username} dossier Top Secret inviato in privato\\._",
            "regole_punteggi": (
                "*🏆 Taglie e Ricompense\\:*\n\n"
                "_🔢 Qui definiamo il valore delle missioni\\. Ogni base ha le sue regole, "
                "ma ecco i valori attuali per il settore {header}\\:_\n\n"
                "1️⃣ *AMBO* vale {premi_ambo} punti\n"
                "2️⃣ *TERNO* vale {premi_terno} punti\n"
                "3️⃣ *QUATERNA* vale {premi_quaterna} punti\n"
                "4️⃣ *CINQUINA* vale {premi_cinquina} punti\n"
                "5️⃣ *TOMBOLA* vale {premi_tombola} punti\n\n"
                "_👾 Inoltre, se attivo nel vostro universo\\:_\n\n"
                "6️⃣ *TOMBOLINO* vale {premi_tombolino} punti\n"
            ),
            "regole_comandi": (
                "*💻 Comandi dell'I\\.A\\.\\:*\n\n"
                "_🎛️ Lista comandi vocali per l'armatura\\. Alcuni richiedono autorizzazione Alpha, altri sono per tutte le reclute\\._\n\n"
                "*1️⃣ /trombola*\n"
                "_Protocollo Alpha\\. Avvia la missione\\. Richiede livello Admin\\._\n"
                "*2️⃣ /impostami*\n"
                "_Apre l'interfaccia olografica per modificare i parametri\\._\n"
                "*3️⃣ /classifiga*\n"
                "_Mostra gli eroi più forti del momento\\._\n"
                "*4️⃣ /azzera*\n"
                "_Formatta il server\\. Attenzione\\: nemmeno la Gemma del Tempo recupera questi dati\\._\n"
                "*5️⃣ /stop*\n"
                "_Interruzione d'emergenza\\. Utile in caso di attacco Ultron\\._\n"
                "*6️⃣ /estrai*\n"
                "_Calcola le probabilità ed estrae un numero\\. Strange, tocca a te\\._\n"
                "*7️⃣ /trombolatori*\n"
                "_Scansione biometrica\\: conta gli eroi attivi sul campo\\._"
            ),
            "regole_unirsi": (
                "*🎫 Arruolamento\\:*\n\n"
                "_🖋️ Vuoi firmare e combattere\\? "
                "Quando il Caposquadra lancia il segnale con /trombola, apparirà il bottone '🕸️ Unisciti'\\. "
                "Sparaci una ragnatela sopra per ricevere l'equipaggiamento\\._"
            ),
            "regole_estrazione": (
                "*🎱 Estrazione Quantica\\:*\n\n"
                "_🔄 I numeri vanno da 1 a 90\\. Una volta estratto il primo, "
                "l'I\\.A\\. segnerà tutto in automatico\\. Voi dovete solo sperare di essere nella timeline vincente "
                "mentre l'Admin gestisce il flusso\\._"
            ),
            "regole_bonus_malus": (
                "*☯️ Artefatti Cosmici \\(Bonus/Malus\\)\\:*\n\n"
                "_🎰 Volete il caos\\? Attivate questi oggetti nelle impostazioni\\._\n"
                "_🎲 Ciascuno di questi oggetti è nascosto nel Tesseract e una volta estratto colpirà un eroe a caso "
                "modificando i suoi punti vitali \\(da 1 a 49\\)\\._\n\n"
                "*1️⃣ {bonus_104_name}*\n"
                "_Chiunque brandisca questo martello, se ne sarà degno, possiederà il potere di Thor\\! "
                "Se il bot ti giudica degno, il fulmine colpirà il tuo punteggio aumentandolo\\._\n\n"
                "*2️⃣ {malus_666_name}*\n"
                "_Un potere troppo grande per i mortali\\. Se provi a impugnare il Guanto senza essere pronto, "
                "l'energia cosmica ti si ritorcerà contro bruciando i tuoi punti\\._\n\n"
                "*3️⃣ {bonus_110_name}*\n"
                "_Fatto interamente in Vibranio\\. Se viene estratto, lo Scudo ti proteggerà dalla sfortuna "
                "e assorbirà l'impatto cinetico convertendolo in punti extra\\._\n\n"
                "*4️⃣ {malus_404_name}*\n"
                "_Un'incursione tra universi\\. Se finisci in questa frattura della realtà, verrai risucchiato "
                "in una timeline dove i tuoi punti non esistono\\._\n\n"                
                "_⏯️ E non è finita\\. C'è una scena post\\-credit\\:_\n"
                "*5️⃣ Tombolino Marvel*\n"
                "_🥡 Premio di consolazione \\(Shawarma\\) per chi vince subito dopo il primo\\. Vale meno, ma hai salvato la città\\._"
            ),
            "impostazioni_solo_admin": "🔒 Accesso negato. Richiesta scansione retina Admin.",
            "pannello_controllo": "*📱 Stark Industries OS*\n\n_📲 Quale sistema vuoi riconfigurare\\?_",
            "descrizione_estrazione": (
                "_⚙️ Vuoi che F\\.R\\.I\\.D\\.A\\.Y\\. estragga i numeri in automatico o preferisci farlo manualmente "
                "come Strange che cerca la variante giusta\\? Scegli qui\\:_"
            ),
            "errore_aggiornamento_menu": "⚠️ Malfunzionamento nei circuiti. Riprova.",
            "descrizione_admin": (
                "_🔑 Vuoi dare le chiavi dell'armatura a tutti\\? È rischioso\\.\\.\\._ "
                "_Premi 'No' per mantenere la gerarchia S\\.H\\.I\\.E\\.L\\.D\\. "
                "Premi 'Sì' per la Civil War \\(tutti comandano\\)\\:_"
            ),
            "descrizione_premi": (
                "_💰 Qui si decide il bottino\\. "
                "Imposta il valore di ogni obiettivo e lascia che il destino agisca\\:_"
            ),
            "descrizione_bonus_malus": (
                "_💎 Vuoi usare le Gemme dell'Infinito\\? Qui attivi/disattivi gli artefatti speciali "
                "per rendere la classifica imprevedibile come Loki\\. Digita /regolo per info top\\-secret\\._"
            ),
            "descrizione_elimina_numeri": (
                "_🧹 Protocollo Pulizia\\. Decidi se il bot deve auto\\-distruggere i messaggi "
                "a fine missione per non lasciare tracce\\. Premi 'Sì' per modalità stealth\\._"
            ),
            "descrizione_tema": (
                "_🎨 Personalizzazione Realtà\\. Decidi quale veste grafica applicare\\. "
                "Il tema Marvel è inevitabile, ma hai libera scelta\\:_"
            ),
            "nessuna_partita_attiva_per_giocatori": "🦗 Sala riunioni vuota. Nessuna missione.",
            "nessun_giocatore_unito": "*🤷‍♂️ Nessun Avenger ha risposto alla chiamata\\!*",
            "numero_giocatori_attivi": "*👥 Eroi in campo\\: {count}*",
            "nessuna_classifica_disponibile": "*📉 Database vuoto\\.*",
            "testo_classifica": "🏆 Hall of Armor \\(Classifica Finale\\)\\:\n\n" + "{lines}",
            "vincitore_ambo": "_🏆 @{escaped} ha conquistato le gemme del Potere e dello Spazio e ha fatto ambo\\!_",
            "vincitore_terno": "_🏆 @{escaped} ha conquistato le gemme del Potere, dello Spazio e della Realtà e ha fatto terno\\!_",
            "vincitore_quaterna": "_🏆 @{escaped} ha conquistato le gemme del Potere, dello Spazio, della Realtà e dell'Anima e ha fatto quaterna\\!_",
            "vincitore_cinquina": "_🏆 @{escaped} ha conquistato le gemme del Potere, dello Spazio, della Realtà, dell'Anima e del Tempo e ha fatto cinquina\\!_",
            "tombola_prima": "_🏆 @{escaped_username}  conquista tutte le gemme dell'Infinito e con il potere del Guanto ha fatto Tombola{extra}_",
            "tombolino": "_🏆 @{escaped_username} riesce a scappare in tempo e non viene polverizzato dallo schiocco di Thanos e fa Tombolino\\!_",
        },
        "barbie":{
            "solo_admin": "🚫 Solo le Barbie Admin possono avviare la festa 💅✨",
            "annuncio_partita":(
                        "*💖✨ Party Tombola Barbie iniziato\\!*\n\n"
                        "_💅 Premi 'Unisciti' per entrare nella Dreamhouse, ma prima assicurati di aver avviato il bot_\n\n"
                        "_🎀 Barbie Moderatrice, quando sei pronta avvia con /estrai 💖 oppure usa /stop per fermare tutto\\. "
                        "Che vinca la Barbie più fortunata\\! Per dubbi usa /regolo 💕_"
                        ),
            "join_non_autorizzato": "🚫 Non sei nella lista VIP della Dreamhouse 💖",
            "non_membro_gruppo": "🚫 Non fai parte del Barbie Club 💅",
            "partita_non_attiva": "🚫 Nessun party Barbie in corso al momento 💕",
            "partita_iniziata": "🚫 Il party è già iniziato 💖 aspetta il prossimo!",
            "unito_partita": "*💖 Sei ufficialmente nella Dreamhouse {group_text}\\! Ecco la tua cartella Barbie ✨\\:*\n\n{escaped_cartella}",
            "non_unito_ora": "🔜 Troppo tardi per entrare nel party Barbie 💅",
            "benvenuto": (
                        "*💖 Benvenuta [{escaped_nickname}](https://t.me/{escaped_username}) nella Dreamhouse\\!*\n\n"
                        "Questo è il bot ufficiale Barbie Tombola ✨, aggiungilo nel tuo gruppo e gioca con le tue amiche 💕\\.\n\n"
                        "Usa /impostami per personalizzare tutto 💅 e /trombola per iniziare il party\\!\n\n"
                        "_💖 Stay fabulous 💅_"
                        ),
            
            "gia_unito":"Sei già dentro il party Barbie 💖\\!",
            "annuncio_unione":"*_💅 {username} è entrata nella Dreamhouse\\!_*",
            "numero_estratto":"💖 Numero glamour estratto!",
            "partita_interrotta":"💔 Party Barbie interrotto!",
            "errore_invio_cartella":"Non riesco a mandarti la cartella Barbie in privato 💌",
            "non_in_partita":"⛔️ Non sei nella Dreamhouse!",
            "numero_estratto_annuncio":"_💖 È stato estratto il numero glamour **{current_number_val:02}**_",
            "stop_solo_admin": "🚫 Solo Barbie Admin possono fermare il party 💅",
            "messaggio_stop": "*💔 Il party Barbie è stato interrotto*",
            "messaggio_cartella": "*💖 Sei nella Dreamhouse {group_text}\\! Ecco la tua cartella ✨\\:*\n\n{escaped_cartella}",
            "mostra_cartella_alert":"💖 La tua cartella glamour:\n\n{formatted_cartella}",
            "estrazione_solo_admin":"🚫 Solo Barbie Admin possono estrarre 💅",
            "nessuna_partita_attiva_per_estrazione":"🚫 Nessun party attivo 💖",
            "numero_avuto_dm":"*💌 Avevi il numero {number_drawn:02}\\!*\n\n{escaped_cart_text}",
            "tutti_numeri_estratti":"✨ Tutti i numeri glamour sono usciti! Party finito 💖",
            
            "bonus_110": "*👑 {bonus_110_name}\\!*\n\n_💖 @{user_affected_escaped_name} entra nella Dreamhouse con un outfit da passerella\\. Tutti si fermano a guardare\\.\\.\\. è pura energia da Barbie Icon\\! I riflettori si accendono e il suo glow up le regala {punti_val} punti\\._",
            "malus_666": "*💔 {malus_666_name}\\!*\n\n_😱 @{user_affected_escaped_name} prova un cambio outfit all'ultimo secondo\\.\\.\\. ma qualcosa va storto\\! Tacchi rotti, trucco sbavato, drama totale nella Dreamhouse\\. Perde {punti_val} punti\\._",
            "bonus_104": "*✨ {bonus_104_name}\\!*\n\n_💅 @{user_affected_escaped_name} trova lo specchio magico della Dreamhouse\\. Un tocco di gloss, un sorriso\\.\\.\\. ed è subito Barbie perfetta\\! L'energia glamour le dona {punti_val} punti\\._",
            "malus_404": "*🌀 {malus_404_name}\\!*\n\n_🤯 @{user_affected_escaped_name} apre l'armadio infinito della Dreamhouse\\.\\.\\. ma si perde tra troppi outfit\\! Quando finalmente esce, il party è già andato avanti\\. Perde {punti_val} punti\\._",
            
            "partita_interrotta_no_punti":"💔 Nessun punto assegnato, party interrotto",
            "nessuna_classifica":"*📊 Nessuna classifica glamour disponibile 💖*",
            "classifica_finale":"🏆 Classifica Barbie Finale\\:\n\n" + "{lines}",
            
            "reset_classifica_solo_admin":"🚫 Solo Barbie Admin possono resettare 💅",
            "messaggio_reset_classifica":"_✨ Tutti i punteggi sono stati cancellati 💖_",
            
            "tombola_prima": "_👑 @{escaped_username} raggiunge l'apice della Dreamhouse\\: BARBIE ICON MOMENT 💖✨{extra}_",
            "tombolino": "_🌟 @{escaped_username} brilla sotto i riflettori\\: Barbie Rising Star 💖\\!_",   

            "errore_invio_regole_privato": (
                        "_💌 @{escaped_username} non riesco a mandarti le regole Barbie in privato 💔\n"
                        "*Vai su @Tombola2_Bot e premi 'Avvia'*" 
                    ),
            "messaggio_invio_regole_privato":"_💖 @{escaped_username} ti ho inviato le regole Barbie 💌_",

            "impostazioni_solo_admin": "🚫 Solo Barbie Admin possono modificare 💅",
            "pannello_controllo": "*💖 Pannello Dreamhouse*\n\n_✨ Scegli cosa personalizzare_",

            "nessuna_partita_attiva_per_giocatori":"🚫 Nessun party Barbie attivo 💔",
            "nessun_giocatore_unito":"*🤷‍♀️ Nessuna Barbie si è unita ancora\\!*",
            "numero_giocatori_attivi":"*💖 Barbie in gioco\\: {count}*",

            "vincitore_ambo": "_💅 @{escaped} crea il suo primo look perfetto: Barbie Duo Glam ✨\\!_",
            "vincitore_terno": "_👠 @{escaped} conquista la passerella con un Barbie Trio Iconic 💖\\!_",
            "vincitore_quaterna": "_👯‍♀️ @{escaped} raduna la squadra perfetta: Barbie Squad Goals ✨\\!_",
            "vincitore_cinquina": "_💕 @{escaped} domina il party con il suo Barbie Dream Team 🌈\\!_",
            "regole_introduzione":(
                "*_💖 REGOLE DELLA DREAMHOUSE\\:_*\n\n"
                "_👋 Benvenuta nella guida ufficiale Barbie\\! Qui potrai esplorare tutte le sezioni del party ✨_\n\n"
                "_💅 Per qualsiasi dubbio scrivici su @AssistenzaTombola2\\_Bot\\._\n"
                "_Siamo sempre pronte ad aiutarti, bestie 💕_\n\n"
            ),

            "regole_punteggi":(
                "*👑 Glam Points\\:*\n\n"
                "_💖 Qui si decide chi è la vera Barbie Icon\\! Questi sono i punteggi attuali nel gruppo {header}\\:_\n\n"
                "1️⃣ *Barbie Duo Glam* vale {premi_ambo} punti\n"
                "2️⃣ *Barbie Trio Iconic* vale {premi_terno} punti\n"
                "3️⃣ *Barbie Squad Goals* vale {premi_quaterna} punti\n"
                "4️⃣ *Barbie Dream Team* vale {premi_cinquina} punti\n"
                "5️⃣ *Barbie Icon Moment* vale {premi_tombola} punti\n\n"
                "_✨ Extra glamour\\:_\n\n"
                "6️⃣ *Barbie Rising Star* vale {premi_tombolino} punti\n"
            ),

            "regole_comandi": (
                "*💖 Comandi Dreamhouse\\:*\n\n"
                "_💅 Tutti i controlli per gestire il party Barbie\\:_\n\n"
                "*1️⃣ /trombola*\n"
                "_Avvia il party 💕 \\(solo Barbie Admin\\)_\n"
                "*2️⃣ /impostami*\n"
                "_Personalizza la Dreamhouse ✨_\n"
                "*3️⃣ /classifiga*\n"
                "_Mostra chi è la Barbie più icon 💖_\n"
                "*4️⃣ /azzera*\n"
                "_Resetta tutto (drama totale 💔)_\n"
                "*5️⃣ /stop*\n"
                "_Ferma il party 💅_\n"
                "*6️⃣ /estrai*\n"
                "_Fai partire il glow up dei numeri ✨_\n"
                "*7️⃣ /trombolatori*\n"
                "_Scopri quante Barbie sono nel party 💖_"
            ),

            "regole_unirsi": (
                "*💅 Come entrare nel party\\:*\n\n"
                "_💖 Quando una Barbie Admin apre il party, premi 'Unisciti' e riceverai la tua cartella glamour✨_\n\n"
                "_Ora non ti resta che brillare e sperare nel tuo momento icon 👑_"
            ),

            "regole_estrazione": (
                "*✨ Glow Numbers\\:*\n\n"
                "_💖 I numeri escono automaticamente e vengono segnati nella tua cartella_\n"
                "_💅 Tu rilassati e goditi il party, la magia la fa il bot_"
            ),

            "regole_bonus_malus": (
                "*💖 Drama & Glow\\:*\n\n"
                "_✨ Vuoi un party movimentato\\? Attiva bonus e malus\\!_\n\n"
                "_💅 Ogni evento può regalarti o toglierti punti a sorpresa_\n\n"
                "*1️⃣ {bonus_104_name}*\n"
                "_Glow up immediato ✨_\n\n"
                "*2️⃣ {malus_666_name}*\n"
                "_Drama totale 💔_\n\n"
                "*3️⃣ {bonus_110_name}*\n"
                "_Momento ICON 👑_\n\n"
                "*4️⃣ {malus_404_name}*\n"
                "_Outfit sbagliato 😱_\n\n"
                "*5️⃣ Barbie Rising Star*\n"
                "_La seconda star del party 🌟_"
            ),

            "impostazioni_solo_admin": "🚫 Solo Barbie Admin possono modificare 💅",

            "pannello_controllo": "*💖 Dreamhouse Control Panel*\n\n_✨ Scegli cosa personalizzare_",
            "descrizione_estrazione": (
                "_💖 Vuoi un party automatico o preferisci controllare tutto tu come una vera Barbie Boss? "
                "Scegli se far uscire i numeri automaticamente oppure manualmente 💅:_"
            ),

            "errore_aggiornamento_menu": "💔 Oops\\! Qualcosa è andato storto nella Dreamhouse\\. Riprova 💖",

            "descrizione_admin": (
                "_👑 Vuoi mantenere il controllo totale della Dreamhouse? "
                "Premi 'Sì' per lasciare tutto alle Barbie Admin oppure 'No' per un party libero e selvaggio 💅:_"
            ),

            "descrizione_premi": (
                "_✨ Qui si decide chi sarà la vera Barbie Icon\\! "
                "Imposta i punti e lascia che il drama faccia il resto 💖:_"
            ),

            "descrizione_bonus_malus": (
                "_💅 Vuoi aggiungere un po’ di drama al party? "
                "Attiva bonus e malus per rendere tutto più spicy 🌶️💖_"
            ),

            "descrizione_elimina_numeri": (
                "_🧹 Vuoi mantenere la Dreamhouse sempre perfetta? "
                "Attiva la pulizia automatica dei messaggi a fine party ✨_"
            ),

            "descrizione_tema": (
                "_💖 Scegli lo stile della tua Dreamhouse\\! "
                "Ogni tema cambia completamente l’atmosfera del party 💅✨_"
            )
        },
        "calcio": {
            "solo_admin": "🚫 Solo l'arbitro può dare il via alla partita ⚽",
            
            "annuncio_partita":(
                        "*⚽🔥 Partita di Trombola iniziata\\!*\n\n"
                        "_🏟️ Premi 'Unisciti' per scendere in campo, ma prima assicurati di aver avviato il bot_\n\n"
                        "_📣 Arbitro, quando sei pronto fischia l’inizio con /estrai oppure interrompi con /stop\\. "
                        "Che vinca il migliore\\! Per dubbi usa /regolo ⚽_"
                        ),

            "join_non_autorizzato": "🚫 Non sei convocato per questa partita ⚽",
            "non_membro_gruppo": "🚫 Non fai parte della squadra",
            "partita_non_attiva": "🚫 Nessuna partita in corso allo stadio",
            "partita_iniziata": "🚫 La partita è già iniziata! Aspetta il prossimo match ⚽",
            
            "unito_partita": "*🏟️ Sei ufficialmente in campo nel gruppo {group_text} per {house}\\! Ecco la tua formazione\\:*\n\n{escaped_cartella}",
            
            "non_unito_ora": "🔜 Il match è iniziato, niente cambi ora ⚽",
            
            "benvenuto": (
                        "*⚽ Benvenuto [{escaped_nickname}](https://t.me/{escaped_username}) nello stadio\\!*\n\n"
                        "Questo è il bot ufficiale Trombola ⚽, gioca con i tuoi amici e domina il campionato\\!\n\n"
                        "Usa /impostami per gestire la squadra e /trombola per iniziare la partita\\. "
                        "Che vinca il migliore\\! 🏆\n\n"
                        "_🔥 Fischio d'inizio\\!_"
                        ),

            "gia_unito":"Sei già in campo ⚽!",
            "numero_estratto":"⚽ Azione in corso!",
            "partita_interrotta":"🛑 Partita sospesa!",
            
            "errore_invio_cartella":"Non riesco a inviarti la formazione ⚽",
            "non_in_partita":"⛔️ Non sei in partita!",
            
            "numero_estratto_annuncio":"_📣 È sceso in campo il numero **{current_number_val:02}** ⚽_",

            "stop_solo_admin": "🚫 Solo l'arbitro può fermare il match",
            "messaggio_stop": "*🛑 Partita interrotta dall'arbitro*",

            "messaggio_cartella": "*🏟️ Sei in campo nel gruppo {group_text} per {house}\\! Ecco la tua formazione\\:*\n\n{escaped_cartella}",
            "mostra_cartella_alert":"⚽ La tua formazione:\n\n{formatted_cartella}",

            "estrazione_solo_admin":"🚫 Solo l'arbitro può estrarre i numeri",
            "nessuna_partita_attiva_per_estrazione":"🚫 Nessuna partita avviata",

            "numero_avuto_dm":"*🎯 Hai preso il numero {number_drawn:02}\\!*\n\n{escaped_cart_text}",

            "tutti_numeri_estratti":"⚽ Tutte le azioni sono state giocate! Fine partita!",

            "bonus_110": "*🏆 {bonus_110_name}\\!*\n\n_⚽ @{user_affected_escaped_name} parte in contropiede, dribbla tutta la difesa e segna sotto l'incrocio\\! Gol spettacolare\\! Guadagna {punti_val} punti\\._",
            "malus_666": "*💥 {malus_666_name}\\!*\n\n_😱 @{user_affected_escaped_name} sbaglia il controllo\\.\\.\\. la palla gli sfugge e finisce in rete\\. Autogol clamoroso\\! Perde {punti_val} punti\\._",
            "bonus_104": "*🧤 {bonus_104_name}\\!*\n\n_🧱 @{user_affected_escaped_name} si lancia in tuffo e para un rigore impossibile\\! Il pubblico esplode\\. Guadagna {punti_val} punti\\._",
            "malus_404": "*🌀 {malus_404_name}\\!*\n\n_😵‍💫 @{user_affected_escaped_name} perde completamente la posizione\\.\\.\\. si ritrova fuori gioco senza accorgersene\\! Azione sprecata\\! Perde {punti_val} punti\\._",

            "partita_interrotta_no_punti":"🌫️ Match sospeso: risultato non valido",

            "nessuna_classifica":"*📊 Nessuna classifica disponibile*",
            "classifica_finale":"🏆 Classifica finale\\:\n\n" + "{lines}",

            "reset_classifica_solo_admin":"🚫 Solo l'arbitro può resettare la classifica",
            "messaggio_reset_classifica":"_🧹 Classifica azzerata\\!_",

            "vincitore_ambo": "_⚽ @{escaped} segna il primo gol\\: Doppietta in arrivo\\!_",
            "vincitore_terno": "_🔥 @{escaped} è scatenato\\: Tripletta\\!_",
            "vincitore_quaterna": "_💥 @{escaped} domina il campo\\: Poker di gol\\!_",
            "vincitore_cinquina": "_👑 @{escaped} è leggenda\\: Manita\\!_",

            "tombola_prima": "_🏆 @{escaped_username} vince il campionato\\! GOL DECISIVO ⚽🔥{extra}_",
            "tombolino": "_🥈 @{escaped_username} sfiora la vittoria\\: Secondo posto\\!_",

            "nessuna_partita_attiva_per_giocatori":"🚫 Nessuna partita in corso",
            "nessun_giocatore_unito":"*🤷‍♂️ Nessun giocatore in campo\\!*",
            "numero_giocatori_attivi":"*👥 Giocatori in campo\\: {count}*",
            "regole_introduzione":(
                "*_⚽ REGOLAMENTO DEL GIUOCO CALCIO\\:_*\n\n"
                "_👋 Benvenuto nello stadio\\! Qui trovi tutte le regole del match_\n\n"
                "_📣 Per assistenza contatta @AssistenzaTombola2\\_Bot\\._\n"
                "_Il VAR è sempre attivo 😏_\n\n"
            ),

            "errore_invio_regole_privato": (
                "_📭 @{escaped_username} non riesco a inviarti il regolamento_\n"
                "*Vai su @Tombola2_Bot e premi 'Avvia'*"
            ),

            "messaggio_invio_regole_privato":"_📬 @{escaped_username} ti ho inviato il regolamento ⚽_",

            "regole_punteggi":(
                "*🏆 Classifica Campionato\\:*\n\n"
                "_⚽ Questi sono i punteggi nel gruppo {header}\\:_\n\n"
                "1️⃣ *Doppietta* vale {premi_ambo} punti\n"
                "2️⃣ *Tripletta* vale {premi_terno} punti\n"
                "3️⃣ *Poker* vale {premi_quaterna} punti\n"
                "4️⃣ *Manita* vale {premi_cinquina} punti\n"
                "5️⃣ *Vittoria del Campionato* vale {premi_tombola} punti\n\n"
                "_🥈 Extra\\:_\n\n"
                "6️⃣ *Secondo posto* vale {premi_tombolino} punti\n"
            ),

            "regole_comandi": (
                "*⚽ Comandi di gioco\\:*\n\n"
                "*1️⃣ /trombola*\n"
                "_Fischio d’inizio_\n"
                "*2️⃣ /impostami*\n"
                "_Configura la squadra_\n"
                "*3️⃣ /classifiga*\n"
                "_Mostra la classifica_\n"
                "*4️⃣ /azzera*\n"
                "_Reset campionato_\n"
                "*5️⃣ /stop*\n"
                "_Fine partita_\n"
                "*6️⃣ /estrai*\n"
                "_Gioca le azioni_\n"
                "*7️⃣ /trombolatori*\n"
                "_Giocatori in campo_"
            ),

            "regole_unirsi": (
                "*👕 Scendere in campo\\:*\n\n"
                "_⚽ Premi 'Unisciti' quando inizia la partita_\n\n"
                "_Riceverai la tua formazione e potrai giocare subito_"
            ),

            "regole_estrazione": (
                "*🎯 Azioni di gioco\\:*\n\n"
                "_⚽ I numeri rappresentano le azioni di gioco_\n"
                "_Il bot segna tutto automaticamente_"
            ),

            "regole_bonus_malus": (
                "*🔥 Eventi di gioco\\:*\n\n"
                "_⚽ Durante la partita possono succedere colpi di scena\\!_\n\n"
                "*1️⃣ {bonus_104_name}*\n"
                "_Parata incredibile 🧤_\n\n"
                "*2️⃣ {malus_666_name}*\n"
                "_Autogol 💥_\n\n"
                "*3️⃣ {bonus_110_name}*\n"
                "_Gol spettacolare 🔥_\n\n"
                "*4️⃣ {malus_404_name}*\n"
                "_Fuorigioco 😵‍💫_\n\n"
                "*5️⃣ Secondo posto*\n"
                "_Secondo posto 🥈_"
            ),

            "impostazioni_solo_admin": "🚫 Solo l'arbitro può modificare le impostazioni",

            "pannello_controllo": "*⚽ Sala VAR*\n\n_📊 Configura il match_",
            "errore_aggiornamento_menu": "⚠️ Errore VAR\\. Riprova l'azione\\!",

            "descrizione_estrazione": (
                "_⚽ Vuoi un gioco veloce o controllato\\? "
                "Puoi scegliere se far partire le azioni automaticamente oppure gestirle manualmente come un vero allenatore\\:_"
            ),

            "descrizione_admin": (
                "_👨‍⚖️ Vuoi lasciare il controllo solo all’arbitro o a tutta la squadra\\? "
                "Decidi chi può gestire la partita\\:_"
            ),

            "descrizione_premi": (
                "_🏆 Imposta il valore dei gol\\! "
                "Decidi quanti punti assegnare per ogni azione decisiva\\:_"
            ),

            "descrizione_bonus_malus": (
                "_🔥 Vuoi rendere la partita imprevedibile\\? "
                "Attiva bonus e malus per colpi di scena degni di una finale\\:_"
            ),

            "descrizione_elimina_numeri": (
                "_🧹 Vuoi tenere lo stadio pulito\\? "
                "Attiva la rimozione automatica delle azioni a fine partita\\:_"
            ),

            "descrizione_tema": (
                "_🎽 Scegli lo stile della tua squadra\\! "
                "Ogni tema cambia il modo in cui vivi la partita\\:_"
            )
        },
        
    }
    templates_for_tema = testi.get(tema, testi["normale"])
    template = templates_for_tema.get(chiave)

    if template is None:
        default_value = kwargs.pop('default', None)
        if default_value is not None:
            template = default_value
        else:
            template = "Testo non trovato"

    theme_names = THEME_BONUS_NAMES.get(tema, THEME_BONUS_NAMES.get('normale', {}))
    for k, v in theme_names.items():
        try:
            safe_val = escape_markdown(str(v), version=2)
        except Exception:
            safe_val = str(v)
        kwargs.setdefault(k, safe_val)

    try:
        return template.format(**kwargs)
    except KeyError as e:
        missing_key = e.args[0] if e.args else 'unknown'
        try:
            safe_kwargs = defaultdict(str, kwargs)
            return template.format_map(safe_kwargs)
        except Exception:
            logger.warning(f"Mancante placeholder in template per chiave '{chiave}': {missing_key}")
            return template 
