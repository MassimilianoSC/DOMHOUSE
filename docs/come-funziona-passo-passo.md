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
