# Connector Shelly: come è fatto e perché

*Aggiornato il 13 novembre 2026, di Youssouf. La prima versione (20–21 ottobre) confrontava due trasporti, MQTT e
WebSocket; quella del 10 novembre fissava la scelta di MQTT e le prove con la Plug. Questa descrive il connector
com'è oggi in `main`, con i modelli Gen4 e i sensori BLU.*

Dove guardare per il resto:
- **il contratto fra motore e connector**: `engine/connector/connector-v2.md` (i rimandi «§» sono a quel file);
- **le misure di laboratorio**, con numeri e tabelle: `LABORATORIO-2026-11-11.md` in questa cartella;
- **l'analisi dell'ingresso**: `docs/analisi-ingresso-mqtt-2026-11-09.md`.

Qui non ci sono id né MAC reali.

## 1. Decisioni

| Tema | Decisione | Dove |
|---|---|---|
| Trasporto | MQTT con un broker nostro; gli Shelly si collegano al broker, il connector è un suo client | D-196 |
| Gateway in appartamento | Nessuno: gli Shelly escono verso internet, nessuna porta da aprire in casa | D-196 |
| Cifratura | TLS fino al broker, porta 8883; certificato di una CA pubblica, verificato dallo Shelly con il bundle integrato (`ssl_ca: "ca.pem"`). Mai `"*"`, mai in chiaro | §7.1 |
| Broker | Uno per VM, nessun instradamento all'ingresso: ogni connector si abbona solo al prefisso del suo appartamento | §7.1 |
| Connector e broker | Si parlano in chiaro sulla rete Docker interna della VM, porta 1883 | §7.1 bis |
| Utenti | Uno per ogni Shelly fisico (`<apartment_id>.<id>`), uno per il connector (`<apartment_id>.connector`) | §7.1 |
| Id nel broker | `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`, `connector` riservato. Il catalogo applica la stessa regola, e una prova controlla che le due copie restino uguali | §7.1 |
| Richieste e risposte | Richieste a QoS 0, risposte e notifiche a QoS 1; abbonamenti a QoS 1 | §7.2 |
| Sensori Bluetooth | Passano da uno Shelly alimentato dello stesso appartamento, che fa da ponte. Un solo ponte per sensore | §3 qui sotto |
| Segreti | In Secret Manager; al connector arriva solo la sua password, come variabile `SHELLY_MQTT_PASSWORD` | §5 |

## 2. Topic e permessi

| Chi | Topic |
|---|---|
| Shelly `<apartment_id>/<id>` | riceve le RPC su `<prefisso>/rpc`; manda le notifiche su `<prefisso>/events/rpc`; pubblica `true`/`false` conservato su `<prefisso>/online` (il `false` è il suo messaggio di ultima volontà) |
| Connector | manda le RPC con `src = <apartment_id>/<id>/connector`; riceve le risposte su `<apartment_id>/<id>/connector/rpc`; si abbona a `<apartment_id>/+/online`, `<apartment_id>/+/events/rpc`, `<apartment_id>/+/connector/rpc` |

**Permessi**: lo Shelly legge e scrive solo `<apartment_id>/<id>/#`; il connector `<apartment_id>/#`.

Lo Shelly risponde su `<src>/rpc`. Con il `src` per dispositivo la risposta resta dentro il suo prefisso: nessuno
Shelly scrive fuori dal proprio spazio, e nessuno può fingere la risposta di un altro, perché lo impedisce il broker
(D-223).

Tre conseguenze che il codice rispetta:
- **Chi ha mandato un messaggio lo dice il topic**, non il campo `src` del payload, che lo scrive il dispositivo. Un
  `src` diverso dall'id del catalogo non fa scartare il messaggio: produce un warn, una volta per dispositivo.
- **Una risposta negata dai permessi sparisce in silenzio**: il broker la scarta, lo Shelly resta collegato e il
  connector vede solo un timeout. Va nella checklist di installazione.
- **Un comando a uno Shelly assente si perde**, non gli arriva al ritorno: per questo le richieste sono a QoS 0.
  Gli id delle richieste partono da un numero casuale a ogni avvio, perché uno Shelly può rimandare una risposta a
  QoS 1 non confermata dopo che il connector è ripartito.

## 3. Come è fatto il codice

Tutto in `engine/connector/shelly/`.

