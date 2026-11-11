# D04: un account solo per lo staging

| Stato | Comandi | Preparata | Chi lancia | Quando |
|---|---|---|---|---|
| **Pronta, non lanciata** | o1, 11 novembre 2026 | memoria storica | il committente | prima del primo appartamento vero, dopo la prova di carico |

## Perché

- Oggi staging e produzione girano con lo **stesso account** (`domotica-bff@`).
- Quell'account può scrivere in **tutti** i database, quindi lo staging potrebbe scrivere in quello della produzione.
- Legge anche tutti i segreti della produzione.

## Termini

- **Account di servizio:** l'identità con cui gira il servizio su Cloud Run.
- **Condizione IAM:** un permesso che vale solo per una risorsa precisa. Qui: solo il database `staging`.

## Prima di lanciare

- La prova di carico deve essere **già fatta**. Lo strumento della prova dà i suoi segreti a `domotica-bff@`. Dopo questi comandi lo staging non li leggerebbe più.
- Dopo i comandi, o1 fa il suo commit. Il commit cambia l'account nel manifesto dello staging.

## 1. Comandi (Git Bash, un blocco solo, nell'ordine)

```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud iam service-accounts create domotica-bff-staging --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --display-name="DOMHOUSE BFF staging"
gcloud projects add-iam-policy-binding domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member=serviceAccount:domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com --role=roles/aiplatform.user --condition=None
gcloud projects add-iam-policy-binding domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member=serviceAccount:domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com --role=roles/firebaseauth.admin --condition=None
gcloud projects add-iam-policy-binding domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member=serviceAccount:domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com --role=roles/firebasecloudmessaging.admin --condition=None
gcloud projects add-iam-policy-binding domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member=serviceAccount:domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com --role=roles/logging.logWriter --condition=None
gcloud projects add-iam-policy-binding domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member=serviceAccount:domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com --role=roles/datastore.user --condition='expression=resource.name=="projects/domotica-poc-511707/databases/staging",title=solo-database-staging,description=D04 lo staging scrive solo nel suo database'
gcloud secrets add-iam-policy-binding langbrain-api-key-dev --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member=serviceAccount:domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding italianway-webhook-secret --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member=serviceAccount:domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor
gcloud secrets add-iam-policy-binding smtp-app-password --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member=serviceAccount:domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor
```

## 2. Verifica (sola lettura)

```bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud projects get-iam-policy domotica-poc-511707 --account=m.scardovellicrac@gmail.com --flatten="bindings[].members" --filter="bindings.members:domotica-bff-staging@" --format="table(bindings.role,bindings.condition.title)"
```

- **Atteso:** 5 righe.
- Quattro senza condizione: `aiplatform.user`, `firebaseauth.admin`, `firebasecloudmessaging.admin`, `logging.logWriter`.
- Una con la condizione `solo-database-staging`: `datastore.user`.

## 3. Dopo

| Passo | Chi |
|---|---|
| Commit del manifesto dello staging con il nuovo account, più una prova che fallisce se staging e produzione hanno lo stesso account | o1 |
| Pubblicazione con `scripts/publish-all.sh` | il committente |
| **Da verificare:** lo staging funziona (accesso, appartamenti, notifiche) e nei log non compaiono 403 «PERMISSION_DENIED» su Firestore | il committente con la memoria storica |
| Cambiare il nome dell'account in `scripts/load/ambiente.py` | o1, a congelamento finito |

## Note

- **Da allora in poi**, ogni `gcloud projects add-iam-policy-binding` vuole `--condition=None`. Altrimenti gcloud lo chiede ogni volta.
- **Resta condiviso Firebase Authentication:** è uno solo per i due ambienti. Limite accettato, scritto in `limiti-noti.md`.
- **`domotica-bff@` resta com'è** e può ancora entrare nel database dello staging. Toglierlo è un passo a parte, da decidere.
