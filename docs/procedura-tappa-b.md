# Tappa B: dall'app di staging ai dispositivi del laboratorio di Y

| Stato | Comandi | Preparata | Chi lancia |
|---|---|---|---|
| **Pronta per la parte con la sola Plug** (sezioni 1–5). Le parti con gli altri dispositivi sono **da completare con il catalogo di Youssouf** (sezione 6) | o1, 13 novembre 2026, sul codice di `247fda0` | memoria storica | il committente, uno alla volta, con la memoria storica in chat (D-116) |

## 0. Che cosa si ottiene e che cosa serve

- **Risultato:** un motore `lab-01` sulla VM, con il connector Shelly, collegato all'app di **staging**. Dall'app si leggono e si comandano i dispositivi del banco di Y.
- **Si parte con la sola Plug di Y** (`shellyplugmg3-9070695cb0d0`).
  - La Plug è già collegata al nostro broker dalla tappa A, con il suo utente.
  - Il suo catalogo lo scriviamo noi: basta l'id nativo, che abbiamo.
- **Gli altri dispositivi** (Shelly 1 Gen4, EM Mini Gen4, sensori BLU) entrano quando Y manda il catalogo e gli id (sezione 6).
- **Già fatto, non si rifà:**
  - broker installato, con certificato valido;
  - conto del connector di `lab-01` (segreto `langbrain-shelly-lab-01`, 11 novembre);
  - utente della Plug (segreto `langbrain-shelly-lab-01-devices`, versione 2, oppure 3 dopo il cambio di password della tappa A).

### Decisioni prese in questa procedura

| Cosa | Valore | Perché |
|---|---|---|
| Porta del motore | **8169** | Lo staging raggiunge solo `10.198.0.2:8100` e `10.198.0.2:8150-8169` (`INSTANCE_ALLOWED`, D04): con 8169 non serve cambiare il server né pubblicare. **Decisione del committente aperta** (domanda della memoria storica): l'alternativa è 8101, con una modifica di o1 al manifesto dello staging e una pubblicazione |
| Immagine del motore | `europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:d274386` | quella del lotto pubblicato alle 14:32 di oggi, la stessa di `dev`; contiene il connector Shelly e basta per la Plug. Per i sensori BLU serve un'immagine nuova (sezione 6.4) |
| Catalogo | solo la Plug, `device_id` **`dev-presa-lab`** | Y lo tiene uguale nel suo catalogo: cambiarlo dopo farebbe perdere lo storico nell'app |
| Ambiente dell'app | **staging** | D-134: niente appartamenti veri; la produzione non si tocca |

### Chi fa che cosa

| Chi | Che cosa |
|---|---|
| Committente | lancia ogni comando, crea l'appartamento nell'app di staging, preme i pulsanti delle prove |
| Memoria storica | rilegge ogni uscita in chat e la registra |
| o1 | corregge i comandi se un'uscita non torna |
| Y | solo nelle prove che comandano un dispositivo (sezione 5): stacca ciò che non può spegnersi e guarda il dispositivo; poi catalogo e id (sezione 6) |

## 1. Controlli prima di cominciare (sola lettura)

