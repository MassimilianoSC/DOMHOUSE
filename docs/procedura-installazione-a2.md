# Installazione di A2: creare un appartamento dall'app (staging)

| Stato | Preparata | Codice | Chi lancia | Comandi |
|---|---|---|---|---|
| **Corretta dopo la revisione del codice** (20 novembre: punti 1–9 fatti; seconda lettura «installabile», poi N1, N2 e C1.4b corretti); da rileggere. Nessun passo provato sul vero | o1, 20 novembre 2026, 13:46; corretta nel pomeriggio | file della VM e server da `bd4a8bf` (impronte in C2) | il committente, un blocco alla volta, in Git Bash, con la memoria storica in chat | C0–C9 |

**Cosa si installa** (`docs/proposta-a2.md`, §7):

| Dove | Che cosa |
|---|---|
| Google Cloud | due ruoli su misura e quattro permessi con condizione: il server crea i due segreti di un appartamento, aggiunge e distrugge versioni, legge solo le chiavi dei motori; la VM legge i segreti dei prefissi dello staging. I segreti fatti a mano di `lab-01` restano fuori per nome |
| VM | `engine-vm.sh`, `broker-vm.sh`, `broker_accounts.py` e `compose.catalog.yaml` nuovi; l'esecutore che esegue `crea_motore` e `togli_motore`, con l'unità allargata; il file dell'immagine approvata; `ENV=staging` in `dev` e `lab-01` |
| Server e sito dello staging | le rotte della creazione (pezzo 2) e le pagine di o2 |

**Regole:**

1. Un blocco alla volta; **incolla alla memoria storica l'uscita di ogni blocco.** Se un'uscita non torna, fermati.
2. Ogni passo che scrive ha accanto il ritorno indietro.
3. Solo lo **staging**. In produzione «Nuovo appartamento» resta spento fino alla seconda VM (risposta 1162).
4. Ogni `gcloud compute ssh` finisce con `< /dev/null`. Un «Segmentation fault» **dopo** l'uscita attesa è innocuo (plink, sul PC).
5. **`broker-vm.sh` nuovo e l'esecutore nuovo vanno sulla VM insieme (C6).** Con il `broker-vm.sh` nuovo, l'esecutore di A3 di oggi non riuscirebbe più a fare il `sync`: non può scrivere il blocco della VM (`/opt/domhouse/.engines.lock`). Fino a C6 il nuovo resta con un altro nome (`broker-vm.sh.a2`), solo per la prova di C4.
6. Fra C3 e C6 niente «Registra», «Rigenera» o «Revoca» su `lab-01`: per sicurezza, anche se `engine-vm.sh` nuovo non tocca il broker.
7. **Lezioni del 20 novembre (A3):**
   - si provano con `systemd-run` le restrizioni dell'unità **e** l'ambiente dei comandi, prima di installare (C4);
   - le credenziali predefinite del PC possono essere scadute: se un comando `gcloud` chiede di ricollegarsi, lancia `gcloud auth login m.scardovellicrac@gmail.com` e rifai il blocco;
   - `ls` dentro `/etc/domhouse` vuole `sudo`.

**Quando:** dopo il push dei commit di A2 (fino al commit di questa procedura). Il giorno lo decide il committente.

## C0. Prerequisiti (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git fetch -q origin && git merge-base --is-ancestor bd4a8bf origin/main && git diff --quiet bd4a8bf HEAD -- scripts/agent scripts/agent-vm.sh scripts/engine-vm.sh scripts/broker-vm.sh scripts/broker_accounts.py engine/compose.catalog.yaml bff && echo "file uguali a bd4a8bf, già su GitHub"
gcloud iam roles list --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format="value(name)" | grep -E "dhA2" || echo "nessun ruolo dhA2"
gcloud projects get-iam-policy domotica-poc-511707 --account=m.scardovellicrac@gmail.com --flatten="bindings[].members" --filter="bindings.role~secretmanager OR bindings.role~dhA2" --format="table[no-heading](bindings.role,bindings.members,bindings.condition.title)"
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='systemctl is-active domhouse-agent-esecutore domhouse-agent-lettore; sudo ls /opt/domhouse/*.settings; sudo ss -ltn | grep -E ":81(5[0-9]) " || echo "porte 8150-8159 libere"; sudo ls /etc/domhouse/agent-immagine-staging 2>&1 | tail -1; sudo ls -d /data' < /dev/null
```

- **Atteso:**
  1. «file uguali a bd4a8bf, già su GitHub»;
  2. «nessun ruolo dhA2»;
  3. nessuna riga di Secret Manager a livello di progetto (il 19 novembre non ce n'erano; i permessi di oggi sono segreto per segreto);
  4. i due servizi `active`; `dev.settings` e `lab-01.settings`; «porte 8150-8159 libere»; «No such file» per `agent-immagine-staging`; `/data`.
- Una porta della fascia occupata: fermati (il primo appartamento la troverebbe occupata e prenderebbe la successiva, ma va capito chi la usa).

## C1. I permessi su Google Cloud (scrive su Google Cloud)

**C1.1 I due ruoli su misura** (progetto §4.1: «creazione» e «versioni»).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud iam roles create dhA2CreaSegreti --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --title='DOMHOUSE A2: creare i segreti di un appartamento' --description='Solo secrets.create; con la condizione sui nomi dello staging' --permissions=secretmanager.secrets.create --stage=GA
gcloud iam roles create dhA2VersioniSegreti --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --title='DOMHOUSE A2: versioni dei segreti di un appartamento' --description='Prima versione e distruzione con ritardo; con la condizione sui nomi dello staging' --permissions=secretmanager.versions.add,secretmanager.versions.list,secretmanager.versions.destroy,secretmanager.secrets.get --stage=GA
```

