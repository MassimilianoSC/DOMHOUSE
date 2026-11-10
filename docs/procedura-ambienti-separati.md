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

## M18. Pubblicare un lotto con un solo comando (D-214): il modo normale dal 10 novembre 2026

`scripts/publish-all.sh` pubblica un lotto intero: staging, controlli, produzione, controlli, motore sulla VM se serve, riepilogo. Lo lancia il committente (D-116).

### Prima di partire

1. Il commit del lotto è su GitHub (`git push` fatto). Se non c'è, lo script si ferma prima di chiedere conferma.
2. In Git Bash funzionano `gcloud` (account proprietario) e `npx firebase-tools` (accesso fatto).
3. C'è `frontend/.env.production` (non è in Git).
4. La VM `langbrain-dev` è accesa: lo script legge il motore via `gcloud compute ssh` (IAP).

Le impostazioni (progetto, account, sito di staging, rete, mittente delle email, notifiche push, VM e appartamento del motore) sono in `scripts/publish-settings.conf`, senza segreti. Non si scrivono più a mano.

### M18.1 Prova a secco (sola lettura)

Cosa fa: legge lo stato vero di staging, produzione e motore, e mostra ogni passo che farebbe. Compila il sito in una copia pulita. Non scrive niente online e non chiede conferma.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
DRY_RUN=1 bash scripts/publish-all.sh <commit del lotto>
```

Verifica, da verificare al primo uso:

1. Righe «ora immagine …» per `domotica-bff-staging` e `domotica-bff`, e «motore dev sulla VM: …».
2. Una delle tre: «codice del motore invariato», «il motore è già all'immagine …», «codice del motore cambiato» con l'elenco dei file.
3. Ultima sezione: «Riepilogo … (prova a secco: niente è stato pubblicato)».
4. La produzione si prova a secco solo se lo staging serve già quel commit (D-203): la prima volta lo script lo dice e salta.

### M18.2 Pubblicazione (scrive su Google Cloud, sul sito e sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
bash scripts/publish-all.sh <commit del lotto>
```

Lo script mostra cosa farà e chiede una sola volta: «scrivi pubblica». Qualunque altra risposta non cambia niente.

Poi, in ordine:

| Passo | Cosa fa | Controllo |
|---|---|---|
| 1. Staging | `publish.sh TARGET=staging` | revisione nuova pronta e al 100 %, immagine del commit, `/health` 200 |
| 2. Produzione | `publish.sh TARGET=prod` (con il suo controllo D-203) | gli stessi, più i valori attivi uguali al manifesto |
| 3. Motore | solo se serve (sotto) | `engine-vm.sh update` aspetta `/health` 200; la VM dice l'immagine nuova |
| 4. Riepilogo | da incollare alla memoria storica | — |

Il motore si aggiorna solo se, fra il commit sulla VM e quello nuovo, cambia un file che entra nella sua immagine: `engine/` senza le cartelle `tests/` e senza i documenti `.md`, più `cloudbuild.engine.yaml` (D-215). L'immagine si costruisce una volta sola; se esiste già non si ricostruisce. `engine-vm.sh` si copia sulla VM, con `engine-vm.sh timers`, solo se la copia sulla VM è diversa da quella del commit.

Esito atteso, da verificare al primo giro vero:

1. Nessun FERMO.
2. Nel riepilogo: le due righe dei servizi con l'immagine del commit al 100 %, la riga del motore («invariato» o «da … a …»), i comandi per tornare indietro, il percorso del registro.
3. Durata stimata 15–25 minuti, non ancora misurata.

### Se si ferma

1. Ogni FERMO dice cosa è successo e cosa fare.
2. Risolto il problema, si rilancia **lo stesso comando**: i passi già fatti e verificati si saltano (scrive «già fatto in un giro precedente»).
3. La produzione non parte mai se i controlli dello staging non sono verdi.
4. Lo script non torna mai indietro da solo. Se serve, nel FERMO e nel riepilogo c'è il comando esatto:
   - server: `gcloud run services update-traffic <servizio> --to-revisions=<revisione di prima>=100 …`;
   - motore: `engine-vm.sh update dev <immagine di prima>` sulla VM.
