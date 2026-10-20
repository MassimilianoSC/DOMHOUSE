# Comandi da lanciare

*Dal 16 ottobre (D-51) questi comandi li lancia la memoria storica, avvisando il committente; il `git push` resta al committente.*

Comandi già pronti che scrivono fuori dal PC e che quindi lancia il committente. Li prepara la memoria storica, o o1/o2
attraverso di lei. Ogni blocco: terminale, cartella, cosa ci si deve aspettare. Le decisioni stanno nel registro
(`docs/registro.md`); qui ci sono solo i comandi delle attività già decise o in attesa di decisione, con il numero.
Dopo averli lanciati, incollare l'esito alla memoria storica.

---

## P-17 — Pubblicazione del lotto 3 (commit `604ed2b`)

Contiene il lotto 1 più le notifiche push (accese nell'ambiente di prova), l'account dedicato per le build e i
permessi per singolo appartamento (D-46).

**Prima: i 4 comandi della sezione P-21** (lo script si ferma se l'account per le build non esiste). Il commit `604ed2b`
va scritto in fondo: senza, lo script pubblicherebbe la versione più recente, che potrebbe contenere lavoro non provato.

Git Bash:
```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git push origin main
TARGET=staging GCP_PROJECT_ID=domotica-poc-511707 GCP_REGION=europe-west8 SMTP_USER=m.scardovellicrac@gmail.com VITE_FCM_ENABLED=true scripts/publish.sh 604ed2b
```
Ci si aspetta: passi in italiano (controlli, copia pulita, costruzione del server su Google con il nuovo account, 1-3
minuti, pubblicazione del server, compilazione e pubblicazione del sito) e alla fine le righe di riepilogo da incollare.
Se compare «FERMO:», seguire l'indicazione. Se chiede «pubblicare lo stesso? (scrivi si)», il push non è andato:
fermarsi. È la prima costruzione con il nuovo account: se fallisce per un permesso mancante, online non cambia nulla;
incollare il messaggio d'errore.

---

## P-21 — Account di servizio dedicato per Cloud Build (preparati da o1)

Da lanciare prima del commit di o1 che lo usa; vale dalla pubblicazione successiva al lotto 1.

Git Bash:
```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud iam service-accounts create domotica-build --project=domotica-poc-511707 --display-name="Cloud Build del BFF"
gcloud projects add-iam-policy-binding domotica-poc-511707 --member=serviceAccount:domotica-build@domotica-poc-511707.iam.gserviceaccount.com --role=roles/logging.logWriter --condition=None
gcloud artifacts repositories add-iam-policy-binding domotica --location=europe-west8 --project=domotica-poc-511707 --member=serviceAccount:domotica-build@domotica-poc-511707.iam.gserviceaccount.com --role=roles/artifactregistry.writer
gcloud storage buckets add-iam-policy-binding gs://domotica-poc-511707_cloudbuild --member=serviceAccount:domotica-build@domotica-poc-511707.iam.gserviceaccount.com --role=roles/storage.objectViewer
```
Ci si aspetta: «Created service account [domotica-build].» e poi tre conferme di policy aggiornata.
Il passo finale (togliere Editor all'account di Compute) si prepara solo dopo una build riuscita con il nuovo account,
e va rimisurato prima.

---

## P-2 — Backup giornaliero di Firestore (D-18)

Git Bash:
```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud firestore backups schedules create --database="(default)" --recurrence=daily --retention=14d --project domotica-poc-511707
```
Ci si aspetta: una descrizione del piano di backup creato, con `dailyRecurrence` e `retention: 1209600s` (14 giorni).
Verifica: `gcloud firestore backups schedules list --database="(default)" --project domotica-poc-511707` mostra un
elemento (il 16 ottobre ne mostrava 0).

---

## P-30 — Cancellare le regole firewall aperte a tutto internet (D-34)

Le due regole predefinite di Google (SSH e Desktop remoto da qualsiasi indirizzo). L'accesso di Youssouf passa da un'altra
regola, `langbrain-allow-iap-ssh`, che resta. Il comando chiede conferma: rispondere `Y`.

Git Bash:
```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute firewall-rules delete default-allow-ssh default-allow-rdp --project domotica-poc-511707
```
Ci si aspetta: «Deleted [.../default-allow-ssh].» e «Deleted [.../default-allow-rdp].»

---

## P-4 — Avviso email se il server non risponde (fatto il 16 ottobre)

Attivo. Per ricrearlo o ripararlo c'è un solo comando, che rilegge tutto e si ferma se qualcosa non torna
(preparato da o1 dopo l'errore E-11: Git Bash storpiava il percorso `/healthz`):
```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
GCP_PROJECT_ID=domotica-poc-511707 EMAIL=m.cracchiolo@hqe.it scripts/monitoring/setup.sh
```
Con `DRY_RUN=1` davanti legge soltanto. Dettagli in `scripts/monitoring/README.md`.

---

## P-1 — Chiave API web di Firebase limitata ai domini dell'app

Passo 1, Git Bash:
```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud services enable apikeys.googleapis.com --project domotica-poc-511707
```
Ci si aspetta: «Operation … finished successfully.» Il passo 2 (limitare la chiave) lo prepara la memoria storica
dopo aver letto quale chiave usa il sito.
