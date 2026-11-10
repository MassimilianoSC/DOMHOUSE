# Limiti noti di DOMHOUSE

*Aggiornato il 9 novembre 2026 (lotto 36). Regola del committente (D-204): ogni limite che conosciamo sta scritto qui.*

**Come leggerlo:** «Stato» dice se il limite è accettato, se è in lavorazione o se va ancora verificato.

## Notifiche

| Limite | Cosa succede | Stato |
|---|---|---|
| **Consegna parziale** | Se una notifica raggiunge solo alcuni telefoni per un errore temporaneo, conta come mandata e non viene ritentata: ritentarla la rimanderebbe a tutti | Accettato |
| **Doppio raro** | Se un server cade mentre manda una notifica, la stessa notifica può partire due volte, mai zero | Accettato |
| **Tempi di recupero** | Se un server cade, la notifica viene ripresa entro pochi minuti; il riepilogo settimanale entro 75 minuti | Accettato |
| **Eventi molto vecchi** | Se nessun server resta collegato a un motore per più di un'ora, gli eventi più vecchi di un'ora non generano notifiche; resta una riga nei log | Accettato |
| **Primo avvio del lotto 36** | Un dispositivo già offline da meno di 6 giorni manda una notifica, anche se era già stata mandata | Una tantum |

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
| **A server spento** | Niente notifiche, e gli eventi di quel periodo non si recuperano | Voluto |
| **Dimostrativi** | Ripartono dai valori iniziali a ogni avvio del server | Voluto |
| **Nessun backup del database** | Il database dello staging non ha backup pianificati: contiene solo dati di prova | Voluto |

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
| **Avvio lento (E-29)** | Dal lotto 37, se l'app non si apre entro 15 secondi compare «Non riesco ad aprire la pagina» con «Ricarica»; se la risposta arriva prima di 30 secondi, l'app entra da sola. Oltre i 30 secondi si finisce sulla pagina di accesso, ma la sessione resta valida. Sullo staging spento il messaggio può comparire per qualche secondo | Accettato |
| **Chiamate che scadono** | Dal lotto 37 ogni chiamata al server ha 30 secondi (90 per le operazioni lente); poi compare «Server non raggiungibile» | Accettato |
| **Comando scaduto** | Un'operazione che scade può essere andata a buon fine sul server: il messaggio non lo può sapere. Comandi e salvataggi non vengono ritentati in automatico | Accettato |
| **Letture ritentate** | Le letture vengono ritentate una volta: prima dell'errore possono passare fino a 60 secondi | Accettato |
| **Errore di disegno** | Dal lotto 37 il messaggio sostituisce tutta l'app, menu compreso, e ciò che si stava scrivendo si perde con la ricarica | Accettato |
| **Pagina di accesso** | Se l'avvio non riesce resta il modulo; il messaggio compare solo sulle pagine protette, e tentare l'accesso dà l'errore normale | Accettato |
| **Correzione E-29 non provata del tutto** | Non provata con Firebase vero, su Safari o su un telefono vero | Da verificare |

## Broker MQTT (dal 9 novembre, non ancora installato)

| Limite | Cosa succede | Stato |
|---|---|---|
| **Certificato pubblico su uno Shelly Gen4** | Nessuna fonte elenca le autorità incluse nel firmware | Da verificare con la prova su un Gen4 (bloccante) |
| **Prefisso con la barra** | La documentazione non conferma che `topic_prefix` accetti `/` né che valga per le richieste RPC | Da verificare sulla stessa prova; se non vale, i permessi vanno adattati |
| **Keep-alive e dimensione dei messaggi Shelly** | Non noti: per ora nessun limite sul keep-alive e pacchetti fino a 256 KB | Da fissare dopo la prova |
| **Coda per dispositivo** | 1000 messaggi o 1 MB, oltre si scarta; alla riconnessione il connector rilegge lo stato | Accettato |
| **Memoria del broker** | Limite di 400 MB configurato, mai raggiunto nelle prove | Da provare |
| **Numeri misurati sul PC** | 186 MB con 5000 dispositivi; non misurati la memoria libera sulla VM e la CPU reale della e2-small | Da misurare alla prima installazione |
| **Motori sulla stessa rete interna** | Si raggiungono fra loro, protetti dalla chiave API | Accettato |
| **Righe del broker nei log** | Non sono JSON e finiscono nel log dei motori | Da verificare alla prima installazione |
| **Credenziali del connector** | Non ancora passate come variabili `SHELLY_*` | Quando entra il modulo MQTT di Youssouf |
| **Mosquitto 3.0** | Toglierà opzioni che usiamo: serviranno i plugin prima di aggiornare | Da fare prima di aggiornare |
| **Ricarica con file non validi** | Fa uscire il broker: i file si controllano prima | Accettato |
| **Dispositivi tolti** | La loro password resta nelle versioni vecchie del segreto, che il broker non legge | Accettato |

## Dispositivi (dal laboratorio di Youssouf)

| Limite | Cosa succede | Stato |
|---|---|---|
| **Sensore temperatura e umidità** | Trasmette ogni 60 secondi: la caldaia può reagire fino a un minuto dopo | Accettato |
| **Sensore di movimento** | A riposo trasmette ogni 15 minuti; sul movimento trasmette subito | Accettato |
| **Portata Bluetooth** | Circa 10 metri al chiuso dal dispositivo che fa da ponte | Da verificare in appartamento |
| **Gen4 in modalità Zigbee** | I sensori Bluetooth spariscono: i Gen4 restano in Wi-Fi | Vincolo di installazione |
| **Infrarossi** | Il climatizzatore non dà conferma di ritorno: l'esito si deduce dal consumo | Accettato |
| **Portata dell'Athom** | Non dichiarata dal produttore; sotto 4–5 metri serve un trasmettitore più potente | Da misurare |
