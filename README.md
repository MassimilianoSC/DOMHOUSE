# DOMHOUSE — app gestore (PWA + BFF)

App per il gestore di appartamenti in affitto breve: riscaldamento e clima, consumi, decisioni del motore,
approvazioni. Frontend React 18 + Vite (PWA), BFF FastAPI stateless che autentica, instrada verso l'istanza
domotica dell'appartamento, rilancia lo stream SSE e inoltra le prenotazioni.

- **Contratto**: `contract/openapi.yaml` (v1.0.4) è condiviso con il team del motore e confrontato in CI: **non va mai modificato**.
  I tipi TypeScript si rigenerano con `make gen-api`.
- **Motore**: `engine/` è il motore domotico, uno per appartamento (`python -m engine`, vedi «Motore e connector sul
  proprio PC»). Lo stesso codice, con il connector simulato, fa gli appartamenti dimostrativi del BFF, montati su
  `/mock/{apartment_id}/api/v1` (`bff/mock_instance`).

## Struttura

```
bff/            FastAPI: auth, proxy istanze, SSE hub, admin, webhook, push, repository (memory | firestore)
bff/bookings/   BookingTranslator (ItalianwayTranslator = STUB, SimulatorTranslator), inoltro idempotente a POST /bookings
bff/mock_instance/  gli appartamenti dimostrativi del BFF, fatti con il codice del motore
engine/         il motore: API del contratto (api.py), logica (core.py), configurazione, log, Dockerfile e compose
engine/connector/   l'interfaccia verso i dispositivi (connector.md), il connector simulato e le prove comuni
frontend/       PWA (React, Tailwind, shadcn/ui, i18n it)
scripts/        set_claims.py, deploy.sh
tests/          pytest: BFF end-to-end, suite condivisa dei repository
```

## Sviluppo locale

```bash
cp bff/.env.example bff/.env          # APP_ENV=dev AUTH_MODE=dev INSTANCE_MODE=mock REPOSITORY=memory
make dev                              # BFF :8000 (+ mock) e PWA :5173
```

Login dev: pulsanti sulla pagina di accesso (`m.cracchiolo@hqe.it` admin, `operatore@demo.it`, `lettura@demo.it`).
Simulatore: `/a/{apartment_id}/simulatore` (solo admin, solo sugli appartamenti con «istanza simulata», in qualunque ambiente: D-97). `MOCK_TIME_SCALE` = secondi reali per
minuto simulato (default 1; 60 = tempo reale).

Test: `python scripts/run_tests.py` (oppure `make test`) è il giro completo; richiede l'emulatore Firestore (JDK 11+ e
`npx firebase-tools setup:emulators:firestore`): senza, il giro è rosso (P-42). Su Windows il JDK si installa da
PowerShell con `winget install EclipseAdoptium.Temurin.21.JDK`. Prove singole:

```bash
pytest tests/repository_suite_test.py                # memory sempre; firestore se FIRESTORE_EMULATOR_HOST è impostato
gcloud emulators firestore start --host-port=localhost:8900 &
FIRESTORE_EMULATOR_HOST=localhost:8900 pytest tests/repository_suite_test.py
pytest tests/backend_test.py tests/backend_phase2_test.py tests/backend_phase3_test.py   # contro un BFF in esecuzione
```

## Motore e connector sul proprio PC

Il motore è un programma Python, uno per appartamento: espone all'app l'API del contratto su `/api/v1` e parla con i
dispositivi attraverso un connector (interfaccia e regole in `engine/connector/connector.md`). Qui sotto come avviarlo
sul proprio PC, prima con il connector simulato, poi con il proprio. Serve Python 3.11 o più recente (in esercizio gira
su `python:3.11-slim`); Docker è facoltativo.

**1. Preparazione** (una volta), dalla radice del repository.

```bash
# Git Bash, Linux o macOS
cd <cartella del repository>
python -m venv .venv
source .venv/bin/activate              # su Windows con Git Bash: source .venv/Scripts/activate
pip install -r engine/requirements.txt -r contract/conformance/requirements.txt pytest
```