| File | Cosa fa |
|---|---|
| `transport/base.py` | Il Protocol `Transport`: chiamate RPC, flusso di notifiche ed eventi di connessione. Il connector conosce solo questo |
| `transport/mqtt.py` | Il trasporto MQTT (aiomqtt): topic, QoS, id delle richieste, riconnessione con attesa crescente |
| `translate.py` | Profili per modello e traduzione dei sensori BLU: dal linguaggio Shelly alle capacità del contratto |
| `command.py` | Un comando: invio, rilettura di conferma, un secondo tentativo di lettura dentro la scadenza |
| `catalog.py` | Lettura e controllo di `catalog.yaml`; chiavi sconosciute rifiutate |
| `connector.py` | `ShellyConnector`: un worker per dispositivo, fotografia a ogni ritorno online, silenzio, ordine dei `ts` |
| `offline.py`, `offline_thresholds.toml` | Soglie di silenzio per tipo di apparato |
| `battery.py` | Livello di batteria dei sensori e avviso di batteria scarica |
| `tests/` | Dispositivi, trasporto e broker finti; catture vere anonimizzate in `tests/fixtures/` |

### 3.1 Modelli coperti

| Apparecchio | Profilo | Capacità | Note |
|---|---|---|---|
| Plug M Gen3 | `PlugMG3` | `switch`, `power_meter` | `Switch.Set` con rilettura |
| Shelly 1 Gen4 | `S1G4` | `switch` oppure `heating` (mai insieme) | Nessuna misura |
| EM Mini Gen4 | `MiniEMG4` | `power_meter` | Potenza da `em1`, energia da `em1data`; al ritorno online non manda `NotifyFullStatus` |
| BLU H&T | `blu_ht` | `temperature`, `humidity` | Attraverso il ponte |
| BLU Motion | `blu_motion` | `motion` | Attraverso il ponte |
| BLU contatto | `blu_door_window` | `contact` | Attraverso il ponte |

Non ancora coperti: `climate` (Athom AR01 a infrarossi, §7.3 punto 5).

### 3.2 Catalogo

```yaml
devices:
  - {device_id: dev-rele, label: Relè, room_id: sala, capabilities: {switch: {}}, shelly: {id: <id dello Shelly>, type: relay}}
  - {device_id: dev-ambiente, label: Sensore, room_id: sala, capabilities: {temperature: {}, humidity: {}}, shelly: {addr: <MAC del sensore>, bridge: <id dello Shelly che fa da ponte>, type: blu_ht}}
```

- `type` è obbligatorio: da lì viene la soglia di silenzio. `offline_after_s` sul singolo dispositivo la sostituisce.
- Un dispositivo alimentato dichiara `id` (quello del broker) e, se serve, `channel`.
- Un sensore BLU dichiara `addr`, `bridge` e `type`. Il ponte deve essere uno Shelly dello stesso catalogo. È la
  risposta al §7.3 punto 4: l'account del broker è dell'apparecchio fisico, il sensore non ha account né topic.

### 3.3 Online, offline e fotografia

- **Dispositivi alimentati**: l'offline arriva dal broker (ultima volontà, 30–90 s dopo la caduta con il keep-alive di
  60 s); il silenzio oltre la soglia (120 s) è la rete di sicurezza.
- **A ogni ritorno online**, in quest'ordine:
  1. `Shelly.GetDeviceInfo` per controllare il modello. Se non è quello del catalogo il dispositivo torna offline,
     la fotografia non viene chiesta e le sue notifiche sono ignorate fino alla connessione successiva. Se il
     controllo non riesce (timeout) si va avanti con il profilo del catalogo e si riprova alla connessione dopo.
  2. `Shelly.GetStatus` per la fotografia del §2.6. Se fallisce il dispositivo resta online e la lettura si ritenta a
     ogni controllo del silenzio, finché riesce o finché arriva una `NotifyFullStatus`, che vale come fotografia.
  3. Solo per un ponte con sensori nel catalogo: `Shelly.GetComponents` (§3.4).
- **Sensori BLU**: offline subito insieme al loro ponte. Con il ponte online conta l'ultimo pacchetto ricevuto, fra
  i componenti del sensore **che non sono in errore** (§3.4), contro la soglia del tipo. Un sensore mai sentito
  resta offline fino al primo pacchetto: nessuno stato inventato.
- **Soglie** (`offline_thresholds.toml`): regola «tre beacon persi più 20 s» con i ritmi misurati. Contatto 920 s,
  Motion 2720 s; H&T 300 s, più larga della regola perché è il sensore che regola il riscaldamento.

### 3.4 I sensori BLU attraverso il ponte

- Il ponte espone ogni sensore come `bthomedevice:<n>` più un `bthomesensor:<n>` per misura. **I numeri non sono
  stabili**: una misura si riconosce da MAC + `obj_id`.
- **Non sono in `Shelly.GetStatus`.** Si leggono con `Shelly.GetComponents` (`dynamic_only`), 10 per pagina: il
  connector legge tutte le pagine, solo sui ponti che hanno sensori nel catalogo.
- Le notifiche portano solo il numero: serve la mappa numero → (MAC, `obj_id`). La mappa si rilegge al ritorno del
  ponte e quando un sensore viene aggiunto o tolto, e **si dimentica** quando il ponte cade o cambia un abbinamento:
  meglio nessuno stato che lo stato di un altro sensore.
