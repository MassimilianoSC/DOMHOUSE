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
Cosa fa: esporta il commit indicato in una cartella temporanea, costruisce `engine/Dockerfile` da lì con Cloud Build e
pubblica `engine:<commit>` nel repository `domotica`. La copia di lavoro non conta: si costruisce sempre il commit del
lotto, anche se nel frattempo il lavoro è andato avanti. Senza commit costruisce HEAD. Con `DRY_RUN=1` davanti dice cosa
costruirebbe, senza Cloud Build.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 scripts/deploy-engine.sh <commit del lotto>
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

Risultato atteso: fra le etichette c'è il commit del lotto (senza argomento, quella stampata da `git rev-parse --short HEAD`).

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

## D2. Impostazioni di un appartamento (D-131, D-133)

Le impostazioni del motore di un appartamento stanno in `/etc/domhouse/<apartment_id>.settings.env`, un file senza segreti,
separato da quello della chiave: gli aggiornamenti (`update`, `key`) non lo toccano. **Non si modifica a mano.** Un valore fuori
intervallo ferma il motore all'avvio con il messaggio nel log; per questo lo script rimette le impostazioni di prima se il
motore non torna su.

**Impostare o togliere un valore** (scrive sulla VM; il motore si ferma per qualche secondo).
Cosa fa: scrive o toglie la riga nel file delle impostazioni, ricrea il container e aspetta `health 200`. Se il motore non
torna su (per esempio per un valore fuori intervallo), rimette le impostazioni di prima, ricrea di nuovo il container e
scrive «impostazione NOME non applicata».

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command="sudo bash /opt/domhouse/engine-vm.sh set dev CONFIRM_ON_WATTS=30"
```

Per tornare al valore predefinito: lo stesso comando con `unset dev CONFIRM_ON_WATTS`.

Verifica (sola lettura):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command="sudo bash /opt/domhouse/engine-vm.sh status dev"
```

Risultato atteso: le impostazioni in vigore, oppure «tutte ai valori predefiniti», e in fondo `health 200: ok …`.

**Impostazioni disponibili** (le soglie che l'app può cambiare da sola stanno invece nella pagina Regole dell'appartamento):
- `CONFIRM_ON_WATTS` (predefinito 20, da 1 a 5000): l'accensione di uno split a infrarosso è confermata se i watt del suo
  misuratore salgono almeno di questo valore rispetto a prima del comando, entro 10 secondi;
- `CONFIRM_OFF_WATTS` (predefinito 15, da 1 a 5000): lo spegnimento è confermato se i watt scendono sotto questo valore,
  entro 10 secondi.
- `THERMOSTAT_HYSTERESIS_C` (predefinito 0.5, da 0.1 a 3): la caldaia, regolata dal termostato o dall'antigelo, si accende
  sotto la temperatura voluta e si spegne sopra la temperatura voluta più questo valore, in gradi;
- `THERMOSTAT_MIN_SWITCH_MINUTES` (predefinito 5, da 1 a 60): minuti minimi fra due accensioni o spegnimenti della caldaia
  decisi dal termostato;
- `COMPRESSOR_MIN_OFF_MINUTES` (predefinito 3, da 1 a 15): pausa minima del compressore dello split dopo uno spegnimento.
  L'app la mostra nelle regole ma non la fa cambiare;
- `COMPRESSOR_WAIT_SECONDS` (predefinito 7, da 0 a 60): un'accensione manuale chiesta a meno di questi secondi dalla fine
  della pausa aspetta la fine invece di essere rifiutata; 0 = rifiutata sempre;
- `MISSED_AFTER_MINUTES` (predefinito 30, da 5 a 720): al riavvio del motore, un'azione programmata scaduta da più di
  questi minuti non si esegue più e risulta «mancata»;
- `APPROVAL_EXPIRES_MINUTES` (predefinito 30, da 5 a 720): un'approvazione senza risposta scade dopo questi minuti:
  respinta (D-119), tranne «Mettere l'appartamento a vuoto dopo il check-out», che viene approvata, e «Spegnere …» a
  casa vuota, che segue `EMPTY_POWER_EXPIRED_ACTION` (D-137);
