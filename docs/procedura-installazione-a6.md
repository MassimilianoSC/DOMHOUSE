# Installazione di A6: eliminare un appartamento (staging), e il recupero dello storico

| Stato | Preparata | Codice | Chi lancia | Comandi |
|---|---|---|---|---|
| **Da rileggere**; si usa solo **dopo** la revisione di sicurezza di A6 e l'unione del ramo `o1-a6-eliminazione` in `main`. Nessun passo provato sul vero: i punti «da verificare» sono segnati | o1, 20 novembre 2026 | ultimo commit del codice: `d72892d` (ramo `o1-a6-eliminazione`); la procedura si controlla in G0 confrontandola con quella su GitHub | il committente, un blocco alla volta, in Git Bash, con la memoria storica in chat | G0–G5, R1–R6 |

**Cosa si installa** (`docs/proposta-a6.md`, risposte 1210: §8 punti 2–8 come proposti, punto 1 provvisorio):

| Dove | Che cosa |
|---|---|
| Server e sito dello staging | «Disattiva» / «Riattiva» del gestore; l'«Attivo» dell'amministratore che porta allo stesso stato, con l'ora; «Elimina» con il nome dopo 7 giorni; lo stato dell'eliminazione e «Riprova»; le email; 2 eliminazioni al giorno per organizzazione. Il vecchio «Elimina» (`DELETE`) risponde sempre 409 `use_elimina` |
| VM | **niente di nuovo**: con la risposta 3 = c (solo gli snapshot del disco, 30 giorni) l'eliminazione usa `togli_motore` di A2 così com'è |
| Google Cloud | niente di nuovo: i segreti si distruggono con il ritardo come per «Annulla» di A2 (il permesso c'è già) |

**Regole:**

1. Un blocco alla volta; **incolla alla memoria storica l'uscita di ogni blocco.** Se un'uscita non torna, fermati.
2. Ogni passo che scrive ha accanto il ritorno indietro. **L'eliminazione stessa non ha ritorno indietro**: da lì solo il recupero (R1–R6).
3. Solo lo **staging**: la creazione e quindi l'eliminazione completa esistono solo dove c'è l'agente (fino ad A10).
4. Ogni `gcloud compute ssh` finisce con `< /dev/null`.
5. **L'attesa di 7 giorni non ha scorciatoie**, nemmeno per la prova: G3 si fa quando `test-a2-02` è disattivato da almeno 7 giorni (lo dice la pagina, «Eliminabile dal …»).

## G0. Prerequisiti (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git fetch -q origin && git log --oneline -1 origin/main && git merge-base --is-ancestor d72892d origin/main && echo "A6 è in main, su GitHub" && git diff --quiet origin/main -- docs/procedura-installazione-a6.md && echo "procedura uguale a quella su GitHub"
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='systemctl is-active domhouse-agent-esecutore; sudo ls /opt/domhouse/*.settings; sudo ls /var/lib/domhouse-executor/ 2>/dev/null | head; sudo cat /etc/domhouse/_broker/apartments' < /dev/null
```

- **Atteso:**
  1. l'ultimo commit di `main`, «A6 è in main, su GitHub» e «procedura uguale a quella su GitHub»;
  2. `active`;
  3. fra le impostazioni `test-a2-02.settings` (l'appartamento di laboratorio, risposta 1205);
  4. `test-a2-02` nell'elenco del broker.

## G1. Server e sito dello staging (il committente pubblica)

Come D4 di A7: `publish.sh` dello staging, server **e** sito, dal commit di `main` che contiene A6.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git fetch -q origin && git merge-base --is-ancestor HEAD origin/main && git log --oneline -1 && while IFS='=' read -r k v; do v="${v%$'\r'}"; case "$k" in ''|'#'*) ;; *) export "$k=$v" ;; esac; done < scripts/publish-settings.conf && TARGET=staging bash scripts/publish.sh "$(git rev-parse --short HEAD)"
```

- **Atteso:** la pubblicazione dello staging riuscita, revisione nuova al 100 %, «PWA: https://domhouse-staging.web.app». Poi **ricarica la pagina** dell'app.
- **Ritorno indietro:** come D4 di A7 (il traffico alla revisione di prima). Un appartamento disattivato con A6 resta disattivato anche con il server di prima (lo stato è lo stesso `enabled` di oggi; i campi in più si ignorano).

## G2. Disattivare `test-a2-02` (scrive: lo stato dell'appartamento, due email)

1. Nell'app, come gestore della piattaforma: Piattaforma → l'organizzazione di `test-a2-02` → Appartamenti → `test-a2-02` → **«Disattiva»**.
2. **Atteso:**
   1. la riga dice «Disattivato» con l'ora e «da» il tuo nome, e «Eliminabile dal …» = fra 7 giorni;
   2. una email «Appartamento disattivato: …» agli amministratori di quell'organizzazione e ai gestori della piattaforma (anche a te);
   3. nel registro attività dell'organizzazione «apartment_disabled».
3. **Prova dell'amministratore** (facoltativa, se c'è un altro appartamento di prova): «Attivo» spento in Amministrazione → la stessa riga con «da» il nome dell'amministratore e la stessa email; poi riacceso: la riga torna senza ora.
4. **Ritorno indietro:** «Riattiva» (la riga torna attiva, senza ora; una nuova disattivazione riparte da zero).