```powershell
# PowerShell (Windows)
cd <cartella del repository>
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r engine/requirements.txt -r contract/conformance/requirements.txt pytest
```

**2. Le prove del motore e del connector**: le prove comuni a ogni connector (`engine/connector/tests/`) e quelle del
motore (`engine/tests/`). Devono essere tutte verdi prima di ogni pull request.

```bash
# Git Bash, Linux, macOS o PowerShell
cd <cartella del repository>
python -m pytest engine -q
```

**3. Avviare il motore con il connector simulato.** La configurazione arriva solo da variabili d'ambiente:

| Variabile | | Cosa |
|---|---|---|
| `APARTMENT_ID` | obbligatoria | l'appartamento servito, es. `apt-prova-01` |
| `API_KEY` | obbligatoria | la chiave che l'app manda in `X-API-Key`, almeno 16 caratteri; sul PC una qualsiasi, generata come sotto |
| `CONNECTOR` | obbligatoria | `simulated`, oppure il nome di un pacchetto in `engine/connector/` (es. `shelly`) |
| `HOST`, `PORT` | facoltative | dove ascolta; predefiniti `127.0.0.1` e `8100` |
| `DATA_DIR` | facoltativa | i dati dell'appartamento, predefinita `/data/<APARTMENT_ID>`; sul PC conviene una cartella locale |
| `CATALOG_PATH` | facoltativa | il catalogo dei dispositivi, predefinito `<DATA_DIR>/catalog.yaml` |
| `MOCK_TIME_SCALE` | solo simulato | secondi reali per ogni minuto delle regole: `60` (predefinito) è il tempo reale, `1` accelera |
| `<NOME>_*` | del connector | le variabili del connector `<nome>`, es. `SHELLY_OFFLINE_AFTER_S` (vedi il punto 5) |

Prima si genera una chiave per il proprio PC, una volta, e si copia il valore stampato: serve in tutti i terminali.

```bash
# Git Bash, Linux, macOS o PowerShell
cd <cartella del repository>
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

```bash
# Git Bash, Linux o macOS
cd <cartella del repository>
export APARTMENT_ID=apt-prova-01 CONNECTOR=simulated DATA_DIR=./dati/apt-prova-01
export API_KEY=<la chiave generata>
python -m engine
```

```powershell
# PowerShell (Windows)
cd <cartella del repository>
$env:APARTMENT_ID = "apt-prova-01"; $env:CONNECTOR = "simulated"; $env:DATA_DIR = ".\dati\apt-prova-01"
$env:API_KEY = "<la chiave generata>"
python -m engine
```

Il motore scrive i suoi log su stdout, una riga JSON per evento (`"msg": "engine started"` all'avvio). Se non parte, lo
dice nel log ed esce: **codice 2** se la configurazione non va (per esempio manca `API_KEY` o è troppo corta),
**codice 3** se il connector non si può usare (`unknown connector`, `connector without make_connector`,
`connector API version mismatch`, `connector setup failed` con il motivo nel campo `error`). Lo stato è in memoria:
fermato il motore, si riparte dai dati iniziali.

**4. Provarlo**, da un secondo terminale, con la stessa chiave (in PowerShell `curl.exe` al posto di `curl`):

```bash
# Git Bash, Linux o macOS
cd <cartella del repository>
export API_KEY=<la chiave generata>
curl http://127.0.0.1:8100/api/v1/health
H=(-H "X-API-Key: $API_KEY" -H "X-Actor: prova@esempio.it" -H "X-Correlation-Id: $(python -c 'import uuid; print(uuid.uuid4())')")
curl "${H[@]}" http://127.0.0.1:8100/api/v1/devices
curl "${H[@]}" -H "Content-Type: application/json" -d '{"capability":"switch","action":"turn_on"}' \
  http://127.0.0.1:8100/api/v1/devices/dev-presa-camera/commands
