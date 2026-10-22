# Ambienti separati (P-67, D-136): procedura dei comandi del committente

*Scritta dalla memoria storica il 21 ottobre 2026 sulla procedura di o1 (pezzi 1–3 di P-67). I comandi che scrivono su
Google Cloud li lancia il committente (D-116). Forma: «cosa fa» e «verifica». Git Bash, sempre dalla cartella `app`.
Quando pubblicare lo decide il committente (D-146): i passi M2–M7 preparano lo staging e non cambiano la produzione; M8–M12
sono la pubblicazione vera e propria.*

**Cosa cambia alla fine:** due servizi Cloud Run (`domotica-bff` produzione, `domotica-bff-staging` prova), due database
Firestore nello stesso progetto (`(default)` e `staging`), due siti Hosting, permessi degli utenti separati per ambiente;
i dimostrativi solo nello staging, la produzione solo con appartamenti veri (un collegamento `mock://` viene rifiutato);
il motore `dev` sulla VM collegato allo staging. Nel sito di prova compare la fascia «Ambiente di prova · i dati sono
separati da quelli veri».

**Nome del sito di prova:** il committente ha scelto `domhouse-staging` (`https://domhouse-staging.web.app`) se l'id è
libero su Firebase Hosting; lo si scopre in M4: se il comando dice che l'id è già preso, si usa il predefinito
`domotica-poc-511707-staging` e si sostituisce il nome in M4, M5, M8 (senza `STAGING_SITE`) e M10.

---

## M0. Una volta sola: credenziali applicative sul PC (scrive solo file locali)

Gli script Python che leggono o scrivono Firestore (M1, M6, M7) usano le «credenziali applicative» di Google sul
PC, diverse dal login di `gcloud`. Cosa fa: apre il browser per l'accesso con l'account proprietario e salva il
file delle credenziali sul PC; poi indica il progetto da addebitare per le chiamate.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud auth application-default login
gcloud auth application-default set-quota-project domotica-poc-511707
```

Verifica: M1 stampa l'elenco invece di «Firestore non risponde entro 30 secondi».

## M1. Elenco dei dimostrativi di oggi (sola lettura; condizione D-136, prima di tutto il resto)

Cosa fa: per ogni organizzazione con dimostrativi stampa gli appartamenti, le persone che li vedono e le modifiche
registrate. Non scrive niente.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
REPOSITORY=firestore GCP_PROJECT_ID=domotica-poc-511707 .venv/Scripts/python -u scripts/list_demos.py
```

Verifica: l'elenco a schermo; incollarlo alla memoria storica. Il committente decide se il cliente ha cambiato qualcosa da
conservare. Se dice «Firestore non risponde entro 30 secondi», fare M0.

## M2. Database Firestore dello staging

Cosa fa: crea il secondo database, vuoto, nello stesso progetto, a Milano.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud firestore databases create --database=staging --location=europe-west8 --type=firestore-native --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

Verifica (sola lettura): deve mostrare `(default)` e `staging`, entrambi `europe-west8`.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud firestore databases list --project=domotica-poc-511707 --format="value(name.basename(),locationId)" --account=m.scardovellicrac@gmail.com
```

## M3. Regole di scadenza (TTL, P-54) sul database staging

Cosa fa: i documenti scaduti si cancellano da soli anche in staging, come in produzione (nove collezioni, un comando in
ciclo).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for c in bookings audit platform_audit support_access webhook_logs mail_limits audit_people actors actor_refs summaries; do gcloud firestore fields ttls update expire_at --collection-group=$c --enable-ttl --database=staging --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --quiet; done
```

Verifica (sola lettura): deve elencare le dieci collezioni con `expire_at` (`summaries` è dei riepiloghi settimanali, passo 11).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud firestore fields ttls list --database=staging --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

## M3b. Regola di scadenza dei riepiloghi settimanali anche in produzione (passo 11, D-150)

Cosa fa: attiva la cancellazione automatica dei riepiloghi scaduti (campo `expire_at`, 12 mesi) nei due database. Non
scrive documenti: si può dare anche prima della pubblicazione.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for db in "(default)" staging; do gcloud firestore fields ttls update expire_at --collection-group=summaries --enable-ttl --database="$db" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --quiet; done
```

Verifica (sola lettura): due righe con `summaries` e stato `ACTIVE` (`CREATING` per qualche minuto subito dopo).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for db in "(default)" staging; do gcloud firestore fields ttls list --database="$db" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format="value(name,ttlConfig.state)" | grep summaries; done
```

## M4. Sito Hosting dello staging

Cosa fa: crea il secondo sito, ancora vuoto. Se risponde che l'id è già preso, ripetere con `domotica-poc-511707-staging`.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
npx firebase-tools hosting:sites:create domhouse-staging --project domotica-poc-511707
```

Verifica: deve mostrare i due siti.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
npx firebase-tools hosting:sites:list --project domotica-poc-511707
```

## M5. Dominio dello staging tra quelli autorizzati di Firebase Auth (console, nessun comando)

Console Firebase → Authentication → Settings → Authorized domains → Add domain: `domhouse-staging.web.app` e
`domhouse-staging.firebaseapp.com` (con il nome scelto in M4).
Cosa fa: permette l'accesso (Google e password) dal sito di staging. Verifica: i due domini nell'elenco, accanto a quelli
di oggi.

## M5b. Chiave API del browser: il sito di prova fra i referrer ammessi (scrive su Google Cloud)