- `CHECKOUT_PRESENCE_MINUTES` (predefinito 30, da 5 a 180): al passaggio a «vuoto» dopo il check-out, se il sensore di
  movimento ha visto qualcuno dopo l'orario di partenza ed entro questi minuti, il motore chiede prima di procedere
  («Mettere l'appartamento a vuoto dopo il check-out»). Dal passo 12 (D-151) è solo il valore iniziale: poi il parametro
  «minuti di presenza» della regola «Risparmio al check-out» si cambia dall'app, nella pagina Regole;
- `EMPTY_POWER_WATTS` (predefinito 300, da 20 a 5000): con l'appartamento vuoto, un misuratore sopra questi watt…
- `EMPTY_POWER_MINUTES` (predefinito 15, da 5 a 240): …per almeno questi minuti fa chiedere se spegnere l'apparecchio
  («Spegnere …»; mai la caldaia, mai durante una forzatura; una richiesta per dispositivo finché il consumo non scende
  e risale);
- `EMPTY_POWER_EXPIRED_ACTION` (predefinito `reject`, valori `reject` oppure `approve`): cosa succede alla richiesta
  «Spegnere …» se nessuno risponde entro la scadenza: `reject` = respinta, l'apparecchio resta acceso; `approve` =
  approvata, l'apparecchio si spegne (D-137: il committente ha scelto `reject` come predefinito perché spegnere un
  apparecchio a casa senza prenotazione può colpire la lavatrice di chi pulisce o uno scaldabagno);
- `MODEL_BASE_URL` (facoltativa, nessun predefinito): l'indirizzo del server pubblicato (`https://…`). Con questa
  l'assistente dell'appartamento risponde con il modello vero, attraverso il server, dentro il tetto mensile del
  progetto (passo 9, D-143). Senza: assistente a parole chiave se il connector è simulato, altrimenti assistente spento;
- `ASK_DAILY_LIMIT` (predefinito 50, da 1 a 1000): domande all'assistente al giorno per appartamento; oltre, «Limite di
  50 domande al giorno raggiunto per questo appartamento: riprova domani»;
- `DEMO_VARIANT` (`auto`, `vuoto`, `occupato`; predefinito `auto`; solo con `CONNECTOR=simulated`): variante del
  dimostrativo al primo avvio dell'appartamento (`vuoto` = nessun ospite, casa fredda; `occupato` = soggiorno in corso;
  `auto` = la regola di prima, «bologna» nell'identificativo); conta solo al primo avvio, poi i dati restano (P-72);
- `ASSISTANT_CONFIRM` (`ospiti`, `sempre`, `multiple`; predefinito `ospiti`): quando l'assistente chiede conferma prima
  di agire: `ospiti` = con ospiti presenti per spegnere clima o caldaia o cambiare modalità, e per due o più azioni
  insieme (D-154, D-162); `sempre` = per ogni azione, programmazioni escluse; `multiple` = solo per due o più azioni
  insieme, anche con ospiti. Non esiste «mai».
- `STREAM_QUEUE_MAX` (predefinito 1000, da 10 a 100000; lotto 35): eventi in attesa per ogni lettore dello stream del
  motore; oltre, quello stream si chiude e il server si ricollega dal suo ultimo evento, senza perdere nulla.
- `TIMEZONE` (predefinito `Europe/Rome`; D-177, lotto 31): fuso orario dell'appartamento; il BFF lo legge dal motore
  (`/apartment.timezone`) e in anagrafica si vede ma non si modifica. Si cambia con
  `sudo bash /opt/domhouse/engine-vm.sh set <apartment_id> TIMEZONE=Europe/London` (riavvio del motore). Un nome che
  non è un fuso orario ferma il motore all'avvio e `engine-vm.sh` rimette il valore di prima. Al primo accesso dopo il
  cambio il registro dell'organizzazione mostra «Fuso orario dell'appartamento «…» cambiato sul motore: … → …».

Le impostazioni del server (nei manifesti, non sulla VM): `AI_MONTHLY_CAP_EUR` 20, `AI_ALERT_PERCENT` 80, i prezzi per
milione di token 0.83, 4.13 e 0.08 € (da aggiornare il 1° gennaio 2027), `AI_DEMOS` per i dimostrativi; tutto in
`bff/API.md`, sezione «Passaggio verso il modello». Il server deve avere il ruolo `roles/aiplatform.user` (comando
del committente, registro P-60 passo 9).

I decimali si scrivono con il punto (per esempio `0.5`): la virgola non è accettata.

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

Risultato atteso: al massimo 7 file `engine-<data>.db` (gli eventuali `before-restore-…` seguono la stessa regola dei 7 giorni, P-71), il timer con la
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

## E2. Controllo ogni 5 minuti, log dei motori e allarmi (passo 10, D-148)

