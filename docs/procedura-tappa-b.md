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
| Immagine del motore | `europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:247fda0` | quella della pubblicazione di `247fda0` del 13 novembre, la stessa di `dev`; contiene il connector Shelly con #10 e #11 e basta per la Plug. Per i sensori BLU serve un'immagine con la correzione di B1 (sezione 6.4) |
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

**Si comincia dopo la pubblicazione di `247fda0`** (committente, 13 novembre): il motore di `lab-01` usa la stessa immagine di `dev`.

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
| immagine di `dev` | `europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:247fda0` |
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
- o1 l'ha già controllato con il codice di `247fda0`, quello dell'immagine del motore: valido, profilo «Shelly Plug M Gen3», soglia offline 120 s.

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
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh install lab-01 8169 europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:247fda0 shelly'
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

## 5. Le prove app ↔ dispositivi (il centro della tappa B)

Ogni prova dimostra un pezzo del punto di contatto fra la nostra parte (sito, server, motore, broker) e quella di Y (connector e dispositivi). Per ogni prova: che cosa fai tu nell'app, che cosa fa o guarda Y al banco, che cosa deve comparire, e da che parte sta il guasto se qualcosa non torna.

### 5.0 Gli strumenti per capire di chi è il guasto

Il percorso di un comando:

| Tratto | Di chi | Come si vede |
|---|---|---|
| 1. sito → server di staging | nostro | l'app mostra un errore; log del server (S) |
| 2. server → motore `lab-01` | nostro | «Verifica connessione» nell'app; `/health` dalla VM (passo 3.2) |
| 3. motore → connector (dentro lo stesso container) | confine: il motore è nostro, il connector di Y | decisioni e log del motore (M) |
| 4. connector → broker | confine: il broker è nostro, il collegamento lo fa il connector di Y | `/health` dice `connector up`; log del broker con `lab-01.connector` (passo 3.2) |
| 5. broker → dispositivo e ritorno | di Y (dispositivo e sue impostazioni), salvo certificato e utenti del broker, che sono nostri | ascolto (A): richiesta del connector e risposta del dispositivo |

**Regola per decidere:** si guarda l'ascolto (A).

- **La richiesta non c'è:** il guasto è prima del broker, cioè nel motore, nel server o nel sito.
- **La richiesta c'è ma la risposta no:** il guasto è nel dispositivo o nella sua rete.
- **Richiesta e risposta ci sono, ma l'app non cambia:** il guasto è nel connector, che non legge bene la risposta, oppure nel motore, nel server o nel sito. Lo dicono il log del motore (M) e il log del server (S).

**(A) Ascolto dei messaggi della presa per 40 secondi** (sola lettura). Lancialo e, entro 5 secondi, fai l'azione della prova nell'app. Per un altro apparecchio si cambia l'id nativo nel topic (sezione 6).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set +x; T=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token | python3 -c "import json,sys; print(json.load(sys.stdin)[\"access_token\"])"); PW=$(curl -sf -H "Authorization: Bearer $T" https://secretmanager.googleapis.com/v1/projects/domotica-poc-511707/secrets/langbrain-shelly-lab-01/versions/latest:access | python3 -c "import base64,json,sys; print(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"]).decode().strip())"); [ -n "$PW" ] || { echo "password del connector non letta da Secret Manager"; exit 1; }; export PW; sudo --preserve-env=PW docker exec -e PW domhouse-broker sh -c "mosquitto_sub -h 172.30.83.2 -p 1883 -i lab-01.connector-ascolto-prove -u lab-01.connector -P \"\$PW\" -t \"lab-01/shellyplugmg3-9070695cb0d0/#\" -v -W 40"; unset PW T'
```

| Riga | Che cos'è |
|---|---|
| `…/rpc {"id":…,"src":"lab-01/shellyplugmg3-9070695cb0d0/connector","method":"Switch.Set",…}` | la richiesta del connector: il comando è arrivato fino al broker |
| `…/connector/rpc {"id":…,"result":…}` | la risposta della presa |
| `…/events/rpc {"method":"NotifyStatus",…"output":…}` | la presa annuncia il cambio di stato |
| `…/online true` | lo stato conservato (normale) |

**(M) Decisioni, dispositivi e log del motore** (sola lettura):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh api lab-01 GET "/decisions?limit=3" | head -1; sudo bash /opt/domhouse/engine-vm.sh api lab-01 GET /devices | head -1; sudo docker logs --since 10m engine-lab-01 2>&1 | tail -15'
```