- Inclinazione e livello di luce sono ignorati: non sono fra le otto capacità.
- **Sensore che il ponte non decodifica**: il ponte riporta `errors` sul `bthomedevice` e continua ad aggiornarne
  l'ora. Un componente in errore non conta come pacchetto: il sensore va offline alla soglia, con un warn.
- **Rilettura per errori**: finché un sensore **del catalogo** è in errore, la mappa del suo ponte viene riletta,
  perché il ritorno potrebbe non essere mai notificato. Al massimo una volta ogni 5 minuti per ponte, contati
  dall'ultima lettura della mappa di qualunque tipo (connessione, abbinamento, errori). Avviene a un controllo del
  silenzio, con il ponte online. Se la rilettura fallisce, la mappa di prima resta e si riprova alla scadenza
  successiva. I sensori fuori catalogo in errore non fanno rileggere niente.

### 3.5 Orologi e `ts`

**Il `ts` di uno `StateChange`**, secondo da dove viene:

| Origine | `ts` |
|---|---|
| Notifica di uno Shelly alimentato (`NotifyStatus`, `NotifyFullStatus`) | l'ora del dispositivo se dista meno di 300 s dalla nostra, altrimenti l'ora di ricezione |
| Fotografia da `Shelly.GetStatus` | l'ora di ricezione della risposta |
| Pacchetto di un sensore BLU | `last_updated_ts` riportato sul nostro orologio con lo scarto del ponte (sotto). La regola dei 300 s **non** vale: un pacchetto vecchio resta vecchio. Solo un valore nel futuro diventa l'ora di ricezione |

Per tutti: **mai oltre l'ora di ricezione** (uno Shelly con l'orologio avanti sposterebbe i consumi nel giorno
sbagliato) e **mai all'indietro** nel flusso, nemmeno fra dispositivi diversi. Quando le due regole si scontrano
vince la seconda.

**L'età di un pacchetto BLU si conta sull'orologio del ponte**, che è quello che scrive `last_updated_ts`. Il
connector tiene per ogni ponte lo scarto fra il suo orologio e il nostro.

- **Da dove si prende lo scarto**, e solo da qui:
  - `sys.unixtime` di `Shelly.GetStatus`, che si legge alla connessione, al nuovo tentativo dopo una lettura fallita
    e per confermare un candidato (sotto). Non a intervalli;
  - il `ts` di una `NotifyStatus` che porta componenti BLU. Non le `NotifyFullStatus` né le `NotifyEvent`, e non le
    altre notifiche del ponte: l'EM Mini manda la potenza con il `ts` ~13,5 s indietro.
- **Scarto entro 300 s**: adottato subito. Sotto i 2 s conta come zero.
- **Scarto oltre 300 s**: è un **candidato**, non viene adottato. Lo diventa solo se una fonte successiva, almeno
  5 minuti dopo, dà lo stesso valore entro 5 s; allora esce il warn `bridge clock off`. Se in quei 5 minuti non
  arrivano pacchetti, al controllo del silenzio il connector rilegge `Shelly.GetStatus`. Una fonte con uno scarto
  diverso fa ripartire l'attesa; una con uno scarto entro 300 s cancella il candidato.
- **Mentre un candidato aspetta** vale lo scarto adottato prima, se c'era; altrimenti nessuno, cioè il nostro
  orologio. Il candidato non serve mai a datare né a calcolare un'età.
- **Scarto oltre un giorno**: ignorato, con il warn `bridge clock implausible`. Resta lo scarto di prima, se c'era.
- **Quando il ponte cade** scarto, candidato e avvisi si azzerano. Una notifica arrivata dopo la caduta non li
  reimposta.

**Dopo un riavvio del ponte.** Lo Shelly riparte con l'orologio sbagliato finché non si sincronizza (al banco la
prima `NotifyFullStatus` dello Shelly 1 Gen4 era fuori di ~1750 s). Quello scarto resta un candidato: con la
riconnessione il connector usa il nostro orologio, senza riconnessione lo scarto di prima. Un sensore che taceva
da tempo resta offline. Il prezzo: un sensore vivo può risultare offline per qualche minuto dopo il riavvio, e un
ponte con l'orologio stabilmente sbagliato tiene i suoi sensori offline per i 5 minuti della conferma.

**Limiti noti**
- Se dopo un riavvio l'orologio resta sbagliato per più di 5 minuti, lo scarto viene confermato e adottato. Quanto
  dura davvero va misurato al banco (§5 punto 2).
- Dopo una correzione dell'orologio del ponte lo scarto resta quello vecchio fino al prossimo pacchetto BLU: con il
  solo Motion o il contatto, anche molti minuti. Pesa solo su una lettura della mappa che capiti in mezzo.