Sulla VM un «controllore» (timer `domhouse-engine-check`, ogni 5 minuti, `engine-vm.sh check-all`) chiede la salute a ogni motore installato e guarda l'età dell'ultimo backup; scrive nel syslog della VM righe riconoscibili (`engine ok|down|silent <id>`, `backup missing <id> age_h=…` oltre le 26 ore, riepilogo `domhouse-check: N motori, M muti`); il backup notturno scrive `backup ok <id>`. L'Ops Agent manda il syslog a Cloud Logging; con `logs-agent` manda anche i log dei container dei motori. Gli allarmi (`scripts/monitoring/engine-alerts.sh`, canale email «Avvisi BFF») leggono quelle righe: VM muta da 10 minuti (una sola email), motore muto o giù (al massimo ogni 30 minuti per appartamento), righe di errore (ogni 30 minuti), backup mancato (ogni 12 ore), disco oltre l'80 % per 10 minuti. Dettagli in `scripts/monitoring/README.md`, sezione «Motori sulla VM». Tre comandi, in quest'ordine, dopo aver copiato il nuovo `engine-vm.sh` sulla VM (C1) e aggiornato il motore (D).

**E2.1 Timer del backup e del controllo** (scrive sulla VM).
Cosa fa: installa (o reinstalla) il timer del backup e il controllo ogni 5 minuti.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="sudo bash /opt/domhouse/engine-vm.sh timers"
```

Verifica: il prossimo giro entro 5 minuti; dopo 5 minuti le righe «engine ok dev» e «domhouse-check: 1 motori, 0 muti».

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="systemctl list-timers domhouse-engine-check.timer --no-pager; sudo journalctl -t domhouse-check -n 5 --no-pager"
```

