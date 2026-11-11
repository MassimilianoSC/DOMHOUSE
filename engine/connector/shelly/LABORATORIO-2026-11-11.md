# Laboratorio dell'11 novembre 2026: Gen4, sensori BLU e scelte da confermare

Note di Youssouf dalla mattina dell'11 novembre, per Massimiliano. Tre parti: cosa è stato **misurato** sui
dispositivi veri, cosa ho **deciso per andare avanti** (da confermare), cosa **propongo o chiedo**. Qui non ci sono
id né MAC reali: i dispositivi sono indicati con il modello. I rimandi «§» sono a `engine/connector/connector-v2.md`.

Banco: Plug M Gen3 (firmware 1.8.99), Shelly 1 Gen4 (2.0.3), EM Mini Gen4 (1.7.0), tre sensori BLU ZB (H&T
`SBHT-203C`, Motion `SBMO-103Z`, contatto porta/finestra), broker Mosquitto di laboratorio sul PC, motore in Docker
sul PC con `CONNECTOR=shelly`.

## 1. In breve

1. **La soglia offline del contatto porta/finestra oggi è sbagliata**: 200 s nel file, ma il sensore a riposo
   trasmette ogni 300 s. Così com'è andrebbe offline a ogni giro. Proposta: 920 s, con la stessa regola del file
   (§3.4).
2. **I sensori BLU non compaiono in `Shelly.GetStatus`**: per la fotografia del §2.6 serve una seconda chiamata,
   `Shelly.GetComponents`, che è paginata (§3.1).
3. **L'EM Mini Gen4 rispetta i 2 secondi del §2.5** (aggiornato alle 15:45). A riposo manda la potenza ogni
   ~14 s, ed era il mio dubbio di stamattina; sotto carico notifica la variazione in 50 ms e poi circa ogni secondo
   (§2.2).
4. **Per il catalogo dei BLU propongo il kit preparato in ufficio**: l'elettricista non configura niente e nessuno
   detta un MAC (§4.1). Risponde anche al §7.3 punto 4.
5. I profili di **Shelly 1 Gen4 ed EM Mini Gen4** e i sensori BLU sono nella pull request #7; nel pomeriggio sono
   stati provati dal vivo con il motore (§7).

## 2. Dispositivi alimentati

### 2.1 Ripartenza dopo uno spegnimento completo
La scatola è rimasta senza corrente tutta la notte, con il DHCP attivo e l'access point dei dispositivi spento.
- Alla riaccensione tutti e tre si sono ricollegati da soli a Wi-Fi e broker, senza reset: configurazione Wi-Fi e
  MQTT restano in memoria.
- Il connector parla solo con il broker, quindi il cambio di IP dei dispositivi non conta. Conta l'indirizzo del
  broker: in laboratorio è l'IP del PC, negli appartamenti è il nome del §7.1.
- La pagina web di uno Shelly risponde qualche secondo dopo che il dispositivo risulta `online` sul broker.
- Il motore, partito prima del broker, si è agganciato da solo con attesa crescente (91 s in quel caso), poi
  `connector up` e dispositivo online.

### 2.2 EM Mini Gen4: la potenza, a riposo e sotto carico
**A riposo** (misure del mattino, senza carico): `em1:0` con `act_power` arriva ogni ~14,4 s, e il suo `ts` è
~13,5 s prima dell'arrivo. Da qui il dubbio sul §2.5.

**Sotto carico** (pomeriggio, catena EM Mini → Shelly 1 → presa montata dall'elettricista, carico: caricabatterie di
un portatile, ~40 W). Orari di arrivo al motore, comando dato dall'API del motore:

