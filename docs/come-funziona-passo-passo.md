# Come funziona DOMHOUSE, passo per passo

*Dalla conversazione fra il committente e la memoria storica, iniziata l'11 novembre 2026. Si scrive un passo alla
volta: la spiegazione, le domande del committente con le risposte, e per ogni passo che cosa resta da fare, da parte
nostra e da parte di Youssouf. Scritto per chi conosce la web app ma non la parte dei dispositivi.*

---

## Passo 1. Il quadro generale: tre zone

Il percorso fra la presa elettrica nell'appartamento e il telefono del gestore attraversa tre zone.

```
 ZONA 1                  ZONA 2                         ZONA 3
 L'APPARTAMENTO          LA "CENTRALE"                  LA WEB APP
 (in casa)               (un computer di Google:        (il mondo del committente)
                          la "VM")
 ┌──────────────┐        ┌──────────────────────┐       ┌───────────────┐
 │ presa Shelly │◄──────►│ broker               │       │ server        │
 │ relè Shelly  │internet│   ▲                  │       │ database      │
 │ sensori      │        │   ▼                  │       │ sito sul      │
 │              │        │ connector ◄► motore  │◄─────►│ telefono      │
 └──────────────┘        └──────────────────────┘       └───────────────┘
   Youssouf               broker e motore: noi            noi
                          connector: Youssouf
```

| Zona | Cosa c'è | Di chi è |
|---|---|---|
| **1. L'appartamento** | Le scatolette Shelly (presa, relè dietro la caldaia, sensori) con il loro firmware, cioè il programma del produttore, che nessuno di noi scrive | Youssouf: sceglie i modelli, li installa, li configura |
| **2. La centrale** | Un computer di Google sempre acceso (la VM). Dentro: il **motore**, il «cervello» di ogni appartamento; il **broker**, il «centralino» a cui gli Shelly telefonano; il **connector**, il «traduttore» fra la lingua degli Shelly e quella del motore | Motore e broker: noi. Connector: Youssouf |
| **3. La web app** | Il sito sul telefono, il server che controlla chi entra, il database con utenti e appartamenti | Noi |

**L'idea chiave:** il committente e Youssouf non si toccano direttamente. Si incontrano nella centrale, e le regole
dell'incontro sono scritte nel contratto del connector (`engine/connector/connector-v2.md`).

### Domande e risposte

**«Ieri lo Shelly di Youssouf si vedeva dal Wi-Fi del PC: che conseguenze ha? Chi lo vede?»**

- Uno Shelly acceso e non ancora configurato crea una sua piccola rete Wi-Fi (per esempio `ShellyPlugMG3-A1B2C3`):
  serve solo alla prima installazione, per dirgli a quale Wi-Fi di casa collegarsi e a quale broker telefonare.
- La vede solo chi è vicino, nella zona 1. La centrale e la web app non la vedono: per loro lo Shelly esiste solo
  quando telefona al broker con il suo nome utente e la sua password.
- Negli appartamenti veri quella rete va spenta alla fine della messa in servizio, altrimenti un ospite potrebbe
  collegarsi e cambiare le impostazioni.

**«Gli Shelly non sono tutti uguali: come distinguiamo quello della caldaia da un sensore?»**

- **Il modello dice che cosa lo Shelly *sa* fare:**

  | Modello | Che cosa sa fare |
  |---|---|
  | Plug M Gen3 (presa) | Accende e spegne ciò che ci si attacca e ne misura il consumo |
  | Shelly 1 Gen4 (relè) | Interruttore nascosto dietro un apparecchio, per esempio la caldaia |
  | EM Mini Gen4 | Misura il consumo di una linea, per esempio quella del climatizzatore |
  | BLU H&T | Sensore di temperatura e umidità, a batteria |
  | BLU Door/Window | Sensore di apertura di una finestra |
  | Athom AR01 (non Shelly) | Telecomando a infrarossi del climatizzatore |

