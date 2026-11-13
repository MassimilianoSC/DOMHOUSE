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

**Quando si comincia:**

1. dopo la pubblicazione di `247fda0` (committente, 13 novembre): il motore di `lab-01` usa la stessa immagine di `dev`;
2. dopo la risposta del committente sulla porta (decisione aperta, sezione 0);
3. **La tappa A può venire prima o dopo.** I passi 1–4 e la prova 1 si fanno anche senza Youssouf, prima della sezione 4 della tappa A (cambio della password). Se la sezione 4 si fa con il motore acceso, valgono le cautele del rischio 9. La `sync` del passo 6.2 resta vietata fra R1 e R4.

### 1.1 La VM oggi

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker ps --format "{{.Names}}  {{.Ports}}"; ls /opt/domhouse/*.settings; sudo sed -n "s/^ENGINE_IMAGE=//p" /opt/domhouse/dev.settings; ls -l /opt/domhouse/compose.broker.yaml; grep -c SHELLY_MQTT_HOST /opt/domhouse/engine-vm.sh; free -m | head -2; sudo bash /opt/domhouse/broker-vm.sh status | grep -E "^appartamenti|^utenti|^broker ok"'
```

| Riga | Atteso |
|---|---|
| container | `engine-dev` sulla porta 8100 e `domhouse-broker` sulla 8883; **nessun** altro motore, e niente sulla 8169 |
| file delle impostazioni | solo `/opt/domhouse/dev.settings` |
| immagine di `dev` | `europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:247fda0` |
| `compose.broker.yaml` | il file c'è. Senza, il motore non entrerebbe nella rete del broker e `install` fallirebbe con un errore poco chiaro |
| numero dopo il file | maggiore di 0: lo script sulla VM sa passare al motore il conto del connector |
| memoria | annota la colonna `available`: serve per il confronto al passo 3.2 |
| broker | `appartamenti: 1`, `utenti devices: 1`, `utenti connectors: 1`, `broker ok cert_days=…` |

- `broker-vm.sh status` non è del tutto in sola lettura: il suo controllo scrive una riga nel registro della VM e rimette il limite sui collegamenti, se mancasse. È innocuo.
- **Se l'immagine di `dev` è un'altra:** si usa quella nei comandi del passo 3.1. Avvisa la memoria storica, che la sostituisce prima.
- **Se c'è già qualcosa sulla 8169:** fermati.

### 1.1 bis Le porte ammesse dal server di staging (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud run services describe domotica-bff-staging --region=europe-west8 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format='yaml(spec.template.spec.containers[0].env)' | grep -A1 INSTANCE_ALLOWED
```

- **Atteso:** `value: 10.198.0.2:8100,10.198.0.2:8150-8169`. Se la 8169 non c'è, fermati.

### 1.2 I segreti di `lab-01` (solo l'elenco delle versioni, mai il valore)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for s in langbrain-shelly-lab-01 langbrain-shelly-lab-01-devices langbrain-api-key-lab-01; do echo "== $s"; gcloud secrets versions list "$s" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --limit=1; done
```

| Segreto | Atteso |
|---|---|
| `langbrain-shelly-lab-01` | una versione `enabled` (password del connector) |
| `langbrain-shelly-lab-01-devices` | in cima la versione 2 (la sezione 4 della tappa A non è ancora fatta: va bene, si prosegue), oppure la 3 **solo se** R4 è riuscito. Con la 3 ma R4 non riuscito: fermati, la sezione 4 è a metà |
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
cp ~/domhouse-lab-01/catalog.yaml ~/domhouse-lab-01/catalog-solo-plug.yaml
git diff --stat 247fda0 HEAD -- engine/connector/shelly/ | tail -1
```

- **Atteso:**
  1. `catalogo valido: [('dev-presa-lab', 'shellyplugmg3-9070695cb0d0', 'plug')]`;
  2. nessuna riga dopo: il codice del connector sul PC è uguale a quello dell'immagine `247fda0`. Se compare una riga, il controllo è fatto su codice diverso: avvisa la memoria storica.
- La copia `catalog-solo-plug.yaml` serve per tornare indietro dopo il catalogo di Y (6.5).
- o1 l'ha già controllato con il codice di `247fda0`: valido, profilo «Shelly Plug M Gen3», soglia offline 120 s.

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
| «health non risponde 200» e nel log «mqtt connect failed» o «mqtt first connection still pending» | il motore non raggiunge il broker, oppure il broker rifiuta il conto del connector: incolla il log, o1 guarda |

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
| avvisi del motore | nessuna riga, oppure avvisi da incollare alla memoria storica. «mqtt rpc answer dropped» è atteso solo se la sezione 4 della tappa A è stata fatta con il motore già acceso: sono le risposte 901 e 902 dei nostri comandi |
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

### 4.1 Crearlo (nell'app di staging, con il tuo account di **gestore della piattaforma**)

Sito: `https://domhouse-staging.web.app`. **Organizzazioni** → **«Flatsharing (prova)»**, l'organizzazione di prova dove stanno già `demo-vuoto`, `demo-occupato` e `dev` → **Appartamenti** → **Nuovo appartamento**:

| Campo nell'app | Valore |
|---|---|
| ID | `lab-01` (proprio questo: dà il nome alla chiave) |
| Nome | `Laboratorio di Youssouf (lab-01)` |
| Indirizzo del sistema domotico | `http://10.198.0.2:8169/api/v1` |
| Porta | vuota (è già nell'indirizzo) |
| Fuso orario | `Europe/Rome` |
| ID Italianway | vuoto: nessuna prenotazione vera deve arrivarci |
| Appartamento dimostrativo | **spento**: i dispositivi sono veri |
| Attivo | **acceso** (è già così) |

- **«Collegamento già usato da un altro appartamento»:** un appartamento della prova di carico usa già `10.198.0.2:8169`. Fermati e avvisa la memoria storica.

### 4.2 Verifica connessione

Sulla riga dell'appartamento: **Verifica connessione**.

- **Atteso:** «Connessione OK».
- **«In questo ambiente di prova si collegano solo il motore di sviluppo e quelli della prova di carico: indirizzo e porta non ammessi»:** indirizzo o porta scritti male; deve essere esattamente `http://10.198.0.2:8169/api/v1`.
- **Altro errore:** incolla il testo alla memoria storica.

### 4.3 La Plug nell'app (sola lettura)

**Con quale account:** il tuo account di lavoro, **amministratore di «Flatsharing (prova)»**. Il gestore della piattaforma non vede i dispositivi degli appartamenti. Vale anche per tutte le prove della sezione 5.

Apri l'appartamento «Laboratorio di Youssouf (lab-01)».

- **Atteso:** la stanza «Laboratorio» con «Presa del laboratorio», in linea, con lo stato (accesa o spenta) e i watt.

## 5. Le prove app ↔ dispositivi (il centro della tappa B)

Ogni prova dimostra un pezzo del punto di contatto fra la nostra parte (sito, server, motore, broker) e quella di Y (connector e dispositivi). Per ogni prova: che cosa fai tu nell'app, che cosa fa o guarda Y al banco, che cosa deve comparire, e da che parte sta il guasto se qualcosa non torna.

### 5.0 Gli strumenti per capire di chi è il guasto

Il percorso di un comando:

| Tratto | Di chi | Come si vede |
|---|---|---|
| 1. sito → server di staging | nostro | l'app mostra un errore; avvisi del server (S) |
| 2. server → motore `lab-01` | nostro | «Verifica connessione» nell'app; `/health` dalla VM (passo 3.2) |
| 3. motore → connector (dentro lo stesso container) | confine: il motore è nostro, il connector di Y | decisioni e log del motore (M): «command sent», «command result» |
| 4. connector → broker | confine: il broker è nostro, il collegamento lo fa il connector di Y | `/health` dice `connector up`; log del broker con `lab-01.connector` (passo 3.2) |
| 5. broker → dispositivo e ritorno | il dispositivo e le sue impostazioni sono di Y; certificato, utenti e permessi del broker sono nostri | ascolto (A): richieste del connector, risposte e notifiche del dispositivo |

**Regola per decidere, nell'ordine:**

1. **(M): c'è la decisione e c'è «command sent»?**
   - No: il comando non è arrivato al connector. Il guasto è nostro: sito, server o motore. Guarda (S).
2. **(M): «command result» con `outcome` `failed` e `reason` `device_offline` o `internal_error`, e in (A) nessuna richiesta?**
   - Il connector ha chiuso il comando senza mandarlo: crede la presa scollegata, oppure non sa tradurre il comando.
   - Il guasto è del connector (Y), oppure dello stato «online» della presa: verifiche 1 e 2 della tappa A.
3. **(A): la richiesta c'è, la risposta no?**
   - In (A) arrivano comunque le `NotifyStatus` della presa, o la lampada scatta: la presa risponde ma non può scrivere sul suo topic di risposta. Permessi o topic del broker: nostro.
   - Dalla presa non arriva niente: la presa o la rete di Y.
4. **(A): richieste e risposte ci sono tutte, ma l'app non cambia o dice fallito?**
   - (M) «command result» con esito riuscito, ma l'app non lo mostra: server o sito, nostro. Guarda (S).
   - (M) «command result» fallito (per esempio `read back failed`) nonostante le risposte in (A): il connector non legge bene le risposte (Y).

**(A) Ascolto dei messaggi della presa per 40 secondi** (sola lettura).

- Lancialo e aspetta la riga «IN ASCOLTO»: il collegamento alla VM impiega qualche secondo. Poi fai l'azione della prova nell'app.
- Ogni riga ha l'ora (UTC, dal broker), il topic e il contenuto.
- Per un altro apparecchio si cambia l'id nativo nel topic (sezione 6).
- **Mai durante R2 della tappa A:** mostrerebbe a video il messaggio con la password nuova.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set +x; T=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token | python3 -c "import json,sys; print(json.load(sys.stdin)[\"access_token\"])"); PW=$(curl -sf -H "Authorization: Bearer $T" https://secretmanager.googleapis.com/v1/projects/domotica-poc-511707/secrets/langbrain-shelly-lab-01/versions/latest:access | python3 -c "import base64,json,sys; print(base64.b64decode(json.load(sys.stdin)[\"payload\"][\"data\"]).decode().strip())"); [ -n "$PW" ] || { echo "password del connector non letta da Secret Manager"; exit 1; }; export PW; echo "IN ASCOLTO per 40 secondi: fai adesso la prova"; sudo --preserve-env=PW docker exec -e PW domhouse-broker sh -c "mosquitto_sub -h 172.30.83.2 -p 1883 -i lab-01.connector-ascolto-prove -u lab-01.connector -P \"\$PW\" -t \"lab-01/shellyplugmg3-9070695cb0d0/#\" -F \"%I %t %p\" -W 40"; unset PW T'
```

| Riga | Che cos'è |
|---|---|
| `… lab-01/shellyplugmg3-9070695cb0d0/rpc {"id":…,"src":"lab-01/shellyplugmg3-9070695cb0d0/connector","method":"Switch.Set",…}` | la richiesta del connector: il comando è arrivato fino al broker |
| `… …/connector/rpc {"id":…,"result":…}` | la risposta della presa al comando |
| `… …/rpc {…"method":"Switch.GetStatus",…}` e poi un'altra `…/connector/rpc` con `"output"` | la rilettura: il connector controlla che la presa sia davvero nello stato chiesto. Senza questa coppia l'app resta «in corso» e poi segna fallito |
| `… …/events/rpc {"method":"NotifyStatus",…"output":…}` | la presa annuncia il cambio di stato |
| `… …/events/rpc {"method":"NotifyStatus",…"apower":…}` | i consumi, circa una volta al minuto |
| `… …/online true` | lo stato conservato (normale) |

**(M) Decisioni e log del motore** (sola lettura):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh api lab-01 GET "/decisions?limit=3&device_id=dev-presa-lab" | head -1; sudo bash /opt/domhouse/engine-vm.sh api lab-01 GET /devices | head -1; sudo docker logs --since 10m engine-lab-01 2>&1 | grep -E "command|device|mqtt" | tail -20'
```

- Nel log: «command sent» (il motore ha passato il comando al connector), poi «command result» con `outcome`, `reason` e `detail`.

**(S) Avvisi ed errori del server di staging negli ultimi 10 minuti** (sola lettura). Il server scrive `level` e `msg`, non la gravità di Cloud Logging: il filtro è quello del rapporto di rodaggio.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="domotica-bff-staging" AND (jsonPayload.level="warning" OR jsonPayload.level="error" OR severity>=WARNING)' --freshness=10m --limit=20 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format='value(timestamp,jsonPayload.level,jsonPayload.apartment_id,jsonPayload.msg,jsonPayload.error,httpRequest.status,httpRequest.requestUrl,textPayload)'
```

### 5.1 Prova 1: la presa si vede nell'app (lettura)

| | |
|---|---|
| **Tu, nell'app** | apri «Laboratorio di Youssouf (lab-01)» |
| **Y, al banco** | attacca alla presa una lampada e la accende, poi la spegne. Con la lampada accesa legge i watt (`apower`) sulla pagina web della presa e te li dice |
| **Deve comparire** | «Presa del laboratorio» in linea; i watt salgono con la lampada accesa e tornano vicino a 0 da spenta, entro circa un minuto; **gli stessi watt** della pagina web, a meno di qualche watt per i tempi diversi |
| **Se la presa è «non in linea»** | verifica 1 della tappa A. Se la presa non è nel broker, il guasto è dalla parte di Y (presa o sua rete). Se è nel broker ma l'app la dà fuori linea: (M), poi o1 guarda catalogo e connector |
| **Se i watt non cambiano** | (A) per un minuto. Se le `NotifyStatus` con `apower` cambiano ma l'app no: connector o motore, (M). Se la presa non manda niente: dalla parte di Y |
| **Se i watt sono diversi da quelli della pagina web** | la traduzione dei valori del connector (Y): annota i due numeri |

### 5.2 Prova 2: accendere e spegnere la presa dall'app (comando)

| | |
|---|---|
| **Prima** | Y conferma che alla presa è attaccata solo la lampada |
| **Tu, nell'app** | lanci (A); alla riga «IN ASCOLTO» premi **Accendi** sulla presa. Poi di nuovo (A) e **Spegni** |
| **Y, al banco** | guarda la lampada e dice quando scatta |
| **Deve comparire nell'app** | lo stato passa da «in corso» al nuovo valore in pochi secondi; in **Decisioni** l'azione con esito applicato |
| **Deve comparire in (A), in quest'ordine** | la richiesta `Switch.Set` e la sua risposta; la rilettura `Switch.GetStatus` e la sua risposta con `output` nuovo; la `NotifyStatus` con `output` nuovo |
| **Deve comparire in (M)** | `"action":"turn_on"` (o `turn_off`), `"outcome":"applied"`, `"device_id":"dev-presa-lab"`; nel log «command sent» e «command result» |
| **Diagnosi** | la regola del 5.0, nell'ordine |
| **Tempo, da verificare la prima volta** | dall'ora della richiesta `Switch.Set` a quella della risposta alla rilettura, in (A). Al banco Y ha misurato 75 ms di mediana per la Plug da sola; da «Accendi» allo stato confermato nell'app si aggiunge il percorso sito → server → motore |

### 5.3 Prova 3: la presa staccata dalla corrente (fuori linea, comando a vuoto, ritorno)

| | |
|---|---|
| **Tu, nell'app** | guardi la presa. Quando è «non in linea», lanci (A) e premi **Accendi** |
| **Y, al banco** | stacca la presa dalla corrente; la riattacca solo quando glielo dici, dopo il comando a vuoto |
| **Deve comparire** | dopo circa 2 minuti la presa è «non in linea» (soglia 120 s più il controllo del silenzio) |
| **Comando a vuoto** | il comando fallisce subito, con il motivo «dispositivo offline» (testo da verificare a schermo); in (A) **nessuna** richiesta; in (M) «command result» con `reason` `device_offline`. Così si prova il percorso d'errore di connector e motore |
| **Ritorno** | riattaccata, la presa torna in linea in meno di un minuto, con il suo stato |
| **Diagnosi** | Non va mai fuori linea: connector, (M). Il comando a vuoto parte lo stesso verso la presa (richiesta in (A)): connector (Y). Non torna in linea: verifica 1 della tappa A. Se non è nel broker, il guasto è dalla parte di Y; se è nel broker, connector o motore: (M) |

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

**Mai durante la sezione 4 della tappa A** (fra R1 e R4): la `sync` qui sotto darebbe al broker la password nuova della Plug prima che la presa la conosca, e la lascerebbe fuori.

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

Il catalogo di Y arriva come pull request, in `engine/connector/shelly/cataloghi/lab-01.yaml` (messaggio a Y). Si usa dopo l'unione, dal repository. Se Y sceglie un altro percorso, o1 riscrive i comandi.

**6.5.1 Controllarlo sul PC** (sola lettura).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
.venv/Scripts/python.exe -c "from pathlib import Path; from engine.connector.shelly.catalog import load_catalog; from engine.connector.shelly.offline import load_thresholds; c = load_catalog(Path('engine/connector/shelly/cataloghi/lab-01.yaml'), load_thresholds()); print('catalogo valido:', [(d.device_id, d.shelly_id or d.blu.addr, d.device_type) for d in c.devices])"
```

- **Atteso:** `catalogo valido: […]`, con dentro `('dev-presa-lab', 'shellyplugmg3-9070695cb0d0', 'plug')`. Se la Plug ha un altro `device_id`, fermati: l'app perderebbe lo storico.

**6.5.2 Copia di sicurezza sulla VM, copia del file nuovo, riavvio del motore** (scrive sulla VM). La copia `catalog-solo-plug.yaml` sul PC è stata fatta al passo 3.0.1.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute scp engine/connector/shelly/cataloghi/lab-01.yaml langbrain-dev:catalog-lab-01.yaml --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo cp -p /data/lab-01/catalog.yaml /data/lab-01/catalog.yaml.prima && sudo install -m 640 -o 10001 -g 10001 ~/catalog-lab-01.yaml /data/lab-01/catalog.yaml && sudo ls -ln /data/lab-01 && sudo bash /opt/domhouse/engine-vm.sh key lab-01'
```

- `key` riscrive il file della chiave e ricrea il container: così il motore rilegge il catalogo.
- **Atteso:** `catalog.yaml` e `catalog.yaml.prima` nella cartella, poi `health 200: ok … connector up`. Dopo, il passo 3.2 con tutti i dispositivi.

**6.5.3 Tornare al catalogo di prima** (scrive sulla VM), se il motore non riparte (codice 3) o qualcosa non va:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo cp -p /data/lab-01/catalog.yaml.prima /data/lab-01/catalog.yaml && sudo bash /opt/domhouse/engine-vm.sh key lab-01'
```

- **Atteso:** `health 200: ok … connector up` con la sola Plug. Se anche la copia sulla VM mancasse, quella del PC è `~/domhouse-lab-01/catalog-solo-plug.yaml`: passi 3.0.2–3.0.3 con quel file.

## 7. Tornare indietro

| Che cosa | Come | Effetto |
|---|---|---|
| L'appartamento nell'app | nell'app di staging, come gestore: elimina l'appartamento `lab-01` | lo staging non lo chiama più; il motore resta |
| Il motore | comando 7.1 | il motore si ferma; il controllo ogni 5 minuti e il backup non lo contano più; i dati restano in `/data/lab-01` |
| La chiave | resta (non costa nulla); per toglierla: 7.2, facoltativo | — |
| L'utente del broker della Plug | 7.3 | la Plug non entra più nel broker |

Per gli apparecchi di Y aggiunti al 6.2: lo stesso comando del 7.3 con il loro id nativo.

### 7.1 Fermare e togliere il motore `lab-01` (scrive sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='cd /opt/domhouse && sudo ENGINE_BIND_IP=10.198.0.2 docker compose --env-file /opt/domhouse/lab-01.settings -f compose.yaml -f compose.broker.yaml down && sudo mv /opt/domhouse/lab-01.settings /opt/domhouse/lab-01.settings.tolto && sudo rm -f /etc/domhouse/lab-01.env && sudo docker ps --format "{{.Names}}"'
```

- **Atteso:** «Container engine-lab-01 Removed»; nell'elenco finale restano `engine-dev` e `domhouse-broker`.
- Spostare `lab-01.settings` fa sì che il controllo ogni 5 minuti non lo cerchi più: altrimenti scatterebbe l'allarme «motore muto». Il file `.env` conteneva la chiave e la password del connector: si toglie, e un `install` lo riscrive.
- **Per rimetterlo:** il passo 3.1. I dati in `/data/lab-01` sono ancora lì.
- Fra il `down` e lo spostamento del file passano pochi secondi. Se il controllo ogni 5 minuti cade proprio lì, scrive «engine silent lab-01» e può arrivare un'email: è innocua. Per evitarla, lancia il comando subito dopo un giro del controllo (al minuto :x1, cioè :01, :06, :11…).

### 7.2 Togliere la chiave (facoltativo; scrive su Secret Manager)

Solo **dopo** aver eliminato l'appartamento nell'app e fermato il motore (7.1).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud secrets delete langbrain-api-key-lab-01 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud secrets versions list langbrain-api-key-lab-01 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- gcloud chiede conferma: rispondi `y`.
- **Atteso:** l'eliminazione, poi `NOT_FOUND` alla seconda riga.

### 7.3 Togliere l'utente del broker della Plug (scrive su Secret Manager, poi sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 bash scripts/broker-secrets.sh remove-device lab-01 shellyplugmg3-9070695cb0d0
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/broker-vm.sh sync'
```

- **Atteso:** «nuova versione di langbrain-shelly-lab-01-devices scritta», poi «lab-01: connector e 0 dispositivi», «changed», «utenti e permessi ricaricati».
- La Plug resta collegata finché non si ricollega: al primo ricollegamento il broker la rifiuta.

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
9. **Sezione 4 della tappa A (cambio della password) con il motore `lab-01` acceso: si può, con queste cautele.**
   - Il connector usa lo stesso topic di risposta dei comandi R2 e R4: per questo R2 e R4 tengono solo la risposta con il loro numero (901, 902).
   - Il connector scarta le nostre risposte e scrive due volte «mqtt rpc answer dropped»: è atteso, non è un guasto.
   - Fra R2 e la fine di R4 **nessuno preme comandi sulla presa nell'app**: in R4 la presa si riavvia, e un comando in quei secondi fallirebbe.
   - In R4 la presa risulta «non in linea» per qualche secondo, poi torna in linea: è il riavvio. Il connector rilegge lo stato da solo.
   - Se la presa restasse fuori (R4 non riuscito) per più di 15 minuti, chi usa lo staging riceve l'avviso «dispositivo offline» (regola «Avviso dispositivo offline»): innocuo.
   - Il connector non risente della `sync` di R3: la sua password non cambia, e la ricarica del broker non fa cadere nessuno.
   - Il motore da solo non manda comandi alla presa: nessuna regola la comanda, salvo la richiesta di approvazione del rischio 10.
   - **Mai l'ascolto (A) durante R2**: mostrerebbe la password nuova.
10. **Regola dei consumi a casa vuota.** `lab-01` non ha prenotazioni, quindi per il motore è «casa vuota».
    - Con un carico oltre 300 W per 15 minuti (valori predefiniti), il motore chiede nell'app «Spegnere Presa del laboratorio».
    - Se nessuno risponde, la richiesta scade ed è respinta: la presa resta accesa. Se qualcuno la approva, la presa si spegne.
    - Quindi: Y non attacca carichi oltre 300 W, oppure nessuno approva quella richiesta.
11. **Assistente spento.** Senza `MODEL_BASE_URL` l'assistente di `lab-01` risponde «non disponibile» (codice 501). Non è un guasto: non fa parte della tappa B.
