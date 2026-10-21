# CLAUDE.md — DOMHOUSE, già «Domotica appartamenti» (PWA + BFF)

Nome visibile dell'app: **DOMHOUSE** (D-76). Gli identificativi tecnici restano `domotica-*`.

**Motore domotico (D-104, 19 ottobre 2026): LangBrain non si usa.** Il motore dietro `contract/openapi.yaml` lo
costruiamo noi (`docs/piano-b-motore-minimo.md`); Youssouf consegna il connector Shelly. I nomi `langbrain-*` (VM
`langbrain-dev`, account `langbrain-vm@`, segreti `langbrain-api-key-<apartment_id>`) **restano**: rinominarli
vorrebbe dire migrare segreti e permessi senza vantaggi per chi usa l'app. Dove qui sotto si legge «LangBrain» o
«istanze LangBrain», si intende il motore domotico per appartamento.

Riferimento operativo per chi lavora in questo repository. `README.md` descrive l'app e le variabili d'ambiente;
qui ci sono gli identificativi reali dell'infrastruttura, le convenzioni e le regole fisse.
Questo è l'**unico** file del repository che contiene valori reali: nessun segreto, solo identificativi.

## Identificativi reali (GCP / Firebase)

| Cosa | Valore |
|---|---|
| Progetto GCP e Firebase | `domotica-poc-511707` (nome `domotica-poc`, numero `444239063209`). Un solo progetto per tutto, nessun progetto Firebase separato |
| Regione | `europe-west8` (Milano); zona della VM `europe-west8-a` |
| Account gcloud | Owner del progetto: `m.scardovellicrac@gmail.com`. Dal 17 ottobre 2026 l'account ATTIVO di gcloud su questo PC è `m.cracchiolo@hqe.it` (altro progetto del committente, nessun ruolo qui): non cambiarlo, e passare l'Owner a ogni comando (`--account=…` oppure `CLOUDSDK_CORE_ACCOUNT=…` davanti agli script) |
| Repository GitHub | `https://github.com/MassimilianoSC/DOMHOUSE` (privato, dal 20 ottobre 2026, storia azzerata: D-117). Il vecchio `MassimilianoSC/DOMOTICA` è archiviato e non si usa più. CI: `.github/workflows/conformita.yml` (tre controlli). |
| Artifact Registry (Docker) | `europe-west8-docker.pkg.dev/domotica-poc-511707/domotica`; immagine BFF `bff:<git-sha-short>` (scelto da `scripts/deploy.sh`) |
| Cloud Run | servizio `domotica-bff`, `europe-west8`, invoker pubblico (l'autenticazione la fa il BFF con il token Firebase), min 1 istanza, CPU sempre allocata, timeout 3600 s |
| URL del BFF (staging) | Il servizio risponde a due URL equivalenti: `https://domotica-bff-444239063209.europe-west8.run.app` (deterministico, usato per webhook Italianway e monitoraggio) e `https://domotica-bff-mgxrktwk6a-oc.a.run.app` (formato vecchio, quello che `deploy.sh` legge da `status.url`). Dal lotto 4 (16 ottobre 2026) la PWA è compilata con il primo (D-53); CORS dipende dall'origine della pagina, non dall'URL, quindi funzionano entrambi. Webhook: `https://domotica-bff-444239063209.europe-west8.run.app/webhooks/italianway` |
| Cloud Build | `cloudbuild.yaml` nella radice: costruisce `bff/Dockerfile` con contesto la radice del repo (serve `contract/`); usa l'account `domotica-build@domotica-poc-511707.iam.gserviceaccount.com` (P-21); all'account predefinito di Compute è stato tolto il ruolo Editor |
| Account di servizio del BFF | `domotica-bff@domotica-poc-511707.iam.gserviceaccount.com` — Cloud Datastore User, Firebase Authentication Admin, Firebase Cloud Messaging API Admin, Logs Writer; accesso ai singoli segreti (non a livello di progetto) |
| Account di servizio della VM | `langbrain-vm@domotica-poc-511707.iam.gserviceaccount.com` — Agent Platform User, Logs Writer, Monitoring Metric Writer; accesso a `langbrain-api-key-dev` |
| VM del motore domotico | `langbrain-dev`, `europe-west8-a`, e2-small, Debian 12, Docker + Compose; nessun IP pubblico; SSH solo via IAP con OS Login; snapshot giornaliero del disco con conservazione 30 giorni (politica `langbrain-daily-snapshot`) |
| IP interno della VM | `10.198.0.2`, statico (prenotazione `langbrain-dev-ip`) |
| Rete | VPC `default`, subnet `default` (`10.198.0.0/20`), Private Google Access attivo, Cloud NAT `langbrain-nat`; in ingresso solo tcp 8100-8199 dalla subnet (tag `langbrain-dev`) |
| Istanze del motore | una per appartamento, container `engine-<apartment_id>` (progetto Compose `domhouse-<apartment_id>`, immagine `europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:<commit>`), porta 81xx, dati in `/data/<apartment_id>` (`engine.db`, SQLite), chiave in `/etc/domhouse/<apartment_id>.env` dal segreto `langbrain-api-key-<apartment_id>`; installazione e aggiornamento con `scripts/engine-vm.sh`, procedura in `docs/motore-vm.md`; sviluppo `dev` su `http://10.198.0.2:8100` (raggiungibile solo dal BFF via VPC) |
| Firestore | database `(default)`, Standard, Native, `europe-west8`; regole di produzione (nessun accesso dai client, scrive solo il BFF via IAM) |
| Firebase Authentication | Email/password e Google; domini autorizzati `localhost`, `domotica-poc-511707.firebaseapp.com`, `domotica-poc-511707.web.app` |
| Firebase Hosting | `https://domotica-poc-511707.web.app` (app web `domotica-web`) |
| Segreti in Secret Manager | `italianway-webhook-secret` (valore provvisorio, da sostituire con quello concordato con Italianway), `langbrain-api-key-dev` (chiave dell'istanza dev, letta da BFF e VM), `gemini-api-key` (segnaposto, non usato), `smtp-app-password` (app password Gmail del mittente delle email di invito, letta dal BFF come `SMTP_PASSWORD`; va creata prima del deploy, altrimenti Cloud Run rifiuta la revisione). In futuro un segreto `langbrain-api-key-<apartment_id>` per ogni appartamento reale |
| Agent Platform (Vertex AI) | location `eu` (i modelli **non** esistono su `europe-west8`); endpoint OpenAI-compatibile `https://aiplatform.googleapis.com/v1/projects/domotica-poc-511707/locations/eu/endpoints/openapi`; autenticazione con l'identità della VM, nessuna chiave |
| Modelli Agent Platform | veloce `google/gemini-3.8-flash`, potente `google/gemini-4-argon` (prefisso `google/` obbligatorio; il flash consuma token di ragionamento, dimensionare `max_tokens` con margine) |

I valori dell'app web Firebase (`VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_APP_ID`, `VITE_FIREBASE_MESSAGING_SENDER_ID`,
chiave VAPID) **non** stanno in questo file: si trovano in
`C:\Users\mcracchiolo\Desktop\DOMOTICA\documenti-interni\CONFIGURAZIONE_GCP\domotica-config.txt` (fuori dal repository;
spostato il 19 ottobre 2026 da `per-youssouf`, che ora contiene solo ciò che si consegna a Youssouf)
e si copiano a mano in `frontend/.env.production`. Le decisioni di infrastruttura e l'elenco delle cose da fare sono nel
documento «Infrastruttura Domotica PoC – riepilogo e configurazione.docx» nella stessa cartella.

## Convenzioni

- **Il codice committato contiene solo placeholder**: `your-gcp-project-id`, `your-vpc-network`, `your-vpc-subnet`,
  `replace-me`, `dev-key`; `europe-west8` è il valore di default. Vale per `bff/cloudrun.yaml`, `bff/cloudrun.staging.yaml`,
  `frontend/.firebaserc`, `bff/.env.example`, `frontend/.env.example` e `README.md`. Non sostituirli mai nei file versionati.
- **I valori reali vanno solo in due posti**: le variabili d'ambiente del comando di deploy (`GCP_PROJECT_ID`, `GCP_REGION`,
  `VPC_NETWORK`, `VPC_SUBNET`, `VITE_FCM_ENABLED`) e `frontend/.env.production`. `scripts/deploy.sh` sostituisce i placeholder
  al volo in un file temporaneo e passa `--project` a gcloud e firebase-tools. Nessuno dei due posti è committato
  (`.gitignore` esclude `.env`, `.env.*`, `*.env`; restano solo gli `.env.example`).