| Evento | Ora | Dopo il cambio del relè |
|---|---|---|
| Relè acceso | 15:38:23,73 | |
| Prima variazione di `watts` (3,4 W) | 15:38:23,79 | 0,05 s |
| `watts` sopra i 20 W (30,0 W) | 15:38:26,78 | 3,1 s |
| Relè spento | 15:40:02,65 | |
| `watts` sotto i 15 W (1,4 W) | 15:40:04,44 | 1,8 s |
| Seconda accensione: `watts` sopra i 20 W | 15:40:47,60 | 2,9 s |

- **Il misuratore notifica subito quando la potenza cambia**, poi circa una volta al secondo finché varia. I ~14 s
  sono solo il ritmo a riposo. «Ogni variazione di `watts` entro 2 secondi» del §2.5 è rispettato.
- I ~3 s per superare i 20 W sono del carico: il caricabatterie sale per gradi (3, 7, 19, 30, 48 W). Stanno dentro
  i 10 s della conferma. Con uno split vero la salita sarà diversa e va misurata su quello.
- Nel leggere queste misure: il flusso del connector non manda mai un `ts` all'indietro, quindi il `ts` di uno
  `StateChange` dell'EM Mini può coincidere con quello del relè. Per i tempi valgono gli orari di arrivo.
- La presa è alimentata solo a relè acceso, e `watts` torna a zero allo spegnimento: il cablaggio è verificato.

### 2.3 Shelly 1 Gen4
- `switch:0` con `output` e `source`, nessuna misura; ogni minuto una notifica con solo `counts`, da ignorare.
- Dopo un riavvio la prima `NotifyFullStatus` ha l'orologio sbagliato (~1750 s): il connector usa già l'ora di
  ricezione oltre lo scarto ammesso.
- Lo Zigbee sui Gen4 è un **firmware alternativo** (`S1G4ZB`), non una modalità che convive con Wi-Fi e MQTT.
  Restiamo sul Bluetooth per i sensori.

### 2.4 Firmware
- Per lo Shelly 1 Gen4 è disponibile la 2.2.0 (del 9 novembre); il banco è sulla 2.0.3. Non ho aggiornato a metà
  delle prove.
- Domanda aperta: su quali versioni ci fermiamo per gli appartamenti (oggi 1.8.99, 2.0.3, 1.7.0)?
- Idea: `Shelly.Update` si può chiamare via RPC, quindi dallo stesso canale MQTT si può lanciare da remoto una
  versione già provata in laboratorio, un appartamento alla volta. Strumento a parte, fuori dal connector.

### 2.5 Verso il §7.3
- **Punto 10** (`online` conservato): un abbonato nuovo a `<prefisso>/#` riceve subito `online true` di tutti e
  tre i dispositivi, prima di qualunque notifica. Quindi sì, è un messaggio conservato, per Gen3 e Gen4. Misurato
  sul broker di laboratorio.
- **Punto 4** e **punto 7**: vedi §4.1 e §3.5.

## 3. Sensori BLU

Ponte usato: Shelly 1 Gen4. Per errore i sensori sono passati anche da Plug M Gen3 ed EM Mini Gen4: **fanno da
ponte tutti e tre**.

### 3.1 Come li espone il ponte
- Ogni sensore associato è un componente `bthomedevice:<n>` (MAC in `config.addr`; in `status`: `battery`,
  `packet_id`, `rssi`, `last_updated_ts`) più un `bthomesensor:<n>` per ogni misura (`config.addr`,
  `config.obj_id`; `status.value`, `status.last_updated_ts`).
- **I numeri `<n>` li assegna il ponte e non sono stabili**: lo stesso sensore ha avuto numeri diversi su ponti
  diversi. Una misura si riconosce da MAC + `obj_id`.
- **`Shelly.GetStatus` non li contiene** (solo `"bthome": {}`). Si leggono con `Shelly.GetComponents`
  (`dynamic_only: true`), che restituisce anche `offset` e `total`: **10 componenti per pagina**. Con tre sensori
  sono già 13. Chi leggesse solo la prima pagina perderebbe gli ultimi sensori senza nessun errore.