**E2.2 Log dei motori a Cloud Logging** (scrive sulla VM: configurazione dell'Ops Agent, i container non si toccano).
Cosa fa: l'Ops Agent manda anche i log dei motori a Cloud Logging; la configurazione di prima resta come copia.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="sudo bash /opt/domhouse/engine-vm.sh logs-agent"
```

Verifica: il comando stampa «active»; dopo 5 minuti, dal PC (sola lettura), deve comparire «engine alive»:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud logging read 'log_id("domhouse_engine")' --project=domotica-poc-511707 --limit=3 --format="value(jsonPayload.msg)" --account=m.scardovellicrac@gmail.com
```

**E2.3 Allarmi** (scrive su Cloud Monitoring; DOPO E2.1, altrimenti «VM muta» scatterebbe subito).
Cosa fa: crea la metrica del controllo e le cinque politiche sul canale «Avvisi BFF»; prima la prova a secco.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com DRY_RUN=1 GCP_PROJECT_ID=domotica-poc-511707 scripts/monitoring/engine-alerts.sh
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 scripts/monitoring/engine-alerts.sh
```

Verifica (sola lettura): le cinque politiche «Motori: …» con `True`.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud alpha monitoring policies list --project=domotica-poc-511707 --format="value(displayName,enabled)" --account=m.scardovellicrac@gmail.com
```

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

## G. Collegare l'app al motore della VM (P-66, D-120)

Da qui il server dell'app (BFF su Cloud Run) passa a `TARGET=prod`: `INSTANCE_MODE=real` e Direct VPC Egress sulla rete
`default`, così raggiunge `10.198.0.2:8100`. Gli appartamenti dimostrativi (`mock://builtin`) restano come sono, serviti
dal BFF stesso (D-97). Prerequisiti: C3 riuscito (il motore `dev` risponde dalla rete interna) e il commit da
pubblicare già su GitHub (`git push` fatto).

**G1. La chiave di `dev` è leggibile dal BFF** (sola lettura).
Il BFF manda al motore la chiave del segreto `langbrain-api-key-<apartment_id>`, sempre ricavato dall'identificativo
dell'appartamento (non si sceglie: correzione S3 di P-36). Per questo l'appartamento nell'app si chiama **`dev`**.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud secrets get-iam-policy langbrain-api-key-dev --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --flatten="bindings[].members" --filter="bindings.role=roles/secretmanager.secretAccessor" --format="value(bindings.members)"
```

Risultato atteso: fra le righe c'è `serviceAccount:domotica-bff@domotica-poc-511707.iam.gserviceaccount.com` (e quella di
`langbrain-vm@`). Se manca, il BFF non può parlare con il motore: va concesso prima di G2.

**G2. Pubblicare il BFF in produzione** (scrive su Google Cloud: Cloud Build, Cloud Run, Firebase Hosting).
Cosa fa: `scripts/publish.sh` pubblica il commit indicato da una copia pulita (non la cartella di lavoro), con
`bff/cloudrun.yaml`: `INSTANCE_MODE=real`, rete `default`/`default`, una sola istanza, notifiche push attive. Chiede di
scrivere `prod` per confermare. Se l'immagine di quel commit esiste già, non la ricostruisce.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com TARGET=prod GCP_PROJECT_ID=domotica-poc-511707 GCP_REGION=europe-west8 \
  VPC_NETWORK=default VPC_SUBNET=default SMTP_USER=m.scardovellicrac@gmail.com VITE_FCM_ENABLED=true \
  scripts/publish.sh <COMMIT>
```

Alla fine stampa le «righe da incollare alla memoria storica»: `Pubblicazione prod …`, `commit: …`, `immagine: …`,
`BFF: https://domotica-bff-444239063209.europe-west8.run.app`, `PWA: https://domotica-poc-511707.web.app`.

**G3. Verificare la pubblicazione** (sola lettura).
Cosa fa: chiede al BFF il suo stato e a Cloud Run la revisione attiva, il traffico, la rete e la modalità.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
curl -s https://domotica-bff-444239063209.europe-west8.run.app/health; echo
gcloud run services describe domotica-bff --region=europe-west8 --project=domotica-poc-511707 \
  --account=m.scardovellicrac@gmail.com \
  --format="value(status.latestReadyRevisionName,status.traffic[0].percent,spec.template.metadata.annotations.'run.googleapis.com/vpc-access-egress')"
gcloud run services describe domotica-bff --region=europe-west8 --project=domotica-poc-511707 \
  --account=m.scardovellicrac@gmail.com --format="yaml(spec.template.spec.containers[0].env)" | grep -A1 -E "INSTANCE_MODE|APP_ENV"
```

Risultato atteso: `{"status":"ok","app_env":"prod"}`; una riga con il nome della nuova revisione, `100` e
`private-ranges-only`; `APP_ENV` con `value: prod` e `INSTANCE_MODE` con `value: real`.

**G4. Creare nell'app l'appartamento di sviluppo collegato a `dev`** (nell'app, come gestore della piattaforma).
Nell'app: **Organizzazioni** → l'organizzazione di prova → **Appartamenti** → **Nuovo appartamento**, con:
- **ID**: `dev` (deve essere proprio questo: è il nome della chiave `langbrain-api-key-dev`);
- **Nome**: `Sviluppo (motore sulla VM)`;
- **URL istanza**: `http://10.198.0.2:8100/api/v1`; **Porta**: vuota (è già nell'URL);
- **Fuso orario**: `Europe/Rome`; **ID Italianway**: vuoto (nessuna prenotazione vera deve arrivarci);
- **Istanza simulata (appartamento dimostrativo)**: attiva. Il motore `dev` ha dispositivi simulati (D-118): così gli
  amministratori vedono il Simulatore e gli elenchi lo segnano «Dimostrativo».

Poi, sulla riga dell'appartamento, **Verifica connessione**.
Verifica: «Connessione OK»; l'ultima verifica risulta «riuscita». Nella pagina dell'appartamento compaiono i 5
dispositivi del motore `dev` (climatizzatore, caldaia, presa stufetta, finestra, sensore), tutti online.

**G5. Un comando arriva al motore sulla VM e torna confermato.**
Nell'app, appartamento «Sviluppo (motore sulla VM)» → **Presa stufetta camera** → **Accendi**.
Verifica nell'app: il comando passa da «in corso» ad acceso in circa 2 secondi (lo stato arriva dallo stream del
motore), e nelle **Decisioni** compare l'accensione con esito applicato. Verifica sul motore (sola lettura sulla VM):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command='sudo bash /opt/domhouse/engine-vm.sh api dev GET "/decisions?limit=3" | head -1; sudo bash /opt/domhouse/engine-vm.sh api dev GET /devices | head -1 | grep -o "\"dev-presa-camera\"[^}]*}"'
```

Risultato atteso: fra le ultime decisioni una con `"action":"turn_on"`, `"outcome":"applied"`,
`"device_id":"dev-presa-camera"` e `"actor":"user:…"` (lo pseudonimo di chi ha premuto, D-87); nella riga del
dispositivo `"switch":{"on":true}`. (Con `sudo docker logs engine-dev --tail 20` si vedono solo avvio ed errori: i
comandi riusciti non scrivono righe di log.)

**G6. Gli appartamenti dimostrativi sono invariati.**
Nell'app, un appartamento con il segno «Dimostrativo» e URL `mock://builtin`: si apre, mostra i suoi dispositivi, il
Simulatore funziona e un comando va a buon fine come prima. Sono serviti dal BFF (una sola istanza, in memoria):
dopo la pubblicazione ripartono dallo stato iniziale, come a ogni pubblicazione.

