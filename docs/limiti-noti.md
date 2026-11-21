# Limiti noti di DOMHOUSE

*Aggiornato il 13 novembre 2026 (revisione per scenari P-90). Regola del committente (D-204): ogni limite che conosciamo sta scritto qui.*

**Come leggerlo:** «Stato» dice se il limite è accettato, se è in lavorazione o se va ancora verificato.

## Notifiche

| Limite | Cosa succede | Stato |
|---|---|---|
| **Consegna parziale** | Se una notifica raggiunge solo alcuni telefoni per un errore temporaneo, conta come mandata e non viene ritentata: ritentarla la rimanderebbe a tutti | Accettato |
| **Doppio raro** | Se un server cade mentre manda una notifica, la stessa notifica può partire due volte, mai zero | Accettato |
| **Tempi di recupero** | Se un server cade, la notifica viene ripresa entro pochi minuti; il riepilogo settimanale entro 75 minuti | Accettato |
| **Eventi molto vecchi** | Se nessun server resta collegato a un motore per più di un'ora, gli eventi più vecchi di un'ora non generano notifiche; resta una riga nei log | Accettato |
| **Primo avvio del lotto 36** | Un dispositivo già offline da meno di 6 giorni manda una notifica, anche se era già stata mandata | Una tantum |

## Notifica «sistema domotico non raggiungibile» (dal lotto 38, D-217; soglia fissa di 15 minuti dal 13 novembre, risposta 1104)

| Limite | Cosa succede | Stato |
|---|---|---|
| **Server che parte durante un fermo** | Ogni copia del server conta dalla sua prima connessione fallita: una copia partita durante il fermo conta da quando parte, quindi la notifica può arrivare fino a N minuti dopo l'inizio vero | Accettato |
| **Nessuna copia del server accesa** | Con il minimo a 0 nessuno controlla e nessuna notifica parte (vale per lo staging) | Accettato |
| **Riassunto a fine manutenzione** | Se il motore riparte due volte nella stessa sospensione conta solo il primo gruppo di azioni saltate; con una sospensione più lunga di 6 giorni il riassunto parte al sesto giorno; se la sospensione viene prolungata dopo che il riassunto è già in attesa, parte alla data vecchia | Accettato |
| **Pubblicazione durante una sospensione** | Una pubblicazione toglie la sospensione degli avvisi | Accettato (M19) |
| **Chiave rifiutata** | Un motore che risponde ma rifiuta la chiave conta come irraggiungibile | Accettato |
| **Categoria spenta dall'utente** | Chi spegne «Dispositivi e sistema domotico offline» nelle sue Impostazioni non riceve nemmeno l'avviso del sistema fermo (la regola offline invece non lo spegne più) | Accettato |
| **Appartamento disattivato** | Gli automatismi continuano, ma notifiche (anche le gravi), riepiloghi, prenotazioni ed Excel si fermano; le prenotazioni non si recuperano alla riattivazione | Accettato, detto nella conferma (risposta 1107) |

## Disponibilità del server

| Limite | Cosa succede | Stato |
|---|---|---|
| **Fermo del 23 ottobre (E-27)** | La causa ultima è interna a Cloud Run e non è dimostrata; le contromisure ne tolgono la condizione nota | Prima sostituzione dopo il lotto 36 (9 novembre, 20:00) regolare: istanza vecchia chiusa in circa 15 minuti, nessun errore. Ma nessuno usava l'app: da riverificare con stream aperti |
| **Una sola VM** | Se la VM si ferma, i motori degli appartamenti si fermano con lei | Accettato per ora |
| **Staging diverso dalla produzione** | Lo staging ha al massimo 1 istanza, la produzione 3: un difetto che compare solo con più istanze non si vede in staging, salvo la prova dedicata | Accettato (D-202) |
| **Sospensione di un'organizzazione** | Con più istanze, l'effetto può arrivare fino a 30 secondi dopo | Accettato (risposta 338) |

## Staging