- Le notifiche portano solo il numero del componente, senza MAC né `obj_id`: serve la mappa letta da
  `GetComponents`. Aggiunta e rimozione di un sensore producono eventi `component_added` e `component_removed`.
- Un `bthomesensor` è notificato **solo quando il valore cambia**. `bthomedevice` è notificato **al massimo una
  volta al minuto** e riporta l'ultimo pacchetto già ricevuto: l'ora dell'evento è `last_updated_ts`, non il `ts`
  della notifica. Un pacchetto nuovo si riconosce da `packet_id`.
- Subito dopo l'associazione i valori sono `null` fino al primo pacchetto.

### 3.2 Le misure

| Sensore | `model_id` | `obj_id` → misura | Capacità (§2.3) |
|---|---|---|---|
| H&T | 17 | 69 temperatura °C · 46 umidità % · 1 batteria % | `temperature.celsius`, `humidity.percent` |
| Motion | 19 | 33 movimento (booleano) · 100 livello di luce 0–2 · 1 batteria % | `motion.detected` |
| Contatto | 20 | 45 aperto (booleano) · 63 inclinazione in gradi · 100 livello di luce 0–2 · 1 batteria % | `contact.open` |

Movimento e contatto arrivano già come booleani; temperatura e umidità come numeri. La batteria è anche in
`bthomedevice.battery`.

### 3.3 I ritmi misurati

| Sensore | A riposo | Agli eventi |
|---|---|---|
| H&T | un pacchetto ogni ~60 s | nessun invio anticipato: la temperatura è scesa di 7 °C in cinque minuti con aggiornamenti solo al minuto |
| Motion | un pacchetto ogni 906 s, che produce solo la notifica di `bthomedevice` | `true` immediato; silenzio finché vede movimento; `false` 63 s dopo l'ultimo movimento |
| Contatto | un pacchetto ogni 302 s (misurato due volte) | apertura e chiusura immediate, anche a 4 s l'una dall'altra; l'inclinazione manda un valore ogni ~5 s mentre si muove |

- Il cambio del livello di luce non fa partire un pacchetto: viaggia con quello successivo.
- Il Motion appena associato può restare muto per minuti se ha davanti una persona: lo stato era già «movimento» e
  non cambia. Non è un guasto.

### 3.4 Soglie offline: un valore da correggere
La regola di `offline_thresholds.toml` (tre beacon persi più 20 s) regge con le misure, tranne un caso:

| Tipo | Beacon nel file (documentazione) | Beacon misurato | Soglia oggi | Soglia con la misura |
|---|---|---|---|---|
| `blu_ht` | 60 s | ~60 s | 200 s | 200 s |
| `blu_door_window` | 60 s | **302 s** | 200 s | **920 s** (3 × 300 + 20) |
| `blu_motion` | 900 s | 906 s | 2720 s | 2720 s |

Con 200 s un contatto sano risulterebbe offline a ogni giro. La correzione entra con il ramo `shelly-blu`.
Durante le prove un pacchetto del contatto si è perso (`packet_id` da 45 a 47, 605 s fra i due) con il sensore sul
banco e segnale buono: con 920 s resta online.

Due cose collegate:
- Il «visto l'ultima volta» di un sensore va preso dal `last_updated_ts` più recente fra tutti i suoi componenti,
  `bthomedevice` compreso: per Motion e contatto a riposo arriva solo quello.
- **Proposta, non applicata:** `blu_ht` a 300 s invece di 200. È il sensore che regola la caldaia
  (`links.sensor_device_id`): se va offline per tre pacchetti Bluetooth persi, il motore smette di regolare.

### 3.5 Cifratura (§7.3 punto 7)
I tre sensori sono stati associati **non cifrati** (`encrypted: false` nella scoperta). Per gli appartamenti la
scelta è aperta; con il kit del §4.1 la chiave si imposterebbe al banco.

