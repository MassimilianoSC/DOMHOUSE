# Scelte tecniche e costi di DOMHOUSE

*Aggiornato il 10 novembre 2026. Configurazioni lette su Google Cloud lo stesso giorno, in sola lettura.*

**A cosa serve:** raccoglie in un posto solo come è fatta DOMHOUSE, perché è fatta così e quanto costa.
Serve al committente per spiegarlo al cliente.

**Regola (D-208):** ogni scelta sullo stack tecnico e ogni spesa che ne deriva si scrive qui, in modo permanente.
I numeri «D-x», «E-x» e «C-x» rimandano alle decisioni, agli errori e ai criteri del registro (`docs/registro.md`).

## 1. Parole usate

| Parola | Cosa vuol dire |
|---|---|
| **Stack** | L'insieme delle tecnologie con cui è costruita l'app |
| **Google Cloud** | I servizi di Google su cui gira tutto, in un solo progetto (`domotica-poc-511707`) |
| **Regione** | Il centro dati dove gira un servizio. Quasi tutto sta a Milano (`europe-west8`) |
| **Server (BFF)** | Il programma che sta fra l'app e gli appartamenti: controlla chi entra e smista le richieste |
| **Motore** | Il programma che governa un appartamento: regole, comandi, sicurezza. Uno per appartamento |
| **VM** | Un computer virtuale sempre acceso, affittato da Google |
| **Istanza** | Una copia in esecuzione del server. Google ne accende o spegne secondo il traffico |
| **Broker MQTT** | Il «centralino» a cui si collegano i dispositivi Shelly per mandare e ricevere messaggi |
| **Certificato TLS** | Il documento digitale che permette il collegamento cifrato e dimostra chi è il server |
| **Staging** | La copia di prova dell'app, separata dalla produzione, per provare prima di pubblicare |
| **Produzione** | L'app vera, quella che userà il cliente |

## 2. Panoramica

| Pezzo | Cosa fa | Tecnologia | Dove gira | Decisioni |
|---|---|---|---|---|
| **App (sito)** | Quello che vedono gestori e amministratori, su telefono e computer | App web installabile (PWA), React | Firebase Hosting di Google | C-5 |
| **Server (BFF)** | Accesso, permessi, smistamento verso i motori, notifiche, aggiornamenti in diretta | Python (FastAPI) su Cloud Run | Milano | D-197, D-201 |
| **Motore per appartamento** | Regole, comandi ai dispositivi, antigelo, prenotazioni | Programma nostro in Python, un container per appartamento | VM `langbrain-dev`, Milano | D-104 |
| **Dati dell'app** | Utenti, organizzazioni, appartamenti, registro attività | Firestore (database di Google) | Milano | D-136 |
| **Dati del motore** | Stato e storia di ogni appartamento | SQLite, un file per appartamento | Sulla VM | D-104 |
| **Accesso** | Login con email e password o con Google | Firebase Authentication | Google | D-141 |
| **Notifiche** | Avvisi sul telefono | Firebase Cloud Messaging | Google | D-39, D-201 |
| **Assistente** | Risponde a domande sull'appartamento e propone azioni | Gemini 3.5 Flash, più una «gemella» Flash-Lite | Google, solo in Europa | D-180, D-187 |
| **Broker MQTT** | Riceve i collegamenti degli Shelly | Mosquitto 2.1.2 | VM, Milano (non ancora installato) | D-196, D-206 |
| **Dispositivi** | Relè, misuratori, prese, sensori, infrarossi per i climatizzatori | Shelly Gen4 (e Plug M Gen3), sensori Shelly BLU, Athom AR01 | Negli appartamenti | D-196 |
| **Dominio di prova** | Il nome con cui i dispositivi trovano il broker | `dh-lab.eu`, DNS su Google | Register.it e Google | D-206 |
| **Monitoraggio** | Email se il server non risponde o un motore tace | Cloud Monitoring | Google | D-104, D-197 |
| **Backup** | Copie per ripartire dopo un guasto | Copia giornaliera dei motori, snapshot del disco, backup di Firestore | Google, Milano | D-104, D-134 |

## 3. Le scelte e il perché

### Server su Cloud Run

- **Cosa:** il server gira su Cloud Run, un servizio di Google che accende le copie del server da solo.
- **Perché:** nessun computer da mantenere; si paga in base alle copie accese.
- **Produzione:** sempre almeno 1 copia accesa, al massimo 3 (D-201).
- **Staging:** 0 copie quando nessuno lo usa, al massimo 1 (D-197, D-202). La prima apertura aspetta qualche secondo.

### Aggiornamenti in diretta e fermo del 23 ottobre (E-27)