5. Il sito di Hosting non ha un comando di ritorno nello script: si ripubblica il commit di prima, oppure si usa la console di Firebase (da verificare).
6. Se lo script dice «C'è già una pubblicazione in corso» e non ce n'è nessuna (finestra chiusa a metà): cancellare la cartella `logs/publish.lock`, poi rilanciare.

### Registro

Tutta l'uscita va anche in `logs/publish-<data-ora>-<commit>.log`; lo stato dei passi di un commit in `logs/publish-state-<commit>.txt`. La cartella `logs/` non va in Git. Alla memoria storica basta incollare il riepilogo.

### Cosa resta a mano

1. `git push` del commit.
2. I login di `gcloud` e `firebase`, e `frontend/.env.production`.
3. Il broker e i suoi segreti: procedura G2 (B5 e successivi), `broker-secrets.sh`.
4. Gli allarmi: `scripts/monitoring/setup.sh` ed `engine-alerts.sh`, quando cambiano.
5. La prova dell'app pubblicata (checklist di collaudo).

M8 e M12 restano come riferimento dei singoli passi; M18 li esegue in ordine. Differenza: M18 pubblica lo staging
sempre con le notifiche push attive (`VITE_FCM_ENABLED=true`, D-39), che il comando di M8 non passava.


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

Non necessaria il 23 ottobre 2026: i dati in produzione sono tutti di prova, inventati dal committente, e Flatsharing non
ha ancora visto l'app. Resta per quando il cliente la vedrà per la prima volta. Proposta di allora: «Gli appartamenti
dimostrativi si trovano su https://domhouse-staging.web.app, con le stesse credenziali; l'app di sempre resta per gli
appartamenti veri.»

## M11. Prima di togliere i dimostrativi dalla produzione: un backup recente (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud firestore backups list --location=europe-west8 --project=domotica-poc-511707 --format="value(name.basename(),snapshotTime)" --account=m.scardovellicrac@gmail.com
```

Verifica: un backup di oggi o di ieri. Poi i dimostrativi si tolgono dall'app di produzione (area Piattaforma, «rimuovi
appartamento»), secondo l'elenco di M1. **Dal 23 ottobre 2026 (D-188) questo passo si fa solo prima della consegna al
cliente, insieme a M16.**

## M12. Pubblicazione della produzione (dal commit del lotto)

Cosa fa: produzione con il database `(default)`. Dal lotto 36 (D-202) in produzione un indirizzo `mock://` è rifiutato: i dimostrativi si provano in staging e vanno tolti dalla produzione **prima** della prima pubblicazione del lotto 36, con M11.

**La produzione si pubblica solo con il commit che gira in staging (D-203).** `publish.sh` lo controlla prima di ogni altro passo, anche nella prova a secco. Se in staging c'è un altro commit, o l'ultima pubblicazione di staging non ha preso il traffico, si ferma con FERMO e dice cosa c'è e cosa volevi pubblicare: pubblica prima in staging. Solo per un'emergenza: `SKIP_STAGING_CHECK=1` davanti al comando; stampa un avviso.

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

## M14. Modello Claude su Vertex AI (D-179): ruolo, abilitazione, quota, impostazioni

Il server (identità `domotica-bff@domotica-poc-511707.iam.gserviceaccount.com`) chiama Vertex AI con la propria
identità, senza chiavi. Il ruolo necessario è `roles/aiplatform.user`, lo stesso già dato per Gemini al passo 9. Per i
modelli Claude servono in più l'abilitazione nel Model Garden (console, un clic per modello: accettazione delle
condizioni di Anthropic) e la quota nella regione scelta.

1. Verifica del ruolo (sola lettura; può farla la memoria storica). Git Bash:

