# Il connector dei dispositivi — specifica per il motore DOMHOUSE

*21 ottobre 2026, approvata da Massimiliano (revisione: solo il numero di versione del contratto, 1.0.5). Nel repository: `engine/connector/connector.md`. Dove si legge
«decide il catalogo» o «da concordare», non è una decisione già presa.*

## 0. In breve

Il motore domotico di DOMHOUSE lo scriviamo noi. È un programma Python (asyncio), uno per appartamento, sulla VM, che
espone all'app l'API del contratto fra app e motore (versione 1.0.5, che non cambia). Il contratto non ti serve:
quello che ti riguarda, cioè le otto capacità dei dispositivi, è nella tabella del §2.3.

Il connector è la parte che parla con i dispositivi reali: dice al motore quali dispositivi ci sono e in che stato
sono, e porta loro i comandi. Tu scrivi il connector per Shelly Gen2; noi scriviamo il resto del motore. Il confine è
un'interfaccia Python piccola e stabile, descritta qui.

## 1. A cosa serve, e cosa resta nel motore

```
  app DOMHOUSE (BFF su Cloud Run)
        │  HTTP: l'API del contratto, /api/v1/…  (chiave X-API-Key)
        ▼
  MOTORE (un processo per appartamento, sulla VM, dati in /data/<apartment_id>)
   · validazione dei comandi e limiti (setpoint_min/max, regola setpoint_limits)
   · regole (finestra aperta, antigelo, antimuffa, pausa del compressore…), priorità
   · modalità (comfort/eco/empty), forzature, programmazioni dalle prenotazioni
   · ciclo di vita dei comandi (command_id, stati, timeout di 10 s, idempotenza)
   · registro delle decisioni, approvazioni, /ask, /_test/state
   · stream degli eventi (SSE) verso l'app, SQLite, consumi orari
        │  interfaccia Python Connector (questo documento)
        ▼
  CONNECTOR  ── traduzione: capacità del contratto ⇄ comandi e notifiche Shelly
             ── trasporto: WebSocket in uscita dai dispositivi / MQTT / cloud Shelly
        ▼
  dispositivi Shelly Gen2 (e quelli che il catalogo vi collega: blaster IR, contatto termostato…)
```

Restano **nel motore**, e il connector non li deve fare:
- validazione e limiti: un fuori limite è `422 out_of_limits`, deciso prima di chiamare il connector;
- regole e priorità: `blocked_by_rule` e `blocked_by_priority`;
- la regolazione della caldaia: il motore decide «acceso/spento» confrontando la temperatura con il setpoint; al
  connector arriva solo l'acceso/spento;
- la verifica «a consumo» dello split a infrarossi (`confirmation: power`), vedi il §2.5;
- le decisioni (`Decision`), lo stream SSE, `/_test/state` (con il connector Shelly risponde 404) e
  `trigger: approval`, che non passa mai dal connector;
- l'ora locale: `kwh_today`, i consumi orari e le date «since» li calcola il motore.

## 2. L'interfaccia

