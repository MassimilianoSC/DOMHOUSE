# Il motore sulla VM: installazione e aggiornamento

*Passo 3c del piano B (P-60, D-115, D-116). I comandi che scrivono su Google Cloud li lancia il committente, dopo la
rilettura della memoria storica. Ogni comando ha una riga «cosa fa» e una «verifica»: il comando di sola lettura da
lanciare dopo, con il risultato atteso. Nessun comando legge il valore di un segreto.*

Prima istanza: **`dev`**, porta **8100**, dati in `/data/dev`, chiave dal segreto **`langbrain-api-key-dev`**
(esistente, già leggibile dalla VM). Il motore gira con il connector simulato (`CONNECTOR=simulated`).

**`dev` resta per sempre con `CONNECTOR=simulated`** (D-118): è l'ambiente di prova, anche quando ci sarà il connector
Shelly. Gli appartamenti veri sono istanze a parte, ciascuna con il suo `apartment_id`, la sua porta 81xx (8101, 8102,
…) e il suo segreto `langbrain-api-key-<apartment_id>`; non si «promuove» `dev` ad appartamento vero.

Valori fissi usati sotto: progetto `domotica-poc-511707`, regione `europe-west8`, zona `europe-west8-a`, VM
`langbrain-dev` (IP interno `10.198.0.2`), account di servizio della VM `langbrain-vm@domotica-poc-511707.iam.gserviceaccount.com`,
account Owner `m.scardovellicrac@gmail.com` (l'account attivo di gcloud su questo PC è un altro: ogni comando lo
indica con `--account` o `CLOUDSDK_CORE_ACCOUNT`).