```
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud projects get-iam-policy domotica-poc-511707 --flatten="bindings[].members" --filter="bindings.members:domotica-bff@domotica-poc-511707.iam.gserviceaccount.com" --format="value(bindings.role)"
```

Verifica: tra le righe c'è `roles/aiplatform.user`. Letto il 22 ottobre 2026 alle 16:51: presente (con
`roles/datastore.user`, `roles/firebaseauth.admin`, `roles/firebasecloudmessaging.admin`, `roles/logging.logWriter`).

2. Solo se il ruolo manca (scrive su GCP: lo lancia il committente, D-116). Git Bash:

```
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud projects add-iam-policy-binding domotica-poc-511707 --member="serviceAccount:domotica-bff@domotica-poc-511707.iam.gserviceaccount.com" --role="roles/aiplatform.user"
```

Cosa fa: dà al server il permesso di chiamare i modelli di Vertex AI (Gemini e Claude) e nient'altro. Verifica:
ripetere il comando del punto 1.

3. Abilitazione dei modelli Claude (console, committente): Vertex AI › Model Garden › cerca «Claude Haiku 5.5» › apri
la scheda › «Abilita» (accettazione delle condizioni); lo stesso per «Claude Sonnet 5.5». Verifica: la misura
`scripts/measure_model.py --endpoint anthropic --location eu --model claude-haiku-5-5` non risponde più
«endpoint HTTP 403» né «404».