- **Segreti**: il BFF li legge da Secret Manager, mai da file. `ITALIANWAY_WEBHOOK_SECRET` arriva via `secretKeyRef` nel
  manifest Cloud Run; le chiavi delle istanze sono `SECRET_MANAGER_PREFIX` (`langbrain-api-key-`) + `apartment_id`
  (o `instance_secret_name`). Nessuna chiave JSON di service account: BFF e VM usano le identità gestite da Google Cloud.
- **`apartment_id`**: identificativi neutri (es. `apt-001`), definiti alla settimana 6, uguali nel motore, nell'app, nei log e in
  Secret Manager. In sviluppo `dev`.
- **Strumenti**: `scripts/deploy.sh` e gli altri script bash si eseguono da **Git Bash**, non da PowerShell. Attenzione:
  Git Bash trasforma in percorso Windows ogni argomento che inizia con «/» passato a gcloud (es. `--path=/healthz` diventa
  `/C:/Program Files/Git/healthz`): usare `MSYS2_ARG_CONV_EXCL="--path="` davanti al comando e rileggere il risultato
  (E-11 del registro); `MSYS_NO_PATHCONV=1` rompe gcloud stesso. `gh` (GitHub CLI)
  non è installato su questa macchina: per le PR usare il sito o la cronologia git.