## 4. Verificato in laboratorio

Banco: broker Mosquitto sul PC con utenti e permessi come in produzione, senza TLS; motore in Docker con
`CONNECTOR=shelly`. I numeri completi sono in `LABORATORIO-2026-11-11.md`.

- **RPC via MQTT** su Gen3 e Gen4: `topic_prefix` e `src` accettano la barra; risposta su `<src>/rpc` con lo stesso
  `id`; nessun rifiuto del broker con i permessi limitati al prefisso.
- **`online` è un messaggio conservato**, su Gen3 e Gen4: un abbonato nuovo lo riceve subito (§7.3 punto 10).
- **Ripartenza dopo un blackout**: i tre Shelly si ricollegano da soli; i sensori tornano online 1,4 s dopo il ponte,
  con la fotografia. L'abbinamento dei sensori sopravvive allo spegnimento del ponte.
- **Comandi**: `acked` in circa 0,25 s sulla Plug.
- **EM Mini e conferma a consumo (§2.5)**: rispettata. La prima variazione di `watts` arriva 0,4–1,2 s dopo la
  commutazione del relè, anche mentre l'EM Mini fa da ponte; a riposo il ritmo è di ~14 s.
- **Orologio dopo un'accensione**: la prima `NotifyFullStatus` ha un `ts` sbagliato (fino a ~1750 s sullo Shelly 1).
- **Contatore di energia della Plug**: dopo una caduta di corrente torna indietro di meno di 1 Wh, non a zero.
- **Ritmi dei sensori**: H&T 60 s; contatto ~300 s più l'invio immediato; Motion ~900 s più l'invio immediato.

## 5. Aperto

1. **Dove mettere il ponte Bluetooth.** Lo Shelly che fa da ponte risponde lentamente alle RPC (fino a 2,7 s, con
   un'attesa del connector di 3 s); senza sensori torna a 75 ms di mediana. Strade: ponte sull'EM Mini, che però con
   il firmware 1.7.0 decodifica solo l'H&T, oppure ponte sul relè con più margine sul comando. Non verificabile al
   banco: la portata del Bluetooth da un quadro elettrico.
2. **Due verifiche al banco**: l'orologio del ponte nei primi minuti dopo un riavvio; se `GetComponents` toglie
   `errors` quando un sensore torna leggibile.
3. **Primo dispositivo vero sul broker della VM** (tappa A, con la Plug) e, con quello, il certificato Let's Encrypt
   accettato da uno Shelly senza installare niente (§7.4, bloccante).
4. **Cifratura dei sensori BLU** (§7.3 punto 7). Dalla documentazione Shelly: la chiave la genera il sensore, si
   legge via Bluetooth e si scrive sul ponte con `BTHomeDevice.SetConfig`. Non provata sui modelli ZB. Con i nuovi
   appartamenti seguiti da un tecnico del cliente, la procedura dovrà essere un manuale o una guida nell'app.
5. **Preparazione dei kit**: ponte e sensori abbinati prima della spedizione, con le righe del catalogo scritte da
   uno script che legge `GetComponents`. Chi lo fa dopo il primo appartamento, e con quale strumento.
6. **`initial_state` del relè dopo un blackout**: da scegliere per gli appartamenti.
7. **Athom AR01** (infrarosso, Tasmota): come entra nel broker con gli stessi permessi (§7.3 punto 5).
8. **Firmware**: per il pilota Plug 1.8.99, Shelly 1 Gen4 2.0.3, EM Mini 1.7.0; una versione nuova solo dopo una
   prova al banco. `Shelly.Update` via RPC permetterebbe aggiornamenti da remoto con uno strumento a parte.
9. Una cattura con una batteria che scende, per le prove di `battery.py`.

## 6. Strade scartate

- **WebSocket in uscita dagli Shelly.** La configurazione Shelly non ha utente, password né certificato client:
  l'unica autenticazione possibile era un segreto nell'URL, visibile nella configurazione del dispositivo e nei log
  dell'ingresso. Il vantaggio era «meno infrastruttura», sparito quando l'ingresso dei dispositivi non poteva più
  passare da Cloud Run (E-27).
- **Cloud Shelly come tramite.** Un intermediario esterno dentro i circa 9 s di scadenza del comando, e meno
  controllo sull'autenticazione.
- **Zigbee per i sensori.** Sui Gen4 è un firmware alternativo, non una modalità che convive con Wi-Fi e MQTT.
- **Due ponti per lo stesso sensore.** Copre solo il guasto del singolo Shelly, non blackout né router, e porta
  duplicati. Si riapre solo con sensori critici (allagamento, fumo).
- **Topic di risposta comune a tutto l'appartamento.** Uno Shelly potrebbe fingere la risposta di un altro, perché
  il `src` nel messaggio lo scrive lui.