4. Località e quota. Secondo la documentazione di Google (letta il 22 ottobre 2026), Claude Haiku 5.5 e Claude Sonnet
5.5 esistono solo nella multi-regione europea `eu` (elaborazione nell'Unione europea), nella multi-regione `us` e
sull'endpoint `global`: nessuna regione singola europea (`europe-west1` ha solo le generazioni precedenti). Le quote
predefinite di progetto sono per famiglia di modelli e località: Haiku 5.5 in `eu` 1.500 richieste al minuto, 15
milioni di token in ingresso e 1,5 milioni in uscita al minuto; Sonnet 5.5 in `eu` 1.250 richieste al minuto. Lettura
dal PC (sola lettura; memoria storica, 22 ottobre, registrata alle 16:58):

```
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud alpha services quota list --service=aiplatform.googleapis.com --consumer=projects/domotica-poc-511707 --format=json
```

Verifica: nell'elenco compaiono le metriche «EU multi-region online prediction requests per base model» con i
bucket `anthropic-claude-haiku` e `anthropic-claude-sonnet`, senza limite esplicito (valgono le quote di famiglia
sopra). Nella console: IAM e amministrazione › Quote e limiti di sistema › filtro «aiplatform» e «anthropic».

5. Impostazioni del server per usare Claude, quando deciso: `AI_API=anthropic`, `AI_MODEL=claude-haiku-5-5` (o
`claude-sonnet-5-5`), `AI_LOCATION=eu` (host `aiplatform.eu.rep.googleapis.com`), prezzi `AI_PRICE_*` confermati sul
listino ufficiale di Google prima della pubblicazione (D-143). Vanno nei manifesti della pubblicazione (M8 per lo
staging, M12 per la produzione). Nessuna chiave da creare né da conservare. **Regola D-180:** per qualunque modello la
località è `eu` o una regione europea (`europe-…`); `global` e `us` sono esclusi in tutti gli ambienti. Il server
rifiuta di partire con una località diversa (messaggio nel log) e `scripts/publish.sh` controlla lo stesso valore nel
manifesto prima di pubblicare.

## M15. Contatori settimanali dell'assistente (decisione 120, lotto 31): scadenza automatica

Il server scrive un documento per appartamento e settimana nella collezione `ai_stats` (domande, timeout, risposte
rapide per causa, richieste gemelle), con il campo `expire_at` a 12 mesi dal lunedì. Perché Firestore li cancelli da
solo serve la regola di scadenza sul campo, nei due database. Non scrive documenti: si può dare anche prima della
pubblicazione del lotto 31.

1. Attivazione (scrive su GCP: lo lancia il committente, D-116). Git Bash:

```
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for db in "(default)" staging; do gcloud firestore fields ttls update expire_at --collection-group=ai_stats --enable-ttl --database="$db" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --quiet; done
```

Cosa fa: attiva la cancellazione automatica dei contatori scaduti (campo `expire_at`, 12 mesi) nel database di
produzione e in quello di staging.

2. Verifica (sola lettura; può farla la memoria storica). Git Bash:

```
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for db in "(default)" staging; do gcloud firestore fields ttls list --database="$db" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format="value(name,ttlConfig.state)" | grep ai_stats; done
```

Verifica: due righe con `ai_stats` e stato `ACTIVE` (`CREATING` per qualche minuto subito dopo l'attivazione).

## M16. Pulizia della produzione prima della consegna al cliente (D-188, D-202)

Dal lotto 36 i dimostrativi `mock://` si tolgono subito (punto 1 fatto il 9 novembre); restano l'appartamento `dev` sulla VM e gli utenti di prova. Prima della
consegna, nell'ordine: (1) M11, backup recente e rimozione dei dimostrativi dall'app; (2) rimozione degli utenti di prova
(Amministrazione › Utenti, oppure Organizzazioni per i gestori) e delle organizzazioni di prova che non servono; (3) controllo,
in sola lettura, che nel database `(default)` non restino dati di prova: appartamenti con `mock://`, decisioni e registri dei
dimostrativi, contatori `ai_stats` dei dimostrativi, approvazioni e programmazioni di prova; la memoria storica prepara il
comando di lettura e l'elenco di ciò che va cancellato, il committente lancia le cancellazioni (D-116); (4) verifica finale con
`scripts/list_demos.py` (REPOSITORY=firestore, sola lettura): «0 dimostrativi».

## M17. Controllo delle impostazioni a ogni pubblicazione (D-197, lotto 35)

**A cosa serve:** evitare che una pubblicazione cambi senza che nessuno se ne accorga le impostazioni del server.

- **Prima di pubblicare** lo script mostra quattro impostazioni, con il valore attivo, il valore nuovo e se cambia: istanze minime, istanze massime, richieste contemporanee per istanza, tempo massimo di una richiesta.
- **Per vederle senza pubblicare niente:** aggiungi `DRY_RUN=1` davanti al comando di `publish.sh`.
- **Dopo la pubblicazione** lo script ricontrolla la versione appena creata.
- **Se un valore è diverso dal previsto** si ferma con la scritta FERMO, dice valore atteso e trovato, e non pubblica il sito: il server è già online con quei valori. Copia i messaggi e passali alla memoria storica.

**Controllo e allarmi prima della produzione:** subito prima di pubblicare in produzione si lancia `scripts/monitoring/setup.sh`, che ricrea il controllo di raggiungibilità e le regole. Il monitoraggio avvisa anche quando Cloud Run rifiuta le richieste perché non ha un'istanza disponibile (al massimo un'email ogni mezz'ora). Lo script usa i componenti `alpha` e `beta` di gcloud: alla prima esecuzione gcloud chiede di installarli, rispondi sì. Se il server è spento, lo script lo aspetta fino a circa un minuto.

> **Attenzione:** fino alla fine del lotto 35 non si pubblica nessun commit successivo a `8a49489` senza il via della memoria storica. Quei commit portano il tempo massimo a 300 s, e prima della chiusura degli stream lato server e della modifica del sito gli aggiornamenti in diretta cadrebbero ogni 5 minuti.

## M19. Spegnimento programmato e riaccensione (D-195, D-217)

Quando nessuno usa l'app per giorni, per non spendere (D-195). **Fino alla consegna la produzione resta accesa**
(rodaggio, D-210): questa procedura vale per lo staging, per dopo la consegna o per un fermo deciso dal committente.
I comandi li lancia il committente (D-116); la memoria storica verifica in sola lettura dopo ogni passo.

### M19.1 Spegnimento, in quest'ordine

1. **Sospendere gli avvisi di irraggiungibilità del sistema domotico** (D-217), così i gestori non ricevono la notifica
   «sistema domotico non raggiungibile» per uno spegnimento voluto. Vale dal lotto 38. Si scrive l'istante di fine,
   con il fuso (+01:00 d'inverno, +02:00 d'estate): fine prevista dello spegnimento più un margine, al massimo 30
   giorni. Allo scadere, se il motore è ancora fermo, l'avviso parte. Git Bash:

   ```
   cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
   gcloud run services update domotica-bff-staging --project=domotica-poc-511707 --region=europe-west8 --account=m.scardovellicrac@gmail.com --update-env-vars=UNREACHABLE_ALERTS_OFF_UNTIL=<istante di fine>
   ```

   Per la produzione lo stesso comando con `domotica-bff` (solo quando D-210 lo permette). L'istante esatto lo scrive
   la memoria storica nel comando al momento, senza segnaposto.

   Verifica (sola lettura):

   ```
   gcloud run services describe domotica-bff-staging --project=domotica-poc-511707 --region=europe-west8 --account=m.scardovellicrac@gmail.com --format="value(spec.template.spec.containers[0].env)" | tr ';' '\n' | grep UNREACHABLE
   ```

   Atteso: una riga con `UNREACHABLE_ALERTS_OFF_UNTIL` e l'istante. Dopo circa un minuto, nei registri del servizio
   la riga «unreachable alerts suspended» con la data; se compare «UNREACHABLE_ALERTS_OFF_UNTIL ignored», il valore
   è sbagliato (senza fuso, passato o oltre 30 giorni), gli avvisi restano attivi e il comando va rilanciato
   corretto. Una pubblicazione toglie la sospensione.
2. Fermare la VM `langbrain-dev` (motori e broker si fermano con lei; i dati restano sul disco).
3. Server di produzione a minimo 0 istanze (solo dopo la consegna o per un fermo deciso: oggi D-210 lo vieta).
4. Togliere il controllo di raggiungibilità `domotica-bff-healthz` e il suo allarme, che altrimenti terrebbero sveglio
   il server; si ricreano con `scripts/monitoring/setup.sh`.
5. Sospendere gli allarmi della VM e dei motori per il periodo dello spegnimento.

Restano attivi e costano poco: disco della VM e disco delle chiavi, snapshot, archivio delle immagini, segreti.

### M19.2 Riaccensione, in quest'ordine

1. Avviare la VM: motori e broker ripartono da soli (`restart: unless-stopped`; il disco delle chiavi si monta da
   `fstab`); controllare con `broker-vm.sh status` ed `engine-vm.sh status dev` (procedura G2, B7).
2. Server di produzione al minimo del manifesto (1), se era stato abbassato: la prossima pubblicazione lo rimette da sé.
3. `scripts/monitoring/setup.sh` per il controllo di raggiungibilità e il suo allarme.
4. **Riattivare gli avvisi di irraggiungibilità** (D-217). Git Bash:

   ```
   cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
   gcloud run services update domotica-bff-staging --project=domotica-poc-511707 --region=europe-west8 --account=m.scardovellicrac@gmail.com --remove-env-vars=UNREACHABLE_ALERTS_OFF_UNTIL
   ```

   Verifica: il comando di verifica del passo 1 dello spegnimento non stampa niente. Se ci si dimentica, la
   sospensione finisce comunque all'istante scritto. Dopo la riattivazione il server riparte: se il motore fosse
   ancora fermo, l'avviso arriva dopo la soglia, contata da lì.

I comandi esatti la memoria storica li prepara al momento, con la verifica: il modello è nella memoria del progetto
(spegnimento del 23–24 ottobre 2026).