curl -N "${H[@]}" http://127.0.0.1:8100/api/v1/stream      # gli eventi in diretta; Ctrl+C per uscire
```

Ogni richiesta, tranne `health` e `version`, vuole i tre header: senza chiave risponde 401, senza `X-Actor` (un'email)
o `X-Correlation-Id` (un UUID) risponde 400. La suite di conformità al contratto, contro il proprio motore con il
connector simulato (dura circa un minuto; i 16 scenari devono passare tutti):

```bash
# Git Bash, Linux o macOS
cd <cartella del repository>
python -m pytest contract/conformance --base-url http://127.0.0.1:8100/api/v1 --api-key "$API_KEY" -q
```

**5. Collegare il proprio connector** (dettagli in `engine/connector/connector.md`, §2.7). Un connector è il
pacchetto `engine/connector/<nome>/` (per Shelly: `engine/connector/shelly/`). Il motore lo sceglie con
`CONNECTOR=<nome>` e lo costruisce una volta sola, all'avvio e prima di `start()`, con la funzione `make_connector`
esposta dal pacchetto nel suo `__init__.py`:

```python
# engine/connector/shelly/__init__.py
from engine.connector.interface import ConnectorConfig

from .connector import ShellyConnector


def make_connector(config: ConnectorConfig) -> ShellyConnector:
    # config.apartment_id, config.data_dir e config.catalog_path (pathlib.Path), config.env: solo le variabili
    # SHELLY_*, es. config.env.get("SHELLY_OFFLINE_AFTER_S", "120"). La chiave dell'API del motore non arriva.
    # Legge e verifica il catalogo; non apre connessioni: quelle in start().
    return ShellyConnector(config)
```

Le proprie variabili hanno il prefisso del nome del connector in maiuscolo più «_» (`SHELLY_` per `shelly`): una
variabile senza prefisso non arriva in `config.env`. Se il catalogo manca o è sbagliato, `make_connector` solleva
un'eccezione il cui messaggio dice quale campo e quale dispositivo sono sbagliati, mai il valore trovato: il motore
scrive «connector setup failed» con quel messaggio ed esce con il codice 3.

Poi lo si avvia come al punto 3, con `CONNECTOR=shelly`, le proprie `SHELLY_*` e il catalogo in `CATALOG_PATH` (o in
`<DATA_DIR>/catalog.yaml`). Con un connector diverso dal simulato `POST /_test/state` risponde 404 e `/ask` 501, come
in esercizio. Le prove comuni girano anche sul proprio connector quando c'è `engine/connector/<nome>/tests/harness.py`
con `make_harness()` (modello: `engine/connector/tests/fake_device.py`) e, se `make_connector` ha bisogno del catalogo,
`connector_env(data_dir)`, che lo scrive in `data_dir` e restituisce le variabili da aggiungere
(es. `{"CATALOG_PATH": str(data_dir / "catalog.yaml")}`). Per i log: `from engine.log import info` e poi
`info("command sent", correlation_id=..., command_id=..., device_id=...)`; ci sono anche `warn` ed `error`. `msg`
breve, in inglese e stabile, i dettagli nei campi, mai segreti.

**6. Con Docker (facoltativo)**, la stessa immagine che va sulla VM:

```bash
# Git Bash, Linux o macOS
cd <cartella del repository>
docker build -f engine/Dockerfile -t domhouse-engine .
docker run --rm -p 127.0.0.1:8100:8100 -e APARTMENT_ID=apt-prova-01 -e CONNECTOR=simulated -e API_KEY="$API_KEY" \
  domhouse-engine
