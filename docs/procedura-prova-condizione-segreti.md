# Prova: un permesso di CREARE segreti limitato dal nome

| Stato | Preparata | Decisione | Chi lancia | Durata | Comandi |
|---|---|---|---|---|---|
| **Pronta, da rileggere** | o1, 15 novembre 2026 | 1125 = a | il committente, un blocco alla volta, in Git Bash | 15–35 minuti, quasi tutti di attesa | 9 blocchi (P0–P8) |

**Domanda:** un permesso `secretmanager.secrets.create` dato con una condizione sul nome (`resource.name.startsWith(...)`) lascia creare **solo** i segreti con quel nome?

**Perché serve:** il progetto della base dello strumento A (`docs/progetto-strumento-a-base.md`, sezione 3.1). Se la condizione funziona, il server potrà creare solo i segreti dei dispositivi.

**Perché va provato e non letto:**

- la creazione si controlla sul progetto, non sul segreto, e la documentazione di Google non dice cosa vale `resource.name` in una creazione;
- non dice nemmeno se Secret Manager usa nel nome il **numero** del progetto (`projects/444239063209/…`) o il suo **identificativo** (`projects/domotica-poc-511707/…`). La pagina [Resource attributes](https://docs.cloud.google.com/iam/docs/conditions-resource-attributes) dice solo che i due «non sono intercambiabili».
- Per questo la prova le tenta **tutte e due insieme**.

## Come è fatta

**Tre account di servizio di prova**, tutti con lo stesso ruolo su misura che contiene **solo** `secretmanager.secrets.create`:

| Account | Permesso | Serve a |
|---|---|---|
| `dh-prova-ctrl` | senza condizione | **controllo:** quando riesce lui, il permesso è arrivato. Così un rifiuto dovuto al ritardo dei permessi non si scambia per una condizione che funziona |
| `dh-prova-num` | condizione con il numero: `projects/444239063209/secrets/dhprova-n-ok-` | prova la forma con il numero |
| `dh-prova-id` | condizione con l'identificativo: `projects/domotica-poc-511707/secrets/dhprova-i-ok-` | prova la forma con l'identificativo |

**Come agisci «come» l'account di prova:** con l'impersonazione di gcloud (`--impersonate-service-account`).

- Il tuo account proprietario prende in prestito l'identità dell'account di prova solo per quel comando.
- Per farlo ti serve il ruolo «Creatore di token dell'account di servizio» su ciascun account di prova: lo dà il blocco P3 e sparisce con la cancellazione degli account (P7).
- L'account attivo di gcloud non cambia: ogni comando ha `--account` e `--project`.

**Solo oggetti di prova:**

- segreti che cominciano con `dhprova-`, **senza versioni** (nessun valore dentro, nessun costo), replica solo in `europe-west8`;
- ruolo su misura `dhProvaCreaSegreti1116`.
- Nessun segreto esistente, motore, VM o broker viene toccato.
- Un ruolo su misura cancellato resta «cancellato» per 7 giorni e il suo id non si può riusare per circa 37 giorni: per questo l'id ha la data.

**Nessun argomento comincia con «/»:** le precauzioni di Git Bash (E-11) qui non servono.

## P0. Controlli prima (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud projects describe domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format='value(projectNumber)'
gcloud secrets list --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --filter='name:dhprova-' --format='value(name)'
gcloud iam service-accounts list --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --filter='email:dh-prova-' --format='value(email)'
gcloud iam roles describe dhProvaCreaSegreti1116 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format='value(name)'
gcloud services list --enabled --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --filter='config.name:iamcredentials.googleapis.com' --format='value(config.name)'
```

| Riga | Atteso |
|---|---|
| 1 | `444239063209` |
| 2 e 3 | **niente**: nessun segreto `dhprova-`, nessun account `dh-prova-` |
| 4 | un errore `NOT_FOUND`: il ruolo non esiste |
| 5 | `iamcredentials.googleapis.com` (serve all'impersonazione; la usa già il certificato del broker) |

Se una riga è diversa, fermati e incolla l'uscita alla memoria storica.

## P1. Ruolo su misura di prova (scrive su Google Cloud)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud iam roles create dhProvaCreaSegreti1116 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --title='DOMHOUSE prova: solo creare segreti' --description='Prova del 16 novembre 2026, da cancellare' --permissions=secretmanager.secrets.create --stage=GA
```

- **Atteso:** «Created role [dhProvaCreaSegreti1116]» e `includedPermissions: - secretmanager.secrets.create`.

## P2. I tre account di prova (scrive su Google Cloud)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for a in dh-prova-ctrl dh-prova-num dh-prova-id; do gcloud iam service-accounts create "$a" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --display-name="DOMHOUSE prova condizione, da cancellare"; done
```

- **Atteso:** tre righe «Created service account [dh-prova-…]».

## P3. Il permesso di impersonarli, per il tuo account (scrive su Google Cloud)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for a in dh-prova-ctrl dh-prova-num dh-prova-id; do gcloud iam service-accounts add-iam-policy-binding "$a@domotica-poc-511707.iam.gserviceaccount.com" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member=user:m.scardovellicrac@gmail.com --role=roles/iam.serviceAccountTokenCreator --format='value(etag)'; done
```

- **Atteso:** tre righe con un codice (l'etag della politica aggiornata), nessun errore.

## P4. Il ruolo ai tre account: uno senza condizione, due con condizione (scrive su Google Cloud)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud projects add-iam-policy-binding domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member=serviceAccount:dh-prova-ctrl@domotica-poc-511707.iam.gserviceaccount.com --role=projects/domotica-poc-511707/roles/dhProvaCreaSegreti1116 --condition=None --format='value(etag)'
gcloud projects add-iam-policy-binding domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member=serviceAccount:dh-prova-num@domotica-poc-511707.iam.gserviceaccount.com --role=projects/domotica-poc-511707/roles/dhProvaCreaSegreti1116 --condition='expression=resource.name.startsWith("projects/444239063209/secrets/dhprova-n-ok-"),title=dhprova-numero' --format='value(etag)'
gcloud projects add-iam-policy-binding domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member=serviceAccount:dh-prova-id@domotica-poc-511707.iam.gserviceaccount.com --role=projects/domotica-poc-511707/roles/dhProvaCreaSegreti1116 --condition='expression=resource.name.startsWith("projects/domotica-poc-511707/secrets/dhprova-i-ok-"),title=dhprova-identificativo' --format='value(etag)'
date '+%H:%M:%S'
```

- **Atteso:** tre righe con un codice e l'ora. **Annota l'ora:** da qui si contano le attese.

## P5. Attesa del controllo: il permesso è arrivato? (scrive: crea segreti di prova vuoti)

Ogni 30 secondi, al massimo per 10 minuti, `dh-prova-ctrl` prova a creare un segreto. Ogni tentativo usa un nome nuovo, così un errore «esiste già» non si confonde con un successo.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
ok=""; for i in $(seq 1 20); do err=$(gcloud secrets create "dhprova-c-$i" --replication-policy=user-managed --locations=europe-west8 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --impersonate-service-account=dh-prova-ctrl@domotica-poc-511707.iam.gserviceaccount.com 2>&1 >/dev/null) && { ok="$i"; break; }; echo "$(date '+%H:%M:%S') controllo, tentativo $i: $(printf '%s\n' "$err" | grep -m1 -E 'ERROR|PERMISSION' | cut -c1-160)"; sleep 30; done; if [ -n "$ok" ]; then echo "$(date '+%H:%M:%S') CONTROLLO RIUSCITO al tentativo $ok"; else echo "$(date '+%H:%M:%S') CONTROLLO MAI RIUSCITO in 10 minuti: PROVA NON CONCLUSIVA, vai a P7"; fi
```

- **Atteso:** qualche riga «tentativo N: … PERMISSION_DENIED …» (il permesso non è ancora arrivato), poi «CONTROLLO RIUSCITO al tentativo N».
- **Se compare «CONTROLLO MAI RIUSCITO»:** la prova non è conclusiva, perché il permesso o l'impersonazione non funzionano. Non fare P6: vai a P7 e incolla l'uscita.
- **Se gli errori non sono `PERMISSION_DENIED`** (per esempio sull'impersonazione): incolla l'uscita.

## P6. Le due forme della condizione (scrive: crea segreti di prova vuoti)

Per ciascun account con condizione:

1. prova il nome **giusto**, ogni 30 secondi, al massimo 10 minuti;
2. **solo dopo che il giusto è riuscito**, prova una volta il nome **sbagliato**.

Il controllo di P5 è già riuscito, quindi il permesso è arrivato.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
prova() { sa="$1@domotica-poc-511707.iam.gserviceaccount.com"; ok=""; for i in $(seq 1 20); do err=$(gcloud secrets create "$2$i" --replication-policy=user-managed --locations=europe-west8 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --impersonate-service-account="$sa" 2>&1 >/dev/null) && { ok="$i"; break; }; echo "$(date '+%H:%M:%S') $1, nome giusto, tentativo $i: $(printf '%s\n' "$err" | grep -m1 -E 'ERROR|PERMISSION' | cut -c1-160)"; sleep 30; done; if [ -z "$ok" ]; then echo "ESITO $1: nome giusto MAI riuscito in 10 minuti"; return; fi; echo "$(date '+%H:%M:%S') $1: nome giusto RIUSCITO al tentativo $ok"; err=$(gcloud secrets create "$3" --replication-policy=user-managed --locations=europe-west8 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --impersonate-service-account="$sa" 2>&1 >/dev/null) && echo "ESITO $1: nome giusto riuscito, nome SBAGLIATO RIUSCITO ANCHE LUI" || { case "$err" in *PERMISSION_DENIED*) echo "ESITO $1: nome giusto riuscito, nome sbagliato RIFIUTATO";; *) echo "ESITO $1: nome sbagliato, ALTRO ERRORE: $(printf '%s\n' "$err" | grep -m1 ERROR | cut -c1-160)";; esac; }; }
prova dh-prova-num dhprova-n-ok- dhprova-n-no-1
prova dh-prova-id dhprova-i-ok- dhprova-i-no-1
```

- **Atteso:** per ciascuno dei due account una riga che comincia con «ESITO». Le possibili:

| Riga «ESITO» | Vuol dire |
|---|---|
| «nome giusto riuscito, nome sbagliato RIFIUTATO» | **la condizione funziona con quella forma** |
| «nome giusto riuscito, nome SBAGLIATO RIUSCITO ANCHE LUI» | la condizione non limita niente |
| «nome giusto MAI riuscito in 10 minuti» | con quella forma la condizione non concede mai la creazione |
| «ALTRO ERRORE» | da guardare: incolla l'uscita |

## P7. Pulizia (scrive su Google Cloud: cancella solo gli oggetti di prova)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for s in $(gcloud secrets list --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --filter='name:dhprova-' --format='value(name.basename())' | tr -d '\r'); do case "$s" in dhprova-*) gcloud secrets delete "$s" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --quiet;; esac; done
for a in dh-prova-ctrl dh-prova-num dh-prova-id; do gcloud projects remove-iam-policy-binding domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member="serviceAccount:$a@domotica-poc-511707.iam.gserviceaccount.com" --role=projects/domotica-poc-511707/roles/dhProvaCreaSegreti1116 --all --format='value(etag)'; done
for a in dh-prova-ctrl dh-prova-num dh-prova-id; do gcloud iam service-accounts delete "$a@domotica-poc-511707.iam.gserviceaccount.com" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --quiet; done
gcloud iam roles delete dhProvaCreaSegreti1116 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --quiet --format='value(deleted)'
```

- **Atteso:**
  1. «Deleted secret [dhprova-…]» per ogni segreto di prova creato. Il `case` cancella solo i nomi che cominciano con `dhprova-`;
  2. tre codici, uno per permesso tolto (se un permesso non c'era, un errore innocuo);
  3. tre «deleted service account»;
  4. `True` per il ruolo.
- Cancellando gli account sparisce anche il tuo permesso di impersonarli (P3).
- `tr -d '\r'`: in Git Bash `gcloud` chiude ogni riga con un ritorno a capo di Windows, che finiva nel nome; il 16 novembre il ciclo ha mancato `dhprova-c-1` per questo (registro `e17c52e`).

## P8. Controllo finale: non resta niente (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
echo "segreti dhprova:"; gcloud secrets list --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --filter='name:dhprova-' --format='value(name)'
echo "account dh-prova:"; gcloud iam service-accounts list --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --filter='email:dh-prova-' --format='value(email)'
echo "ruolo:"; gcloud iam roles describe dhProvaCreaSegreti1116 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format='value(deleted)'
echo "permessi sul progetto per dh-prova:"; gcloud projects get-iam-policy domotica-poc-511707 --account=m.scardovellicrac@gmail.com --flatten='bindings[].members' --filter='bindings.members:dh-prova-' --format='value(bindings.role,bindings.members)'
```

| Riga | Atteso |
|---|---|
| segreti `dhprova` | niente |
| account `dh-prova` | niente |
| ruolo | `True`: cancellato. Resta visibile come «cancellato» per 7 giorni, poi sparisce da solo |
| permessi sul progetto | niente |

## Se la prova si interrompe a metà

Lancia **P7** e poi **P8**, così come sono. P7 cancella solo ciò che trova: un oggetto che non esiste dà un errore innocuo, e il resto prosegue.

## L'esito, in parole semplici

| Esito | Quando | Cosa si fa |
|---|---|---|
| **Riuscita** | il controllo è riuscito e almeno una delle due forme dice «nome giusto riuscito, nome sbagliato RIFIUTATO» | il server avrà il permesso di creare con la condizione scritta in quella forma (numero o identificativo) |
| **Fallita** | il controllo è riuscito, ma nessuna forma dà quell'esito: il nome giusto non riesce mai, oppure riesce anche lo sbagliato | si passa all'**alternativa (a)**: il server crea segreti senza condizione, ma non può leggere né scrivere versioni fuori dai nomi dei dispositivi |
| **Non conclusiva** | il controllo non è riuscito in 10 minuti, oppure compaiono errori diversi dal rifiuto del permesso | si capisce la causa con o1 e si ripete, con un ruolo dall'id nuovo |

**Da incollare alla memoria storica:** le uscite di P5, P6 e P8. Nessuna contiene valori di segreti: i segreti di prova sono vuoti.