- **Atteso:** due ruoli creati, con i permessi elencati (uno e quattro).
- **Ritorno indietro:** `gcloud iam roles delete dhA2CreaSegreti --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com` (e lo stesso per `dhA2VersioniSegreti`). Un ruolo cancellato tiene il suo id per circa 37 giorni: per rifarlo serve un id nuovo.

**C1.2 Il server dello staging: creazione e versioni sui nomi dello staging, i segreti di `lab-01` esclusi per nome; lettura delle sole chiavi dei motori** (proposta §3.3, revisione punto 13; condizioni con il **numero** del progetto, prova 1125).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
set +H
N=projects/444239063209/secrets
SA=serviceAccount:domotica-bff-staging@domotica-poc-511707.iam.gserviceaccount.com
NOMI="(resource.name.startsWith(\"$N/langbrain-shelly-lab-\") || resource.name.startsWith(\"$N/langbrain-shelly-test-\") || resource.name.startsWith(\"$N/langbrain-api-key-lab-\") || resource.name.startsWith(\"$N/langbrain-api-key-test-\"))"
FUORI="resource.name != \"$N/langbrain-shelly-lab-01\" && !resource.name.startsWith(\"$N/langbrain-shelly-lab-01/\") && resource.name != \"$N/langbrain-shelly-lab-01-devices\" && !resource.name.startsWith(\"$N/langbrain-shelly-lab-01-devices/\") && resource.name != \"$N/langbrain-api-key-lab-01\" && !resource.name.startsWith(\"$N/langbrain-api-key-lab-01/\")"
LETTURA="resource.name.startsWith(\"$N/langbrain-api-key-lab-\") || resource.name.startsWith(\"$N/langbrain-api-key-test-\")"
gcloud projects add-iam-policy-binding domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member="$SA" --role=projects/domotica-poc-511707/roles/dhA2CreaSegreti --condition="expression=$NOMI && $FUORI,title=a2-creazione-staging" --format='value(etag)'
gcloud projects add-iam-policy-binding domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member="$SA" --role=projects/domotica-poc-511707/roles/dhA2VersioniSegreti --condition="expression=$NOMI && $FUORI,title=a2-versioni-staging" --format='value(etag)'
gcloud projects add-iam-policy-binding domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member="$SA" --role=roles/secretmanager.secretAccessor --condition="expression=$LETTURA,title=a2-lettura-staging" --format='value(etag)'
```

- **Atteso:** tre righe con un `etag`.
- `set +H` serve perché le esclusioni contengono `!`: senza, Git Bash lo prenderebbe come un rimando alla cronologia dei comandi («event not found»).
- Le chiavi di `dev` e `lab-01` il server le legge già con i permessi segreto per segreto di oggi: la condizione «lettura» non le deve coprire.
- **Ritorno indietro:** per ciascuno dei tre, `gcloud projects remove-iam-policy-binding` con lo stesso `--member`, lo stesso `--role` e `--all`.

**C1.3 La VM: lettura dei segreti dei prefissi dello staging** (proposta §7 punto 2: oggi `langbrain-vm@` legge solo i quattro segreti di oggi, uno per uno; senza questo il primo motore si ferma con «segreto illeggibile»).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
N=projects/444239063209/secrets
VM="resource.name.startsWith(\"$N/langbrain-api-key-lab-\") || resource.name.startsWith(\"$N/langbrain-api-key-test-\") || resource.name.startsWith(\"$N/langbrain-shelly-lab-\") || resource.name.startsWith(\"$N/langbrain-shelly-test-\")"
gcloud projects add-iam-policy-binding domotica-poc-511707 --account=m.scardovellicrac@gmail.com --member=serviceAccount:langbrain-vm@domotica-poc-511707.iam.gserviceaccount.com --role=roles/secretmanager.secretAccessor --condition="expression=$VM,title=a2-vm-staging" --format='value(etag)'
```