### 1.1 La VM oggi

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker ps --format "{{.Names}}  {{.Ports}}"; ls /opt/domhouse/*.settings; sudo sed -n "s/^ENGINE_IMAGE=//p" /opt/domhouse/dev.settings; free -m | head -2; sudo bash /opt/domhouse/broker-vm.sh status | grep -E "^appartamenti|^utenti|^broker ok"'
```

| Riga | Atteso |
|---|---|
| container | `engine-dev` sulla porta 8100 e `domhouse-broker` sulla 8883; **nessun** altro motore, e niente sulla 8169 |
| file delle impostazioni | solo `/opt/domhouse/dev.settings` |
| immagine di `dev` | `europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:d274386` |
| memoria | annota la colonna `available`: serve per il confronto al passo 3.2 |
| broker | `appartamenti: 1`, `utenti devices: 1`, `utenti connectors: 1`, `broker ok cert_days=…` |

- **Se l'immagine di `dev` è un'altra:** si usa quella nei comandi del passo 3.1. Avvisa la memoria storica, che la sostituisce prima.
- **Se c'è già qualcosa sulla 8169:** fermati.

### 1.2 I segreti di `lab-01` (solo l'elenco delle versioni, mai il valore)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for s in langbrain-shelly-lab-01 langbrain-shelly-lab-01-devices langbrain-api-key-lab-01; do echo "== $s"; gcloud secrets versions list "$s" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --limit=1; done
```

| Segreto | Atteso |
|---|---|
| `langbrain-shelly-lab-01` | una versione `enabled` (password del connector) |
| `langbrain-shelly-lab-01-devices` | in cima la versione 2, oppure la 3 se il cambio di password della tappa A è fatto |
| `langbrain-api-key-lab-01` | **errore `NOT_FOUND`**: non esiste ancora, si crea al passo 2 |

## 2. La chiave del motore `lab-01` (scrive su Secret Manager)

**Che cos'è:** la chiave con cui il server dell'app parla al motore. Il nome del segreto viene dall'identificativo dell'appartamento: `langbrain-api-key-lab-01`. Non si sceglie (D-90).

### 2.1 Crearla

Il valore lo genera Python e passa direttamente a gcloud: non compare mai a video né sulla riga di comando.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
.venv/Scripts/python.exe -c "import secrets,sys; sys.stdout.write(secrets.token_urlsafe(32))" | gcloud secrets create langbrain-api-key-lab-01 --data-file=- --replication-policy=user-managed --locations=europe-west8 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** «Created version [1] of the secret [langbrain-api-key-lab-01].»

### 2.2 Chi la può leggere: la VM e il server di staging, non la produzione

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud secrets add-iam-policy-binding langbrain-api-key-lab-01 --member=serviceAccount:langbrain-vm@domotica-poc-511707.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor --condition=None --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud secrets add-iam-policy-binding langbrain-api-key-lab-01 --member=serviceAccount:domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor --condition=None --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **`domotica-bff@` (produzione) volutamente no:** la produzione non può parlare con `lab-01`, anche per sbaglio (D-134).

### 2.3 Controllo (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud secrets versions list langbrain-api-key-lab-01 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud secrets get-iam-policy langbrain-api-key-lab-01 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --flatten="bindings[].members" --filter="bindings.role=roles/secretmanager.secretAccessor" --format="value(bindings.members)"
```

- **Atteso:** la versione `1`, `enabled`; esattamente due righe, `serviceAccount:langbrain-vm@…` e `serviceAccount:domotica-bff-staging@…`.

## 3. Il motore `lab-01` sulla VM

### 3.0 Il catalogo con la sola Plug

**Che cos'è:** il file che dice al motore quali dispositivi ci sono (formato in `engine/connector/shelly/catalog.py`). Non contiene segreti.

**3.0.1 Scriverlo sul PC e controllarlo con il lettore del motore** (scrive solo sul PC, fuori dal repository).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
mkdir -p ~/domhouse-lab-01
cat > ~/domhouse-lab-01/catalog.yaml <<'EOF'
rooms:
  - {room_id: laboratorio, name: Laboratorio}
devices:
  - device_id: dev-presa-lab
    label: Presa del laboratorio
    room_id: laboratorio
    capabilities: {switch: {}, power_meter: {}}
    shelly: {id: shellyplugmg3-9070695cb0d0, type: plug}
EOF
.venv/Scripts/python.exe -c "from pathlib import Path; from engine.connector.shelly.catalog import load_catalog; from engine.connector.shelly.offline import load_thresholds; c = load_catalog(Path.home() / 'domhouse-lab-01' / 'catalog.yaml', load_thresholds()); print('catalogo valido:', [(d.device_id, d.shelly_id, d.device_type) for d in c.devices])"
```

- **Atteso:** `catalogo valido: [('dev-presa-lab', 'shellyplugmg3-9070695cb0d0', 'plug')]`.
- o1 l'ha già controllato con il codice di `d274386`, l'immagine del motore: valido, profilo «Shelly Plug M Gen3», soglia offline 120 s.

**3.0.2 Copiarlo sulla VM** (scrive sulla VM, nella cartella di chi si collega).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute scp ~/domhouse-lab-01/catalog.yaml langbrain-dev:catalog-lab-01.yaml --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** `catalog.yaml` al 100 %.

**3.0.3 Metterlo dove lo legge il motore** (scrive sulla VM). Il motore lo cerca in `/data/lab-01/catalog.yaml`. La cartella appartiene all'utente del container (10001).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo install -d -m 750 -o 10001 -g 10001 /data/lab-01 && sudo install -m 640 -o 10001 -g 10001 ~/catalog-lab-01.yaml /data/lab-01/catalog.yaml && sudo ls -ln /data/lab-01'
```

- **Atteso:** `-rw-r----- 1 10001 10001 … catalog.yaml`.

### 3.1 Installare e avviare il motore (scrive sulla VM)

**Che cosa fa** `engine-vm.sh install`, già sulla VM dal lotto pubblicato:

1. scrive `/opt/domhouse/lab-01.settings` (`CONNECTOR=shelly`, porta 8169);
2. scrive `/etc/domhouse/lab-01.env`, permessi 600, con la chiave del passo 2 e il conto del connector:
   - `SHELLY_MQTT_HOST=172.30.83.2`, `PORT=1883`, `TLS=false`, `USERNAME=lab-01.connector`;
   - la password dal segreto `langbrain-shelly-lab-01`;
3. mette il motore anche nella rete interna del broker (`compose.broker.yaml`);
4. lo avvia e aspetta `/health`.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh install lab-01 8169 europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:d274386 shelly'
```

- **Atteso, nell'ordine:**
  1. le impostazioni con `CONNECTOR=shelly` e `PORT=8169`;
  2. «Conto del connector sul broker dal segreto langbrain-shelly-lab-01»;
  3. «scritto /etc/domhouse/lab-01.env (chiave e conto del connector sul broker)»;
  4. in fondo `health 200: ok {…} connector up`.
- **`health 200: degraded … connector up`:** il motore e il broker vanno, ma la Plug non risulta collegata. Controlla la verifica 1 della tappa A.
- **Errori possibili:**

| Che cosa compare | Causa |
|---|---|
| «segreto langbrain-api-key-lab-01 non leggibile dalla VM» | manca il passo 2.2 |
| «segreto langbrain-shelly-lab-01 non leggibile dalla VM» | permesso della VM sul segreto del connector mancante |
| «health non risponde 200» e nel log «connector setup failed» (codice d'uscita 3) | catalogo mancante o sbagliato: passi 3.0.x |
| «health non risponde 200» e nel log «mqtt broker not connected» | il motore non raggiunge il broker: incolla il log, o1 guarda |

### 3.2 Controlli dopo l'installazione (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='curl -s -w " HTTP %{http_code}\n" http://10.198.0.2:8169/api/v1/health; sudo bash /opt/domhouse/engine-vm.sh api lab-01 GET /devices | head -1; sudo docker logs --since 10m domhouse-broker 2>&1 | grep "lab-01.connector"; sudo docker logs --tail 20 engine-lab-01 2>&1 | grep -i -E "warn|error" | tail -5; free -m | head -2'
```

| Riga | Atteso |
|---|---|
| `/health` | `"apartment_id":"lab-01"`, `"connector":{"status":"up","connected_devices":1,…}` e `HTTP 200` |
| `/devices` | il dispositivo `dev-presa-lab` con `"online":true`, lo stato di `switch` e i watt |
| broker | «New client connected … u'lab-01.connector'» |
| avvisi del motore | nessuna riga, oppure avvisi da incollare alla memoria storica |
| memoria | `available` più bassa di quella del passo 1.1 di circa 100 MB (**da verificare**: è il primo motore con il connector Shelly sulla VM) |

- Dal prossimo giro di 5 minuti il controllo della VM scrive anche «engine ok lab-01» e il backup notturno copia `lab-01`. Si vede con:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo journalctl -t domhouse-check --since "-6min" --no-pager | grep -E "lab-01|motori"'
```

- **Atteso:** «engine ok lab-01» e «domhouse-check: 2 motori, 0 muti».

## 4. L'appartamento nell'app di staging

**Che cosa serve:**

- il server di staging raggiunge già la VM attraverso la rete interna (Direct VPC egress) e ammette la porta 8169 (`INSTANCE_ALLOWED`);
- la chiave la legge da `langbrain-api-key-lab-01` (passo 2);
- i dati vanno nel database Firestore `staging`, non in quello della produzione.

### 4.1 Crearlo (nell'app di staging, come gestore della piattaforma)

Sito: `https://domhouse-staging.web.app`. **Organizzazioni** → l'organizzazione di prova che usi per lo staging → **Appartamenti** → **Nuovo appartamento**:

| Campo | Valore |
|---|---|
| ID | `lab-01` (proprio questo: dà il nome alla chiave) |
| Nome | `Laboratorio di Youssouf (lab-01)` |
| URL istanza | `http://10.198.0.2:8169/api/v1` |
| Porta | vuota (è già nell'URL) |
| Fuso orario | `Europe/Rome` |
| ID Italianway | vuoto: nessuna prenotazione vera deve arrivarci |
| Istanza simulata (appartamento dimostrativo) | **spenta**: i dispositivi sono veri |

### 4.2 Verifica connessione

Sulla riga dell'appartamento: **Verifica connessione**.

- **Atteso:** «Connessione OK».
- **«In questo ambiente di prova si collegano solo il motore di sviluppo e quelli della prova di carico: indirizzo e porta non ammessi»:** URL o porta scritti male; deve essere esattamente `http://10.198.0.2:8169/api/v1`.
- **Altro errore:** incolla il testo alla memoria storica.

### 4.3 La Plug nell'app (sola lettura)

Apri l'appartamento «Laboratorio di Youssouf (lab-01)».

- **Atteso:** la stanza «Laboratorio» con «Presa del laboratorio», in linea, con lo stato (accesa o spenta) e i watt.

## 5. Le prove app ↔ dispositivi

**Regola per ogni prova che comanda un dispositivo:** prima Y conferma che a quel dispositivo non è attaccato niente che non possa spegnersi; durante, Y guarda il dispositivo.

| N. | Prova | Serve | Atteso nell'app | Atteso al banco |
|---|---|---|---|---|
| 1 | Plug: consumi | solo la Plug | i watt cambiano quando Y attacca o stacca un carico (una lampada) | — |
| 2 | Plug accesa e spenta dall'app (**Accendi**, **Spegni**) | la Plug e **Y presente** | lo stato passa da «in corso» al nuovo valore in pochi secondi; nelle **Decisioni** l'accensione con esito applicato | Y vede la presa scattare |
| 3 | Plug staccata dalla corrente da Y | la Plug e Y | dopo circa 2 minuti la presa risulta «non in linea» (soglia del tipo `plug`, 120 s, più il controllo del silenzio); riattaccata, torna in linea | — |
| 4 | Temperatura del sensore H&T che sale quando Y lo scalda con la mano | **catalogo di Y** (sezione 6) | la temperatura sale entro qualche secondo dal pacchetto | — |
| 5 | Contatto della finestra aperto | **catalogo di Y**, con un clima o una caldaia nel catalogo | «Aperta»; dopo i minuti della regola, il motore spegne clima e caldaia | Y vede il relè della caldaia scattare |
| 6 | Sensore di movimento e misuratore EM Mini | **catalogo di Y** | movimento rilevato; watt del misuratore | — |
| 7 | Verifiche al banco: orologio del ponte dopo un riavvio (B1), `errors` dei BLU, consumo di uno split fermo | **catalogo di Y** e **immagine nuova** (6.4) | — | esiti da registrare |

Verifica di ogni comando sul motore (sola lettura):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh api lab-01 GET "/decisions?limit=3" | head -1; sudo bash /opt/domhouse/engine-vm.sh api lab-01 GET /devices | head -1'
```

- **Atteso dopo la prova 2:** fra le ultime decisioni `"action":"turn_on"` (o `turn_off`), `"outcome":"applied"`, `"device_id":"dev-presa-lab"`; nel dispositivo `"switch":{"on":…}` uguale a quello che Y vede.
- **Da verificare la prima volta:** il tempo da «Accendi» allo stato confermato. Y ha misurato al banco 75 ms di mediana per la Plug da sola. Nell'app ci aggiungiamo il percorso server → motore → broker → presa e ritorno.

## 6. Da completare con il catalogo di Youssouf

### 6.1 Che cosa chiedere a Y, per ogni apparecchio

| Campo | Esempio | Note |
|---|---|---|
| id nativo dello Shelly | `shelly1g4-…`, `shellyemmini…-…` | dalla pagina web del dispositivo; diventa l'utente del broker `lab-01.<id nativo>` |
| modello | Shelly 1 Gen4, EM Mini Gen4 | deve avere un profilo in `translate.py` |
| dispositivi del catalogo che ospita | un relè «Caldaia», un misuratore «Split» | un apparecchio può ospitarne più d'uno |
| sensori BLU di cui fa da ponte | MAC del sensore e tipo (`blu_ht`, `blu_motion`, `blu_door_window`) | i sensori BLU **non** hanno un utente del broker: passano dal ponte |
| che cosa gli è attaccato al banco | una lampada, niente | per sapere che cosa si può spegnere nelle prove |

E il catalogo completo nel formato di `catalog.py`, con la Plug già scritta come al passo 3.0.1 (`device_id` `dev-presa-lab`).

### 6.2 Utente del broker per ogni apparecchio (scrive su Secret Manager e sulla VM)

Per **ogni** id nativo dato da Y. Il comando sotto è la forma: o1 lo riscrive completo, con gli id veri, quando arrivano.

```bash
# Git Bash — FORMA, da completare con l'id nativo di Y
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 bash scripts/broker-secrets.sh add-device lab-01 <id nativo>
```

Poi una sola volta, dopo l'ultimo:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/broker-vm.sh sync'
```

- **Atteso:** «lab-01: connector e N dispositivi» (N = la Plug più gli apparecchi nuovi), «changed», «utenti e permessi ricaricati».

### 6.3 Impostazioni MQTT su ogni apparecchio (le fa Y)

Come la Plug nella tappa A: la tabella è in `docs/motore-vm.md`, G2, passo B5. Valori di `lab-01`:

| Campo | Valore |
|---|---|
| `server` | `mqtt.dh-lab.eu:8883` |
| `ssl_ca` | `"ca.pem"` |
| `client_id` e `user` | `lab-01.<id nativo>` |
| `topic_prefix` | `lab-01/<id nativo>` |
| `rpc_ntf`, `enable_rpc` | `true` |
| `status_ntf`, `enable_control` | `false` |
| `pass` | la password del segreto: **come arriva a Y è una decisione del committente** (domanda della memoria storica). Proposta di o1: come la Plug l'11 novembre, e appena l'apparecchio è collegato si cambia con il metodo della tappa A, sezione 4, così quella passata non vale più |

Controllo: verifica 1 della tappa A, con l'id nuovo.

### 6.4 Immagine del motore per i sensori BLU

- I sensori BLU hanno bisogno di `ebfe4dc` (PR #10) **e** della correzione di B1 che Y sta facendo (decisione 1113).
- Quando la correzione è unita e provata, si costruisce l'immagine di quel commit (`docs/motore-vm.md`, B1, con `scripts/deploy-engine.sh`). Poi:

```bash
# Git Bash — FORMA, da completare con il commit della correzione di B1
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh update lab-01 europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:<commit>'
```

### 6.5 Catalogo nuovo sul motore

- Passi 3.0.1–3.0.3 con il file di Y, poi un riavvio del motore. Va fatto con `key`, che riscrive il file della chiave e ricrea il container, e così fa rileggere il catalogo:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh key lab-01'
```

- **Atteso:** `health 200: ok … connector up`, poi il passo 3.2 con tutti i dispositivi.
- Un catalogo sbagliato ferma il motore (codice 3). Si rimette quello di prima, che è ancora in `~/domhouse-lab-01/catalog.yaml` sul PC, con i passi 3.0.2–3.0.3 e lo stesso comando `key`.

## 7. Tornare indietro

| Che cosa | Come | Effetto |
|---|---|---|
| L'appartamento nell'app | nell'app di staging, come gestore: elimina l'appartamento `lab-01` | lo staging non lo chiama più; il motore resta |
| Il motore | comando 7.1 | il motore si ferma; il controllo ogni 5 minuti e il backup non lo contano più; i dati restano in `/data/lab-01` |
| La chiave | resta (non costa nulla); per toglierla: comando della memoria storica | — |
| Gli utenti del broker | `broker-secrets.sh remove-device lab-01 <id nativo>`, poi `broker-vm.sh sync` | l'apparecchio non entra più |

### 7.1 Fermare e togliere il motore `lab-01` (scrive sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='cd /opt/domhouse && sudo ENGINE_BIND_IP=10.198.0.2 docker compose --env-file /opt/domhouse/lab-01.settings -f compose.yaml -f compose.broker.yaml down && sudo mv /opt/domhouse/lab-01.settings /opt/domhouse/lab-01.settings.tolto && sudo rm -f /etc/domhouse/lab-01.env && sudo docker ps --format "{{.Names}}"'
```

- **Atteso:** «Container engine-lab-01 Removed»; nell'elenco finale restano `engine-dev` e `domhouse-broker`.
- Spostare `lab-01.settings` fa sì che il controllo ogni 5 minuti non lo cerchi più: altrimenti scatterebbe l'allarme «motore muto». Il file `.env` conteneva la chiave e la password del connector: si toglie, e un `install` lo riscrive.
- **Per rimetterlo:** il passo 3.1. I dati in `/data/lab-01` sono ancora lì.

## 8. Rischi e cose da verificare

1. **Niente appartamenti veri (D-134):** `lab-01` è il banco di Y.
   - Sta solo nello staging.
   - La produzione non ha la chiave (passo 2.2) né l'appartamento.
2. **Produzione non toccata:** nessuna pubblicazione e nessun cambio al server. Il motore `dev` e il broker non si riavviano. L'unica cosa in comune è la VM.
3. **La VM è una sola, e piccola (e2-small):** un motore in più.
   - Memoria da guardare al passo 3.2.
   - Il controllo ogni 5 minuti scrive `vm mem_used_pct`.
4. **Allarmi:** da quando è installato, `lab-01` entra nel controllo ogni 5 minuti.
   - Se il motore cade o perde il broker, arriva l'email «Motori: motore muto o giù».
   - Una Plug scollegata **non** fa scattare l'allarme: il motore risponde «degraded», non «down».
5. **Prova di carico:** finché `lab-01` occupa la porta 8169, `scripts/load/carico_vm.py` si rifiuta di partire, perché controlla che le porte 8150–8189 siano libere. Prima della prova di carico si ferma `lab-01` (7.1).
6. **Comandi ai dispositivi veri:** possono spegnere ciò che Y ha attaccato. Per questo Y conferma prima di ogni prova di comando (sezione 5).
7. **Componenti nuovi, da verificare** (regola del 10 novembre):
   - è la **prima volta** che il connector Shelly gira sulla VM e si collega al broker vero, con il conto di `lab-01.connector`;
   - prima volta che il catalogo viene letto da `/data/lab-01/catalog.yaml`;
   - prima volta che l'app comanda uno Shelly vero.
   - Nessuna versione nuova di immagini o programmi: il motore è quello già pubblicato (`d274386`), il broker non cambia.
8. **Sensori BLU:** non prima della correzione di B1 e dell'immagine nuova (6.4). Con l'immagine di oggi un sensore morto potrebbe risultare vivo dopo un riavvio del ponte.