| Limite | Cosa succede | Stato |
|---|---|---|
| **Si spegne da solo** | Senza richieste si spegne: la prima apertura aspetta qualche secondo | Voluto |
| **Assistente del motore di prova dopo un'ora di silenzio** | Il motore `dev` chiama l'assistente attraverso il server di staging. Se lo staging dorme, il primo «Chiedi» può superare i 28 secondi (risveglio più modello) e rispondere «Non sono riuscito a rispondere in tempo»; il secondo funziona. I motori veri usano il server di produzione, sempre acceso, e non hanno questo limite (o1, 16 novembre) | Accettato: limite dello staging |
| **A server spento** | Niente notifiche, e gli eventi di quel periodo non si recuperano | Voluto |
| **Dimostrativi** | Ripartono dai valori iniziali a ogni avvio del server | Voluto |
| **Nessun backup del database** | Il database dello staging non ha backup pianificati: contiene solo dati di prova | Voluto |
| **Stessa identità della produzione (D04)** | Lo staging gira con lo stesso account della produzione: potrebbe scrivere anche nel database della produzione e leggerne i segreti | In lavorazione: comandi pronti (o1, 11 nov), da lanciare prima del primo appartamento vero |
| **Accessi condivisi** | Anche dopo D04, staging e produzione usano lo stesso Firebase Authentication: lo staging può ancora gestire gli account di accesso della produzione. Si separa solo con un secondo progetto Firebase | Accettato |
| **Porta segnata occupata dopo «Riprova»** (A2, risposta 1208) | Se l'agente trova occupata la porta scelta per un appartamento nuovo e si preme «Riprova», l'app prende la porta libera successiva e segna quella vecchia come occupata: nessuna creazione la userà più finché il supporto non controlla chi la usa sulla VM e la libera a mano. «Annulla» invece la libera subito. Staging 10 porte, produzione 49 | Accettato; come liberarla: documento di o1 |
| **Chiave con lo stesso nome creata fuori dall'app** (A2, risposte 1206 e 1207) | La creazione resta «a metà» e conta nel limite delle 5 l'ora; «Riprova» serve solo dopo che il supporto ha tolto quella chiave, altrimenti «Annulla» e un altro ID (lo dice il messaggio) | Accettato |
| **Capienza: un motore senza «ENV» conta come staging** (A7, revisione del codice, 20 novembre) | Nella regola dei posti liberi un motore della VM senza la riga `ENV` nelle impostazioni conta come motore dello staging (oggi `dev` e `lab-01` hanno `ENV=staging` da C3 di A2, e i motori creati dall'app hanno sempre `ENV`). Sulla VM di sola produzione (A10) un motore installato a mano senza `ENV` verrebbe contato nel posto sbagliato | Da rivedere con A10; A7 non ancora installato |

## Aggiornamenti in diretta

| Limite | Cosa succede | Stato |
|---|---|---|
| **Pagina in sottofondo** | L'app non si aggiorna in tempo reale; si rimette in pari quando torni | Voluto |
| **Browser che se ne va** | Il server può non accorgersene: lo stream resta aperto al massimo 4 minuti | Accettato |
| **Mai provato su un telefono** | La riapertura degli stream è stata provata solo su computer | Da verificare (checklist D27) |

## App nel browser

| Limite | Cosa succede | Stato |
|---|---|---|
| **Copia dell'app bloccata (E-29)** | Il 9 novembre la copia salvata in Chrome non è partita e il sito non si apriva; chiudere e riaprire Chrome l'ha risolto. Probabile blocco di Chrome, non dimostrato; in teoria può capitare a chiunque; un caso solo finora | Decisione dopo il lotto 36: togliere il gestore `fetch` dalla copia salvata (o2, circa 2 ore; senza rete l'app non si aprirebbe) |
| **Sito vecchio dopo una pubblicazione (P-92)** | La prima apertura dopo una pubblicazione mostra ancora il sito vecchio: si aggiorna solo ricaricando o riaprendo l'app. Chi non ricarica mai resta vecchio. Con il server nuovo può vedere scritte tecniche (per esempio «summer_min») o campi mancanti; i dati non si rovinano | Da correggere prima della produzione (P-92, domanda 1116); fino ad allora, dopo ogni pubblicazione ricaricare la pagina |
| **Avvio lento (E-29)** | Dal lotto 37, se l'app non si apre entro 15 secondi compare «Non riesco ad aprire la pagina» con «Ricarica»; se la risposta arriva prima di 30 secondi, l'app entra da sola. Senza risposta, dal lotto 37 (D-211) compare una pagina con «Ricarica» invece della pagina di accesso, e la sessione resta valida. Sullo staging spento il messaggio può comparire per qualche secondo | Accettato |
| **Chiamate che scadono** | Dal lotto 37 ogni chiamata al server ha 30 secondi (90 per le operazioni lente); poi compare «Server non raggiungibile» | Accettato |
| **Comando scaduto** | Un'operazione che scade può essere andata a buon fine sul server: il messaggio non lo può sapere. Comandi e salvataggi non vengono ritentati in automatico | Accettato |
| **Letture ritentate** | Le letture vengono ritentate una volta: prima dell'errore possono passare fino a 60 secondi | Accettato |
| **Errore di disegno** | Dal lotto 37 il messaggio sostituisce tutta l'app, menu compreso, e ciò che si stava scrivendo si perde con la ricarica | Accettato |
| **Nessun «Esci» dalla pagina «Ricarica»** | Per uscire dall'account la pagina deve prima riaprirsi (D-211) | Accettato |
| **«Il servizio non risponde» solo con un errore del server** | Un servizio che non risponde affatto dà il testo prudente «Non riesco ad aprire la pagina»: senza risposta l'app non distingue fra rete e servizio | Accettato |
| **Wi-Fi senza internet** | Il dispositivo si crede in rete: compare il testo prudente e, quando internet torna, la pagina non si riapre da sola perché il browser non segnala nessun ritorno; serve «Ricarica» | Accettato |
| **Ritorno della rete con il servizio lento** | Se il servizio non è raggiungibile entro 1,5 secondi dal ritorno della rete, la ricarica automatica finisce sul testo prudente e non si ripete: serve «Ricarica» | Accettato |
| **Casi coperti solo dalle prove automatiche** | «Il servizio non risponde» e le riletture del profilo diverse da quella periodica dell'amministratore (fine di un accesso di assistenza, cambio del nome) | Accettato |
| **Attese massime non provabili a mano** | Il limite di 30 e 90 secondi, la pagina «Non riesco ad aprire la pagina» dopo 15 secondi e il messaggio per un errore di disegno si verificano solo con le prove automatiche: senza rete l'errore arriva subito. Il collaudo a mano (sezione O) prova solo l'assenza di rete | Accettato |
| **Correzione E-29 non provata del tutto** | Non provata con Firebase vero, su Safari o su un telefono vero | Da verificare |

## Contratto dell'app

| Limite | Cosa succede | Stato |
|---|---|---|
| **«Non in linea» subito** | Il contratto dell'app (1.0.5) dice che un dispositivo diventa «non in linea» dopo i minuti della regola «Avviso dispositivo offline»; il motore lo segna invece appena il connector lo sa, e usa i minuti solo per la decisione e la notifica | Voluto (D-225): l'app mostra subito la verità; il contratto non si modifica (regola 1) |

## Prenotazioni

| Limite | Cosa succede | Stato |
|---|---|---|
| **Formato di Italianway non ancora noto** | Il traduttore delle prenotazioni è provvisorio: con prenotazioni reali di Italianway il pre-arrivo automatico e il risparmio al check-out **non sono disponibili** finché Italianway non manda il formato vero | Da chiedere a Leonardo (committente) |
| **Check-in e check-out effettivi** | Non sappiamo se Italianway li manderà. Se li manda: il check-in effettivo non porta il comfort a un ospite arrivato prima del pre-arrivo (S22); il check-out effettivo non anticipa il risparmio (S23); un check-in ritentato dopo una modifica viene scartato (S24) | Da chiedere a Leonardo; riparazioni dopo la risposta (P-90) |
| **Occupazione prima del check-in** | Fino all'orario di check-in della prenotazione l'occupazione è «Vuoto», anche durante il pre-arrivo | Accettato (guida corretta il 13 novembre) |

## Motore

| Limite | Cosa succede | Stato |
|---|---|---|
| **Esecuzione in parte: check-out con presenza** | Un check-out con presenza rilevata diventa un'approvazione: l'esecuzione non è legata all'azione programmata, quindi niente «eseguita in parte»; l'eventuale fallimento lo dice la decisione dell'approvazione | Accettato |
| **Esecuzione in parte: comandi successivi** | I comandi che la regolazione manda dopo, per conto suo, non contano per l'azione | Accettato |
| **Esecuzione in parte: riavvio durante un'attesa** | Un'accensione rimandata per la pausa del compressore e interrotta da un riavvio conta come non riuscita, anche se poi la regolazione la fa comunque | Accettato |
| **Testo delle notifiche** | Nella notifica il testo si taglia a 200 caratteri; nelle Decisioni resta intero | Accettato |
| **Approvata ma non eseguita** | Dal lotto 38 il fallimento si vede nelle Decisioni («Azione approvata ma non eseguita»), ma l'approvazione resta «Approvata» e l'app riceve un OK: il contratto non ha uno stato «non eseguita» | Accettato |
| **Riepilogo fatto in ritardo** | Se il motore è irraggiungibile per tutto il lunedì, il riepilogo fatto dopo può ancora perdere le approvazioni scadute nei primi giorni della settimana | Accettato |
| **Caldaia e clima dopo la chiusura della finestra** | Dal lotto 38 tornano da soli, circa un minuto dopo la chiusura dell'ultima finestra; la caldaia può aspettare in più il minimo fra due accensioni. Se la modalità cambia a finestra aperta vale quella nuova, anche quando la finestra si chiude prima che la regola scatti (dal lotto 40, D08: prima restava la temperatura della modalità vecchia); un dispositivo offline alla chiusura torna quando risponde | Corretto il 10 novembre (`cb50298`); caso della finestra chiusa prima della regola corretto l'11 novembre (o1 `6cfa5f8`) |
| **Riconoscimento di Cloud Run** | Il blocco dell'accesso di sviluppo riconosce Cloud Run dalla variabile `K_SERVICE`; su un altro servizio vale solo il controllo su `APP_ENV` | Accettato |
| **Pausa del compressore dopo un riavvio** | Era tenuta in memoria e un riavvio la azzerava | Corretto il 10 novembre (`ce7d7a5`): si salva e continua dopo un riavvio; lotto 38 |
| **Finestra chiusa e riaperta mentre la regola aspetta** | Partono due attese, e il clima si spegne allo scadere della prima (c'era già prima del lotto 38) | Accettato |
| **Azione programmata rifiutata dal motore** | Diventava «non riuscita» senza una riga nelle Decisioni con il motivo | Corretto il 10 novembre (`0e1d04a`), nel lotto 38 |
| **Caldaia comandata a mano senza sensore** | Un comando a mano sulla caldaia vale anche se poi il sensore smette di rispondere (D-164): il relè resta acceso senza sosta, anche a casa vuota | Accettato (risposta 1105), con la notifica «caldaia senza regolazione» dal 13 novembre |
| **Telecomando del climatizzatore** | I limiti di temperatura non valgono per il telecomando, e il sistema non vede la temperatura scelta: vede solo acceso o spento, dal consumo, e solo se c'è il misuratore | Accettato |
| **Climatizzatore spento col telecomando** | Viene creduto spento solo dopo 5 minuti di consumo sotto 15 W: nei primi 5 minuti l'app lo mostra acceso | Accettato (risposta 1101) |
| **Sensore della finestra senza segnale** | Una finestra il cui sensore va offline conta come chiusa: se è davvero aperta, si scalda finché qualcuno non interviene | Accettato (risposta 1102) |
| **Il motore non sa la stagione** | In comfort la caldaia è abilitata alla temperatura di comfort tutto l'anno: una notte fresca d'estate può accenderla | Da decidere (P-90, osservazione E1) |
| **Caldaia rotta con il comando che funziona** | Nessun avviso se la temperatura resta sotto l'antigelo e non risale | Da decidere (P-90, osservazione E2) |
| **Prezzo dell'Excel** | L'importo usa il prezzo in vigore il giorno in cui si scarica il file, anche per i mesi passati | Accettato (scritto in guida) |

## Orari e cambio d'ora

| Limite | Cosa succede | Stato |
|---|---|---|
| **Ora doppia** | A ottobre un'ora che capita due volte si salva sempre la prima volta (ora legale): dal sito non si può scegliere la seconda | Accettato |
| **Simulatore nelle notti del cambio** | Check-in e check-out a un'ora inesistente o doppia seguono la regola della Programmazione, ma senza la riga di spiegazione: è uno strumento di prova | Accettato |
| **Simulatore prima del caricamento** | Se l'appartamento non è ancora caricato, i valori proposti si calcolano con l'ora italiana; cambia solo il giorno proposto per un appartamento su un altro fuso, l'invio usa sempre il suo fuso | Accettato |
| **Cambio d'ora nel rodaggio** | Il prossimo è il 28 marzo 2027, dopo la consegna: è provato solo dalle prove automatiche (D-210) | Accettato |

## Broker MQTT (installato sulla VM il 10 novembre; nessun dispositivo vero collegato)

| Limite | Cosa succede | Stato |
|---|---|---|
| **Permesso DNS della VM tolto (15 novembre, difetto E-31)** | Senza il permesso su `domhouse-dns-lab@`, il certificato del broker non si può rinnovare. Il prossimo rinnovo è intorno al 10 gennaio 2027; l'allarme sulla scadenza scatta a 14 giorni. La riga «broker cert renew failed» oggi non ha un allarme | **Rimettere il permesso (procedura `docs/procedura-permesso-dns.md`, D4) quando `cert_days` ≤ 35, ai primi di gennaio 2027**, dopo la correzione di E-31 |
| **Certificato pubblico su uno Shelly Gen4** | Nessuna fonte elenca le autorità incluse nel firmware | Da verificare con la prova su un Gen4 (bloccante) |
| **Prefisso con la barra** | La documentazione non conferma che `topic_prefix` accetti `/` né che valga per le richieste RPC | Da verificare sulla stessa prova; se non vale, i permessi vanno adattati |
| **Keep-alive e dimensione dei messaggi Shelly** | Non noti: per ora nessun limite sul keep-alive e pacchetti fino a 256 KB | Da fissare dopo la prova |
| **Coda per dispositivo** | 1000 messaggi o 1 MB, oltre si scarta; alla riconnessione il connector rilegge lo stato | Accettato |
| **Memoria del broker** | Limite di 400 MB configurato, mai raggiunto nelle prove | Da provare |
| **Numeri misurati sul PC** | 186 MB con 5000 dispositivi; non misurati la memoria libera sulla VM e la CPU reale della e2-small | Da misurare alla prima installazione |
| **Motori sulla stessa rete interna** | Si raggiungono fra loro, protetti dalla chiave API; anche attraverso l'indirizzo interno della VM (10.198.0.2), quindi il motore `dev` raggiunge le API degli altri | Accettato (controllo di sicurezza del 17 novembre, rilievo C3) |
| **Righe del broker nei log** | Non sono JSON e finiscono nel log dei motori | Da verificare alla prima installazione |
| **Credenziali del connector** | Passate come variabili `SHELLY_MQTT_*` nel file `/etc/domhouse/<apt>.env` (600 di root) del motore; il connector usa l'ingresso interno del broker (172.30.83.2:1883, senza TLS, rete `domhouse-broker-internal`), non la 8883 pubblica | Fatto (lotto 39); verificato sulla VM il 17 novembre (controllo di sicurezza del passo 3) |
| **Utente di un accesso rifiutato** | Mosquitto scrive il Client ID, non l'utente: per questo ogni Shelly usa un Client ID uguale al suo utente. Chi prova da fuori può scegliere un Client ID qualsiasi e uscire dal conteggio dell'allarme; il limite sui collegamenti vale lo stesso | Accettato |
| **Limite per indirizzo** | Vale solo sugli indirizzi della VM, oggi solo IPv4 pubblico | Accettato |
| **Ordine all'avvio** | Montaggio del disco delle chiavi prima di Docker e limite sui collegamenti: non provabili sul PC | Da verificare al primo riavvio vero della VM |
| **Righe di Mosquitto in Cloud Logging** | Arrivano solo se l'agente della VM tiene le righe non JSON dei container | Da verificare dopo l'installazione |
| **Conto Let's Encrypt** | lego non sa disattivarlo: se la sua chiave uscisse, si apre un conto nuovo e si revocano i certificati vecchi | Accettato |
| **Comandi accodati per i dispositivi offline** | Il broker conserva le sessioni 14 giorni: se uno Shelly si collega con sessione non pulita, una richiesta inviata con QoS 1 mentre è scollegato verrebbe eseguita al ritorno, in ritardo | Deciso e provato sul broker vero (D-215, risposta 744): richieste con QoS 0, che il broker non conserva mai per chi è scollegato; sessioni di tutto il broker che scadono dopo 1 ora. La sessione pulita sugli Shelly non è impostabile. Sulla VM con la procedura del lotto 38 |
| **Risposte a nome di un altro dispositivo** | Oggi, dentro lo stesso appartamento, ogni dispositivo può scrivere sul topic delle risposte al connector | Deciso (D-215): un topic di risposta per dispositivo; da applicare al broker (o1) |
| **Cambio della configurazione del broker** | Un cambio di `mosquitto.conf` arrivava al broker solo con un riavvio a mano | Corretto nel lotto 39 (`0ae12ba`): `install` riavvia il broker quando la configurazione è cambiata; sulla VM con la prossima procedura |
| **Motore dopo un riavvio della VM** | Se Docker partisse prima dell'indirizzo interno, il motore non aprirebbe la porta. Provato l'11 novembre: non succede (rete a 5,7 s, Docker a 11,5 s) | Protezione in più nel lotto 39 (`e3551f7`): all'avvio un'unità aspetta l'indirizzo e accende i motori fermi; sulla VM con la prossima procedura |
| **Motore fermato a mano** | Dal lotto 39 il controllo ogni 5 minuti riaccende un motore il cui contenitore è fermo: un motore fermato a mano con `docker stop` riparte entro 5 minuti; non esiste un «fermo apposta» (i comandi di `engine-vm.sh` come il ripristino sono protetti da un blocco) | Accettato |
| **Mosquitto 3.0** | Toglierà opzioni che usiamo: serviranno i plugin prima di aggiornare | Da fare prima di aggiornare |
| **Ricarica con file non validi** | Fa uscire il broker: i file si controllano prima | Accettato |
| **Dispositivi tolti** | La loro password resta nelle versioni vecchie del segreto, che il broker non legge | Accettato |

## Documenti

| Limite | Cosa succede | Stato |
|---|---|---|
| **Versione scritta nella suite di conformità** | Due commenti in `contract/conformance/` (README e `conftest.py`) dicono 1.0.4, mentre il contratto è 1.0.5. La cartella `contract/` non si tocca (regola 1 di `CLAUDE.md`; unica eccezione la 1.0.5, D-107) | Accettato: solo commenti, nessun effetto sulle prove |

## Dispositivi (dal laboratorio di Youssouf)

| Limite | Cosa succede | Stato |
|---|---|---|
| **Sensore temperatura e umidità** | Trasmette ogni 60 secondi: la caldaia può reagire fino a un minuto dopo | Accettato |
| **Sensore di movimento** | A riposo trasmette ogni 15 minuti; sul movimento trasmette subito | Accettato |
| **Portata Bluetooth** | Circa 10 metri al chiuso dal dispositivo che fa da ponte | Da verificare in appartamento |
| **Gen4 in modalità Zigbee** | I sensori Bluetooth spariscono: i Gen4 restano in Wi-Fi | Vincolo di installazione |
| **Infrarossi** | Il climatizzatore non dà conferma di ritorno: l'esito si deduce dal consumo | Accettato |
| **Portata dell'Athom** | Non dichiarata dal produttore; sotto 4–5 metri serve un trasmettitore più potente | Da misurare |
| **Relè della caldaia senza sicurezza propria** | Se la catena si interrompe (server, broker, motore, Wi-Fi della caldaia), il relè resta com'era: o scalda per tutto il fermo, o a casa vuota l'antigelo non agisce | Da fare con Youssouf prima del pilota: spegnimento automatico sul relè e rinnovo dal motore (P-90 S4) |
| **Due split sullo stesso misuratore** | Lo stato dei due split si confonde (uno spento risulta acceso) | Da chiedere al cliente se ci sono dual split (P-90 S8) |
| **Split fermo a temperatura raggiunta** | Sotto 15 W viene creduto spento; con alcuni modelli in riscaldamento il consumo a riposo è basso | Da misurare al collaudo per ogni modello e regolare la soglia per appartamento (P-90 S9) |
| **Orologio del ponte Bluetooth** | Dalla #12 di Youssouf (unita il 15 novembre, `bbe3e7c`, non ancora pubblicata) uno scarto d'orologio del ponte oltre 300 s si adotta solo se una seconda lettura, almeno 5 minuti dopo, dà lo stesso valore. Il caso visto al banco (ponte riavviato con l'orologio indietro di circa 1750 s) è chiuso. **Resta un caso:** se l'orologio sbagliato dura più di 5 minuti, viene confermato, e un sensore morto può sembrare vivo | Da misurare al banco da Youssouf (quanto ci mette il ponte a rimettere l'ora dopo un riavvio) |
| **Ponte con l'orologio avanti (R1)** | Con un ponte che ha l'orologio stabilmente **avanti** di oltre 5 minuti, per i 5 minuti di attesa dopo ogni ricollegamento un sensore morto da poco può tornare in linea con la sua lettura vecchia. Prima della #12 non succedeva. È raro: gli Shelly prendono l'ora da internet | Correzione chiesta a Youssouf il 16 novembre |
| **Sensori offline dopo un riavvio del ponte** | Con un ponte ripartito con l'orologio indietro, per circa 5 minuti i suoi sensori risultano offline, anche se sono vivi (prezzo voluto della risposta 1113). Un contatto della finestra offline vale chiuso: se la regola della finestra aveva spento il clima, il clima si riaccende | Accettato |
| **Sensore che esce da un errore di lettura** | Quando il ponte smette di segnalare l'errore di un sensore, questo torna online entro 5 minuti, non entro 30 secondi: la rilettura si fa al massimo ogni 5 minuti per ponte (#10) | Accettato |
| **Dispositivo sostituito con lo stesso nome interno** (pagina «Stato dei dispositivi», non ancora pubblicata) | Se uno Shelly guasto si sostituisce tenendo lo stesso `device_id`, il nuovo compare «Offline da …» invece di «Mai collegato», perché eredita l'ultima volta visto del vecchio | Accettato finché lo strumento A (catalogo) non lo distingue |
| **Comando a una presa appena staccata** (E-35, 16 novembre) | Nei 60–90 secondi dopo lo stacco, prima che il broker se ne accorga, la presa risulta ancora in linea e il comando parte. Ora l'app dice che il dispositivo non ha risposto e la decisione «Il dispositivo non ha risposto: riprova, e se succede ancora controlla che sia acceso e collegato» (un tempo scaduto può essere anche un ponte lento o un messaggio perso). Il motore riconosce il caso dalla nota tecnica del connector («transport timeout»): è una traduzione provvisoria | Da togliere quando il connector di Youssouf manderà direttamente `device_offline` (domanda del 16 novembre) |
| **Stanza tolta dal catalogo** (dalla PR #17 di Youssouf, catalogo vuoto e riavvio con un catalogo nuovo) | Al riavvio un dispositivo già salvato riprende la stanza scritta nel database del motore anche se il catalogo nuovo non ha più quella stanza: il dispositivo risulta in una stanza che non esiste | Da decidere con A4 (modulo del catalogo); trovato dalla revisione della PR #17 il 17 novembre |
| **Comandi a mano della caldaia senza minimo fra commutazioni (E-37)** | Il termostato automatico rispetta i 5 minuti fra due commutazioni (D-126), i comandi dati a mano dall'app no: clic ripetuti possono accendere e spegnere il relè in pochi secondi (visto su `lab-01` il 18 novembre: 11 comandi in 7 secondi). Con una caldaia vera può rovinarla | **Corretto nel codice** (`9576073`, o1, 18 novembre): accensione a mano dentro il minimo rimandata allo scadere (la fa il termostato), spegnimento sempre immediato. **Installato su `lab-01` il 19 novembre**; da pubblicare; giro completo delle prove da fare |
| **Il broker può non ripartire dopo un riavvio della VM (E-38, 19 novembre)** | Al riavvio della VM o di Docker, se un motore con dispositivi veri partiva prima del broker poteva prendersi l'indirizzo interno fisso del broker: il broker restava spento. Visto il 19 novembre dopo il riavvio della finestra del passo 3; ripristinato a mano | **Corretto e provato** (o1, `63ef157`, installato il 19 novembre con `docs/procedura-e38-vm.md`): gli indirizzi automatici della rete interna stanno da `.128` in su, il `.2` del broker resta fuori; dopo un riavvio di prova della VM broker, motori e agente sono ripartiti da soli |
| **Accessi rifiutati: conto che si può gonfiare** (A5, revisione del codice, 20 novembre; revocati 21 novembre) | Chi conosce l'utente di un dispositivo vero (`<appartamento>.<dispositivo>`), o di un dispositivo revocato nelle ultime 24 ore (risposta 1211), può farne salire il conto collegandosi al broker con una password sbagliata: la pagina mostrerebbe rifiuti anche se lo Shelly è a posto, e per un revocato «Lo Shelly prova ancora a collegarsi: spegnilo» anche se lo Shelly è già spento | Accettato; A5 non ancora installato |
| **Accessi rifiutati con il controllo della VM fermo** (A5, revisione del codice) | Se il controllo ogni 5 minuti della VM non gira, il server mostra «nessun rifiuto» invece di «non lo so»; se ne accorge l'allarme «VM muta» | Accettato; A5 non ancora installato |
| **Matter non si spegne via MQTT sul firmware 1.x** (EM Mini 1.7.0, Plug 1.8.99; Youssouf, 18 novembre) | La chiamata `Matter.SetConfig` risponde senza errore ma Matter resta acceso, anche dopo un riavvio; sullo Shelly 1 con la 2.2.0 funziona | Aggirato: nelle istruzioni dei kit Matter si spegne dalla pagina web dello Shelly. Dal 18 novembre i tre Shelly del banco sono sulla 2.x (prova 1154) e Matter resta spento dopo l'aggiornamento; la chiamata via MQTT sulla 2.x di EM Mini e Plug non è ancora stata riprovata |
| **Finestra di configurazione dopo l'aggiornamento del firmware** (prova 1154, 18 novembre) | Per circa 4 minuti dopo l'aggiornamento lo Shelly riaccende da solo Bluetooth, Matter e access point, poi li richiude: in quei minuti le impostazioni 1153 sembrano cambiate (visto sull'EM Mini: chiamate Bluetooth riaccese) | Accettato: nelle istruzioni dei kit le impostazioni si ricontrollano dopo quei 4 minuti |
| **Ritorno al firmware 1.x** (prova 1154, 18 novembre) | Non documentato da Shelly e non provato: caricare a mano una versione vecchia potrebbe far perdere i dati di fabbrica (es. accesso al Cloud) o non accettare il campo `provision: complete` della 2.x | Accettato: l'aggiornamento alla 2.x si considera senza ritorno; un'eventuale prova solo su un dispositivo di scorta |
| **Relè al ritorno della corrente e interruttore a muro** (impostazione 1153, 18 novembre) | Con «restore_last» il relè riprende l'ultimo stato che aveva. Uno Shelly 1 con l'ingresso in modalità «follow» e un interruttore a muro collegato, dopo un blackout, non segue la posizione dell'interruttore finché qualcuno non lo muove. Al banco non cambia niente | Da decidere nelle istruzioni dei kit (come impostare l'ingresso dello Shelly della caldaia) |