- **Atteso:** una riga con un `etag`.
- **Ritorno indietro:** `gcloud projects remove-iam-policy-binding` con lo stesso `--member`, `--role=roles/secretmanager.secretAccessor` e `--condition="expression=$VM,title=a2-vm-staging"`.

**C1.4 Controllo** (sola lettura).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud projects get-iam-policy domotica-poc-511707 --account=m.scardovellicrac@gmail.com --flatten="bindings[].members" --filter="bindings.role~secretmanager OR bindings.role~dhA2" --format="table[no-heading](bindings.role,bindings.members,bindings.condition.title)"
```

- **Atteso:** esattamente quattro righe, ciascuna con il suo titolo: `dhA2CreaSegreti` e `dhA2VersioniSegreti` a `domotica-bff-staging@` (`a2-creazione-staging`, `a2-versioni-staging`), `secretAccessor` a `domotica-bff-staging@` (`a2-lettura-staging`) e a `langbrain-vm@` (`a2-vm-staging`). Nessuna riga senza titolo: un permesso senza condizione aprirebbe tutti i segreti.
- I permessi nuovi di IAM possono metterci qualche minuto ad arrivare: C9 lo tiene in conto.

**C1.4a Lo strumento di verifica acceso** (aggiunto il 20 novembre durante l'installazione: senza, C1.4b risponde `SERVICE_DISABLED`, «Policy Troubleshooter API has not been used in project»). Scrive su Google Cloud ma accende solo uno strumento di lettura, gratuito.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud services enable policytroubleshooter.googleapis.com --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** «Operation … finished successfully» (o niente, se era già acceso).
- **Ritorno indietro:** lo stesso comando con `disable`.
- Il 20 novembre l'esito di C1.4b si è letto meglio con `--format=json`: per ogni permesso con condizione, `conditionExplanation.value` (`True`/`False`) e `allowAccessState`; in cima `overallAccessState` (`CAN_ACCESS` / `CANNOT_ACCESS`).

**C1.4b Le esclusioni, provate** (revisione del codice, punto 9, e seconda lettura; sola lettura: lo strumento di Google che spiega se un permesso è concesso, senza toccare niente). Le condizioni guardano il nome del segreto: lo strumento lo deve ricevere (`--resource-name`, `--resource-service`, `--resource-type`), altrimenti non le sa valutare.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for c in "domotica-bff-staging secretmanager.versions.add langbrain-shelly-lab-01" "domotica-bff-staging secretmanager.versions.add langbrain-shelly-test-x" "langbrain-vm secretmanager.versions.access domhouse-agent-ordini-staging"; do set -- $c; echo "== $1 $2 $3"; gcloud policy-intelligence troubleshoot-policy iam "//secretmanager.googleapis.com/projects/444239063209/secrets/$3" --principal-email="$1@domotica-poc-511707.iam.gserviceaccount.com" --permission="$2" --resource-name="projects/444239063209/secrets/$3" --resource-service=secretmanager.googleapis.com --resource-type=secretmanager.googleapis.com/Secret --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com 2>&1 | grep -iE "access|state|condition|unknown" | head -4; done
```

- **Atteso**, nell'ordine:
  1. il server su `langbrain-shelly-lab-01`: **negato** (escluso per nome);
  2. il server su `langbrain-shelly-test-x`: **concesso** (anche se il segreto non esiste: si valuta la condizione sul nome);
  3. la VM su `domhouse-agent-ordini-staging`: **negato** (la chiave delle firme non è nei suoi prefissi).
- La parola esatta dipende dalla versione di `gcloud` (per esempio `CAN_ACCESS` / `CANNOT_ACCESS`, o `GRANTED` / `NOT_GRANTED`): incolla l'uscita, la legge la memoria storica.
- **Fermati** davanti a un esito diverso dall'atteso **o** a un esito condizionale sconosciuto (`UNKNOWN_CONDITIONAL`, «unknown» accanto a una condizione): vuol dire che lo strumento non ha valutato la condizione, quindi la prova non vale. Non si va a C2 finché la memoria storica non lo ha guardato con o1.