- **Cosa:** l'app riceve gli aggiornamenti con un collegamento aperto verso il server (SSE, «stream»).
- **Il problema:** il 23 ottobre la produzione si è fermata due volte. Gli stream restavano aperti un'ora e una copia vecchia del server non si spegneva.
- **Cosa abbiamo fatto:** stream chiusi dal server ogni 4 minuti e riaperti dall'app; niente stream con l'app in sottofondo; richieste di al massimo 300 secondi; allarme sugli errori 429.
- **Soluzione strutturale (D-201):** fino a 3 copie del server. Le notifiche e i lavori a orario si «prenotano» sul database, così non partono due volte.
- **Stato:** la causa ultima è interna a Google e non è dimostrata. Si verifica alla prossima sostituzione di copia (vedi `docs/limiti-noti.md`).

### Un motore per appartamento, su una sola VM

- **Cosa:** ogni appartamento ha il suo motore, in un container separato sulla stessa VM (e2-small, Milano).
- **Perché:** il motore governa la casa anche quando nessuno usa l'app; un guasto in un appartamento non tocca gli altri.
- **Sicurezza:** la VM non ha indirizzo pubblico; il server la raggiunge dalla rete interna di Google.
- **Scartato:** LangBrain, il motore esterno previsto all'inizio. Il committente non lo ha voluto (D-104).
- **Limite accettato per ora:** se la VM si ferma, si fermano tutti i motori.

### Ambienti separati: staging e produzione

- Due copie del server e due database nello stesso progetto (D-134, D-136).
- La produzione si pubblica solo se lo staging ha lo stesso codice (D-203).
- Gli appartamenti dimostrativi stanno solo in staging (D-202).
- Si pubblica poco e a gruppi, perché ogni pubblicazione richiede tempo (D-205).

### Dispositivi: Shelly Gen4 con MQTT e broker nostro

- **Cosa:** i dispositivi Shelly si collegano con il protocollo MQTT a un broker nostro sulla VM (D-196).
- **Perché:** ogni dispositivo ha il suo utente e la sua password; sappiamo subito se è collegato.
- **Scartati:**
  - il cloud di Shelly: dipenderemmo da un servizio esterno;
  - il collegamento WebSocket attraverso Cloud Run: le connessioni lunghe sono proprio ciò che ha causato il fermo E-27.
- **Perché Gen4:** è il catalogo che si troverà all'installazione; Zigbee e Matter integrati; differenza di costo minima.
- **Infrarossi:** due Athom AR01 in laboratorio (uno trasmette, uno fa da climatizzatore finto). Anche loro parlano MQTT.
- **Chi lo costruisce:** il collegamento fra dispositivi e motore («connector») lo scrive Youssouf.

### Come i dispositivi raggiungono la VM: da decidere

- **Opzione A:** indirizzo pubblico fisso sulla VM, aperta solo sulla porta 8883. Circa 3,5 € al mese. Consigliata dall'analisi.
- **Opzione D:** un bilanciatore di Google davanti alla VM, che resta senza indirizzo pubblico. Circa 16 € al mese.
- **Scartate:** la cifratura fatta da Google (le password dei dispositivi passerebbero in chiaro) e il proxy TCP (costo incerto).
- **Dettagli:** `docs/analisi-ingresso-mqtt-2026-11-09.md`.

### Dominio e certificato

- **Dominio di prova:** `dh-lab.eu`, comprato dal committente su Register.it il 9 novembre 2026, rinnovo automatico (D-206).
- **Dopo:** si dismette quando i dispositivi passano al dominio del cliente.
- **Certificato:** Let's Encrypt, gratuito, rinnovato in automatico. Il rinnovo usa l'identità della VM, nessun file di chiave di Google.
- **Da provare:** che uno Shelly Gen4 accetti il certificato senza installare nulla (prova bloccante).

### Chiavi del certificato su un disco separato

- **Cosa:** le due chiavi del certificato stanno su un piccolo disco a parte, senza copie automatiche (D-207, D-208).
- **Perché:** il disco principale viene copiato ogni sera e le copie restano 30 giorni su Google. Le chiavi non devono finire lì: il certificato si rifà, non si ripristina.
- **Condizioni:** leggibili solo dal broker; il broker non parte se il disco manca, e scatta un allarme.
- **Stato:** disco `langbrain-dev-tls` creato e collegato alla VM il 10 novembre 2026. Restano la preparazione del disco e la procedura di revoca e riemissione, da provare una volta (o1).

### Database: Firestore per l'app, SQLite per i motori

- **Firestore:** database gestito da Google, a Milano; lo scrive solo il server. Backup giornaliero, conservato 14 giorni, solo per la produzione: lo staging contiene dati di prova e non ha backup.
- **SQLite:** un file per appartamento sulla VM. Copia ogni sera, conservata 7 giorni, più lo snapshot del disco.

### Assistente: modello solo in Europa