Python 3.11 (l'immagine è `python:3.11-slim`). Tutto asincrono: niente chiamate bloccanti nel ciclo di asyncio; le
librerie bloccanti vanno in `asyncio.to_thread`. Date sempre «aware», in UTC.

### 2.1 Il Protocol

`interface.py` dichiara `CONNECTOR_API_VERSION = "1"`. Ogni connector la ripete in un attributo di classe:

```python
class ShellyConnector:
    api_version = "1"
```

All'avvio il motore confronta `connector.api_version` con la sua `CONNECTOR_API_VERSION`. Se non coincidono **non
parte**: scrive nel log «connector API version mismatch» con le due versioni ed esce con il codice 3. Allo stesso
modo, con il codice 3, si ferma se il connector indicato da `CONNECTOR` non esiste («unknown connector»), se non
offre `make_connector` («connector without make_connector», §2.7), o se `make_connector` fallisce o il suo
pacchetto non si importa, per esempio per una libreria mancante («connector setup failed»). Il
container riparte (`restart: unless-stopped`) e ripete l'errore finché qualcuno non allinea le versioni: si vede
subito, invece di funzionare a metà. Il numero cambia **solo** quando cambia l'interfaccia del §2 in modo
incompatibile (un tipo, un campo obbligatorio, il significato di un esito). Lo cambiamo noi, in una pull request
concordata, insieme a `interface.py` e `tests/test_interface.py`.

```python
class Connector(Protocol):
    async def start(self) -> None
        # avvia trasporto e catalogo; ritorna quando è pronto a ricevere dispositivi.
        # Non aspetta che siano tutti online.
    async def stop(self) -> None
        # chiude tutto in modo pulito (serve alle prove e allo spegnimento del container)
    def rooms(self) -> list[Room]
    def devices(self) -> list[DeviceInfo]
        # il catalogo con l'ultimo stato noto; sempre tutti i dispositivi del catalogo, anche offline
    async def execute(self, cmd: ConnectorCommand, on_progress: Callable[[str], None]) -> CommandResult
    def changes(self) -> AsyncIterator[StateChange]
        # un solo consumatore (il motore); non finisce finché il connector non viene fermato
    def status(self) -> ConnectorStatus
```

Le chiamate di base sono cinque: `start`, `devices`, `execute`, `changes`, `status`; `rooms()` e `stop()` completano
l'interfaccia.

### 2.2 I tipi (dataclass frozen)

```python
Room(room_id: str, name: str)

DeviceInfo(
    device_id: str,          # stabile, scelto nel catalogo (es. "dev-clima-soggiorno"); è l'id che vede l'app
    label: str,              # nome in italiano; il gestore lo può cambiare nell'app: quel cambio lo tiene il motore
    room_id: str,
    online: bool,
    last_seen: datetime | None,
    capabilities: dict[str, dict],   # una chiave per capacità, vedi la tabella del §2.3
    links: dict[str, str])           # collegamenti fra dispositivi, vedi sotto; {} se non ce ne sono

ConnectorCommand(
    command_id: str, correlation_id: str,    # per i log; command_id è unico e puoi usarlo come id della RPC
    device_id: str, capability: str,          # solo "switch", "climate", "heating"
    target: dict,                             # lo STATO COMPLETO da raggiungere, non l'azione del contratto (§2.4)
    deadline: datetime)                       # entro cui restituire l'esito (circa 9 s dopo la creazione)

CommandResult(
    outcome: "confirmed" | "delivered" | "failed",
    reason: "device_offline" | "device_rejected" | "internal_error" | None,
    state: dict | None,       # con "confirmed": lo stato riportato dal dispositivo
    detail: str | None)       # per i log, in inglese breve; mai segreti

StateChange(
    device_id: str,
    kind: "state" | "online",
    capability: str | None,   # con kind="state"
    state: dict | None,       # con kind="state": i campi del dispositivo per quella capacità (§2.3)
    online: bool | None,      # con kind="online"
    ts: datetime)             # quando è successo: ora del dispositivo se affidabile, altrimenti di ricezione

ConnectorStatus(up: bool, connected_devices: int, last_event_at: datetime | None, detail: str | None)
    # il motore lo copia nel suo stato di salute: up=False lo segnala all'app come motore non disponibile
```

**`links`** è un campo **separato** da `capabilities`, apposta: il motore copia `capabilities` nell'elenco dei
dispositivi che manda all'app, mentre `links` non esce mai verso l'app. Le chiavi previste sono due:
- `confirmation_device_id` (solo per un dispositivo con `climate` e `confirmation: power`): il `device_id` del
  dispositivo con `power_meter` che misura lo split. Il motore lo usa per verificare i comandi (§2.5).
- `sensor_device_id` (solo per un dispositivo con `heating`): il `device_id` del dispositivo con `temperature` che
  il motore usa per regolare la caldaia (acceso/spento rispetto al setpoint).

Entrambi devono indicare dispositivi dello stesso catalogo, con quella capacità. Il motore lo controlla all'avvio e,
se il collegamento manca o è sbagliato, lo scrive nel log e tratta lo split come `confirmation: none` e la caldaia
come non regolabile. Chiavi diverse da queste due: solo se concordate.

### 2.3 Le otto capacità del contratto

Le otto capacità sono il modo in cui l'app vede ogni dispositivo: un dispositivo ne ha una o più, ciascuna con i suoi
campi. Questa tabella è **derivata da openapi.yaml v1.0.5, components.schemas.Cap\*** (il contratto fra l'app e il
motore): i nomi dei campi sono esattamente quelli del contratto. Non ti serve altro del contratto.

| Capacità | Schema | Campi (tipo) | Obbligatori |
|---|---|---|---|
| `switch` | `CapSwitch` | `on` (booleano) | `on` |
| `power_meter` | `CapPowerMeter` | `watts` (numero), `kwh_today` (numero, dalla mezzanotte locale dell'appartamento) | tutti |
| `climate` | `CapClimate` | `on` (booleano), `mode` (`cool` \| `heat` \| `dry` \| `fan`), `setpoint` (numero), `fan` (`auto` \| `low` \| `mid` \| `high`), `setpoint_min` (numero), `setpoint_max` (numero), `confirmation` (`power` \| `device` \| `none`) | tutti |
| `heating` | `CapHeating` | `on` (booleano), `setpoint` (numero), `setpoint_min` (numero), `setpoint_max` (numero) | tutti |
| `temperature` | `CapTemperature` | `celsius` (numero) | `celsius` |
| `humidity` | `CapHumidity` | `percent` (numero) | `percent` |
| `contact` | `CapContact` | `open` (booleano), `since` (data e ora, oppure null: da quando è nello stato attuale) | tutti |
| `motion` | `CapMotion` | `detected` (booleano), `last_seen` (data e ora, oppure null) | tutti |

Un dispositivo ha una chiave per ogni capacità presente; l'app ignora le chiavi che non conosce. `confirmation` dice
come il motore verifica l'esito di un comando allo split: `power` = dalla variazione di potenza, `device` = conferma
del dispositivo, `none` = nessuna verifica (si mostra lo stato richiesto).

La tabella seguente dice **chi riporta cosa**. «Dispositivo» è quello che riporti tu in `StateChange.state` e in
`DeviceInfo`; «motore» quello che calcola o tiene il motore; «catalogo» i valori fissi. `energy_total_wh` **non è un
campo del contratto**: è il dato grezzo che passi al motore, da cui il motore calcola `kwh_today`.

| Capacità | Cosa riporta chi |
|---|---|
| `switch` (`CapSwitch`) | dispositivo: `on` |
| `power_meter` (`CapPowerMeter`) | dispositivo: `watts`, `energy_total_wh` (il contatore cumulativo grezzo; se riparte da zero dopo un riavvio, il motore lo riconosce dal calo) · motore: `kwh_today` (dalla mezzanotte LOCALE dell'appartamento) e i consumi orari che l'app mostra |
| `climate` (`CapClimate`, split a infrarossi) | catalogo: `setpoint_min`, `setpoint_max`, `confirmation` (`power` \| `device` \| `none`) · motore: `on`, `mode`, `setpoint`, `fan` (l'ultimo stato richiesto: l'infrarosso non ha ritorno) · dispositivo: niente, salvo conferma vera (`confirmation: device`). Con `confirmation: power` il misuratore è quello indicato da `links.confirmation_device_id` (§2.2), non il `power_meter` dello stesso dispositivo (lo split a infrarossi di solito non ne ha uno) |
| `heating` (`CapHeating`, caldaia con contatto del termostato oggi; pompa di calore Modbus domani) | dispositivo: `on` (il relè) · catalogo: `setpoint_min`, `setpoint_max` · motore: `setpoint` e la regolazione, con la temperatura del dispositivo indicato da `links.sensor_device_id` (§2.2) |
| `temperature` (`CapTemperature`) | dispositivo: `celsius` |
| `humidity` (`CapHumidity`) | dispositivo: `percent` |
| `contact` (`CapContact`) | dispositivo: `open` · motore: `since` |
| `motion` (`CapMotion`) | dispositivo: `detected` · motore: `last_seen` (dagli eventi con `detected=true`) |

I comandabili sono solo `switch`, `climate` e `heating`. Quale apparecchio fisico
realizza `climate` e `heating` (blaster IR, Shelly con contatto, altro) lo decide il **catalogo**: è la tua scelta, da
fissare presto. Capacità in più non previste dal contratto: no, se non concordate prima.

### 2.4 Il comando: dal contratto al connector

Nel contratto l'app manda un comando con un'azione (`turn_on`, `turn_off`, `set_climate`, `set_heating`) e
parametri parziali (`on`, `mode`, `setpoint`, `fan`). Il motore lo valida, applica regole e limiti, e ti passa
sempre lo **stato completo da raggiungere**:
- `switch`: `{"on": true|false}`
- `heating`: `{"on": true|false}`. Il setpoint non ti arriva mai: la regolazione è del motore.
- `climate`: `{"on", "mode", "setpoint", "fan"}` tutti presenti (il motore completa quelli mancanti con lo stato
  attuale); con `on=false` gli altri campi sono indicativi.

Il tuo compito: far raggiungere quello stato al dispositivo, e dire come è andata.

### 2.5 Esiti e tempi

Nel contratto un comando passa per `pending → sent → verifying → acked | failed | timeout`, con un timeout di
10 secondi. Ruoli:
- `pending` lo mette il motore, alla creazione.
- `on_progress("sent")`: chiamalo appena il comando è consegnato al trasporto (RPC inviata, frame infrarosso spedito).
  Obiettivo: entro 1 s.
- `on_progress("verifying")`: chiamalo se aspetti una conferma dal dispositivo.
- Il risultato:
  - `"confirmed"` + `state`: il dispositivo ha confermato (per esempio `Switch.Set` seguito dallo stato dell'uscita) →
    il motore mette `acked`;
  - `"delivered"`: consegnato, ma il dispositivo non può confermare (infrarosso). Il motore decide con
    `confirmation`: `power` → guarda i `watts` del dispositivo indicato da `links.confirmation_device_id`: se
    cambiano in modo coerente con il comando entro i 10 s (in su per un'accensione, verso zero per uno spegnimento),
    `acked`; altrimenti `timeout` con reason `no_confirmation`. Senza quel collegamento il motore tratta il caso come
    `none` e lo scrive nel log. `none` → `acked` con lo stato richiesto. Per questo è importante che il misuratore
    collegato mandi i suoi cambi di `watts` in `changes()` senza ritardi (entro pochi secondi): è da lì che arriva la
    conferma;
  - `"failed"` + `reason`: `device_offline` (offline, o lo diventa durante il comando), `device_rejected` (il
    dispositivo ha risposto con un errore RPC), `internal_error` (errore del trasporto o tuo). Il `detail` va nei log.
- **La scadenza**: restituisci l'esito ENTRO `cmd.deadline`. Se non ce la fai, il motore annulla la tua coroutine
  (`asyncio.CancelledError`: gestiscila senza lasciare nulla a metà) e mette `timeout`.
- **Ripetizioni**: puoi ritentare a livello di trasporto dentro la scadenza (i comandi sono stati da raggiungere,
  quindi idempotenti); oltre la scadenza mai.
- Il motore ti manda **al massimo un comando alla volta per dispositivo**: non serve gestire la concorrenza sullo
  stesso dispositivo.
- **Niente coda per i dispositivi offline**: il contratto risponde 409 al motore, non a te; tu rispondi
  `failed/device_offline` subito.

### 2.6 Casi limite

- **Offline durante la verifica**: restituisci `failed/device_offline` ed emetti
  `StateChange(kind="online", online=False)`.
- **Quando sei offline**: socket chiuso → `online=False` subito. Silenzio oltre `offline_after_s` (configurabile,
  predefinito 120 s) → `online=False`. Usa il ping o il keep-alive del trasporto.
- **Riconnessione**: emetti `online=True` e poi una **fotografia completa**, cioè uno `StateChange` `"state"` per ogni
  capacità del dispositivo, letto dallo stato completo (es. `Shelly.GetStatus`). Il motore si riallinea su quella.
- **Ordine**: per uno stesso dispositivo, nell'ordine in cui accadono, senza riordinare. Fra dispositivi diversi
  nessuna garanzia.
- **Duplicati**: puoi mandare lo stesso stato più volte, il motore li scarta. Non sopprimere stati diversi per
  «risparmiare».
- **Notifiche parziali** (Shelly manda solo i campi cambiati): riempi tu lo stato completo dei campi «dispositivo»
  della capacità, partendo dall'ultimo noto.
- **Dispositivi sconosciuti** (non nel catalogo): ignorali, con un warn nel log. Mai inventare `device_id`.
- **Unità**: °C, %, W, Wh. Numeri come float.

### 2.7 Il punto di aggancio: `make_connector`

È così che il motore trova e costruisce il tuo connector. Con `CONNECTOR=shelly` (§5) il motore importa il modulo
`engine.connector.shelly`, cioè `engine/connector/shelly/__init__.py`, e vi cerca questa funzione:

```python
def make_connector(config: ConnectorConfig) -> Connector
```

- **`config`** è un `ConnectorConfig` (dataclass frozen in `interface.py`), costruito dal motore e già verificato:
  - `apartment_id: str`;
  - `data_dir: pathlib.Path`: la cartella dei dati dell'appartamento (`DATA_DIR`, predefinita `/data/<apartment_id>`);
  - `catalog_path: pathlib.Path`: il catalogo (`CATALOG_PATH`, predefinito `<data_dir>/catalog.yaml`, §5);
  - `env: Mapping[str, str]`: **solo le tue variabili d'ambiente**, cioè quelle con il prefisso del nome del
    connector in maiuscolo più «_»: per `CONNECTOR=shelly` tutte e sole le `SHELLY_*` (`SHELLY_OFFLINE_AFTER_S`,
    quelle del trasporto come `SHELLY_WS_PORT`, eventuali segreti come `SHELLY_TOKEN`), con i nomi originali.

  In `config` trovi le tue variabili (prefisso `SHELLY_`); **la chiave dell'API del motore non ti arriva**, e
  nemmeno le altre impostazioni del motore (`APARTMENT_ID`, `API_KEY`, `CONNECTOR`, `HOST`, `PORT`, `DATA_DIR`,
  `CATALOG_PATH`, `MOCK_*`, `DOMOTICA_*`). Le tue variabili segrete seguono le regole del §5: mai nel catalogo, mai nei log.
- **Restituisce** il connector: un oggetto con `api_version` (§2.1) e i metodi del Protocol.
- **La chiama il motore, una volta sola, all'avvio**, prima di `start()`. È sincrona.
- **Cosa può fare:** leggere e verificare il catalogo, che è un file locale e veloce. **Cosa non fa:** aprire
  connessioni o avviare il trasporto. Quelle stanno solo in `start()`.
- **Catalogo mancante o sbagliato:** `make_connector` solleva un'eccezione con un messaggio chiaro. Il messaggio dice
  **quale campo e quale dispositivo** sono sbagliati, **mai il valore trovato**: «device dev-caldaia:
  links.sensor_device_id non esiste nel catalogo», non «valore "xyz" non valido». È la stessa regola dei log (§5),
  valida anche per gli errori: così il motore può riportare il messaggio nel log senza rischi. Il motore non
  parte: scrive nel log «connector setup failed» con i campi `connector`, `error_type` ed `error` (il messaggio, al
  massimo 300 caratteri) ed esce con il codice 3, come per gli altri casi del §2.1. Così un catalogo rotto si vede
  all'avvio, non alla prima chiamata.
- **La prova comune** `test_make_connector_is_the_engines_entry_point` (in `tests/test_interface.py`) importa il tuo
  modulo, chiama `make_connector` come fa il motore e verifica versione e metodi: senza `make_connector` non passa.
  Verifica anche che `config` sia un `ConnectorConfig` senza la chiave dell'API e che in `env` ci siano solo le tue
  variabili.
  Il modello è `make_connector` in fondo a `simulated.py`.

## 3. Isolamento del trasporto

Il trasporto (come arrivano i messaggi: WebSocket in uscita dai Gen2, MQTT con un broker nostro, o il cloud Shelly come
tramite) sta in **un** modulo, dietro un'interfaccia interna tua:

```python
class Transport(Protocol):
    async def start(self) -> None
    async def stop(self) -> None
    async def call(self, shelly_id, method, params, timeout_s) -> dict
        # una RPC; errori TransportOffline, TransportTimeout, RpcError(code, message)
    def notifications(self) -> AsyncIterator[Notification]
        # NotifyStatus / NotifyFullStatus / NotifyEvent con shelly_id e received_at
    def connected(self) -> set[str]
```

Struttura (pacchetto del motore `engine/`, accanto al server `bff/` nella radice dell'app):

```
engine/connector/
  interface.py           # il Protocol, i tipi del §2, ConnectorConfig e CONNECTOR_API_VERSION (nostri)
  simulated.py           # SimulatedConnector e SimulatedDevice, il dispositivo finto (nostri, §4)
  shelly/                # IL TUO PERIMETRO
    __init__.py          # make_connector(config): il punto di aggancio (§2.7)
    catalog.py           # lettura e verifica del catalogo (§5), links compresi
    translate.py         # capacità ⇄ RPC e notifiche: funzioni pure, senza I/O
    connector.py         # ShellyConnector: catalogo, online/offline, execute, changes
    transport/
      base.py            # il Protocol Transport e gli errori
      ws_outbound.py     # oppure mqtt.py / cloud.py: UNO è in uso, scelto dalla configurazione
    tests/               # le tue prove: translate, ShellyConnector con FakeTransport, trasporto
      harness.py         # make_harness(): così le prove comuni girano anche sul ShellyConnector
      fake_device.py     # dispositivo Gen2 finto: risponde alle RPC e manda notifiche
      fake_transport.py
  tests/
    test_interface.py    # le prove comuni a OGNI connector (nostre); trova da sola ogni <nome>/tests/harness.py
    fake_device.py       # l'harness del simulato: connector più set_online e set_state (nostro, modello per il tuo)
```

Collaudo: alla domanda **«se cambiamo trasporto, quali file cambiano?»** la risposta è **«uno: il modulo in
`transport/`, più una riga di configurazione. I test del connector non cambiano»**, perché usano `FakeTransport`. Le
prove del trasporto stanno a parte, accanto al suo modulo.

## 4. Come si lavora

- Codice nel repository dell'app, cartella `engine/connector/` (il pacchetto del motore `engine/` sta accanto al
  server `bff/`; dentro c'è anche il motore simulato, che il server importa per gli appartamenti dimostrativi).
  Prove con pytest nella stessa cartella.
- **Il perimetro:** tuo è `engine/connector/shelly/`, con il catalogo (`catalog.py`) e le sue prove; nostri sono
  `interface.py`, `simulated.py` e la cartella `tests/` con le prove comuni. Le modifiche ai file
  nostri si propongono con una pull request a parte (nota, sezione 7).
- Un ramo tuo (es. `connector-shelly`) e pull request verso `main`; niente push diretti. Revisione di Massimiliano
  prima dell'unione. La cartella `contract/` del repository (contratto e prove di conformità) non si tocca.
- La CI su GitHub, a ogni push, esegue anche le prove del connector (pytest su `engine/connector/`) e la suite di
  conformità contro il motore in modalità simulata. Si unisce solo con tutto verde.
- Dipendenze nuove (es. la libreria WebSocket): dichiarate nei requisiti e approvate in revisione.
- I modelli da cui partire, già nel repository: `SimulatedConnector` e il dispositivo finto `SimulatedDevice` in
  `simulated.py` (catalogo seminato, esecuzione con le attese 0,3/0,2/1,0 s, stati di prova), estratti dal motore
  simulato dell'app con le prove dell'app e della conformità verdi; l'harness del simulato in `tests/fake_device.py`.
  Il `ShellyConnector` deve passare le stesse prove comuni di `tests/test_interface.py`: basta che tu scriva
  `shelly/tests/harness.py` sul modello di `tests/fake_device.py`, e le prove comuni lo trovano da sole.
  `harness.py` offre:
  - `make_harness()`, obbligatoria: il connector con il suo dispositivo finto, per le prove;
  - `connector_env(data_dir) -> dict`, facoltativa: serve se `make_connector` ha bisogno di qualcosa oltre la
    configurazione del motore. Riceve la cartella dei dati temporanea della prova (`pathlib.Path`) e restituisce le
    variabili d'ambiente da aggiungere: per lo Shelly scrive un catalogo di prova in `data_dir` e restituisce
    `{"CATALOG_PATH": str(data_dir / "catalog.yaml")}`. Se scrivi il catalogo proprio in
    `data_dir/catalog.yaml` basta anche restituire `{}`, perché quello è il percorso predefinito.

## 5. Configurazione, segreti, log

- **Catalogo**: un file per appartamento, `/data/<apartment_id>/catalog.yaml`, sul volume dell'istanza. Contiene le
  stanze, i dispositivi (`device_id`, `label`, `room_id`, capacità con i valori del catalogo: limiti e
  `confirmation`) e, per ognuno, una sezione `shelly:` (id del dispositivo Shelly, canale, componente; per `climate` il
  blaster e il `power_meter` collegato). Niente segreti nel catalogo. Il formato lo proponi tu; lo leggono
  `catalog.py` e il motore attraverso `devices()` e `rooms()`.

  **Esempio indicativo: il formato definitivo lo proponi tu.**

  ```yaml
  rooms:
    - {room_id: soggiorno, name: Soggiorno}
    - {room_id: camera, name: Camera}
  devices:
    - {device_id: dev-presa-camera, label: Presa stufetta, room_id: camera, capabilities: {switch: {}, power_meter: {}}, shelly: {id: shellyplus1pm-a8032ab1c2d3, channel: 0}}
    - {device_id: dev-finestra-camera, label: Finestra camera, room_id: camera, capabilities: {contact: {}}, shelly: {id: shellyblu-door-7c2f, ble: true}}
    - {device_id: dev-clima-soggiorno, label: Climatizzatore, room_id: soggiorno, capabilities: {climate: {setpoint_min: 16, setpoint_max: 24, confirmation: power}}, links: {confirmation_device_id: dev-misura-clima}, shelly: {id: <blaster IR>, ir_profile: <modello split>}}
    - {device_id: dev-misura-clima, label: Misuratore clima, room_id: soggiorno, capabilities: {power_meter: {}}, shelly: {id: shellypmmini-b1c2d3, channel: 0}}
    - {device_id: dev-caldaia, label: Caldaia, room_id: soggiorno, capabilities: {heating: {setpoint_min: 7, setpoint_max: 23}}, links: {sensor_device_id: dev-ambiente-soggiorno}, shelly: {id: shellyplus1-e4f5a6, channel: 0}}
    - {device_id: dev-ambiente-soggiorno, label: Sensore soggiorno, room_id: soggiorno, capabilities: {temperature: {}, humidity: {}}, shelly: {id: shellyhtg3-a1b2c3}}
  ```

  Gli id Shelly sono inventati; per lo split l'apparecchio a infrarossi lo sceglie il catalogo.
- **Configurazione del processo** (variabili d'ambiente, lette una volta all'avvio):
  - del motore: `APARTMENT_ID`, `API_KEY` e `CONNECTOR=shelly|simulated` sono **obbligatorie**. `API_KEY` è la
    chiave d'accesso che l'app deve mandare, **di almeno 16 caratteri**: se manca o è più corta il motore non parte
    ed esce con il codice 2, scritto nel log. Facoltative: `HOST`, `PORT` (predefinita 8100), `DATA_DIR`
    (predefinita `/data/<apartment_id>`), `CATALOG_PATH` (predefinito `<DATA_DIR>/catalog.yaml`);
  - del connector: tutte con il prefisso `SHELLY_`, cioè `SHELLY_OFFLINE_AFTER_S` e quelle del tuo trasporto (es.
    `SHELLY_WS_PORT`). Le leggi da `config.env` in `make_connector` (§2.7): una variabile senza il prefisso non ti
    arriva.
- **Segreti** (credenziali dei dispositivi, token del trasporto): in Secret Manager, con un nome per appartamento nella
  famiglia `langbrain-*` (es. `langbrain-shelly-<apartment_id>`, da concordare; il prefisso `langbrain-` resta solo
  perché è quello degli identificativi già creati su Google Cloud, e non indica il motore). La VM li legge con la
  sua identità all'avvio e il compose li passa al processo come variabili d'ambiente, come la chiave dell'API.
  Mai nel catalogo, nel repository o nei log.
- **Log**: una riga JSON per evento su stdout, con `ts`, `level`, `msg` (breve, in inglese, stabile: gli allarmi
  leggono i messaggi), `apartment_id` e, nei comandi, `correlation_id`, `command_id`, `device_id`. Usa la funzione di
  log del motore, `engine/log.py`: `info(msg, **campi)`, `warn(msg, **campi)`, `error(msg, **campi)`, per esempio
  `from engine.log import info` e poi `info("command sent", correlation_id=..., command_id=..., device_id=...)`.
  `apartment_id` lo aggiunge da sola: il motore la prepara all'avvio. I campi con key, token, password, secret o
  authorization nel nome escono come `[redacted]`, ma è solo una rete di sicurezza: mai payload RPC con credenziali.

## 6. Cosa il connector NON deve fare

- Decidere: niente regole, limiti, priorità, modalità, programmazioni, termostato, approvazioni, decisioni.
- Esporre API verso l'app o scrivere nell'archivio del motore (SQLite): passa tutto dall'interfaccia.
- Accodare comandi per dispositivi offline, o ritentare oltre la scadenza.
- Calcolare l'ora locale, `kwh_today` o i consumi orari.
- Leggere `X-Actor` o dati delle persone: il connector non sa chi ha chiesto il comando.
- Bloccare il ciclo di asyncio, usare stato globale (due connector nello stesso processo devono poter coesistere nelle
  prove), terminare il processo per un errore di un dispositivo (al più `status().up=False` con `detail`).
- Aprire porte verso internet senza il punto d'ingresso concordato (l'ingresso dei dispositivi è da progettare
  insieme: nota, sezione 2).
- Toccare la cartella `contract/` del repository.