**C1.5 Le etichette del repository del motore non si spostano più** (proposta §4.3 punto 4, revisione punto 6).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud artifacts repositories update domotica --location=europe-west8 --immutable-tags --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format="value(dockerConfig.immutableTags)"
```

- **Atteso:** `True`.
- Un rilancio di una pubblicazione sullo stesso commit resta possibile: `publish.sh` (server) e `deploy-engine.sh` (motore) non ricostruiscono un'immagine che esiste già, quindi non rispingono la stessa etichetta. Si fermerebbe solo `deploy.sh` lanciato da solo su un commit già costruito: si usa sempre `publish.sh` o `publish-all.sh`.
- **Ritorno indietro:** lo stesso comando con `--no-immutable-tags`.

## C2. I file sulla VM (nella cartella di chi si collega)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='mkdir -p ~/a2/agent' < /dev/null
gcloud compute scp scripts/agent-vm.sh scripts/engine-vm.sh scripts/broker-vm.sh scripts/broker_accounts.py engine/compose.catalog.yaml langbrain-dev:a2/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute scp scripts/agent/comune.py scripts/agent/lettore.py scripts/agent/esecutore.py scripts/agent/domhouse-agent-esecutore.service scripts/agent/domhouse-agent-lettore.service langbrain-dev:a2/agent/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='cd ~/a2 && sed -i "s/\r*$//" *.sh *.py *.yaml agent/*.py agent/*.service && sha256sum *.sh *.py *.yaml agent/* | cut -c1-16,65-' < /dev/null
```

- **Atteso:** dieci file, poi dieci impronte che cominciano così (calcolate da o1 su `bd4a8bf`, senza i ritorni a capo):

| File | Impronta |
|---|---|
| `agent-vm.sh` | `b013386278381469` |
| `broker-vm.sh` | `6a853a834686660b` |
| `broker_accounts.py` | `8eaec49d1866ac0a` |
| `compose.catalog.yaml` | `ba1ecece9b543add` |
| `engine-vm.sh` | `057406a726a30a4a` |
| `agent/comune.py` | `a576ed9ab186d810` |
| `agent/domhouse-agent-esecutore.service` | `d17f567cf8cfaca2` |
| `agent/domhouse-agent-lettore.service` | `9824996a467272be` |
| `agent/esecutore.py` | `f7e3f2948d96e401` |
| `agent/lettore.py` | `69511594f1e8aa35` |

- Una diversa: fermati.

## C3. `engine-vm.sh` e il compose del catalogo; `ENV` su `dev` e `lab-01` (scrive sulla VM; nessun motore si riavvia)