- **Modello:** Gemini 3.5 Flash; se non risponde entro 3 secondi parte una gemella, Gemini 3.5 Flash-Lite (D-187).
- **Perché:** nelle prove 50 risposte corrette su 50, in circa 1 secondo.
- **Località:** solo Europa. Il server si rifiuta di partire con un modello fuori dall'Europa (D-180).
- **Tetto di spesa:** 20 € al mese per tutto il progetto, avviso all'80 %; massimo 50 domande al giorno per appartamento (D-143).

### Accesso

- Oggi: email e password, oppure account Google.
- Deciso: verifica in due passaggi con app di autenticazione, costo 0 €, prima del primo appartamento vero (D-141). Non ancora fatta.

## 4. Costi

**Come leggere:** «misurato» viene dalla fatturazione; «stimato» viene dal listino di Google. Le stime vanno riconfermate in Fatturazione.

### Spese su Google Cloud

| Voce | Costo indicativo | Tipo | Fonte |
|---|---|---|---|
| Server di produzione (min 1, max 3) | 45–60 € al mese | Fisso; sale solo se servono più copie | Stimato da listino, 9 nov |
| Server di staging (min 0) | Quasi zero quando nessuno lo usa | A consumo | Stimato, D-197 |
| VM dei motori (e2-small) con disco da 30 GB | Circa 0,6 € al giorno (circa 18 € al mese), più gli snapshot | Fisso | Stimato da listino, 23 ott |
| Uscita verso internet della VM (Cloud NAT) | Circa 0,1 € al giorno, più l'indirizzo esterno | Fisso | Stimato da listino, 23 ott |
| Disco separato per le chiavi del certificato (10 GB) | 0,42 € al mese | Fisso | Listino Google letto il 10 nov alle 9:15 |
| Zona DNS di `dh-lab.eu` | Circa 0,18 € al mese | Fisso | Stimato, analisi del 9 nov |
| Ingresso dei dispositivi | Opzione A circa 3,5 € al mese; opzione D circa 16 € al mese | Fisso | Stimato, **da decidere** |
| Assistente | Circa 2 € al mese per appartamento con 20 domande al giorno; tetto 20 € al mese | A consumo | Stimato da listini di terze parti, D-187 |
| Archivio delle immagini del server e dei motori (1,6 GB, oltre la quota gratuita di 0,5 GB) | Pochi centesimi al mese | A consumo | Stimato, 10 nov |
| Database, segreti, log, monitoraggio | Trascurabili | A consumo | Stimato, 23 ott |
| Hosting dell'app, notifiche, verifica in due passaggi con app | 0 € | Gratuito | D-39, D-141 |

### Spesa misurata

- **Ottobre, fino al 23:** 18,85 € in tutto (di cui 0,81 € per l'assistente).
- Erano quasi tutti costi fissi di risorse sempre accese, non costi d'uso (registro, §7 «Costi»).
- Allora lo staging era sempre acceso; dal lotto 35 si spegne da solo.

### Fuori da Google Cloud

| Voce | Costo | Fonte |
|---|---|---|
| Dominio `dh-lab.eu` (Register.it) | 0 € il primo anno (promozione). Rinnovo annuale, scadenza 9 novembre 2027: prezzo del rinnovo da leggere prima della scadenza | D-206, committente 10 nov |
| Kit di laboratorio (Shelly, sensori, Athom) | 131,30 €, una tantum | D-196, committente 10 nov |

### Controlli sulla spesa

- Budget «DOMHOUSE 50 EUR al mese», con avvisi al 50, 90 e 100 % (D-134).
- Budget «Budget-Domotica-POC» da 100 €, precedente.
- Tetto dell'assistente: 20 € al mese.

### Spegnimento quando nessuno usa l'app (D-195)

- Si spengono: la VM, le copie del server (minimo 0), il controllo di raggiungibilità.
- Restano e costano: disco della VM, snapshot, archivio immagini, segreti. Circa 0,2–0,3 € al giorno.
- Per riaccendere bastano pochi comandi, scritti nella procedura (passo M17).

## 5. Sicurezza in breve

- **Credenziali sulla VM (C-12):** nessuna credenziale di Google Cloud sulla VM. Le chiavi dei certificati TLS stanno sulla VM, leggibili solo dal servizio che le usa, fuori dalle copie che escono dalla VM.
- **Segreti:** password e chiavi stanno in Secret Manager di Google, mai nei file del codice né nei documenti.
- **Identità:** server e VM usano identità gestite da Google, senza file di chiave.
- **Dati in Europa:** servizi a Milano; modello dell'assistente solo in Europa (D-180).
- **Rete:** la VM non ha indirizzo pubblico. Con l'opzione A ne avrà uno, aperto solo sulla porta dei dispositivi.

## 6. Come si aggiorna questo file

- Ogni nuova scelta tecnica o spesa entra qui insieme alla sua decisione nel registro.
- Una cifra stimata diventa «misurata» quando la si legge in Fatturazione.
- Quando una voce «da decidere» viene decisa, si aggiorna la riga e si cita la decisione.
- I limiti noti stanno in `docs/limiti-noti.md`, non qui.
