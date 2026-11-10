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

## Orari e cambio d'ora

| Limite | Cosa succede | Stato |
|---|---|---|
| **Ora doppia** | A ottobre un'ora che capita due volte si salva sempre la prima volta (ora legale): dal sito non si può scegliere la seconda | Accettato |
| **Simulatore nelle notti del cambio** | Check-in e check-out a un'ora inesistente o doppia seguono la regola della Programmazione, ma senza la riga di spiegazione: è uno strumento di prova | Accettato |
| **Simulatore prima del caricamento** | Se l'appartamento non è ancora caricato, i valori proposti si calcolano con l'ora italiana; cambia solo il giorno proposto per un appartamento su un altro fuso, l'invio usa sempre il suo fuso | Accettato |
| **Cambio d'ora nel rodaggio** | Il prossimo è il 28 marzo 2027, dopo la consegna: è provato solo dalle prove automatiche (D-210) | Accettato |

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
| **Utente di un accesso rifiutato** | Mosquitto scrive il Client ID, non l'utente: per questo ogni Shelly usa un Client ID uguale al suo utente. Chi prova da fuori può scegliere un Client ID qualsiasi e uscire dal conteggio dell'allarme; il limite sui collegamenti vale lo stesso | Accettato |
| **Limite per indirizzo** | Vale solo sugli indirizzi della VM, oggi solo IPv4 pubblico | Accettato |
| **Ordine all'avvio** | Montaggio del disco delle chiavi prima di Docker e limite sui collegamenti: non provabili sul PC | Da verificare al primo riavvio vero della VM |
| **Righe di Mosquitto in Cloud Logging** | Arrivano solo se l'agente della VM tiene le righe non JSON dei container | Da verificare dopo l'installazione |
| **Conto Let's Encrypt** | lego non sa disattivarlo: se la sua chiave uscisse, si apre un conto nuovo e si revocano i certificati vecchi | Accettato |
| **Comandi accodati per i dispositivi offline** | Il broker conserva le sessioni 14 giorni: se uno Shelly si collega con sessione non pulita, una richiesta inviata con QoS 1 mentre è scollegato verrebbe eseguita al ritorno, in ritardo | Deciso (D-215): richieste con QoS 0, sessione pulita sui dispositivi, sessioni dei dispositivi che scadono in minuti; da applicare al broker (o1) e da verificare sul Gen4 |
| **Risposte a nome di un altro dispositivo** | Oggi, dentro lo stesso appartamento, ogni dispositivo può scrivere sul topic delle risposte al connector | Deciso (D-215): un topic di risposta per dispositivo; da applicare al broker (o1) |
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