Copia di prima in `/opt/domhouse/prima-a2`. `engine-vm.sh` nuovo va bene anche con l'agente e i timer di oggi (registro, risposta di o1 su `a8f628b`). `broker-vm.sh` nuovo resta da parte, con un altro nome, per C4 (regola 5).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; B=/opt/domhouse/prima-a2; if ! sudo test -e $B/engine-vm.sh; then sudo mkdir -p $B; sudo cp -p /opt/domhouse/engine-vm.sh /opt/domhouse/broker-vm.sh /opt/domhouse/broker_accounts.py $B/; echo "copia di prima fatta"; fi; sudo install -m 755 ~/a2/engine-vm.sh /opt/domhouse/engine-vm.sh; sudo install -m 644 ~/a2/compose.catalog.yaml /opt/domhouse/compose.catalog.yaml; sudo install -m 755 ~/a2/broker-vm.sh /opt/domhouse/broker-vm.sh.a2; sudo bash /opt/domhouse/engine-vm.sh timers > /dev/null && echo timer-ok; for a in dev lab-01; do sudo bash /opt/domhouse/engine-vm.sh env $a staging | grep "^ENV="; done' < /dev/null
```

- **Atteso:** «copia di prima fatta» (a un rilancio niente), «timer-ok», due righe `ENV=staging`.
- `ENV` sta solo nelle impostazioni (`/opt/domhouse/<apt>.settings`): `dev` e `lab-01` non si riavviano.
- **Ritorno indietro:** `sudo install -m 755 /opt/domhouse/prima-a2/engine-vm.sh /opt/domhouse/engine-vm.sh && sudo bash /opt/domhouse/engine-vm.sh timers; sudo rm -f /opt/domhouse/compose.catalog.yaml /opt/domhouse/broker-vm.sh.a2`. La riga `ENV` può restare: l'`engine-vm.sh` di prima la ignora.

## C4. La prova dell'unità allargata e dell'ambiente dei comandi, prima di installarla (sola lettura, salvo file di prova tolti subito)

Le stesse restrizioni dell'unità nuova (`ReadWritePaths=/opt/domhouse /etc/domhouse /data`, i `ReadOnlyPaths` dentro di loro, `CapabilityBoundingSet=CAP_CHOWN CAP_DAC_OVERRIDE`, `MemoryMax=512M`; nei `-p` di `systemd-run` un'impostazione ripetuta si somma) e lo stesso ambiente che l'esecutore dà agli script (`PATH`, `DOCKER_CONFIG`, `DOMHOUSE_LOCK_HELD=1`).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='P="-p User=root -p Group=domhouse-agent -p SupplementaryGroups=domhouse-broker -p NoNewPrivileges=yes -p ProtectSystem=strict -p ProtectHome=yes -p PrivateTmp=yes -p ReadWritePaths=/opt/domhouse -p ReadWritePaths=/etc/domhouse -p ReadWritePaths=/data -p ReadOnlyPaths=/opt/domhouse/agent -p ReadOnlyPaths=/opt/domhouse/engine-vm.sh -p ReadOnlyPaths=/opt/domhouse/broker-vm.sh -p ReadOnlyPaths=/opt/domhouse/broker_accounts.py -p ReadOnlyPaths=-/opt/domhouse/compose.yaml -p ReadOnlyPaths=-/opt/domhouse/compose.catalog.yaml -p ReadOnlyPaths=-/opt/domhouse/compose.broker.yaml -p ReadOnlyPaths=-/opt/domhouse/_broker -p ReadOnlyPaths=/etc/domhouse/agent.conf -p ReadOnlyPaths=-/etc/domhouse/agent-ordini.key -p ReadOnlyPaths=-/etc/domhouse/agent-risultati.key -p ReadOnlyPaths=-/etc/domhouse/agent-immagine-staging -p ReadOnlyPaths=-/etc/domhouse/agent-immagine-prod -p ReadOnlyPaths=-/data/_broker -p CapabilityBoundingSet=CAP_CHOWN -p CapabilityBoundingSet=CAP_DAC_OVERRIDE -p RestrictAddressFamilies=AF_UNIX -p RestrictAddressFamilies=AF_INET -p MemoryMax=512M -p UMask=0077"; E="-E PATH=/usr/sbin:/usr/bin:/sbin:/bin -E DOCKER_CONFIG=/var/lib/domhouse-executor/docker -E DOMHOUSE_LOCK_HELD=1"; sudo systemd-run --quiet --pipe --wait $P /bin/sh -c "id; for d in /opt/domhouse /etc/domhouse /data; do touch \$d/.prova-a2 && rm -f \$d/.prova-a2 && echo scrittura-ok \$d; done; mkdir /data/.prova-a2 && chown 10001:10001 /data/.prova-a2 && chmod 750 /data/.prova-a2 && touch /data/.prova-a2/x && rm -rf /data/.prova-a2 && echo dati-10001-ok; for f in /opt/domhouse/engine-vm.sh /etc/domhouse/agent.conf /opt/domhouse/agent/esecutore.py; do touch \$f 2>/dev/null && echo SCRIVIBILE \$f || echo sola-lettura-ok \$f; done; head -1 /proc/net/tcp > /dev/null && head -1 /proc/net/tcp6 > /dev/null && echo proc-net-ok; echo porta-8100-in-ascolto: \$(cat /proc/net/tcp /proc/net/tcp6 | grep -cE \":1FA4 [0-9A-F]+:[0-9A-F]+ 0A \")"; sudo systemd-run --quiet --pipe --wait $E $P /bin/sh -c "docker compose version && docker login --help > /dev/null && echo docker-login-ok"; sudo systemd-run --quiet --pipe --wait $E $P /bin/bash /opt/domhouse/engine-vm.sh status dev | tail -1; sudo systemd-run --quiet --pipe --wait $E $P /bin/bash /opt/domhouse/broker-vm.sh.a2 sync | tail -1' < /dev/null
```