## G3. Eliminare `test-a2-02` (quando «Eliminabile dal …» è passato; senza ritorno indietro)

Prima, la fotografia di quello che c'è (sola lettura):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='for f in /opt/domhouse/test-a2-02.settings /etc/domhouse/test-a2-02.env /etc/domhouse/test-a2-02.catalog.yaml /data/test-a2-02 /etc/domhouse/_broker/devices/test-a2-02; do sudo test -e $f && echo "c è $f" || echo "manca $f"; done; sudo grep -cx test-a2-02 /etc/domhouse/_broker/apartments; docker ps --filter name=engine-test-a2-02 --format "{{.Names}} {{.Status}}"' < /dev/null
for s in langbrain-api-key-test-a2-02 langbrain-shelly-test-a2-02; do echo "== $s"; gcloud secrets versions list $s --format="value(name,state)" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com; done
```

- **Atteso:** «c'è …» per le impostazioni, la chiave, il catalogo e la cartella dei dati; `1`; il contenitore `engine-test-a2-02 Up …`; per ciascun segreto almeno una versione `enabled`.
- I due segreti sono la chiave del motore (`SECRET_MANAGER_PREFIX` dello staging, `langbrain-api-key-`) e la password del connector (`langbrain-shelly-`), come in `bff/secret_admin.py` `names`.

Poi nell'app: `test-a2-02` → **«Elimina»** → la finestra mostra nome, id e indirizzo e cosa si perde → scrivi il nome esatto → conferma.

- **Atteso:** «Eliminazione in corso», poi entro pochi minuti la riga sparisce dall'elenco. Una email «Eliminazione avviata: …». Nel registro attività «apartment_deletion_started» e «apartment_deleted».
- **Se si ferma** («Eliminazione non riuscita» con il passo e il messaggio): incolla il messaggio alla memoria storica; «Riprova» riprende dal passo fermo.

## G4. Non è rimasto niente (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='for f in /opt/domhouse/test-a2-02.settings /etc/domhouse/test-a2-02.env /etc/domhouse/test-a2-02.catalog.yaml /data/test-a2-02 /etc/domhouse/_broker/devices/test-a2-02; do sudo test -e $f && echo "RESTA $f" || echo "tolto $f"; done; sudo grep -cx test-a2-02 /etc/domhouse/_broker/apartments || true; docker ps -a --filter name=engine-test-a2-02 --format "{{.Names}}" | grep -c . || true' < /dev/null
for s in langbrain-api-key-test-a2-02 langbrain-shelly-test-a2-02; do echo "== $s"; gcloud secrets versions list $s --format="value(name,state)" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com; done
.venv/Scripts/python.exe -c "from google.cloud import firestore; db = firestore.Client(project='domotica-poc-511707', database='staging'); a = db.collection('apartments').document('test-a2-02'); print('documento:', a.get().exists); print('credenziali:', len(list(a.collection('device_credentials').stream()))); print('id riservato:', db.collection('apartment_ids_used').document('test-a2-02').get().exists)"
```