La chiave «Browser key (auto created by Firebase)» accetta richieste solo dai siti elencati (P-1): senza il sito di
prova, l'accesso con Google e con password fallisce prima di arrivare al server, con il messaggio generico «Accesso
non riuscito: controlla email e password» (scoperto il 22 ottobre). Cosa fa: aggiunge i due indirizzi del sito di prova
ai referrer ammessi, mantenendo quelli di oggi. Il valore della chiave non compare mai.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud services api-keys update projects/444239063209/locations/global/keys/d6cdcf10-17c7-4318-b1af-7ff65352eb72 --allowed-referrers="https://domotica-poc-511707.web.app/*,https://domotica-poc-511707.firebaseapp.com/*,http://localhost:5173/*,https://domhouse-staging.web.app/*,https://domhouse-staging.firebaseapp.com/*" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

Verifica (sola lettura): i cinque indirizzi.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud services api-keys describe projects/444239063209/locations/global/keys/d6cdcf10-17c7-4318-b1af-7ff65352eb72 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format="value(restrictions.browserKeyRestrictions.allowedReferrers)"
```

## M6. Permessi degli utenti nel formato per ambiente

Cosa fa: chi ha i permessi vecchi («piatti», per esempio il primo amministratore) riceve ANCHE i permessi di produzione
nel formato nuovo; quelli vecchi restano, così il server di oggi continua a funzionare. Si può lanciare in qualunque momento,
anche prima di M12. Nessuna sessione viene chiusa. Prima senza `--apply` (mostra soltanto), poi con.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
.venv/Scripts/python scripts/set_claims.py --migrate-claims
```

Se l'elenco è giusto:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
.venv/Scripts/python scripts/set_claims.py --migrate-claims --apply
```

Verifica: un secondo lancio senza `--apply` deve dire «0 account da riscrivere».

## M7. Primo amministratore e gestori della piattaforma nello staging

Deciso (D-149): entra il committente, come gestore della piattaforma e primo amministratore dell'organizzazione di
prova; poi invita dall'app chi vuole. Cosa fa: l'accesso allo staging per chi lo usa; la produzione non cambia. La
memoria storica scrive i due comandi completi al momento (con l'email del committente e il nome dell'organizzazione di
prova scelto in M9). Forma:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
.venv/Scripts/python scripts/set_claims.py --email <email> --tenant <tenant di staging> --role admin --env staging
REPOSITORY=firestore GCP_PROJECT_ID=domotica-poc-511707 FIRESTORE_DATABASE=staging .venv/Scripts/python scripts/set_claims.py --platform-add <email>
```

## M8. Pubblicazione dello staging (dal commit del lotto)

Cosa fa: crea il servizio `domotica-bff-staging` sul database `staging` e pubblica il sito di staging. Il commit lo indica
la memoria storica al momento.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com TARGET=staging STAGING_SITE=domhouse-staging GCP_PROJECT_ID=domotica-poc-511707 VPC_NETWORK=default VPC_SUBNET=default SMTP_USER=m.scardovellicrac@gmail.com scripts/publish.sh <commit del lotto>
```

Verifica: le righe finali con BFF e PWA (`https://domhouse-staging.web.app`); l'accesso con l'amministratore di M7; la
fascia «Ambiente di prova» in alto.

## M9. Dimostrativi ricreati nello staging (dall'app)

Dall'area Piattaforma del sito di staging (D-136, decisione 4): i dimostrativi si ricreano da zero; l'appartamento `dev`
si collega al motore della VM (indirizzo `http://10.198.0.2:8100/api/v1`, id `dev`).

## M10. Frase per il cliente, prima del cambio (condizione D-136)

La manda il committente. Proposta: «Da <data> gli appartamenti dimostrativi si trovano su https://domhouse-staging.web.app,
con le stesse credenziali; l'app di sempre resta per gli appartamenti veri.»

## M11. Prima di togliere i dimostrativi dalla produzione: un backup recente (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud firestore backups list --location=europe-west8 --project=domotica-poc-511707 --format="value(name.basename(),snapshotTime)" --account=m.scardovellicrac@gmail.com
```

Verifica: un backup di oggi o di ieri. Poi i dimostrativi si tolgono dall'app di produzione (area Piattaforma, «rimuovi
appartamento»), secondo l'elenco di M1.

## M12. Pubblicazione della produzione (dal commit del lotto)

Cosa fa: produzione con il database `(default)`, senza dimostrativi: un indirizzo `mock://` viene ora rifiutato.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
CLOUDSDK_CORE_ACCOUNT=m.scardovellicrac@gmail.com TARGET=prod GCP_PROJECT_ID=domotica-poc-511707 VPC_NETWORK=default VPC_SUBNET=default SMTP_USER=m.scardovellicrac@gmail.com VITE_FCM_ENABLED=true scripts/publish.sh <commit del lotto>
```

Verifica: la nuova revisione al 100 %; nel sito di produzione nessuna fascia «Ambiente di prova» e nessun dimostrativo.
Dopo: la memoria storica verifica in sola lettura i due servizi, e il motore `dev` sulla VM continua a servire lo staging.

---

## M13. Motore sulla VM e allarmi (lotti 21–23)

Dopo M8 (o M12), con il commit del lotto scelto: immagine del motore (`docs/motore-vm.md` B1), copia del nuovo
`engine-vm.sh` e di `compose.yaml` sulla VM (C1) e reinstallazione di `dev` con la nuova immagine (C2, ripetibile);
facoltativo `engine-vm.sh set dev MODEL_BASE_URL=<indirizzo del server di staging>` per l'assistente vero (D2);
poi i tre comandi del passo 10 (sezione E2: timer, log dei motori, allarmi).