**G7. Tornare indietro a staging** (scrive su Google Cloud), se qualcosa non va.
Cosa fa: ripubblica lo stesso commit con `TARGET=staging` (`bff/cloudrun.staging.yaml`: `INSTANCE_MODE=mock`, niente
rete VPC). I dati in Firestore non cambiano; l'appartamento `dev` resta, ma in staging il BFF raggiunge solo
`mock://` e la sua verifica fallisce finché non si torna a prod.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com TARGET=staging GCP_PROJECT_ID=domotica-poc-511707 GCP_REGION=europe-west8 \
  SMTP_USER=m.scardovellicrac@gmail.com VITE_FCM_ENABLED=true scripts/publish.sh <COMMIT>
```

Verifica: G3, con `{"status":"ok","app_env":"staging"}` e `INSTANCE_MODE` `value: mock`.

---

## G2. Broker MQTT dei dispositivi (D-196, D-199, D-207, D-208, D-209)

Il broker è un solo container per tutta la VM (`domhouse-broker`). I dispositivi entrano dalla porta 8883 con TLS, ognuno con il suo utente; i connector dalla porta interna 1883, che non è pubblicata.

Cartelle:

| Dove | Cosa | Snapshot |
|---|---|---|
| `/mnt/domhouse-tls` (disco `langbrain-dev-tls`) | chiavi: `broker/` (certificato servito), `acme/` (conto Let's Encrypt e certificati di lego) | no |
| `/opt/domhouse/_broker` | compose, configurazione, impostazioni, regola del limite | sì (23:00) |
| `/etc/domhouse/_broker` | utenti (solo hash), elenco appartamenti, `acme.settings` | sì |
| `/data/_broker` | sessioni e messaggi in coda | sì |

Regole delle chiavi (C-12):

1. Le chiavi stanno solo sul disco `domhouse-tls`, dell'utente 1883, file 600 e cartelle 700.
2. Sulla VM non c'è nessuna credenziale di Google Cloud: lego usa l'identità della VM per agire come `domhouse-dns-lab@`.
3. Se il disco non è montato il broker non parte, nessun comando scrive chiavi, il controllo ogni 5 minuti scrive `broker down (disco delle chiavi non montato ...)` e scatta l'allarme «Motori: broker MQTT giù».

`lab-01` e `shelly-lab-1` sono nomi di esempio: si sostituiscono con l'appartamento e il dispositivo veri prima di lanciare i comandi.

### B0. Permesso per il certificato (scrive su Google Cloud)

Cosa fa: permette all'identità della VM di agire come l'account DNS, che può scrivere solo nella zona `domhouse-lab`. Serve a lego per la prova DNS di Let's Encrypt.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud iam service-accounts add-iam-policy-binding domhouse-dns-lab@domotica-poc-511707.iam.gserviceaccount.com \
  --member=serviceAccount:langbrain-vm@domotica-poc-511707.iam.gserviceaccount.com \
  --role=roles/iam.serviceAccountTokenCreator \
  --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

Verifica: nell'elenco stampato c'è `roles/iam.serviceAccountTokenCreator` con `serviceAccount:langbrain-vm@…`, e nessun altro membro.

### B1. Copiare i file sulla VM (scrive sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="mkdir -p ~/broker-files"
gcloud compute scp scripts/broker-vm.sh scripts/broker_accounts.py scripts/engine-vm.sh engine/broker/compose.yaml engine/broker/mosquitto.conf engine/compose.broker.yaml langbrain-dev:broker-files/ \
  --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

Verifica: 6 file copiati, tutti al 100 %.

### B2. Preparare il disco delle chiavi (scrive sulla VM; si può ripetere)

Cosa fa:

1. Installa `nftables` se manca.
2. Formatta il disco `domhouse-tls` solo se è vuoto.
3. Aggiunge una sola volta la riga in `/etc/fstab` (con UUID, `nofail`: se il disco manca la VM si avvia lo stesso).
4. Monta il disco su `/mnt/domhouse-tls` e rende immutabile la cartella vuota sotto, così senza disco lì non si scrive niente.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command='command -v nft > /dev/null || sudo apt-get install -y nftables; sudo bash ~/broker-files/broker-vm.sh prepare-tls-disk && grep domhouse-tls /etc/fstab && findmnt /mnt/domhouse-tls'
```