- Ogni apparecchio ha un **codice di fabbrica unico**, come una targa: per esempio `shellyplugmg3-A1B2C3D4E5F6`.
- **Il catalogo dice che cosa quello Shelly *fa* in quell'appartamento.** È una tabella per appartamento, scritta da
  Youssouf: per ogni codice di fabbrica il nome che vedrà il gestore, la stanza, che cosa fa nella nostra lingua e i
  legami (per esempio «la caldaia si regola con il sensore del soggiorno").

  | Codice di fabbrica | Nome nell'app | Stanza | Che cosa fa |
  |---|---|---|---|
  | `shelly1g4-…` | Caldaia | Soggiorno | Accende e spegne la caldaia, regolata dal sensore del soggiorno |
  | `shellyplugmg3-…` | Presa stufetta | Camera | Accende e spegne, misura il consumo |
  | sensore BLU `…` | Sensore soggiorno | Soggiorno | Temperatura e umidità |

- Il catalogo sta nella centrale: lo leggono il connector, per capire chi sta parlando, e il motore. La web app riceve
  solo il risultato pulito («Caldaia, soggiorno, accesa»); il codice di fabbrica il gestore non lo vede mai.

**«Nell'app abbiamo già dei nomi, come "Presa stufetta camera": vanno comunicati a Youssouf, o erano finti?»**

- Quelli di oggi sono **finti**: vengono dai dispositivi simulati degli appartamenti dimostrativi.
- I nomi veri li scrive Youssouf nel catalogo di ogni appartamento, guardando la casa reale. Il gestore può poi
  cambiarli dall'app: il motore ricorda il nome nuovo.
- Già deciso, e scritto nel contratto: le **otto capacità** (accende e spegne, consumo, climatizzatore, caldaia,
  temperatura, umidità, finestra, movimento), i **due legami** (caldaia-sensore, climatizzatore-misuratore), le
  **regole del catalogo** (codici unici, niente password, una stanza per dispositivo).
- Non ancora detto a Youssouf: uno **stile per i nomi**, come nei dimostrativi: che cosa è, più la stanza se ce n'è
  più d'uno («Caldaia», «Climatizzatore soggiorno», «Presa stufetta camera», «Finestra camera», «Sensore soggiorno»).

### Cosa resta da fare (passo 1)

| Chi | Che cosa | Per quando |
|---|---|---|
| Youssouf | Mandarci i **codici di fabbrica** degli Shelly del laboratorio da collegare (per esempio Plug M Gen3, Shelly 1 Gen4, EM Mini Gen4) | Prima della prova con il nostro broker (tappa A) |
| Youssouf | Scrivere il **catalogo di `lab-01`**, con i nomi nello stile dei dimostrativi | Prima del test dall'app (tappa B) |
| Youssouf | Nella procedura di messa in servizio: **spegnere la rete Wi-Fi di installazione** di ogni Shelly | Prima di un appartamento vero |
| Youssouf | Aggiornare il suo documento di progetto (`DESIGN.md`, ancora a Gen2) a Gen4 e MQTT | Senza urgenza |
| Noi (committente) | Creare sul broker gli **utenti dei dispositivi** con quei codici (procedura G2, passo B5) | Appena arrivano i codici |
| Noi (committente) | Decidere **come Youssouf riceve le password** degli Shelly (proposta: permesso di leggere solo quel segreto) | Appena arrivano i codici |
| Noi (memoria storica) | Comunicare a Youssouf lo **stile dei nomi** del catalogo | Nel prossimo messaggio |
| Noi (o1) | Dare al motore di `lab-01` le impostazioni del connector e farlo leggere il catalogo | Lotto 39 |

---

## Passo 2. Il viaggio di un dato: «la presa sta consumando 12 watt»

Un messaggio vero, registrato nel laboratorio di Youssouf il 10 novembre. La presa è nell'appartamento di laboratorio
`lab-01`.

```
 ZONA 1               ZONA 2 (la centrale)                          ZONA 3 (web app)
 presa ──①──► ②─internet─► ③ broker ──► ④ connector ──► ⑤ motore ──► ⑥ server ──► ⑦ telefono
```

| Tappa | Cosa succede | Di chi è |
|---|---|---|
| ① In casa | La presa misura 12,3 W; il suo firmware decide da solo di avvisare, quando il valore cambia e a intervalli regolari | Youssouf (sceglie e configura) |
| ② Verso la centrale | All'accensione la presa «telefona» una volta al broker (`mqtt.dh-lab.eu`, porta 8883, cifrato), con il suo utente e la sua password, e la linea resta aperta. Percorso: Wi-Fi di casa, router, internet, VM. Scrive nel suo dialetto: «io sono `shellyplugmg3-…`, la mia uscita 0 consuma 12,3 W» | Youssouf configura; noi diamo nome, utente e password |
| ③ Il broker | Controlla che la presa scriva solo nel suo spazio e passa il messaggio a chi ascolta: il traduttore di `lab-01`. Frazioni di secondo | Noi (installato il 10 novembre) |
| ④ Il connector | Guarda nel catalogo chi è `shellyplugmg3-…` e riscrive nella nostra lingua: «Presa stufetta: consumo 12,3 W» | Youssouf (gira dentro il nostro motore) |
| ⑤ Il motore | Aggiorna lo stato, i kWh di oggi, salva, controlla le regole e annuncia la novità con un numero progressivo | Noi |
| ⑥ Il server | Ascolta gli annunci del motore e li inoltra ai telefoni dei gestori con il permesso di vedere l'appartamento | Noi |
| ⑦ Il sito | Aggiorna la scheda: «Presa stufetta · 12,3 W», senza ricaricare | Noi |

Dalla presa al telefono: in genere pochi secondi; conta soprattutto quando lo Shelly decide di avvisare.

**Cosa è provato:** da ⑤ a ⑦ funziona da settimane con i dispositivi simulati; ③ è installato e provato, senza
Shelly veri; ④ è provato da Youssouf con i suoi test e con i messaggi registrati, non ancora dentro il nostro motore;
① e ② funzionano nel laboratorio verso il broker di prova di Youssouf, non ancora verso il nostro.

### Domande e risposte

**«E MQTT?»** È la lingua fra gli Shelly e il broker: una **bacheca con tante caselle**. Chi scrive mette un
messaggio in una casella; chi è iscritto la riceve subito; il broker tiene le caselle e controlla chi può scrivere
dove. Le caselle di una presa di `lab-01`:

| Casella | Cosa ci passa | Chi scrive |
|---|---|---|
| `lab-01/<codice presa>/events/rpc` | Le novità: «consumo 12,3 W» | La presa |
| `lab-01/<codice presa>/online` | «Sono collegata» / «non ci sono più» | La presa (o il broker per lei, se cade) |
| `lab-01/<codice presa>/rpc` | I comandi: «accenditi» | Il traduttore |
| `lab-01/<codice presa>/connector/rpc` | La risposta: «fatto, sono accesa» | La presa |

Ogni presa scrive solo nelle caselle che cominciano con il suo codice: non può parlare a nome di un'altra (D-223).

**«Abbiamo un traduttore finto per le prove?»** Sì: il **connector simulato**, scritto da noi, con dispositivi finti
dentro di sé. Fa funzionare i dimostrativi, l'appartamento `dev` e il Simulatore. Rispetta lo stesso contratto del
connector di Youssouf: per il motore sono intercambiabili (`CONNECTOR=simulated` oppure `CONNECTOR=shelly`). Le prove
comuni a ogni connector le supera il simulato da sempre e, verificato da o1 il 10 novembre, anche quello di Youssouf.

**«Come arriva il traduttore di Youssouf sulla VM? Pubblica lui?»** No:

1. Youssouf scrive il codice in un suo ramo su GitHub.
2. Apre una pull request («vorrei che questo entrasse nel progetto»): è la #4.
3. o1 la rivede (fatto l'11 novembre), il committente la approva: solo allora entra nel progetto.
4. Al primo lotto pubblicato con `publish-all.sh`, lanciato dal committente, entra nella versione nuova del motore.
5. Per `lab-01` si crea sulla VM un motore che usa il traduttore Shelly e il catalogo del laboratorio: lo prepara o1,
   lo lancia il committente.

Youssouf ha sul progetto i permessi di amministratore della VM (D-47, 16 ottobre): tecnicamente potrebbe entrarci, ma la
procedura prevede che non pubblichi lui. Da ridiscutere prima della consegna.

**«Se Youssouf non scrive il connector definitivo, i test non possono partire?»**

- I test della nostra parte girano già da settimane con il connector simulato.
- Il test con uno Shelly vero ha bisogno di un traduttore che parli Shelly: il simulato non parla con dispositivi
  reali.
- **La tappa A** (lo Shelly si collega al nostro broker) **non ha bisogno di nessun traduttore**: o1 ascolta il broker
  con l'utente del connector di `lab-01` e legge i messaggi così come arrivano. Si fa appena Youssouf configura uno
  Shelly.
- **La tappa B** (dall'app alla presa) ha bisogno del suo traduttore, ma non di quello definitivo: basta quello della
  pull request #4, già completo per la Plug M Gen3, con la correzione di una riga sull'invio dei comandi. Gli altri
  modelli arriveranno uno alla volta.

**«Quindi il traduttore di Youssouf è parziale?»** Sì, in un senso preciso: è un **interprete con un dizionario**.

- **L'interprete c'è già**, ed è la parte più difficile: collegarsi al broker e restare collegato, leggere il catalogo,
  capire quando un dispositivo sparisce (soglie di offline per tipo), mandare un comando e aspettarne la conferma,
  rifare la «fotografia» quando un dispositivo si ricollega, leggere il livello delle batterie. Vale per tutti i
  modelli; le prove comuni dicono che rispetta il contratto.
- **Il dizionario ha una sola pagina: la Plug M Gen3.** Per ogni modello nuovo serve una pagina: come quel modello
  parla e che cosa significano i suoi messaggi, con prove e messaggi registrati in laboratorio.

| Pagina che manca | Impegno (stima della memoria storica, da confermare da Youssouf) |
|---|---|
| Shelly 1 Gen4, relè della caldaia | Piccolo: molto simile alla presa |
| EM Mini Gen4, misuratore del climatizzatore | Piccolo: solo consumo |
| Sensori Bluetooth (temperatura e umidità, finestra, movimento) | Medio: passano da uno Shelly Gen4 «ponte» e hanno un formato diverso; il catalogo oggi non sa descrivere un ponte con più sensori |
| Athom AR01, telecomando a infrarossi | Il più diverso: non è uno Shelly, parla un altro dialetto (Tasmota) con caselle diverse; punto aperto del contratto (§7.3, punto 5) |

Per il primo test basta la pagina della presa. Per un appartamento vero servono almeno caldaia e sensori, e
l'infrarosso se ci sono climatizzatori.

### Cosa resta da fare (passo 2)

| Chi | Che cosa | Per quando |
|---|---|---|
| Youssouf | Configurare uno o più Shelly del laboratorio per telefonare al nostro broker (procedura G2, passo B5) | Tappa A |
| Noi (o1) | Preparare il comando di sola lettura per ascoltare il broker con l'utente del connector di `lab-01` durante la tappa A | Tappa A |
| Committente | Approvare l'unione della pull request #4 (rivista da o1 l'11 novembre) | Prima della tappa B |
| Noi (o1) | All'unione: le librerie del motore nella CI e le prove Shelly nel giro completo | Il giorno dell'unione |
| Committente | Pubblicare il lotto con il traduttore di Youssouf (`publish-all.sh`) | Prima della tappa B |
| Noi (o1), committente | Creare sulla VM il motore di `lab-01` con il traduttore Shelly e il catalogo | Prima della tappa B |
| Committente | Rivalutare i permessi di Youssouf sulla VM (D-47) | Prima della consegna |
| Youssouf | Le pagine del dizionario per gli altri modelli: relè della caldaia, misuratore, sensori Bluetooth con il ponte, infrarosso Athom; e il catalogo con gli Shelly «ponte» | Prima di un appartamento vero; stima da chiedergli |

---

## Passo 3. Il viaggio inverso: «il gestore accende la presa dal telefono»

```
 ZONA 3 (web app)                       ZONA 2 (la centrale)                        ZONA 1
 telefono ─①─► server ─②─► motore ─③─► connector ─④─► broker ─⑤─internet─► presa
     ▲                                                                         │
     └──────────── ⑥ la conferma torna indietro per la strada del passo 2 ─────┘
```

| Tappa | Cosa succede | Di chi è |
|---|---|---|
| ① Il tocco | Il gestore tocca «Accendi»; il sito manda la richiesta al server con un codice per seguirla; sulla scheda compare «in corso» | Noi |
| ② Il server | Controlla chi è, se può comandare (la sola lettura no), se vede l'appartamento; passa la richiesta al motore giusto | Noi |
| ③ Il motore | Controlla le regole (con una finestra aperta non accende il riscaldamento); se il dispositivo è offline risponde subito «non raggiungibile»; altrimenti dice al traduttore lo **stato da raggiungere**: «la presa deve essere accesa» | Noi |
| ④ Il connector | Riscrive in dialetto Shelly e mette il comando nella casella della presa (`lab-01/<codice presa>/rpc`), nel modo **«non conservato»**: se la presa non è collegata il comando si perde invece di restare in attesa, così una stufa non si accende un'ora dopo | Youssouf (correzione di una riga da fare) |
| ⑤ Il broker e la presa | Il broker consegna il comando sulla linea aperta; la presa scatta | Noi il broker, il produttore la presa |
| ⑥ La conferma | La presa risponde nella sua casella di risposta («fatto, sono accesa») e manda la novità («uscita accesa»); i messaggi rifanno la strada del passo 2; la scheda passa a «eseguito» | Tutti |

**Tempi:** il motore aspetta la conferma al massimo 9 secondi, poi il comando risulta «nessuna risposta» e il gestore
lo vede. Con una presa vera in un Wi-Fi normale ci aspettiamo uno o due secondi: si misurerà nel test vero.

**Due casi speciali:**

- **La caldaia non si comanda come la presa.** Il gestore non dice «accendi il relè», dice «riscaldamento abilitato a
  21 °C». Poi il motore, ogni minuto, confronta la temperatura del sensore con i 21 °C e dà al relè l'ordine «accenditi»
  o «spegniti». Così la caldaia segue la temperatura anche quando nessuno guarda l'app.
- **Il climatizzatore a infrarossi non può confermare:** il telecomando «spara» il comando ma non sa se è arrivato.
  Il motore guarda il **consumo** sulla linea del climatizzatore: se sale, si è acceso. Per questo nel laboratorio c'è
  anche il misuratore EM Mini.

**Cosa è provato:** da ① a ③ e il ritorno al telefono funzionano da settimane con il connector simulato; ④ e ⑤ con una
presa vera sono il cuore della tappa B.

### Cosa resta da fare (passo 3)

| Chi | Che cosa | Per quando |
|---|---|---|
| Youssouf | Mandare i comandi nel modo «non conservato» (QoS 0) nel suo connector, con le sue prove | Prima del primo comando vero (tappa B) |
| Youssouf | Per il relè della caldaia: la pagina del dizionario dello Shelly 1 Gen4 e il legame con il sensore nel catalogo | Prima di un appartamento vero |
| Youssouf | Per il climatizzatore: la pagina dell'Athom e il legame con il misuratore EM Mini nel catalogo; misurare in laboratorio in quanti secondi sale il consumo dopo il comando (il motore aspetta un aumento di 20 W entro circa 8 secondi) | Prima di un appartamento con climatizzatori |
| Noi (tutti) | Misurare nel test vero il tempo fra il tocco e «eseguito» | Tappa B |

---

## Passo 4. Quando qualcosa si rompe

| Cosa si rompe | Cosa vede il motore | Cosa vede il gestore | Notifica |
|---|---|---|---|
| **Una presa si stacca** (spina tolta, guasto) | Il broker avvisa subito «non c'è più» per lei | La scheda passa a «non in linea»; i comandi a quella presa vengono rifiutati subito | Sì, se resta offline più dei minuti della regola «Avviso dispositivo offline» (15 di base) |
| **Un sensore a batteria tace** (batteria scarica) | Dopo una soglia di silenzio diversa per tipo (un sensore di movimento a riposo parla solo ogni 15 minuti, quindi la sua soglia è più lunga) | «Non in linea»; dal livello della batteria si capirà se è scarica | Come sopra |
| **Cade internet in casa** | Tutti i dispositivi dell'appartamento «non ci sono più» | Tutte le schede «non in linea»; in casa le cose restano come sono (la presa accesa resta accesa) | Sì, dopo i minuti della regola |
| **Si ferma il traduttore** | «Collegamento ai dispositivi perso» | Avviso «sistema domotico» e riga nelle Decisioni | Sì, «… sistema domotico non raggiungibile» |
| **Si ferma la VM** (motore e broker) | Niente: il motore è fermo | «Sistema domotico non raggiungibile» | Sì, dopo i minuti della regola (dal lotto 38) |
| **Si ferma il server della web app** | Il motore continua da solo: regole e programmazioni vanno avanti | L'app non si apre | No: email di allarme a chi gestisce la piattaforma (oggi HQE) |

- **Al ritorno ognuno si ricollega da solo:** gli Shelly richiamano il broker, il traduttore rifà la «fotografia» dello
  stato di tutti i dispositivi, il server si ricollega al motore. Provato l'11 novembre spegnendo e riaccendendo la VM:
  tutto è ripartito in pochi secondi.
- **I comandi dati mentre un dispositivo è offline non restano in coda:** vengono rifiutati subito. Meglio un rifiuto
  chiaro che una stufa accesa ore dopo.

### Decisioni e osservazioni

- **«Non in linea» subito (D-225):** il motore segna un dispositivo «non in linea» appena il traduttore lo sa; i minuti
  della regola servono solo a decidere quando mandare la notifica. Così l'app mostra sempre la verità e non dice «in
  linea» per una presa che rifiuta i comandi. Il contratto dell'app, scritto a ottobre, diceva «dopo i minuti»: la frase
  è superata e resta (il contratto non si modifica); la spiegazione è nel contratto del connector (§2.6) e nei limiti
  noti.
- **A chi arrivano le email di allarme:** oggi solo all'indirizzo del committente in HQE. Con il cliente probabilmente
  dovranno arrivare (anche) a lui; dipende dal rapporto con il cliente, ancora da definire. Si decide con il passaggio del
  progetto al cliente (P-81). Tecnicamente basta cambiare o aggiungere un indirizzo.

### Cosa resta da fare (passo 4)

| Chi | Che cosa | Per quando |
|---|---|---|
| Youssouf | Segnalare un dispositivo offline appena lo sa, senza aspettare i minuti della regola (contratto del connector, §2.6) | Già così nel suo connector: da confermare nel test |
| Youssouf | Per ogni tipo di sensore a batteria, la soglia di silenzio giusta (il suo file delle soglie di offline per tipo) | Prima dei sensori Bluetooth |
| Noi (o1) | Scrivere in `bff/API.md` che «non in linea» è immediato (D-225) | Lotto 39 |
| Committente | Decidere a chi arrivano le email di allarme dopo la consegna | Con il passaggio al cliente (P-81) |
| Tutti | Nel test vero: staccare la presa e controllare «non in linea» subito, la notifica dopo i minuti, il ritorno da solo | Tappa B |