## 4. Scelte prese per andare avanti (da confermare)

Valgono per il ramo `shelly-blu`, in lavorazione. Sono tutte dalla parte più piccola; quelle che toccano il
formato del catalogo o il contratto le segnalo.

### 4.1 Catalogo dei BLU: kit preparato in ufficio (§7.3 punto 4)
- **Vincolo**: l'elettricista (D-227) deve solo montare. Un MAC dettato a voce è poco affidabile, e un MAC mandato
  a me può restare giorni prima di entrare nel catalogo; non è ancora deciso chi fa l'assistenza.
- **Scelta**: ponte e sensori di un appartamento si associano al banco prima della spedizione. Uno script legge
  `GetComponents` dal ponte e scrive le righe del catalogo; ogni sensore parte con un'etichetta («Finestra
  camera»). Lo script è lo stesso lavoro della messa in servizio già prevista.
- **Nel catalogo**: un sensore dichiara il suo MAC, lo Shelly che fa da ponte e il `type`
  (`shelly: {addr, bridge, type}`); il ponte deve essere un dispositivo dello stesso catalogo. È la risposta che
  propongo al §7.3 punto 4: l'id del broker resta quello dell'apparecchio fisico (il ponte), e i sensori si legano
  al `device_id` con MAC + ponte.
- **Verificato alle 15**: l'associazione sopravvive allo spegnimento del ponte (vedi §7).
- **Limiti**: ponte e sensori viaggiano insieme; sostituire un sensore guasto richiede una nuova associazione sul
  posto. Il processo (chi prepara i kit) lo sto definendo con il team.
- Alternativa tenuta da parte: nessun MAC nel catalogo, il connector lega per tipo e nome. Più comoda sul posto,
  più codice e più casi nel connector.

### 4.2 Un solo ponte per sensore
«Offline insieme al ponte» resta com'è. Il doppio ponte (lo stesso sensore su due Shelly) funziona tecnicamente, ma
copre solo il guasto del singolo Shelly, non blackout né router, e porta duplicati e più casi di prova. Accantonato;
si riapre solo se entrano sensori critici (allagamento, fumo) o se il pilota mostra ponti che si bloccano.

### 4.3 Inclinazione e livello di luce: ignorati
Non sono fra le otto capacità. Ignorarli evita anche le raffiche dell'inclinazione. Vedi §5.2.

### 4.4 `GetComponents` solo sui ponti dichiarati
Chi non ha sensori nel catalogo si comporta come oggi: nessuna chiamata in più sul percorso della Plug. Il prezzo:
un sensore associato allo Shelly sbagliato risulta solo «assente dal suo ponte». Con il kit è un caso raro; la
diagnosi la fa lo script.

### 4.5 Sensore mai sentito: offline fino al primo pacchetto
Con valori `null` il connector non inventa uno stato e non dichiara online (§2.6). Se i valori non sopravvivono al
riavvio del ponte, dopo un blackout il Motion può risultare offline fino a 15 minuti e il contatto fino a 5: non
sono cose critiche, si aspetta il primo pacchetto. Al blackout delle 15 i tre sensori sono tornati online 1,4 s dopo
il ponte, con la loro fotografia (§7).

### 4.6 Dai profili Gen4 (ora nella pull request #7)
- Lo Shelly 1 Gen4 copre `switch` oppure `heating` (mai insieme nel catalogo). `links.sensor_device_id` è
  facoltativo finché non ci sono i BLU: senza, il motore segue solo il comando di una persona.
- `setpoint_min` e `setpoint_max` della caldaia non sono controllati nel catalogo: farlo romperebbe le prove
  esistenti con `heating: {}`.

## 5. Proposte e domande