- **Atteso:**
  1. `uid=0(root) gid=…(domhouse-agent) groups=…(domhouse-agent),1883(domhouse-broker)`;
  2. tre «scrittura-ok» (`/opt/domhouse`, `/etc/domhouse`, `/data`);
  3. «dati-10001-ok»: una cartella data a 10001 e svuotata da root, quindi `CAP_CHOWN` e `CAP_DAC_OVERRIDE` funzionano (N3);
  4. tre «sola-lettura-ok» (lo script, la configurazione e il codice dell'agente restano in sola lettura; revisione, punto 2). Un «SCRIVIBILE»: fermati;
  5. «proc-net-ok» e «porta-8100-in-ascolto: 1» (o più): la porta di `dev`, pubblicata da Docker, si vede in `/proc/net/tcp*`. Con **0** Docker non usa il suo proxy: allora il controllo della porta libera resta solo sulle impostazioni dei motori (revisione, «da verificare» 2), e lo si scrive nel registro;
  6. la versione di `docker compose` e «docker-login-ok»: il client e il suo `login` partono sotto le restrizioni e con 512 MB (revisione, punto 8);
  7. da `status dev` la riga «health 200: …»: `docker` dal socket, il token della VM e il motore sull'indirizzo interno, sotto le restrizioni;
  8. dal `sync` del `broker-vm.sh` nuovo «unchanged», con il blocco lasciato all'esecutore (`DOMHOUSE_LOCK_HELD=1`).
- **Da verificare** (non provabile sul PC; proposta §4.2, «da verificare» dell'unità): tutto in questo blocco. Non si prova qui un'installazione vera: la fa C9 con l'app.
- Un «Permission denied», un errore o un processo fermato per memoria: **fermati** e incolla; non si installa (si decide con o1 cosa aprire).

## C5. L'immagine approvata dell'agente (scrive sulla VM)

L'immagine su cui gira `dev` oggi, per digest: quella del registro **e** quella del contenitore devono coincidere (revisione del codice, punto 6). Da qui in poi la riscrive `publish-all.sh` a ogni pubblicazione (passo 3b), con lo stesso controllo.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
I="$(gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo sed -n "s/^ENGINE_IMAGE=//p" /opt/domhouse/dev.settings' < /dev/null 2>/dev/null | tr -d '\r' | tail -1)"; D="$(gcloud artifacts docker images describe "$I" --format='value(image_summary.digest)' --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com | tr -d '\r')"; R="$(gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker image inspect -f "{{join .RepoDigests \" \"}}" "$(sudo docker inspect -f "{{.Image}}" engine-dev)"' < /dev/null 2>/dev/null | tr -d '\r' | tail -1)"; echo "$I"; echo "$D"; echo "$R"; A="${I%:*}@$D"; if [[ "$I" =~ ^europe-west8-docker\.pkg\.dev/domotica-poc-511707/domotica/engine:[0-9a-f]{7,40}$ && "$D" =~ ^sha256:[0-9a-f]{64}$ && " $R " == *" $A "* ]]; then gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="echo '$A' | sudo tee /etc/domhouse/agent-immagine-staging.nuovo > /dev/null && sudo chmod 644 /etc/domhouse/agent-immagine-staging.nuovo && sudo mv -f /etc/domhouse/agent-immagine-staging.nuovo /etc/domhouse/agent-immagine-staging && sudo ls -l /etc/domhouse/agent-immagine-staging && sudo cat /etc/domhouse/agent-immagine-staging" < /dev/null; else echo "immagine o digest non letti, o il motore non gira su quel digest: fermati"; fi
```

- **Atteso:** l'immagine di `dev` (`…/engine:<commit>`), il suo digest (`sha256:` e 64 cifre), i `RepoDigests` del contenitore (fra loro `…/engine@` e lo stesso digest), poi il file `-rw-r--r-- root root` con una riga `…/engine@sha256:…`.
- **Ritorno indietro:** `sudo rm -f /etc/domhouse/agent-immagine-staging` (senza il file, `crea_motore` rifiuta «immagine non approvata»).
- Il file c'è **prima** di C6: l'esecutore nuovo, all'avvio, lo trova e lo tiene in sola lettura (seconda lettura della revisione, N2).

## C6. L'agente nuovo e `broker-vm.sh` nuovo, insieme (scrive sulla VM; il broker non si riavvia)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; sudo install -m 755 ~/a2/broker-vm.sh /opt/domhouse/broker-vm.sh; sudo install -m 644 ~/a2/broker_accounts.py /opt/domhouse/broker_accounts.py; sudo rm -f /opt/domhouse/broker-vm.sh.a2; sudo AMBIENTE=staging SOTTOSCRIZIONE=projects/domotica-poc-511707/subscriptions/domhouse-staging-ordini-vm RISULTATI=projects/domotica-poc-511707/topics/domhouse-staging-risultati bash ~/a2/agent-vm.sh install; sudo bash ~/a2/agent-vm.sh status | head -2; grep -E "^(ReadWritePaths|ReadOnlyPaths|CapabilityBoundingSet|SupplementaryGroups|MemoryMax)" /etc/systemd/system/domhouse-agent-esecutore.service; sudo bash /opt/domhouse/broker-vm.sh sync | tail -2' < /dev/null
```

- **Atteso:**
  1. «esiste già» per il gruppo `domhouse-broker`, «agente installato: ambiente staging», i due servizi `active`;
  2. `ReadWritePaths=/opt/domhouse /etc/domhouse /data`, la riga `ReadOnlyPaths=` di C4, `CapabilityBoundingSet=CAP_CHOWN CAP_DAC_OVERRIDE`, `SupplementaryGroups=domhouse-broker`, `MemoryMax=512M`;
  3. dal `sync` «lab-01: connector e 3 dispositivi» (ora conta anche le impronte del file, `72090ae`) e «unchanged».
- **Ritorno indietro:**
  1. `sudo install -m 755 /opt/domhouse/prima-a2/broker-vm.sh /opt/domhouse/broker-vm.sh; sudo install -m 644 /opt/domhouse/prima-a2/broker_accounts.py /opt/domhouse/broker_accounts.py`;
  2. l'agente di A3: lo stesso comando `install` da `~/a3` (Q2.4 di A3).
  - L'agente di A3 rifiuta `crea_motore` («non disponibile»): dopo C7 il server lo direbbe come creazione rimasta a metà.

## C7. Il server e il sito dello staging (il committente pubblica)

Le rotte della creazione (pezzo 2) e le pagine di o2. Nessuna variabile nuova nel manifesto: il server usa Secret Manager con la sua identità, e `INSTANCE_ALLOWED` dello staging copre già 8150–8169. Il sito prende tutte le modifiche del sito fino a HEAD.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git fetch -q origin && git merge-base --is-ancestor HEAD origin/main && git log --oneline -1 && while IFS='=' read -r k v; do v="${v%$'\r'}"; case "$k" in ''|'#'*) ;; *) export "$k=$v" ;; esac; done < scripts/publish-settings.conf && TARGET=staging bash scripts/publish.sh "$(git rev-parse --short HEAD)"
```

- **Atteso:** la riga del commit, poi la pubblicazione dello staging riuscita, con la revisione nuova al 100 %, e «PWA: https://domhouse-staging.web.app».
- **Dopo:** nell'app dello staging **ricarica la pagina** (una scheda aperta tiene il sito di prima).
- **Ritorno indietro:** `gcloud run services update-traffic domotica-bff-staging --to-revisions=<la revisione di prima>=100 --region=europe-west8 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com`; la revisione di prima la dice l'uscita di `publish.sh`.

## C8. «Prova l'agente» (scrive: un ordine «stato»)

Nell'app dello staging, pagina della piattaforma → «Prova l'agente» su `lab-01`.

- **Atteso:** esito **riuscito**, come in Q5 di A3 (l'agente nuovo firma come quello di A3).
- **Altro esito** o «in attesa» oltre un minuto: incolla le ultime righe di `sudo journalctl -u domhouse-agent-lettore -u domhouse-agent-esecutore -n 30 --no-pager`.

## C9. Le prove vere con l'app (scrive: segreti, ordini, un motore)

**C9.1 Una creazione che si ferma, poi «Annulla»** (il percorso di `togli_motore` senza installare niente). Una porta occupata a mano fa rifiutare `crea_motore` al passo 0. **Almeno cinque minuti dopo C1** (il ritardo di IAM; revisione, «da verificare» 3).

1. Sulla VM, un ascoltatore sulla porta 8150 (dura 15 minuti, poi si chiude da solo):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo systemd-run --unit=prova-a2-porta --property=RuntimeMaxSec=900 /usr/bin/python3 -m http.server 8150 --bind 127.0.0.1 && sleep 2 && sudo ss -ltn | grep ":8150 "' < /dev/null
```