Verifica:

1. L'ultima riga dello script è `disco delle chiavi pronto: /dev/sdb UUID=… su /mnt/domhouse-tls, …` (il nome `/dev/sdX` può cambiare).
2. In `fstab` c'è una sola riga `UUID=… /mnt/domhouse-tls ext4 defaults,nofail,…`.
3. `findmnt` mostra il disco montato.

Rilanciato una seconda volta dice `già presente` e non formatta. Un disco con un file system diverso, o con dati senza file system, non viene mai formattato: lo script si ferma e lo dice.

### B3. Il certificato (scrive sulla VM e chiede il certificato a Let's Encrypt)

Prima di partire: il nome `mqtt.dh-lab.eu` deve risolvere da internet, e la catena DNSSEC del dominio deve essere a posto (D-206). Let's Encrypt non rilascia se la verifica DNS fallisce.

Cosa fa: lego, come utente 1883, apre il conto Let's Encrypt (senza email) e ottiene il certificato con la prova DNS. Poi lo mette nella cartella del broker.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command='sudo bash ~/broker-files/broker-vm.sh cert-new mqtt.dh-lab.eu domhouse-lab domhouse-dns-lab@domotica-poc-511707.iam.gserviceaccount.com'
```

Verifica: compaiono `broker cert new notAfter=…` e `certificato pronto in /mnt/domhouse-tls/broker: ora install`.

### B4. Installare il broker (scrive sulla VM)

Cosa fa:

1. Aggiorna il controllo ogni 5 minuti.
2. Installa il broker, il limite sui collegamenti nuovi alla 8883 e il timer del rinnovo quotidiano.
3. Avvia il broker.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command='sudo install -m 755 ~/broker-files/engine-vm.sh /opt/domhouse/engine-vm.sh && sudo bash ~/broker-files/broker-vm.sh install eclipse-mosquitto:2@sha256:75d6662dee52c947dc9dd9c29f1d8d7ffef78ddaf38001caa09755681e8bbc98'
```

Verifica:

1. Compare `limite attivo: alla porta 8883, oltre 60 collegamenti nuovi di fila e poi 30/minute per indirizzo, …`.
2. Compare `domhouse-broker-limit.service abilitato, timer domhouse-broker-cert.timer attivo`.
3. L'ultima riga è `broker sano: healthy, porta TLS 8883 risponde`.

### B5. Conti di un appartamento (scrive su Secret Manager, poi sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 bash scripts/broker-secrets.sh add-apartment lab-01
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 bash scripts/broker-secrets.sh add-device lab-01 shelly-lab-1
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command='sudo bash /opt/domhouse/broker-vm.sh add-apartment lab-01'
```

Verifica:

1. Compaiono `langbrain-shelly-lab-01 creato`, `langbrain-shelly-lab-01-devices creato` e `nuova versione … scritta`, senza password a video.
2. Poi `lab-01: connector e 1 dispositivi`, `changed` e `utenti e permessi ricaricati`.

Su ogni Shelly, nelle impostazioni MQTT:

| Campo | Valore |
|---|---|
| Server | `mqtt.dh-lab.eu:8883`, TLS con verifica del certificato |
| Utente | `lab-01.shelly-lab-1` |
| Client ID | lo stesso dell'utente, `lab-01.shelly-lab-1`: così la riga di un accesso rifiutato dice quale dispositivo è |
| Prefisso | `lab-01/shelly-lab-1` |

### B6. Allarmi del broker (scrive su Google Cloud)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com GCP_PROJECT_ID=domotica-poc-511707 bash scripts/monitoring/engine-alerts.sh
```