### 5.1 Soglie offline modificabili dal cliente, per appartamento
Idea emersa con chi lavora all'interfaccia: una pagina di configurazione. Una parte c'è già
(`SHELLY_OFFLINE_THRESHOLDS_PATH` per appartamento, `offline_after_s` sul singolo dispositivo). Mancano la strada
dall'interfaccia al file (oggi le soglie si leggono all'avvio) e dei **minimi**: sotto il doppio del ritmo del
sensore (120, 600 e 1800 s) il sensore risulterebbe sempre offline. Passa per un'API del motore che oggi non c'è:
è una decisione tua.

### 5.2 Inclinazione e luce come capacità nuove
Casi d'uso: finestra a vasistas distinta da finestra spalancata (fermare il riscaldamento solo nel secondo caso),
luci accese solo se è buio. Richiede capacità nuove: da valutare dopo il pilota.

### 5.3 Altre domande
1. Firmware su cui fermarsi, e aggiornamenti da remoto (§2.4).
2. `blu_ht` a 300 s (§3.4).
3. Cifratura dei BLU negli appartamenti (§3.5).
4. Chi fa l'assistenza quando un sensore va sostituito sul posto (§4.1).

## 6. Stato dei rami

| Ramo | Contenuto | Stato |
|---|---|---|
| `shelly-qos0` | Richieste RPC a QoS 0 e ritocchi della revisione della #4 | Pull request #6 |
| `shelly-blu` | Profili Shelly 1 Gen4 ed EM Mini Gen4, i tre sensori BLU, `GetComponents`, soglia del contatto | Pull request #7 (contiene anche il lavoro di `shelly-gen4`, riallineato a `main`) |
| `developYouss` | `DESIGN.md` (pull request #1) | Aperta; da aggiornare con queste note e con `connector-v2.md` |

Le catture di laboratorio di oggi sono anonimizzate in `tests/fixtures/` del ramo `shelly-blu`.

## 7. Prova dal vivo del pomeriggio: sei dispositivi con il motore

Motore in Docker sul PC, costruito dal ramo `shelly-blu`, catalogo con Plug, Shelly 1, EM Mini e i tre sensori
(ponte: Shelly 1). È la prima volta che Gen4 e BLU passano dal connector vero.

- **Avvio**: sei dispositivi online. `Shelly.GetComponents` funziona anche via MQTT, con le due pagine.
- **Blackout** (corrente tolta e ridata alla scatola): i tre sensori vanno offline 31 ms dopo il loro ponte; al
  ritorno sono online 1,4 s dopo il ponte, con la fotografia. L'EM Mini è risultato offline 39 s dopo gli altri:
  probabilmente il broker si è accorto più tardi della sua caduta. Dopo il ritorno, tutti e sei corretti.
- **Comandi al relè**: `turn_on` e `turn_off` entrambi `acked`.
- **Sensori**: apertura e chiusura del contatto con `since` aggiornato; `detected` vero al passaggio, con
  `last_seen`; temperatura e umidità dell'H&T che seguono la mano.
- **Regole del motore**: l'umidità al 90 % (la mano sul sensore) ha fatto scattare `mold_warning`. Il dato dei
  sensori arriva quindi fino alle decisioni.

### Due punti aperti, emersi qui
1. **Lo Shelly 1 che fa da ponte risponde lentamente alle RPC**: fra 69 ms e 2,8 s misurati sul broker, contro i
   78–144 ms della Plug; i due comandi hanno impiegato 4,9 s e 2,5 s in tutto. Causa probabile, non dimostrata: la
   scansione Bluetooth. A 2,8 s siamo vicini ai 3 s di attesa del connector. Da rimisurare con i sensori dissociati
   prima di decidere (attesa più lunga, oppure ponte su un altro Shelly).
2. **La fotografia dei BLU è datata all'inizio della lettura di `GetComponents`**, circa 1 s prima dei dati. Non
   riordina nulla; la correggo nel ramo `shelly-blu`.

Per o1, fuori dal mio perimetro: un `turn_on` ha aspettato 1,6 s nel motore prima di arrivare al connector.
