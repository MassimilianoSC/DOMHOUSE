# Piano B: motore minimo dietro lo stesso contratto — piano di dettaglio

*17 ottobre 2026. Analisi, non decisione. Scritta dalla memoria storica sull'analisi tecnica di o1 (nessun codice).
Il Piano B scatta solo se il motore basato su LangBrain non arriva, per tempi o per condizioni di licenza.*

Il contratto `contract/openapi.yaml` (v1.0.4) e la suite `contract/conformance/` **non cambiano**. Il BFF non cambia:
per lui il motore minimo è un'istanza come le altre (stesso contratto, stessa chiave
`langbrain-api-key-<apartment_id>`, stesso indirizzo `10.198.0.2:81xx`).

---

## 1. Da dove si parte

`bff/mock_instance/` (`app.py`, `state.py`, `__main__.py`) implementa già tutto il contratto con effettori simulati e
stato in memoria, e passa la suite di conformità (16 su 16, più C14 con il connector fermo).

**Non esiste una classe `SimulatedEffector`.** Gli effettori sono sparsi dentro `ApartmentSim` (`state.py`):
- `seed_devices()`: catalogo di dispositivi, stanze e capacità con i limiti (`setpoint_min`/`max`, `confirmation`);
- `self.devices`: stato dei dispositivi (online, `last_seen`, stato per capacità);
- `_run_command()`: esecuzione simulata (attese di 0,3, 0,2 e 1,0 s per pending → sent → verifying → acked;
  `failed` se il dispositivo va offline durante la verifica);
- `test_state()`: i cambiamenti «dal mondo» (online/offline, sensori, finestra), oggi solo da `POST /_test/state`;
- `connector_up()` e la parte connector di `health()`: lo stato del collegamento;
- `watts_for()` ed `energy()`: consumi sintetici e deterministici.

Tutto il resto (regole, modalità, programmazioni, prenotazioni, approvazioni, decisioni, stream, `/ask`) è logica del
motore e resta nel motore.

## 2. Il confine con Youssouf: l'interfaccia «connector»

Youssouf scrive l'implementazione Shelly e cura laboratorio, messa in servizio e catalogo dei dispositivi; il motore
sopra il connector lo scriviamo noi. L'interfaccia proposta, piccola e asincrona (Python):

```python
class Connector(Protocol):
    async def start(self) -> None
    def devices(self) -> list[DeviceInfo]
        # device_id, label, room_id, capacità con i limiti: il catalogo
    async def execute(self, device_id, capability, action, params, on_progress) -> CommandResult
        # on_progress("sent" / "verifying"); esito: acked | failed(reason: device_offline, timeout, rejected, …)
    def changes(self) -> AsyncIterator[StateChange]
        # device_id, capability, state | online, last_seen, ts
    def status(self) -> ConnectorStatus
        # up/down, connected_devices, last_event_at
```

Copre i tre punti richiesti: dispositivi con capacità, flusso dei cambi di stato, comando con esito. La regola della
finestra, i limiti di setpoint e la registrazione delle decisioni restano **fuori** dal connector, nel motore.

- `SimulatedConnector`: quello che oggi è dentro `ApartmentSim`, con le stesse attese, più due metodi solo di prova
  (`set_online`, `set_state`) usati da `/_test/state`.
- `ShellyConnector`: lo scrive Youssouf (WebSocket in uscita dai dispositivi Gen2 verso il servizio, comandi RPC,
  notifiche di stato, capacità mappate sul catalogo).

**Estrazione senza rompere il mock**, in quattro passi, verificando dopo ciascuno:
1. aggiungere `connector.py` (interfaccia e `SimulatedConnector`) spostandoci il codice com'è, attese comprese;
2. `ApartmentSim` chiede al connector invece di toccare `self.devices` (`_run_command` → `connector.execute`,
   `test_state` → `connector.set_*`) e consuma `connector.changes()` per emettere `device.state`/`device.online` e far
   partire la regola della finestra;