```

Sulla VM ogni appartamento ha il suo motore, dallo stesso modello `engine/compose.yaml`: la sua porta 81xx, i suoi dati
in `/data/<apartment_id>` (`engine.db`, SQLite) e la chiave in un file fuori dal repository. Lo installa e lo aggiorna
`scripts/engine-vm.sh`; l'immagine la costruisce `scripts/deploy-engine.sh`.

## Variabili d'ambiente (BFF)

| Nome | Valori | Note |
|---|---|---|
| `APP_ENV` | dev \| staging \| prod | ambiente; il simulatore non dipende più da qui ma dal campo «istanza simulata» dell'appartamento (D-97) |
| `AUTH_MODE` | dev \| firebase | in `firebase` il token ID deve avere i claim `tenant_id` e `role` |
| `INSTANCE_MODE` | mock \| real | `real` usa `instance_url` dell'appartamento e la chiave da Secret Manager |
| `REPOSITORY` | memory \| firestore | Firestore: collezioni `tenants`, `users`, `apartments`, `bookings`, `webhook_logs` |
| `FCM_ENABLED` | true \| false | push FCM; con `false` l'app mostra toast |
| `GCP_PROJECT_ID`, `GCP_REGION`, `FIREBASE_PROJECT_ID` | | placeholder `your-gcp-project-id`, `europe-west8` |
| `SECRET_MANAGER_PREFIX` | `langbrain-api-key-` | nome segreto = prefisso + `apartment_id` (o `instance_secret_name`) |
| `ITALIANWAY_WEBHOOK_SECRET`, `ITALIANWAY_SIGNATURE_HEADER` | | HMAC-SHA256 esadecimale sul body grezzo (accetta anche `sha256=<hex>`) |
| `INSTANCE_TIMEOUT_S`, `PORT`, `BFF_ROOT_PATH` | | `BFF_ROOT_PATH` = prefisso unico quando il BFF è dietro un path (es. `/api`) |
| `CORS_ORIGINS` | | origini della PWA ammesse fuori da dev, separate da virgola |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | default `smtp.gmail.com`, `465` | email di invito; senza `SMTP_USER`/`SMTP_PASSWORD` l'invito è solo registrato. Su Cloud Run la password arriva dal segreto `smtp-app-password` |
| `MAIL_FROM_NAME` | default `DOMHOUSE` | nome del mittente e dell'app nell'email di invito (oggetto «Invito a DOMHOUSE»), D-76 |
| `APP_PUBLIC_URL` | | URL della PWA, usato nelle email di invito e come ritorno dal link «scegli la password» |

Frontend: `VITE_BFF_URL`, `VITE_AUTH_MODE`, `VITE_FCM_ENABLED`, `VITE_FIREBASE_*` (vedi `frontend/.env.example`).

## Messa in produzione

Prerequisiti (una tantum, progetto `your-gcp-project-id`):

1. Abilita API: Cloud Run, Artifact Registry, Cloud Build, Firestore (modalità Native, regione `europe-west8`), Secret Manager, Firebase Auth (Email/password e Google), Cloud Messaging.
2. Artifact Registry: `gcloud artifacts repositories create domotica --repository-format=docker --location=europe-west8`.
3. Service account `domotica-bff@your-gcp-project-id.iam.gserviceaccount.com` con ruoli `roles/datastore.user`, `roles/secretmanager.secretAccessor`, `roles/firebaseauth.admin`, `roles/firebasemessaging.admin`.
4. Segreti: `italianway-webhook-secret`, `smtp-app-password` (password SMTP del mittente delle email di invito, es. app
   password Gmail) e uno per istanza `langbrain-api-key-<apartment_id>`; `domotica-bff` deve poterli leggere
   (`roles/secretmanager.secretAccessor` sul singolo segreto). I segreti citati nel manifest devono esistere prima del
   deploy, altrimenti Cloud Run rifiuta la revisione.
5. `frontend/.env.production` con `VITE_AUTH_MODE=firebase`, `VITE_FIREBASE_*` del progetto web, `VITE_FCM_ENABLED` e `VITE_FIREBASE_VAPID_KEY` quando si attiva FCM.

Deploy (da Git Bash):

```bash
# staging: mock integrato nel BFF, simulatore attivo, Firestore e Firebase Auth reali
TARGET=staging GCP_PROJECT_ID=your-gcp-project-id GCP_REGION=europe-west8 SMTP_USER=<mittente> scripts/deploy.sh
# produzione: istanze reali del motore raggiunte via Direct VPC Egress
TARGET=prod GCP_PROJECT_ID=your-gcp-project-id GCP_REGION=europe-west8 VPC_NETWORK=<rete> VPC_SUBNET=<subnet> SMTP_USER=<mittente> scripts/deploy.sh
```

Lo script costruisce l'immagine con Cloud Build usando `cloudbuild.yaml` (il Dockerfile sta in `bff/` ma il contesto di
build è la radice del repository, perché l'immagine include anche `contract/`: per questo non si usa
`gcloud builds submit --tag`, che cerca un Dockerfile nella radice). Poi applica `bff/cloudrun.staging.yaml` o
`bff/cloudrun.yaml` sostituendo i placeholder in un file temporaneo, rende pubblico l'invoker (l'autenticazione la fa il
BFF), legge l'URL del servizio, compila la PWA con `VITE_BFF_URL` e pubblica su Firebase Hosting
(`frontend/firebase.json`, `.firebaserc`). Opzioni: `SKIP_BUILD=1` riusa l'ultima immagine, `SKIP_HOSTING=1` pubblica
solo il BFF.

Primo amministratore e utenti invitati:

```bash
python scripts/set_claims.py --email admin@azienda.it --tenant t-flatsharing-demo --role admin --create --send-reset-link
python scripts/set_claims.py --from-repo     # claim per tutti gli utenti invitati dall'area Amministrazione
```

Un utente invitato dall'area Amministrazione riceve un'email (link all'app, «Accedi con Google» e un link Firebase per
scegliere la password, valido 1 ora; «Reinvia» ne genera uno nuovo). Può accedere anche senza claim: il BFF lo riconosce
dall'email, **solo se verificata**, e migra il record `inv-*` al suo uid Firebase al primo accesso; i claim, quando
presenti, prevalgono. Quando l'admin cambia il ruolo di un utente con claim, il BFF aggiorna anche i claim; quando lo
rimuove, cancella anche l'account Firebase.

Account: «Password dimenticata?» nella pagina di accesso; nelle Impostazioni nome, cambio password ed email (per chi
accede con password), «Esci da tutti i dispositivi» (sessioni revocate rifiutate dal BFF entro 60 s) ed eliminazione del
proprio account (non per l'ultimo amministratore).

Webhook Italianway: configurare `https://<bff>/webhooks/italianway` con header `X-Signature`.
`ItalianwayTranslator` è uno **stub** finché il payload reale non è documentato (vedi "Domande aperte" nel contratto).
La scheda **Webhook** dell'area Amministrazione mostra le ultime 100 chiamate ricevute (timestamp, esito HMAC, `event_id`,
`correlation_id`, codice e tentativi dell'inoltro a `/bookings`, corpo grezzo): persistite nel repository (collezione
`webhook_logs` su Firestore), visibili solo agli amministratori.

Push FCM: `FCM_ENABLED=true` sul BFF e `VITE_FCM_ENABLED=true` + `VITE_FIREBASE_VAPID_KEY` sul frontend; con FCM attivo il
BFF apre uno stream per ogni appartamento abilitato così le notifiche non dipendono da un browser aperto.

## Note di architettura

- Autenticazione e `Last-Event-ID` viaggiano solo negli header (anche per lo stream, via fetch SSE); mai in query string.
- Nessuna UI ottimistica: i comandi mostrano «in corso» finché lo stream non conferma (`command.updated`, `device.state`).
- Il BFF archivia ogni `BookingEvent` inoltrato (`GET /app/apartments/{id}/bookings`): da qui ricava «Soggiorno in corso»
  (check-in della prenotazione `current_booking_id`) e il confronto con il soggiorno precedente, senza toccare il contratto.
- Ogni errore mostra l'ID di correlazione copiabile, lo stesso che compare nei log JSON del BFF.
