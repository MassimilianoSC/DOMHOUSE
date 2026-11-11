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
3. **L'EM Mini Gen4 manda la potenza ogni ~14 s**, non al cambio: la conferma a consumo del §2.5 (variazione entro
   2 s) è a rischio con questo misuratore. La misura con un carico vero è prevista nel pomeriggio dell'11 (§2.2).
4. **Per il catalogo dei BLU propongo il kit preparato in ufficio**: l'elettricista non configura niente e nessuno
   detta un MAC (§4.1). Risponde anche al §7.3 punto 4.
5. I profili di **Shelly 1 Gen4 ed EM Mini Gen4** sono pronti sul ramo `shelly-gen4`, che ora va riallineato a
   `main` prima della pull request (§5).

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

### 2.2 EM Mini Gen4: ritardo della potenza
- `em1:0` (con `act_power`) arriva ogni ~14,4 s, e il suo `ts` è ~13,5 s prima dell'arrivo. Confermato anche
  nelle catture di oggi, sempre senza carico.
- Non sappiamo ancora se una variazione di carico anticipa la notifica o aspetta il giro. Se aspetta, il misuratore
  non rispetta «ogni variazione di `watts` entro 2 secondi» del §2.5 e la conferma `power` dello split può dare
  `no_confirmation` anche quando lo split si è acceso.
- Attenzione nel leggere la misura: il flusso del connector non manda mai un `ts` all'indietro, quindi dopo un
  comando al relè la notifica dell'EM Mini può uscire con il `ts` del cambio del relè. La misura va letta sulla
  cattura MQTT (ora di arrivo e `ts` del dispositivo), non sugli `StateChange`.
- Oggi alle 15 l'elettricista chiude la catena del banco (EM Mini → Shelly 1 → presa). Carico: un caricabatterie
  sopra i 20 W. Porto i tempi misurati.

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
- **Da verificare** oggi alle 15: che l'associazione sopravviva allo spegnimento del ponte.
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
sono cose critiche, si aspetta il primo pacchetto. Lo misuro alle 15.

### 4.6 Già nel ramo `shelly-gen4`
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
| `shelly-gen4` | Profili Shelly 1 Gen4 (`switch`/`heating`) ed EM Mini Gen4 (`power_meter`), finti e prove | Un commit sopra `shelly-banco` prima dell'unione: 466 passate, 3 saltate (Python 3.11 in Docker, `python -m pytest engine -q -rs`). Ora è 146 commit dietro `main`: lo riallineo e apro la pull request |
| `shelly-blu` | I tre sensori BLU, `GetComponents`, soglia del contatto | In lavorazione dall'11 novembre |
| `developYouss` | `DESIGN.md` (pull request #1) | Aperta; da aggiornare con queste note e con `connector-v2.md` |

Catture di laboratorio di oggi (associazioni, ritmi, pagine di `GetComponents`): entrano anonimizzate in
`tests/fixtures/` con il ramo `shelly-blu`.