Verifica: «Motori: broker MQTT giù», «Motori: certificato del broker in scadenza» e «Motori: broker, troppi accessi rifiutati» risultano `creata` (o `esiste già` se c'erano); le altre `esiste già`.

### B7. Controllare il broker (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command='sudo bash /opt/domhouse/broker-vm.sh status'
```

Verifica:

1. `broker ok cert_days=<numero>`.
2. `accessi rifiutati sulla 8883 nell'ultima ora: <numero>`.
3. `collegamenti scartati dal limite: <numero>`.
4. Una riga del disco `/mnt/domhouse-tls`.

### B8. Verifica dall'esterno dopo l'apertura della 8883 (sola lettura, da Cloud Shell)

Si fa dopo i comandi della memoria storica per l'indirizzo pubblico, la regola `mqtt-tls-in` e il record DNS. Si lancia da Cloud Shell (console di Google Cloud, icona del terminale), che sta fuori dalla rete della VM.

```bash
# Cloud Shell
cd ~
IP=$(gcloud compute instances describe langbrain-dev --zone=europe-west8-a --project=domotica-poc-511707 --format='get(networkInterfaces[0].accessConfigs[0].natIP)'); echo "IP pubblico: $IP"
for p in 22 1883 8100 8101 8199 8883; do timeout 3 bash -c "</dev/tcp/$IP/$p" 2>/dev/null && echo "porta $p APERTA" || echo "porta $p chiusa"; done
sudo apt-get install -y -qq nmap > /dev/null && sudo nmap -Pn -p 1-1024,1883,8100-8199,8883 "$IP"
openssl s_client -connect "$IP:8883" -servername mqtt.dh-lab.eu -verify_return_error < /dev/null 2>/dev/null | openssl x509 -noout -subject -issuer -enddate
```

Esito atteso:

1. Solo `porta 8883 APERTA`; tutte le altre `chiusa`.
2. `nmap` mostra `8883/tcp open` e tutte le altre porte `filtered` (nessuna `open`, nessuna `closed`).
3. `openssl` stampa `subject=CN = mqtt.dh-lab.eu`, l'emittente Let's Encrypt e la scadenza.

Se compare un'altra porta aperta: togliere subito la regola `mqtt-tls-in` (comando della memoria storica) e avvisare.

### B9. Il NAT non serve più (sola lettura; prima di eliminarlo)

Con l'indirizzo pubblico la VM esce da quello, non dal NAT. Da controllare a indirizzo attivo, **prima** dell'eliminazione:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute routers get-nat-mapping-info langbrain-router --region=europe-west8 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute instances list --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format='table(name,networkInterfaces[0].accessConfigs[0].natIP)'
gcloud logging read 'resource.type="nat_gateway"' --freshness=30m --limit=5 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format='value(timestamp,jsonPayload.connection.src_ip,jsonPayload.connection.dest_ip)'
```

Verifica:

1. `get-nat-mapping-info` non elenca più `langbrain-dev`. Restano voci senza nome macchina (`instanceName: ''`, indirizzi `10.198.0.16`–`10.198.0.23`): sono le interfacce di rete di Cloud Run, che il NAT prenota per tutta la sottorete ma che non lo usano, perché i due servizi hanno `vpc-access-egress: private-ranges-only` (da ricontrollare con `gcloud run services describe`).
2. Tutte le macchine dell'elenco hanno un indirizzo pubblico (oggi c'è solo `langbrain-dev`).
3. Nei registri del NAT non c'è niente dopo l'attivazione dell'indirizzo.

Poi, sulla VM, le uscite che usa davvero (vanno ripetute identiche dopo l'eliminazione del NAT):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='
echo "server (assistente): $(curl -s -o /dev/null -w %{http_code} https://domotica-bff-mgxrktwk6a-oc.a.run.app/health)"
echo "Artifact Registry: $(curl -s -o /dev/null -w %{http_code} https://europe-west8-docker.pkg.dev/v2/)"
echo "Docker Hub: $(curl -s -o /dev/null -w %{http_code} https://registry-1.docker.io/v2/)"
echo "Let'"'"'s Encrypt: $(curl -s -o /dev/null -w %{http_code} https://acme-v02.api.letsencrypt.org/directory)"
sudo apt-get update -qq && echo "apt: ok"
sudo bash /opt/domhouse/broker-vm.sh sync | tail -1
sudo bash /opt/domhouse/engine-vm.sh check-all | tail -2
systemctl is-active google-cloud-ops-agent'
```

Esito atteso:

| Riga | Valore |
|---|---|
| server (assistente) | `200` |
| Artifact Registry | `401` (raggiunto, chiede le credenziali) |
| Docker Hub | `401` |
| Let's Encrypt | `200` |
| apt | `apt: ok` |
| `broker-vm.sh sync` (Secret Manager) | `unchanged` |
| `check-all` | il riepilogo `N motori, 0 muti` e `broker ok cert_days=…` |
| Ops Agent | `active` |

Infine, da PC, i registri arrivano ancora (Cloud Logging):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud logging read 'resource.type="gce_instance" AND log_id("syslog") AND jsonPayload.message:"domhouse-check"' --freshness=15m --limit=3 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format='value(timestamp,jsonPayload.message)'
```

Verifica: righe degli ultimi 5 minuti. Anche il grafico della memoria della VM (Ops Agent) continua senza buchi.

### B10. Prove del certificato durante il rodaggio (scrive sulla VM, chiede certificati a Let's Encrypt)

Il primo rinnovo automatico cadrebbe dopo la consegna (D-210): durante il rodaggio si provano, una volta ciascuno, il rinnovo forzato e la revoca con riemissione (D-207). Ognuno conta come un certificato nuovo nel limite di Let's Encrypt (5 alla settimana per lo stesso nome): non ripeterli.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command='sudo bash /opt/domhouse/broker-vm.sh cert-renew force && sudo systemctl start domhouse-broker-cert.service && sudo journalctl -u domhouse-broker-cert.service -n 5 --no-pager'
```

Verifica:

1. Compaiono `broker cert new notAfter=…` e `ricarica fatta: la porta 8883 serve il certificato …`, e i relè restano collegati.
   Se il tipo di chiave cambia (per esempio da ECDSA a RSA-2048, predefinito dal 10 novembre), la ricarica non basta: compaiono `la ricarica non basta (tipo di chiave cambiato?): riavvio del broker, i dispositivi si ricollegano`, poi `broker sano…` e `riavvio fatto: la porta 8883 serve il certificato …`.
2. Il giro del timer subito dopo dice `certificato invariato: rinnovo non ancora dovuto`.
3. Da Cloud Shell, chiave e catena servite:

```bash
# Cloud Shell
cd ~
openssl s_client -connect mqtt.dh-lab.eu:8883 -servername mqtt.dh-lab.eu -showcerts < /dev/null 2>/dev/null | grep -E '^ *[0-9]+ s:|^ *i:'
openssl s_client -connect mqtt.dh-lab.eu:8883 -servername mqtt.dh-lab.eu < /dev/null 2>/dev/null | openssl x509 -noout -text | grep -E 'Public Key Algorithm|Public-Key'
```

   Atteso (da verificare al primo rinnovo vero): `rsaEncryption`, `(2048 bit)`; catena foglia → YR1 o YR2 → Root YR con emittente ISRG Root X1 (la catena lunga, chiesta per nome con `--preferred-chain`).

Revoca e riemissione: si usa quando la chiave è uscita, o potrebbe essere uscita, dalla VM.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com \
  --command='sudo bash /opt/domhouse/broker-vm.sh cert-revoke key-compromise'
```

Verifica:

1. Compaiono `broker cert revoked (mqtt.dh-lab.eu, key-compromise)`, poi `broker cert new notAfter=…` e `ricarica fatta …`.
2. La chiave è nuova: lego ne crea una a ogni certificato.
3. Il certificato vecchio resta archiviato in `/mnt/domhouse-tls/acme/archives`, sullo stesso disco.

Per un cambio senza sospetti sulla chiave (per esempio un altro nome): `cert-revoke superseded`.

### Dopo un ripristino da snapshot

Il disco delle chiavi non ha snapshot: il certificato **non si ripristina, si rifà**.

1. Se il disco `langbrain-dev-tls` c'è ancora, il broker riparte da solo; basta B7.
2. Se il disco è perso:
   1. crearne uno nuovo come in D-208;
   2. lanciare B2: la riga di `fstab` col disco vecchio (ripristinata dallo snapshot) viene sostituita e lo script dice `sostituita (il disco … non c'è più)`; una riga diversa dalla nostra la lascia com'è e si ferma;
   3. poi B3 (`cert-new`) e `sudo bash /opt/domhouse/broker-vm.sh restart`.
3. Una chiave persa insieme al disco non è uscita dalla VM: non va revocata. La revoca serve solo se si sospetta che una chiave sia uscita (B10).

### Cosa si salva

1. **Utenti:** la fonte sono i segreti; `sync` riscrive gli hash in qualunque momento.
2. **Certificato e conto ACME:** non si salvano, si rifanno (B3).
3. **`/data/_broker`:** sessioni e messaggi conservati, già nello snapshot delle 23:00. Se si perde, i relè si ricollegano e il connector rilegge lo stato.

## H. Non ancora qui

- Allarmi dai log dei container (D-104): passo 10 del piano. Il backup applicativo c'è (sezione E), insieme allo
  snapshot giornaliero del disco della VM.
- Righe di log del motore per i comandi riusciti (oggi solo avvio, avvisi ed errori): con gli allarmi, passo 10.