2. Nell'app: Organizzazioni → un'organizzazione di prova → Appartamenti → «Nuovo appartamento», id `test-a2-01`, nome «Prova A2 uno».
3. **Atteso:** «In preparazione», poi entro un paio di minuti «Creazione rimasta a metà» con «La porta scelta è occupata sulla macchina virtuale».
4. «Annulla creazione», con la conferma. **Atteso:** «Annullamento in corso», poi la riga sparisce con «Creazione di Prova A2 uno annullata».
5. Controllo (sola lettura) e fine dell'ascoltatore:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
for s in langbrain-api-key-test-a2-01 langbrain-shelly-test-a2-01; do echo "== $s"; gcloud secrets versions list "$s" --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --format="table[no-heading](name,state,scheduledDestroyTime)"; done
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo systemctl stop prova-a2-porta 2>/dev/null; sudo ls /opt/domhouse/*.settings; sudo ls /var/lib/domhouse-executor/creati 2>/dev/null; sudo cat /var/lib/domhouse-executor/seq/test-a2-01' < /dev/null
```

- **Atteso:** per ciascun segreto una versione `DISABLED` con una `scheduledDestroyTime` fra 7 giorni (distruzione con ritardo); sulla VM ancora solo `dev.settings` e `lab-01.settings`, nessun segno in `creati`, e la lapide della `seq` di `test-a2-01` (il numero dell'ultimo ordine).
- **«I permessi sulle chiavi non sono ancora attivi»** (`segreto_illeggibile`) o «Le chiavi non sono state create»: IAM non è ancora arrivato (C1). Aspetta cinque minuti, poi «Annulla» o «Riprova».

**C9.2 Una creazione fino a «Pronto»** (il percorso intero: segreti, capienza, motore, broker, collegamento).

1. Nell'app: «Nuovo appartamento», id `test-a2-02`, nome «Prova A2 due».
2. **Atteso:** «In preparazione» con i passi che avanzano, poi entro qualche minuto «Pronto» (il primo `pull` dell'immagine può allungare).
3. Controllo sulla VM (sola lettura):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo cat /opt/domhouse/test-a2-02.settings; sudo cat /var/lib/domhouse-executor/creati/test-a2-02; echo; sudo cat /etc/domhouse/test-a2-02.catalog.yaml; sudo grep -x test-a2-02 /etc/domhouse/_broker/apartments; sudo docker inspect -f "{{.Config.Image}} {{.State.Health.Status}}" engine-test-a2-02; sudo ls -ln /data/test-a2-02; sudo ls -l /etc/domhouse/_broker/devices/test-a2-02; sudo journalctl -u domhouse-agent-esecutore --since "-30 min" --no-pager | grep -ic -E "oom|out of memory|killed"' < /dev/null
```

- **Atteso:**
  1. le impostazioni con `PORT=8150`, `CONNECTOR=shelly`, `ENGINE_IMAGE=…/engine@sha256:…` (quella di C5) ed `ENV=staging`;
  2. il segno di creazione con porta, immagine ed `env`;
  3. il catalogo vuoto (`rooms: []`, `devices: []`);
  4. `test-a2-02` nell'elenco del broker;
  5. il contenitore con l'immagine per digest e `healthy`;
  6. `/data/test-a2-02` di `10001 10001`;
  7. il file dei dispositivi di `test-a2-02`, vuoto (`-rw------- … 0`): il broker non cerca mai un segreto vecchio per lui (revisione, «da verificare» 4);
  8. **0** righe con «oom», «out of memory» o «killed» nel giornale dell'esecutore (revisione, punto 8). Più di 0: incolla le righe.
- **Altro stato:** incolla il messaggio della riga «Cosa è successo» con l'ID richiesta e le ultime righe del giornale dell'esecutore (`sudo journalctl -u domhouse-agent-esecutore -n 30 --no-pager`).

**C9.3 Dopo:** `test-a2-02` resta un motore dello staging (tre su quattro, con `dev` e `lab-01`). «Annulla» non c'è più dopo «Pronto» (risposta 1165): l'eliminazione vera è di A6. Se il committente lo vuole togliere prima, la memoria storica prepara i comandi a mano (`engine-vm.sh remove`, `broker-vm.sh remove-apartment`, il segno, i segreti, il documento in Firestore).

## Dopo l'installazione: quando si sostituisce un file protetto

L'unità tiene in sola lettura per l'esecutore `agent.conf`, le due chiavi, l'immagine approvata, gli script e i compose. Un file **sostituito** sull'host dopo l'avvio dell'esecutore non è più coperto finché l'esecutore non riparte (seconda lettura della revisione, N1). Per questo:

1. `publish-all.sh` riavvia l'esecutore, sotto il blocco della VM, dopo ogni file che sostituisce sulla VM;
2. chi sostituisce a mano una chiave o `agent.conf` lancia subito dopo, sulla VM: `sudo flock -w 300 /opt/domhouse/.engines.lock systemctl restart domhouse-agent-esecutore`;
3. finché non riparte, l'esecutore rifiuta gli ordini che cambiano la VM («fallito», con l'allarme `protezione_persa` nel giornale): nessun danno, solo «Riprova» dopo il riavvio.

## Da verificare sulla VM (revisione del codice, 20 novembre)

| N. | Che cosa | Dove si vede |
|---|---|---|
| 1 | `docker login`, `compose pull` e `up` sotto le restrizioni dell'unità (512 MB) e i permessi dei file con `UMask=0077` | C4 (punto 6), C9.2 (punti 1, 5, 8) |
| 2 | `/proc/net/tcp*` vede le porte pubblicate da Docker | C4 (punto 5) |
| 3 | il ritardo di IAM dopo C1 | C9.1 (almeno cinque minuti dopo) |
| 4 | `add-apartment` di un appartamento nuovo crea il file dei dispositivi vuoto | C9.2 (punto 7) |
| 5 | i `ReadOnlyPaths` vincono sui `ReadWritePaths` più larghi | C4 (punto 4), C6 (punto 2) |
| 6 | dopo C6 nessun `protezione_persa` nel giornale dell'esecutore (i file protetti c'erano tutti all'avvio) | C9.2: `sudo journalctl -u domhouse-agent-esecutore --no-pager \| grep -c protezione_persa` deve dire 0 |

## Decisioni per il committente (non di o1)

1. **`test-a2-02` dopo la prova** (C9.3): resta come appartamento di laboratorio fino ad A6, oppure si toglie a mano.
2. **Due scelte di o1 nel codice del server**, da confermare o cambiare:
   - un segreto con il nome giusto ma non nostro (`secret_conflict`) lascia l'appartamento «rimasto a metà» (con «Riprova» e «Annulla») e la creazione conta nel limite delle 5 l'ora;
   - una porta che la VM dice occupata (`porta_occupata`) resta segnata come tale finché qualcuno non la libera a mano: «Riprova» non la riprende mai.

## Da incollare alla memoria storica

Le uscite di tutti i blocchi, comprese le impronte di C2, l'esito di C4 e gli stati visti in C9.