**(S) Avvisi ed errori del server di staging negli ultimi 10 minuti** (sola lettura):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="domotica-bff-staging" AND severity>=WARNING' --freshness=10m --limit=10 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format='value(timestamp,severity,jsonPayload.message,textPayload)'
```

### 5.1 Prova 1: la presa si vede nell'app (lettura)

| | |
|---|---|
| **Tu, nell'app** | apri «Laboratorio di Youssouf (lab-01)» |
| **Y, al banco** | attacca alla presa una lampada e la accende, poi la spegne |
| **Deve comparire** | «Presa del laboratorio» in linea; i watt salgono con la lampada accesa e tornano vicino a 0 da spenta, entro circa un minuto |
| **Se la presa è «non in linea»** | verifica 1 della tappa A. Se la presa non è nel broker, il guasto è dalla parte di Y (presa o sua rete). Se è nel broker ma l'app la dà fuori linea: (M), poi o1 guarda catalogo e connector |
| **Se i watt non cambiano** | (A) per un minuto. Se le `NotifyStatus` con `apower` cambiano ma l'app no, il guasto è da noi o nel connector: (M). Se la presa non manda niente, è dalla parte di Y |

### 5.2 Prova 2: accendere e spegnere la presa dall'app (comando)

| | |
|---|---|
| **Prima** | Y conferma che alla presa è attaccata solo la lampada |
| **Tu, nell'app** | lanci (A), poi entro 5 secondi premi **Accendi** sulla presa; dopo, lo stesso con **Spegni** |
| **Y, al banco** | guarda la lampada e dice quando scatta |
| **Deve comparire nell'app** | lo stato passa da «in corso» al nuovo valore in pochi secondi; in **Decisioni** l'azione con esito applicato |
| **Deve comparire in (A)** | la richiesta `Switch.Set`, la risposta, poi la `NotifyStatus` con `output` nuovo |
| **Deve comparire in (M)** | `"action":"turn_on"` (o `turn_off`), `"outcome":"applied"`, `"device_id":"dev-presa-lab"` |
| **Diagnosi** | Nessuna richiesta in (A): guasto da noi (sito, server o motore), guarda (S) e (M). Richiesta senza risposta: dalla parte di Y (la presa). Risposta arrivata e lampada scattata, ma l'app resta «in corso» o dice fallito: connector o motore, (M) |
| **Da verificare la prima volta** | il tempo da «Accendi» allo stato confermato. Al banco Y ha misurato 75 ms di mediana per la Plug da sola; qui si aggiunge il percorso sito → server → motore → broker → presa e ritorno |

### 5.3 Prova 3: la presa staccata dalla corrente (fuori linea e ritorno)

| | |
|---|---|
| **Tu, nell'app** | guardi la presa |
| **Y, al banco** | stacca la presa dalla corrente; dopo 3 minuti la riattacca |
| **Deve comparire** | dopo circa 2 minuti la presa è «non in linea» (soglia 120 s più il controllo del silenzio); riattaccata, torna in linea in meno di un minuto, con il suo stato |
| **Diagnosi** | Non va mai fuori linea: (M), connector. Non torna in linea: verifica 1 della tappa A. Se non è nel broker, il guasto è dalla parte di Y; se è nel broker, connector o motore: (M) |

### 5.4 Prova 4: temperatura del sensore H&T (da completare con il catalogo di Y, sezione 6)

| | |
|---|---|
| **Tu, nell'app** | guardi la temperatura della stanza del sensore |
| **Y, al banco** | scalda il sensore con la mano per un minuto |
| **Deve comparire** | la temperatura sale di qualche grado, entro qualche secondo da ogni pacchetto del sensore |
| **Diagnosi** | (A) sul **ponte** BLU. Se le `NotifyStatus` con `bthomesensor` cambiano ma l'app no: connector o motore, (M). Se dal ponte non arriva niente: sensore o ponte, dalla parte di Y |

### 5.5 Prova 5: contatto della finestra aperto e regola (da completare con il catalogo di Y)

| | |
|---|---|
| **Serve** | nel catalogo un contatto BLU e un relè «caldaia» (o un clima) nella stessa stanza; la regola della finestra accesa nell'app |
| **Tu, nell'app** | accendi la caldaia; poi guardi la stanza |
| **Y, al banco** | apre il contatto e lo tiene aperto oltre i minuti della regola |
| **Deve comparire** | «Aperta» entro qualche secondo; dopo i minuti della regola, la caldaia spenta dal motore, con la decisione e il suo motivo in **Decisioni** |
| **Diagnosi** | «Aperta» non compare: come la prova 4. Compare ma la caldaia resta accesa: motore (nostro), (M). Il motore decide ma il relè non scatta: come la prova 2 |

### 5.6 Prova 6: movimento e misuratore EM Mini (da completare con il catalogo di Y)

| | |
|---|---|
| **Tu, nell'app** | guardi il sensore di movimento e il misuratore |
| **Y, al banco** | passa davanti al sensore; accende un carico sul misuratore |
| **Deve comparire** | movimento rilevato; watt del misuratore |
| **Diagnosi** | come le prove 4 e 1 |

### 5.7 Prova 7: le verifiche al banco (da completare; serve l'immagine nuova, 6.4)

| Verifica | Y fa | Si guarda |
|---|---|---|
| Orologio del ponte dopo un riavvio (B1) | riavvia il ponte con un H&T spento da oltre 5 minuti | l'H&T deve restare «non in linea» nell'app; (A) sul ponte per l'orologio di `sys` |
| `errors` dei sensori BLU | toglie e rimette la batteria di un sensore | il sensore va fuori linea, poi torna entro 5 minuti dal primo pacchetto |
| Consumo di uno split fermo | se ne ha uno sul misuratore | i watt a riposo, per la soglia di conferma dei comandi |

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
   - Nessuna versione nuova di immagini o programmi: il motore è quello della pubblicazione di `247fda0`, il broker non cambia.
8. **Sensori BLU:** non prima della correzione di B1 e dell'immagine nuova (6.4). Con l'immagine di oggi un sensore morto potrebbe risultare vivo dopo un riavvio del ponte.