Come funziona sulla VM (lo fa `scripts/engine-vm.sh`, che gira sulla VM come root con l'identità della VM):
- `/opt/domhouse/`: lo script, `compose.yaml` (modello unico) e un file `<apartment_id>.settings` per appartamento
  (APARTMENT_ID, PORT, CONNECTOR, ENGINE_IMAGE: niente segreti);
- `/etc/domhouse/<apartment_id>.env`: `API_KEY=…` dal segreto `langbrain-api-key-<apartment_id>`, permessi 600, di
  root. Lo script legge il segreto solo per scrivere questo file: non lo stampa, non lo scrive nei log;
- `/data/<apartment_id>/`: `engine.db` (SQLite in WAL), proprietario uid 10001, l'utente del container; in
  `backup/` le copie quotidiane `engine-<data UTC>.db` degli ultimi 7 giorni (sezione E);
- il timer systemd `domhouse-engine-backup.timer`: ogni giorno alle 22:30 UTC, prima dello snapshot del disco delle
  23:00, fa il backup di tutti gli appartamenti installati;
- il container `engine-<apartment_id>` (progetto Compose `domhouse-<apartment_id>`), `restart: unless-stopped`, porta
  81xx sull'IP interno, log JSON di Docker ruotati.

---

## A. Dal PC, una volta sola

**A1. Il segreto della chiave esiste.**
Cosa fa: elenca le versioni di `langbrain-api-key-dev`, senza leggerne il valore.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud secrets versions list langbrain-api-key-dev --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

Verifica: almeno una riga con `STATE` uguale a `enabled`.

**A2. La VM può leggere quel segreto.**
Cosa fa: mostra chi ha il ruolo Secret Accessor sul segreto (sola lettura).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud secrets get-iam-policy langbrain-api-key-dev --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --flatten="bindings[].members" --filter="bindings.role=roles/secretmanager.secretAccessor" --format="value(bindings.members)"
```

Verifica: c'è la riga `serviceAccount:langbrain-vm@domotica-poc-511707.iam.gserviceaccount.com`. Se manca, va
concesso prima di proseguire (comando a parte, da preparare con la memoria storica).

**A3. La VM può scaricare le immagini da Artifact Registry** (scrive su Google Cloud).
Cosa fa: dà a `langbrain-vm@` il ruolo Artifact Registry Reader sul solo repository `domotica`.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud artifacts repositories add-iam-policy-binding domotica --location=europe-west8 --project=domotica-poc-511707 \
  --member="serviceAccount:langbrain-vm@domotica-poc-511707.iam.gserviceaccount.com" --role="roles/artifactregistry.reader" \
  --account=m.scardovellicrac@gmail.com
```

Verifica (sola lettura):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud artifacts repositories get-iam-policy domotica --location=europe-west8 --project=domotica-poc-511707 \
  --account=m.scardovellicrac@gmail.com --flatten="bindings[].members" \
  --filter="bindings.role=roles/artifactregistry.reader" --format="value(bindings.members)"
```

Risultato atteso: la riga `serviceAccount:langbrain-vm@domotica-poc-511707.iam.gserviceaccount.com`.

---

## B. Dal PC, a ogni nuova versione del motore

**B1. Costruire l'immagine** (scrive su Google Cloud: Cloud Build e Artifact Registry).
Cosa fa: costruisce `engine/Dockerfile` con Cloud Build e pubblica `engine:<commit>` nel repository `domotica`. La
copia di lavoro di `engine/` deve essere senza modifiche: l'etichetta dell'immagine è il commit.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 scripts/deploy-engine.sh
```

L'ultima riga stampa l'immagine, per esempio
`Immagine pronta: europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:1a2b3c4`. Quel valore serve in C2 e
in D2: sotto è scritto `<IMMAGINE>`.

Verifica (sola lettura):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git rev-parse --short HEAD
gcloud artifacts docker tags list europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

Risultato atteso: fra le etichette c'è quella stampata da `git rev-parse --short HEAD`.

---

## C. Prima installazione di `dev` sulla VM (comandi dal PC, attraverso IAP)

**C1. Copiare script e modello sulla VM** (scrive sulla VM, nella cartella di chi si collega).
Cosa fa: copia `scripts/engine-vm.sh` ed `engine/compose.yaml` nella home sulla VM, attraverso IAP.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute scp scripts/engine-vm.sh engine/compose.yaml langbrain-dev: \
  --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

Verifica:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="ls -l ~/engine-vm.sh ~/compose.yaml"
```

Risultato atteso: i due file, con la data di oggi.

**C2. Installare e avviare il motore `dev`** (scrive sulla VM; legge il segreto con l'identità della VM).
Cosa fa: sulla VM, come root, prepara `/opt/domhouse`, `/data/dev` (uid 10001) e `/etc/domhouse/dev.env` (chiave dal
segreto, permessi 600), scarica `<IMMAGINE>` e avvia il container `engine-dev` sulla porta 8100; poi aspetta che
`/api/v1/health` risponda.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command="sudo bash ~/engine-vm.sh install dev 8100 <IMMAGINE> simulated"
```

Risultato atteso, in fondo all'output:
`health 200: ok {'name': 'domhouse-engine', 'version': '0.3.0'} connector up`. Se invece compare un errore, lo script
dice quale passo è fallito (segreto non leggibile, login ad Artifact Registry rifiutato, health che non risponde con
le ultime righe del log del motore).

**C3. Il motore risponde dalla rete interna** (regola 3 del CLAUDE.md).
Cosa fa: chiama `http://10.198.0.2:8100/api/v1/health`, cioè l'indirizzo interno della VM, quello che userà il BFF.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command="curl -s -w ' HTTP %{http_code}\n' http://10.198.0.2:8100/api/v1/health"
```

Risultato atteso: un JSON con `"status":"ok"`, `"name":"domhouse-engine"`, `"apartment_id":"dev"` e in fondo
`HTTP 200`. (La chiamata dal BFF su Cloud Run, attraverso Direct VPC Egress, fa parte del passaggio a `TARGET=prod`,
P-66.)

**C4. Riavvio automatico e dati sul disco.**
Cosa fa: mostra la politica di riavvio del container e i file del motore (sola lettura).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command="sudo docker inspect -f '{{.HostConfig.RestartPolicy.Name}} {{.Config.Image}}' engine-dev; sudo ls -ln /data/dev; sudo ls -l /etc/domhouse; systemctl list-timers domhouse-engine-backup.timer --no-pager"
```

Risultato atteso: `unless-stopped <IMMAGINE>`; in `/data/dev` il file `engine.db` (con `engine.db-wal` e
`engine.db-shm`) e la cartella `backup`, di proprietà `10001`; in `/etc/domhouse` il file `dev.env` con permessi
`-rw-------` di root; il timer `domhouse-engine-backup.timer` con la prossima esecuzione alle 22:30 UTC.

**C5. Prova del ripristino, una volta, su `dev`** (scrive sulla VM; D-118).
Cosa fa, in un solo comando: un backup; un cambiamento di stato (la modalità dell'appartamento passa a `eco`); il
ripristino dal backup appena fatto; la modalità letta prima, dopo il cambiamento e dopo il ripristino. Le chiamate al
motore passano da `engine-vm.sh api`, che prende la chiave dal file di root senza mostrarla.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command='V=/opt/domhouse/engine-vm.sh; sudo bash $V backup dev && sudo bash $V api dev GET /apartment | head -1 | grep -o "\"mode\":\"[a-z]*\"" && sudo bash $V api dev POST /apartment/mode "{\"mode\":\"eco\"}" | tail -1 && sleep 3 && sudo bash $V api dev GET /apartment | head -1 | grep -o "\"mode\":\"[a-z]*\"" && sudo bash $V restore dev engine-$(date -u +%Y-%m-%d).db && sudo bash $V api dev GET /apartment | head -1 | grep -o "\"mode\":\"[a-z]*\""'
```

Risultato atteso, nell'ordine: `backup dev: /data/dev/backup/engine-<oggi>.db (… byte, integrity_check ok)`;
`"mode":"comfort"`; `HTTP 202`; `"mode":"eco"`; le righe del ripristino con `il database di prima resta in
/data/dev/backup/before-restore-….db` e `health 200: ok …`; di nuovo `"mode":"comfort"`. Cioè: dopo il ripristino lo
stato è quello del backup, non quello del cambiamento. (Se la modalità di partenza non è `comfort`, conta che la prima
e l'ultima riga siano uguali.)

---

## D. Aggiornare `dev` a una nuova versione

**D1.** Costruire la nuova immagine come in B1 e annotare `<IMMAGINE>`.

**D2. Passare alla nuova immagine** (scrive sulla VM). I dati in `/data/dev` restano.
Cosa fa: aggiorna `ENGINE_IMAGE` in `/opt/domhouse/dev.settings`, scarica l'immagine, ricrea il container e aspetta
`health`. Stampa anche l'immagine precedente, per tornare indietro.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command="sudo bash /opt/domhouse/engine-vm.sh update dev <IMMAGINE>"
```

Verifica: la riga `immagine: <precedente> -> <IMMAGINE>` e in fondo `health 200: ok …`.
Tornare indietro: lo stesso comando con l'immagine precedente.

Se sono cambiati anche `scripts/engine-vm.sh` o `engine/compose.yaml`: prima C1 (copia), poi C2 con la nuova immagine.
`install` è ripetibile: riscrive impostazioni e chiave, non tocca i dati.

**D3. Dopo un cambio della chiave in Secret Manager** (nuova versione di `langbrain-api-key-dev`).
Cosa fa: riscrive `/etc/domhouse/dev.env` dal segreto e ricrea il container.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command="sudo bash /opt/domhouse/engine-vm.sh key dev"
```

Verifica: in fondo `health 200: ok …`.

---

## E. Backup e ripristino

Ogni giorno alle 22:30 UTC il timer `domhouse-engine-backup.timer` lancia `engine-vm.sh backup-all`: per ogni
appartamento installato, una copia coerente di `engine.db` fatta con la funzione di backup di SQLite (anche mentre il
motore scrive), controllata con `PRAGMA integrity_check`, in `/data/<apartment_id>/backup/engine-<data UTC>.db`; le
copie più vecchie di 7 giorni si cancellano. Lo snapshot del disco delle 23:00 contiene quindi anche le copie. Il
ripristino rimette una copia al posto di `engine.db` a motore fermo e conserva il database di prima.

**E1. Un backup adesso** (scrive sulla VM).
Cosa fa: la copia di oggi di `dev` (la riscrive, se c'è già).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command="sudo bash /opt/domhouse/engine-vm.sh backup dev"
```

Verifica: `backup dev: /data/dev/backup/engine-<oggi>.db (… byte, integrity_check ok)`.

**E2. Le copie e il timer** (sola lettura).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command="sudo ls -ln /data/dev/backup; systemctl list-timers domhouse-engine-backup.timer --no-pager; sudo journalctl -u domhouse-engine-backup.service -n 5 --no-pager"
```

Risultato atteso: al massimo 7 file `engine-<data>.db` (più gli eventuali `before-restore-…`), il timer con la
prossima esecuzione alle 22:30 UTC e, dopo la prima notte, le righe `backup dev: …` dell'ultima esecuzione.

**E3. Ripristinare una copia** (scrive sulla VM: il motore si ferma per qualche secondo).
Cosa fa: controlla che la copia sia integra, ferma `engine-dev`, sposta il database attuale in
`/data/dev/backup/before-restore-<ora>.db`, mette la copia al posto di `engine.db`, riavvia e aspetta `health`.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command="sudo bash /opt/domhouse/engine-vm.sh restore dev engine-<AAAA-MM-GG>.db"
```

Verifica: `il database di prima resta in …` e in fondo `health 200: ok …`. Per annullare il ripristino: lo stesso
comando con il file `before-restore-….db` indicato.

---

## F. Sulla VM (riferimento, se si è collegati con `gcloud compute ssh`)

| Comando | Cosa mostra |
|---|---|
| `sudo bash /opt/domhouse/engine-vm.sh status dev` | impostazioni, container e `health` |
| `sudo docker logs engine-dev --tail 50` | le ultime righe JSON del motore (`engine started`, `restored`, comandi) |
| `sudo docker ps --filter name=engine-` | i motori in esecuzione |
| `curl -s http://10.198.0.2:8100/api/v1/health` | lo stato del motore dalla rete interna |
| `sudo bash /opt/domhouse/engine-vm.sh api dev GET /apartment` | una chiamata al motore con la sua chiave (mai mostrata) |
| `sudo bash /opt/domhouse/engine-vm.sh backup dev` | un backup subito (sezione E) |

Un nuovo appartamento sulla stessa VM: C2 con il suo `apartment_id` e la sua porta 81xx (8101, 8102, …), dopo aver
creato il segreto `langbrain-api-key-<apartment_id>` e dato a `langbrain-vm@` Secret Accessor su di esso.

## G. Non ancora qui

- Allarmi dai log dei container (D-104): passo 10 del piano. Il backup applicativo c'è (sezione E), insieme allo
  snapshot giornaliero del disco della VM.
- Il collegamento dell'app al motore della VM (`instance_url` `http://10.198.0.2:8100`, `instance_secret_name`
  `langbrain-api-key-dev`) e `TARGET=prod`: lotto a parte, P-66.