3. la sequenza degli eventi resta identica, perché le prove la leggono (C01, C07: `blocked_by_rule` dopo «sent»);
4. dopo ogni passo: il giro completo (l'app usa il mock attraverso il BFF) e la suite di conformità contro il mock da
   solo. *Nota della memoria storica:* la suite contro il mock gira già a ogni push nella CI su GitHub (D-95); o1
   propone di aggiungerla anche al giro sul PC come «passo zero».

## 3. Cosa manca per un motore reale su una VM

| Parte | Cosa serve |
|---|---|
| Servizio a sé | Un processo per appartamento, come le istanze `lb-<id>`: porta 81xx, base `/api/v1`, dati in `/data/<apartment_id>`, chiave da variabile d'ambiente obbligatoria (senza chiave non parte, nota di consegna §4). Oggi il mock serve più appartamenti dentro il BFF. |
| Effettori reali | Il `ShellyConnector` di Youssouf, con le capacità mappate sul catalogo. |
| Persistenza SQLite | `/data/<id>/engine.db` in WAL. Tabelle: appartamento (modalità, forzatura) e regole; dispositivi (stato, `last_seen`); eventi con id autoincrementale (monotono anche dopo un riavvio; buffer di un'ora per `Last-Event-ID` con pulizia periodica); comandi; decisioni; programmazioni; prenotazioni ed eventi elaborati (idempotenza); chiavi di idempotenza (60 s); approvazioni e coda; richieste `/ask`; telemetria oraria. Al riavvio i comandi a metà diventano `failed` (motivo `restart`) con la loro decisione. |
| Scheduler | Oggi un ciclo al secondo in memoria. Va letto da SQLite, con la regola per gli arretrati (scaduta da meno di 30 minuti si esegue, altrimenti `failed` «missed» con decisione), il cambio d'ora nelle ore locali dell'appartamento e le modifiche concorrenti. |
| Regole deterministiche | Nel mock ci sono `window_open_off` (riflesso dopo N minuti), `setpoint_limits` (nei comandi), pre-arrivo e partenza (programmazioni dalle prenotazioni); l'antigelo solo come valore della modalità «empty». Mancano: antigelo e antimuffa come controllo periodico a casa vuota, pausa minima del compressore (3 minuti), avviso di dispositivo offline dopo N minuti (evento e decisione, così partono le notifiche del BFF), limiti applicati in tutti i percorsi (modalità, programmazioni, `/ask`). |
| Approvazioni | Oggi nascono solo da `/_test/state` e da `/ask`. Servono fonti vere (per esempio `/ask` su un'azione rischiosa, una regola che propone qualcosa ad appartamento occupato), coda, scadenza con `expires_action`, persistenza. |
| Consumi | `GET /energy` oggi è sintetico: va calcolato dalla telemetria dei `power_meter`, a ore. `avoided_hvac_hours` resta `null` finché non lo calcoliamo, come ammette il contratto. |
| `/ask` | Per ultimo e dietro la feature `ask` (fino ad allora `501` e assente da `features`): Gemini su Agent Platform con chiamate di funzione verso un insieme chiuso di strumenti (modalità, comando, programmazione); ogni azione passa dalle stesse regole; quelle rischiose diventano approvazioni; limiti di tempo e di costo; `health.model_provider` con lo stato vero. |
| Gestione | `health` con lo stato vero di database e connector, backup giornaliero dei volumi SQLite, log strutturati, aggiornamenti senza perdere lo stato. |

## 4. Ordine di costruzione e stima (giornate di o1)

**Stato al 21 ottobre 2026** (il dettaglio è nel registro, P-60 e decisioni D-104…D-130): passi 0, 1, 2, 3, 3b, 3c, 4 e 5
**fatti e online** (lotti 15, 16, 17: il motore gira sulla VM come servizio `dev` con il connector simulato, il BFF è in
`TARGET=prod`); passo 6 **in corso**; passi 7, 8, 9, 10 da fare; la riga I (ingresso dei dispositivi) aspetta la scelta di
Youssouf. Il backup di SQLite (passo 10) è già fatto con il 3d.

| Passo | Cosa | Stima |
|---|---|---|
| 0 | Suite di conformità contro il mock da solo anche nel giro sul PC (in CI c'è già) | 0,5 |
| 1 | Interfaccia connector e `SimulatedConnector` estratti dal mock, a comportamento identico | 1,5–2 |
| 2 | Servizio a sé, uno per appartamento (pacchetto, configurazione, chiave obbligatoria, Dockerfile e compose per la VM). Istruzioni nel README del repository per avviare connector e motore sul proprio PC. **Il comando al connector contiene solo i campi della capacità** (§2.4 di `connector.md`); oggi il simulatore passa anche `setpoint_min`/`setpoint_max` e altri dati non necessari al dispositivo (D-108). **Prova:** un test nell'harness di `engine/connector/tests/` verifica che `ConnectorCommand` per `heating` porti solo `on`, e per `climate` solo `on`, `mode`, `setpoint`, `fan`. `energy_total_wh` non esce in `GET /devices` (serve solo a calcolare `kwh_today`) | 1,5 |
| 3 | **Primo traguardo:** persistenza SQLite e conformità C01–C16 che passa con effettori simulati su SQLite, **fuori dal BFF, sulla VM**, come servizio a sé, con prove di riavvio (id degli eventi, comandi a metà, programmazioni) | 4–5 |
| 3b | **Contratto 1.0.5, solo documentazione** (P-63, D-107): via LangBrain dalle descrizioni, `x-youssouf` → `x-motore`, esempi `implementation.name` → `domhouse-engine`, prefissi di `actor` invariati con `brain` e `organ:` riservati. Prova obbligatoria: alberi identici dopo aver tolto `description`, `summary`, `example(s)` e `x-*`; gen-api senza differenze; conformità 16/16; `CONTRACT_SHA256` della CI aggiornato | 0,5 |
| 3c | Immagine del motore da Cloud Build su Artifact Registry (`engine:<sha>`), permesso di lettura per `langbrain-vm@` (P-62), procedura d'installazione e aggiornamento sulla VM (`/data/<id>`, `/etc/domhouse/<id>.env` da Secret Manager, compose), prima istanza con `CONNECTOR=simulated` e `/health` che risponde dalla rete interna (regola 3 del CLAUDE.md). Pulizia pianificata per la conservazione (D-94). (D-115) | 1–1,5 |
| I | **Ingresso dei dispositivi su GCP**: dipendenza esterna, la scelta di Youssouf (P-65); si costruisce e si stima dopo | — |
| 4 | Scheduler robusto (arretrati, cambio d'ora, concorrenza) | 1 |
| 5 | Regole complete (antigelo, antimuffa, compressore, offline, limiti ovunque) | 2–3 |
| 6 | Telemetria e consumi reali | 1,5 |
| 7 | Lato nostro del connector Shelly: prove con un finto server WebSocket Gen2, configurazione, collegamento al motore | 1,5–2 |
| 8 | Approvazioni con fonti reali e persistenza | 1 |
| 9 | `/ask` con Gemini e funzioni, dietro la feature | 3–4 |
| 10 | Gestione (health vero, backup, log) | 1 |
| | **Totale** (più il connector di Youssouf) | **circa 19–23** |
| | di cui primo traguardo (passi 0–3) | circa 8–9 |

## 5. Rischi

1. **Catalogo:** Shelly Gen2 comanda bene prese e relè e legge i consumi, ma clima e caldaia stanno spesso dietro un
   altro apparecchio (infrarossi, contatto del termostato). Se il catalogo non copre `climate`/`heating` come il
   contratto li descrive, servono profili per tipo di dispositivo. Da decidere presto con Youssouf.
2. **Conferma dell'esecuzione:** `confirmation: power` presuppone un misuratore sullo stesso apparecchio; senza, la
   verifica è debole o a tempo.
3. **Diventiamo proprietari di un motore:** manutenzione, turni, aggiornamenti e sicurezza, oggi di LangBrain e di
   Youssouf.
4. **SQLite e processi:** un processo per appartamento, WAL e backup; molti appartamenti vogliono dire molti processi
   sulla VM (memoria e porte), da misurare.
5. **Comportamenti che il mock inventa e il contratto non fissa** (tempi di verifica, priorità delle regole): vanno
   scritti, altrimenti la conformità passa ma il comportamento reale sorprende.
6. **`/ask`:** costo, tempi e risposte sbagliate. Mitigazioni: strumenti chiusi, regole sempre applicate, approvazione
   per le azioni rischiose, feature spenta finché non è pronta.
7. **Sicurezza di rete:** i dispositivi aprono un WebSocket verso la VM, quindi serve un punto d'ingresso
   dall'appartamento (VPN o tunnel) senza esporre la VM. Da progettare con Youssouf; oggi non esiste.
8. **Tempi:** il primo traguardo è realistico; regole complete e `/ask` sono la parte lunga.

## 6. Cosa cambierebbe nei documenti per Youssouf (`per-youssouf/`)

- **`README-youssouf.md`:** la sua consegna passa da «un'istanza del motore conforme al contratto» a «il connector
  Shelly conforme all'interfaccia connector, più catalogo, laboratorio e messa in servizio». La suite di conformità
  resta il collaudo del motore, ma la lanciamo noi. Le tappe diventano quelle del connector: dispositivi e stato, poi
  comandi con esito, poi telemetria.
- **Un documento nuovo, `connector.md`:** l'interfaccia (i cinque metodi), il formato di `DeviceInfo`, `StateChange` e
  `CommandResult`, gli errori, le attese, le prove con il finto server WebSocket, il collegamento al motore
  (configurazione, segreti dei dispositivi). Requisito di isolamento del trasporto: qualunque sia la scelta (WebSocket in uscita dai dispositivi, MQTT con
  broker nostro, o cloud Shelly come tramite), il trasporto deve stare in un modulo isolato del connector, sostituibile
  senza toccare la traduzione in capacità né il resto del motore: la domanda di collaudo è «se cambiamo trasporto, quali
  file cambiano?» e la risposta attesa è «uno, e i test del connector no».
- **`NOTE-TECNICHE-MOTORE.md`:** restano istanza per appartamento, porta 81xx, volume `/data/<id>` e segreto
  `langbrain-api-key-<id>` (il nome «langbrain» resterebbe solo negli identificativi; rinominarli costerebbe una
  migrazione dei segreti, da decidere). Esce tutto ciò che riguarda LangBrain dentro il motore (brain, organi, suo
  fornitore di modelli); `health.model_provider` diventa Gemini.
- **`CONFIGURAZIONE_GCP`** (dal 19 ottobre in `documenti-interni\`, fuori da `per-youssouf`): si aggiungono i servizi del motore sulla VM (unità e compose), il backup dei volumi SQLite
  e, per `/ask`, le credenziali di Agent Platform.
- **`conformance/` e `openapi.yaml`:** invariati.

## 7. Scelte e soglie registrate (D-101, 17 ottobre)

- Il connector sarà una **libreria Python in un pacchetto separato, con i suoi test**, trasformabile in processo a sé se
  servirà indipendenza nei rilasci.
- **Soglie per far scattare il Piano B:** quelle tecniche del piano di lavoro (fine settimana 3: un relè reale non si
  accende dalla PWA passando dal motore; fine settimana 5: le prenotazioni non generano le azioni da sole) e una
  **contrattuale**: se licenza e compenso con Youssouf non sono chiusi entro il **[data da indicare dal committente]**,
  partono i passi 0–3 come assicurazione.
- Il rischio 7 (ingresso dei dispositivi verso la VM) vale anche con LangBrain: la nota di consegna ora lo chiede a
  Youssouf entro la settimana 2.

## 8. Prossimo passo possibile (se e quando si decide il Piano B)

o1 può scrivere la specifica dell'interfaccia connector come proposta da allegare per Youssouf, senza codice nel
repository. Nessuna attività è avviata: questo documento è solo il dettaglio del Piano B.