- **CORS**: PWA (Hosting) e BFF (Cloud Run) hanno origini diverse; il BFF accetta solo `CORS_ORIGINS` (già nei manifest con
  i domini `.web.app` e `.firebaseapp.com` del progetto). Il riepilogo infrastruttura ipotizza in alternativa i rewrite di
  Hosting `/app/**` e `/webhooks/**` verso Cloud Run: non sono implementati, il frontend chiama `VITE_BFF_URL` direttamente.

## Regole fisse

1. **`contract/openapi.yaml` non si modifica mai, per nessun motivo**, con un'unica eccezione decisa dal committente: la
   versione 1.0.5 **solo documentazione** (D-107, P-63: descrizioni, esempi e chiavi `x-*`; struttura identica, provata da
   uno script che confronta gli alberi senza quei campi; `CONTRACT_SHA256` nella CI e `CONTRACT_BLOB` in `scripts/publish.sh`
   aggiornati nello stesso commit). È il contratto v1.0.5 fra app e motore (il nostro, `engine/`) e confrontato in CI. Se una funzionalità sembra richiedere un campo in più, si risolve nel BFF o nel
   frontend (come già fatto per «Soggiorno in corso»), non nel contratto. Prima di ogni commit `git diff --stat contract/`
   deve essere vuoto. I tipi TypeScript si rigenerano con `make gen-api`, mai a mano.
2. **Nessun segreto né file `.env*` in Git.** Niente chiavi API, HMAC, token, chiavi JSON di service account, né `bff/.env`,
   `frontend/.env`, `frontend/.env.production`. Restano versionati solo `bff/.env.example` e `frontend/.env.example`, con
   placeholder. In caso di dubbio su un valore, va in Secret Manager o nelle variabili d'ambiente del deploy.
3. **Il primo deploy usa `TARGET=staging`** (`bff/cloudrun.staging.yaml`: mock integrato nel BFF con `INSTANCE_MODE=mock`,
   simulatore attivo, Firestore e Firebase Auth reali, una sola istanza perché il mock tiene lo stato in memoria).
   **`TARGET=prod` (`bff/cloudrun.yaml`, `INSTANCE_MODE=real`, Direct VPC Egress su `default`/`default`) solo quando il motore
   domotico sarà in esecuzione sulla VM**, cioè quando `http://10.198.0.2:8100/api/v1/health` risponde dalla rete interna.

## Deploy (riferimento rapido)

