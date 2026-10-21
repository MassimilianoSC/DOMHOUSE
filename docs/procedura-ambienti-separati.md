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

## M1. Elenco dei dimostrativi di oggi (sola lettura; condizione D-136, prima di tutto il resto)

Cosa fa: per ogni organizzazione con dimostrativi stampa gli appartamenti, le persone che li vedono e le modifiche
registrate. Non scrive niente.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
REPOSITORY=firestore GCP_PROJECT_ID=domotica-poc-511707 .venv/Scripts/python -u scripts/list_demos.py
```

Verifica: l'elenco a schermo; incollarlo alla memoria storica. Il committente decide se il cliente ha cambiato qualcosa da
conservare. (Il 21 ottobre, lanciato dalla memoria storica, lo script è rimasto fermo senza output: in verifica da o1.)

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
for c in bookings audit platform_audit support_access webhook_logs mail_limits audit_people actors actor_refs; do gcloud firestore fields ttls update expire_at --collection-group=$c --enable-ttl --database=staging --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --quiet; done
```

Verifica (sola lettura): deve elencare le nove collezioni con `expire_at`.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud firestore fields ttls list --database=staging --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
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

## M6. Permessi degli utenti nel formato per ambiente

Cosa fa: chi ha i permessi vecchi («piatti», per esempio il primo amministratore) li riceve come permessi di produzione.
Nessuna sessione viene chiusa. Prima senza `--apply` (mostra soltanto), poi con.

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

Email reali da decidere con il committente (la memoria storica scrive i comandi completi quando sono decise).
Cosa fa: l'accesso allo staging per chi lo usa; la produzione non cambia. Forma dei comandi (da completare):

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