- **Atteso:**
  1. cinque «tolto …», poi `0` (non è più nell'elenco del broker) e `0` (nessun contenitore);
  2. ogni versione dei due segreti `DESTROY_SCHEDULED` (si possono riattivare per 7 giorni) o `DESTROYED`;
  3. «documento: False», «credenziali: 0», «id riservato: True» (l'id resta usato, D-67).
- La porta di `test-a2-02` torna libera per la prossima creazione (il collegamento in `external_ids` è tolto da `remove_apartment`).

## G5. Il vecchio «Elimina» non salta l'attesa (sola lettura)

Nell'app, su un appartamento **dimostrativo** di prova attivo: la riga non ha più il pulsante del vecchio «Elimina»; «Elimina» compare solo dopo «Disattiva» e 7 giorni. Il server risponde 409 `use_elimina` alla vecchia chiamata (provato dalle prove automatiche, `tests/deletion_test.py`).

---

# Recupero dello storico di un appartamento eliminato (R1–R6)

**Quando:** entro 30 giorni dall'eliminazione (gli snapshot del disco della VM, uno al giorno alle 23:00 UTC, si tengono 30 giorni; risposta 1210, punto 3). Dopo, non c'è più niente da recuperare.

**Cosa si recupera:** lo storico del motore (`engine.db`: misure, decisioni, regole) in un appartamento **nuovo** creato con A2, con un id nuovo (l'id vecchio resta usato, D-67; risposta 1210, punto 7). I dispositivi vanno riconfigurati sul posto con password nuove («Registra»), perché le loro impronte sono state tolte.

**Da provare** con un appartamento di prova prima di servire (piano, riga A6: «il recupero dello storico è provato»). Tutti i passi sono «da verificare» finché la prova non è fatta.

## R1. Lo snapshot giusto (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute snapshots list --filter="sourceDisk~langbrain-dev" --sort-by=~creationTimestamp --limit=10 --format="table(name,creationTimestamp,diskSizeGb,status)" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** gli snapshot del disco `langbrain-dev`, il più recente in cima. Scegli il più recente **di prima** dell'eliminazione (l'ora dell'eliminazione è nel registro attività, «apartment_deleted»): la memoria storica scrive il suo nome nei comandi di R2.

## R2. Un disco dallo snapshot, collegato in sola lettura (scrive su Google Cloud)

La memoria storica prepara il comando con il nome dello snapshot scelto in R1: `gcloud compute disks create recupero-a6 --source-snapshot=<nome da R1> --zone=europe-west8-a …` e poi `gcloud compute instances attach-disk langbrain-dev --disk=recupero-a6 --mode=ro --zone=europe-west8-a …`.

- **Ritorno indietro:** R6.

## R3. Il file dello storico (sulla VM, sola lettura del disco recuperato)

- Montare il disco in sola lettura (`sudo mount -o ro,noload /dev/disk/by-id/google-recupero-a6-part1 /mnt/recupero`: **da verificare** il nome del dispositivo, `ls -l /dev/disk/by-id/ | grep recupero`).
- Il file migliore è l'ultima copia notturna, coerente: `/mnt/recupero/data/<id vecchio>/backup/` (le copie delle 22:30, 7 giorni). Se non c'è, `engine.db` nella cartella dei dati.
- Copiarlo in `/var/tmp/recupero-<id vecchio>.db` (cartella di root, 600) e controllarlo **come utente 10001**: `sudo -u '#10001' python3 -c 'import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute("PRAGMA integrity_check").fetchone()[0])' /var/tmp/recupero-<id vecchio>.db` → **Atteso:** `ok`.

## R4. L'appartamento nuovo (app)

Con A2, nell'organizzazione di prima: «Nuovo appartamento» con un id nuovo, fino a «Pronto».

## R5. Lo storico dentro il motore nuovo (scrive sulla VM)

- Copiare il file nella cartella delle copie del motore nuovo, con il proprietario del motore: `sudo install -o 10001 -g 10001 -m 600 /var/tmp/recupero-<id vecchio>.db /data/<id nuovo>/backup/recupero.db`.
- `sudo bash /opt/domhouse/engine-vm.sh restore <id nuovo> recupero.db`: controlla l'integrità, ferma il motore, tiene una copia di prima, mette il file, riparte.
- **Atteso:** «Ripristino di …» e il motore di nuovo sano. Nell'app, le misure e le regole di prima nell'appartamento nuovo.
- Poi nell'app, per ogni dispositivo: «Registra» e la password nuova copiata nello Shelly sul posto.

## R6. Pulizia (scrive su Google Cloud e sulla VM)

- `sudo umount /mnt/recupero; sudo shred -u /var/tmp/recupero-<id vecchio>.db`.
- `gcloud compute instances detach-disk langbrain-dev --disk=recupero-a6 …` e `gcloud compute disks delete recupero-a6 …` (la memoria storica li prepara completi): un disco recuperato è una copia in più di dati personali, non resta.

## Dopo l'installazione

- Da annotare in `docs/limiti-noti.md` (memoria storica): lo storico si recupera solo dagli snapshot, 30 giorni, con un disco intero; gli appartamenti spenti prima di A6 non sono eliminabili finché «Disattiva» non scrive l'ora; un appartamento collegato a mano (`lab-01`) perde solo il documento, il motore sulla VM va tolto a mano.
- Le uscite di tutti i blocchi alla memoria storica.