```bash
# Staging (primo deploy e finché il motore non gira sulla VM)
TARGET=staging GCP_PROJECT_ID=domotica-poc-511707 GCP_REGION=europe-west8 SMTP_USER=m.scardovellicrac@gmail.com scripts/deploy.sh

# Produzione (solo dopo la regola 3)
TARGET=prod GCP_PROJECT_ID=domotica-poc-511707 GCP_REGION=europe-west8 VPC_NETWORK=default VPC_SUBNET=default SMTP_USER=m.scardovellicrac@gmail.com scripts/deploy.sh
```

`SMTP_USER` è il mittente delle email di invito (temporaneamente l'account Gmail del proprietario del progetto, con app
password nel segreto `smtp-app-password`); senza `SMTP_USER` l'invito viene solo registrato e l'admin avvisa a mano.
L'email contiene il link all'app, l'indicazione «Accedi con Google» e un link Firebase per scegliere la password (vale 1
ora; dall'area Amministrazione «Reinvia» ne genera uno nuovo).
Account (ottobre 2026): «Password dimenticata?» sulla pagina di accesso; nelle Impostazioni nome visualizzato, cambio
password ed email (solo per chi accede con password, con la password attuale), uscita da tutti i dispositivi ed
eliminazione del proprio account (bloccata per l'ultimo admin). Il BFF rifiuta i token di sessioni revocate o account
eliminati (controllo in `bff/accounts.py`, cache di 60 s), accetta un invito solo con email verificata, aggiorna i claim
quando l'admin cambia ruolo e cancella l'account Firebase quando l'admin rimuove un utente. Le email inviate da Firebase
(reset, verifica, cambio email) usano `auth.languageCode = "it"`; la lingua predefinita dei modelli si imposta nella
console Firebase (Authentication > Modelli). Verifica in due passaggi non attiva: richiede l'upgrade a Identity Platform.
Opzioni: `SKIP_BUILD=1` riusa l'ultima immagine, `SKIP_HOSTING=1` pubblica solo il BFF, `VITE_FCM_ENABLED=true` solo con
`FCM_ENABLED=true` sul BFF e `VITE_FIREBASE_VAPID_KEY` in `frontend/.env.production`.
Prerequisiti: gcloud autenticato sul progetto, node + yarn, firebase-tools loggato (`npx firebase-tools login`),
`frontend/.env.production` compilato. Dopo il deploy: primo amministratore con
`python scripts/set_claims.py --email <admin> --tenant <tenant_id> --role admin --create --send-reset-link`.

## Infrastruttura già pronta (riepilogo del 15 ottobre 2026)

Da non ricreare: API abilitate (Cloud Run, Compute Engine, Secret Manager, Firestore, Vertex AI, Logging, Monitoring,
Cloud Build, Artifact Registry, IAM, IAP), repository Artifact Registry `domotica`, i due account di servizio con i
ruoli sopra, i segreti elencati sopra, Firestore `(default)`, Firebase Authentication, Hosting, coppia VAPID generata,
VM `langbrain-dev` con rete, NAT, firewall e snapshot giornaliero. I container del motore sulla VM si installano con `scripts/engine-vm.sh` (`docs/motore-vm.md`, D-116).

## Organizzazione del lavoro (dal 16 ottobre 2026)

Tre sessioni nella stessa cartella: **memoria storica** (dirige, tiene i documenti, non scrive codice), **o1** (server:
`bff/`, `tests/`, `scripts/`, build), **o2** (sito: `frontend/`). Il committente decide e lancia tutto ciò che scrive fuori
dalla macchina, compreso il `git push`.
- Regole di convivenza, vincolanti per tutte le sessioni: `docs/regole-convivenza.md` (commit per percorso con
  etichetta `[o1]`/`[o2]`/`[reg]`, messaggio con `-F`, mai `git add -A`, mai cancellare `.git/index.lock`).
- Perimetri: `docs/prompt-o1.md`, `docs/prompt-o2.md`. Route del BFF usate dal sito: `bff/API.md`.
- Decisioni, piano, cose da fare, errori, idee da valutare e stato del momento: **solo** in `docs/registro.md`,
  che scrive solo la memoria storica. Nessun altro file tiene un elenco di cose da fare.
- Guida utente e checklist di collaudo: `docs/guida-utente.md`, `docs/checklist-collaudo.md`.
