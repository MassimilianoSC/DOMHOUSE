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
