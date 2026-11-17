# Passo 3 sulla VM: le correzioni del controllo di sicurezza (17 novembre)

| Stato | Preparata | Codice | Quando | Chi lancia | Comandi |
|---|---|---|---|---|---|
| **Pronta, da rileggere.** Nessun passo provato sul vero | o1, 17 novembre 2026 | `b722e1e`, `1f0db35`, `9ace3fd`, `929d948` | **dopo la fine della sessione dei due Shelly** (D-213); fra l'inizio e la fine di quella sessione niente sulla VM. Il giorno e l'ora li decide il committente | il committente, un blocco alla volta, in Git Bash, con la memoria storica in chat | 13 blocchi (P0–P12) |

## Prima di cominciare: il fermo e le mail

**Fermo previsto: in tutto 5–10 minuti di motori non raggiungibili, in tre momenti.**

| Passo | Cosa si ferma | Quanto |
|---|---|---|
| P3 | il broker, ricreato sulla sua rete nuova: Plug, Shelly e connector di `lab-01` si scollegano e si ricollegano da soli | meno di 1 minuto |
| P10 | l'aggiornamento di `docker-ce` riavvia Docker: con live-restore spento si fermano e ripartono tutti i container | 1–2 minuti |
| P10 | il riavvio della VM, fino a `/health` 200 dei due motori | 2–4 minuti |

- **La produzione usa il motore `dev`:** in quei minuti l'app di produzione e quella dello staging dicono «collegamento ai dispositivi non disponibile». Nessun dato si perde: i motori ripartono dal loro database.
- **Mail degli allarmi:** «motore giù», «VM muta» e «broker giù» possono mandare una mail durante il fermo. È atteso: la memoria storica avvisa il committente prima della finestra.

**Cosa si corregge** (esito: `controllo-vm-17nov/ESITO-CONTROLLO-SICUREZZA-VM.md`):

| Voce | Che cosa | Commit | Passo |
|---|---|---|---|
| C2 | niente collegamenti nuovi in uscita dal broker; la sua rete su `172.30.84.0/24` | `b722e1e` | P3 |
| C5 | `tls_version tlsv1.2` scritto | `b722e1e` | P3 |
| C8 | la prova oraria dei metadati da tutte le reti, broker compreso | `1f0db35` | P4 |
| sysctl, H5, H6 | `kptr_restrict` e `ptrace_scope` a 1, `LLMNR=no`, sshd senza inoltri e con 3 tentativi | `929d948` | P5 |
| H2 | la cartella dell'utente OS Login: file vecchi via, cartella a 700 | — | P7 |
| H3/C7 | l'utente vecchio `m_scardovellicrac`: fuori da docker e adm, bloccato | — | P8 |
| H7 | le immagini vecchie del motore (tenute quelle in uso e le due precedenti) | `9ace3fd` | P9 |
| H1, pacchetti | gli 11 pacchetti di Docker e Google, poi il riavvio | — | P10 |

**Regole:**

1. Un blocco alla volta; **incolla alla memoria storica l'uscita di ogni blocco.**
2. **Se un'uscita non torna, fermati.**
3. Ogni passo che scrive ha accanto il ritorno indietro.
4. Un comando che finisce con `grep` e non trova righe esce con 1, e gcloud lo mostra come un guasto del collegamento («plink.exe exited with return code [1]»): per questo i blocchi che finiscono con `grep` hanno `; true` in fondo. Conta solo il testo.
5. **Dopo questa procedura, `publish-all.sh` solo con un commit che contiene `929d948`:** con uno più vecchio rimetterebbe sulla VM l'`engine-vm.sh` di prima.

## P0. Controlli prima (sola lettura)

**P0.1 Sul PC: i file da portare sono quelli dei commit.**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git log --oneline -1 929d948 && git merge-base --is-ancestor 929d948 HEAD && git diff --quiet 929d948 -- scripts/engine-vm.sh scripts/broker-vm.sh scripts/host-vm.sh engine/broker/compose.yaml engine/broker/mosquitto.conf && echo "file uguali a 929d948"
```

- **Atteso:** la riga di `929d948` e «file uguali a 929d948». Se manca la seconda riga, fermati.

**P0.2 Sulla VM: lo stato di partenza.**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='uname -r; ls /var/run/reboot-required; grep domhouse-tls /etc/fstab; findmnt -n -o TARGET,OPTIONS /mnt/domhouse-tls; sudo docker network inspect -f "{{range .IPAM.Config}}{{.Subnet}}{{end}}" domhouse-broker_default; sudo nft list tables; dpkg-query -W containerd.io docker-buildx-plugin docker-ce-cli docker-ce-rootless-extras docker-ce docker-compose-plugin google-cloud-cli google-cloud-ops-agent google-compute-engine google-guest-agent google-osconfig-agent; echo "aggiornabili: $(apt list --upgradable 2>/dev/null | grep -c upgradable)"; echo "immagini del motore: $(sudo docker images --format "{{.Repository}}" | grep -c domotica/engine)"; true'
```

| Riga | Atteso |
|---|---|
| `uname -r` | `6.1.0-54-cloud-amd64`, poi `/var/run/reboot-required` |
| fstab | la riga di `/mnt/domhouse-tls` **con `nofail`** (la scrive `broker-vm.sh prepare-tls-disk`). **Se manca `nofail`, fermati:** il riavvio di P10 si bloccherebbe senza quel disco |
| `findmnt` | `/mnt/domhouse-tls` con `nosuid,nodev,noexec` |
| rete del broker | `172.19.0.0/16` (la sceglie Docker; P3 la porta a `172.30.84.0/24`) |
| `nft list tables` | fra le altre `inet domhouse_broker` e `inet domhouse_metadata` |
| `dpkg-query` | undici righe pacchetto–versione: **sono le versioni per tornare indietro in P10** |
| aggiornabili, immagini | circa 11 e circa 20 |

**P0.3 La prova rossa di C2: oggi il broker può aprire collegamenti in uscita.**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker exec domhouse-broker wget -q -T 5 -O /dev/null http://10.198.0.2:8100/api/v1/health; echo "dal broker verso il motore dev: uscita $?"'
```

- **Atteso:** «uscita 0»: il broker raggiunge il motore `dev`. È la prova rossa: dopo P3 deve diventare un numero diverso da 0.
- **Da verificare:** che l'immagine del broker abbia `wget` (Mosquitto su Alpine, con busybox). Se risponde «not found», incollalo: la prova di P3 si fa in un altro modo.

## P1. Copiare i file sulla VM (scrive solo nella cartella di chi si collega)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command="mkdir -p ~/passo3/broker"
gcloud compute scp scripts/engine-vm.sh scripts/broker-vm.sh scripts/host-vm.sh langbrain-dev:passo3/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
gcloud compute scp engine/broker/compose.yaml engine/broker/mosquitto.conf langbrain-dev:passo3/broker/ --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** cinque file copiati, tutti al 100 %.

## P2. Installare gli script e i file del broker (scrive sulla VM; nessun container si riavvia)

Tiene una copia dei file di prima in `/opt/domhouse/prima-passo3` e toglie i ritorni a capo di Windows.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; B=/opt/domhouse/prima-passo3; sudo mkdir -p $B; sudo cp -p /opt/domhouse/engine-vm.sh /opt/domhouse/broker-vm.sh $B/; sudo cp -p /opt/domhouse/_broker/compose.yaml $B/broker-compose.yaml; sudo cp -p /opt/domhouse/_broker/mosquitto.conf $B/mosquitto.conf; cd ~/passo3; sed -i "s/\r*$//" engine-vm.sh broker-vm.sh host-vm.sh broker/compose.yaml broker/mosquitto.conf; sudo install -m 755 engine-vm.sh /opt/domhouse/engine-vm.sh; sudo install -m 755 broker-vm.sh /opt/domhouse/broker-vm.sh; sudo install -m 644 broker/compose.yaml /opt/domhouse/_broker/compose.yaml; sudo install -m 644 broker/mosquitto.conf /opt/domhouse/_broker/mosquitto.conf; sha256sum /opt/domhouse/engine-vm.sh /opt/domhouse/broker-vm.sh /opt/domhouse/_broker/compose.yaml /opt/domhouse/_broker/mosquitto.conf; sudo ls -l $B'
```

- **Atteso:** quattro impronte e i quattro file di prima in `/opt/domhouse/prima-passo3`.
- Il broker gira ancora con la configurazione di prima: la nuova vale da P3.
- **Ritorno indietro:**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; B=/opt/domhouse/prima-passo3; sudo install -m 755 $B/engine-vm.sh /opt/domhouse/engine-vm.sh; sudo install -m 755 $B/broker-vm.sh /opt/domhouse/broker-vm.sh; sudo install -m 644 $B/broker-compose.yaml /opt/domhouse/_broker/compose.yaml; sudo install -m 644 $B/mosquitto.conf /opt/domhouse/_broker/mosquitto.conf; echo "file di prima rimessi"'
```

## P3. Il broker: la rete nuova, l'uscita chiusa, TLS 1.2 (scrive sulla VM; il broker si ferma meno di un minuto)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; sudo bash /opt/domhouse/broker-vm.sh limit; sudo bash /opt/domhouse/broker-vm.sh network; sudo docker network inspect -f "{{range .IPAM.Config}}{{.Subnet}}{{end}}" domhouse-broker_default; echo "tls_version nel broker: $(sudo docker exec domhouse-broker grep -c "^tls_version tlsv1.2$" /mosquitto/config/mosquitto.conf || true)"'
```

- **Atteso:**
  1. «limite attivo: …» e «uscita chiusa: nessun collegamento nuovo parte dalla rete del broker (172.30.84.0/24)»;
  2. «rete domhouse-broker_default: 172.19.0.0/16 -> 172.30.84.0/24; il broker si ferma un momento …», poi «broker sano: healthy, porta TLS 8883 risponde»;
  3. `172.30.84.0/24`;
  4. «tls_version nel broker: 1»: il broker legge la configurazione nuova.
- Con `set -e` un `grep` vuoto fermerebbe il blocco prima di `; true`: per questo qui e in P8 il `grep` ha `|| true` (regola 4).

**P3.1 Controllo, dopo un minuto (sola lettura).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker exec domhouse-broker wget -q -T 5 -O /dev/null http://10.198.0.2:8100/api/v1/health; echo "dal broker verso il motore dev: uscita $?"; sudo docker exec domhouse-broker wget -q -T 5 -O /dev/null http://example.com; echo "dal broker verso internet: uscita $?"; sudo bash /opt/domhouse/broker-vm.sh status | grep -E "scartati|connessioni|^broker"; for p in 8100 8169; do curl -s -m 5 http://10.198.0.2:$p/api/v1/health | python3 -c "import json,sys; h=json.load(sys.stdin); print(h[\"apartment_id\"], h[\"status\"], h[\"connector\"][\"status\"])"; done; true'
```

- **Atteso:**
  1. le due uscite **diverse da 0** (il collegamento nuovo è scartato: è la prova verde di C2);
  2. «collegamenti in uscita dal broker scartati: 2» o più; «collegamenti scartati dal limite: …» come prima;
  3. «connessioni sulla porta TLS: N» con **N ≥ 1**: la Plug (e gli Shelly della sessione delle 14:00) ricollegati. Se è 0, aspetta un altro minuto e rilancia: i dispositivi ritentano da soli;
  4. «broker ok cert_days=…»;
  5. `dev ok … up` e `lab-01 ok … up`: il connector di `lab-01` è ricollegato sulla rete interna.
- Nell'app di staging, `lab-01`: la Plug in linea.
- **Ritorno indietro** (il broker si riavvia di nuovo; la rete resta su `172.30.84.0/24`, che non dà fastidio):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; B=/opt/domhouse/prima-passo3; sudo install -m 755 $B/broker-vm.sh /opt/domhouse/broker-vm.sh; sudo install -m 644 $B/broker-compose.yaml /opt/domhouse/_broker/compose.yaml; sudo install -m 644 $B/mosquitto.conf /opt/domhouse/_broker/mosquitto.conf; sudo bash /opt/domhouse/broker-vm.sh limit; sudo bash /opt/domhouse/broker-vm.sh restart'
```

- Il `limit` di prima riscrive la tabella senza le due catene dell'uscita; `restart` fa rileggere `mosquitto.conf`.

## P4. La prova dei metadati da tutte le reti (scrive sulla VM solo l'ora dell'ultimo controllo)

`engine-vm.sh` è già quello nuovo (P2): si forza la prova oraria.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo rm -f /opt/domhouse/.metadata-checked; sudo bash /opt/domhouse/engine-vm.sh check-all > /dev/null; sudo journalctl -t domhouse-check --since "-3min" --no-pager | grep metadata; true'
```

- **Atteso:** «metadata blocked reti=4» (le reti di `dev` e `lab-01` e le due del broker). Nessuna riga «metadata OPEN» né «metadata probe failed».
- **Ritorno indietro:** l'`engine-vm.sh` di prima, con il ritorno di P2 (solo la riga di `engine-vm.sh`).

## P5. sysctl, LLMNR e sshd (scrive sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash ~/passo3/host-vm.sh apply'
```

- **Atteso:** le tre sezioni (sysctl, systemd-resolved, sshd), «sshd ricaricato» e la riga che chiede `confirm`.
- **Da qui hai 10 minuti per P6.** Se non arriva `confirm`, il file di sshd si toglie da solo (è voluto: vuol dire che il collegamento nuovo non è riuscito).

## P6. Conferma da un collegamento NUOVO, e controllo (scrive solo la conferma)

Questo blocco apre un collegamento nuovo: se riesce, sshd con le regole nuove fa entrare.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/host-vm.sh confirm; sudo bash /opt/domhouse/host-vm.sh check'
```

- **Atteso:**
  1. «confermato: il file di sshd resta»;
  2. `kernel.kptr_restrict 1`, `kernel.yama.ptrace_scope 1`;
  3. `x11forwarding no`, `allowagentforwarding no`, `maxauthtries 3`, `allowtcpforwarding yes`;
  4. «porte LLMNR 5355 in ascolto: 0».
- **Se il collegamento non riesce** («Too many authentication failures» o simili): **non rilanciare a ripetizione.** Aspetta 10 minuti: il file di sshd si toglie da solo; poi rilancia questo blocco, che risponderà senza le regole di sshd, e incolla tutto alla memoria storica.
- **Ritorno indietro di P5:** `sudo bash /opt/domhouse/host-vm.sh undo` (toglie i tre file e rimette i due valori di sysctl di prima), nello stesso modo di questo blocco.

## P7. La cartella dell'utente OS Login (scrive sulla VM)

Via i file vecchi (copie del 10–12 novembre, una prova con chiavi, la storia dei comandi, le credenziali di gcloud dell'account della VM) e il catalogo copiato in C2 (quello vero sta in `/data/lab-01`). `~/passo3` e `~/agente` restano.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='cd ~ && rm -rf broker-files compose.yaml engine-vm.sh prova-gemini.sh catalog-lab-01.yaml .bash_history .config/gcloud && chmod 700 ~ && stat -c "%a %n" ~ && ls -la ~'
```

- **Atteso:** `700 /home/m_scardovellicrac_gmail_com`, e nell'elenco nessuno dei file tolti.
- **Ritorno indietro:** `chmod 755 ~`. I file tolti non tornano: sono copie vecchie di file che stanno nel repository o in `/opt/domhouse`, e le credenziali di gcloud si rifanno da sole se servono.

## P8. L'utente vecchio `m_scardovellicrac` (scrive sulla VM)

Non si cancella (non si potrebbe tornare indietro): esce dai gruppi `docker` e `adm`, non ha più una shell e l'account è scaduto.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; sudo gpasswd -d m_scardovellicrac docker; sudo gpasswd -d m_scardovellicrac adm; sudo usermod -s /usr/sbin/nologin -e 1 m_scardovellicrac; id m_scardovellicrac; getent passwd m_scardovellicrac; sudo chage -l m_scardovellicrac | grep -i "account expires" || true'
```

- **Atteso:** due «Removing user m_scardovellicrac from group …»; `id` con solo il suo gruppo; la shell `/usr/sbin/nologin`; «Account expires: Jan 02, 1970».
- **Ritorno indietro:** `sudo usermod -aG docker,adm -s /bin/bash -e "" m_scardovellicrac`.

## P9. Le immagini vecchie del motore (scrive sulla VM)

**P9.1 L'elenco (sola lettura):**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh prune-images'
```

- **Atteso:** «tengo …:d368f0d (in uso)», «tengo …:f4c6a20 (in uso)», due «tengo … (per tornare indietro)», poi le righe «da togliere …» e «prova a secco: niente tolto». **Incolla l'elenco e aspetta l'ok della memoria storica.**

**P9.2 La pulizia:** lo stesso comando con `prune-images apply`.

- **Atteso:** una riga «tolta …» per ognuna delle «da togliere».
- **Ritorno indietro:** non serve. Le immagini restano in Artifact Registry: `engine-vm.sh update <appartamento> <immagine>` la riscarica se un giorno serve.

## P10. Pacchetti di Docker e Google, poi il riavvio (scrive sulla VM; il fermo più lungo)

**P10.1 Una copia del disco di avvio (scrive su Google Cloud).** Il disco delle chiavi (`langbrain-dev-tls`) non ha copie per scelta (C-12) e il riavvio non lo tocca.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute disks snapshot langbrain-dev --zone=europe-west8-a --snapshot-names=langbrain-dev-prima-passo3 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** «Creating snapshot(s) langbrain-dev-prima-passo3…done.»
- La si cancella dopo una settimana senza problemi: `gcloud compute snapshots delete langbrain-dev-prima-passo3 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com`.

**P10.2 L'aggiornamento dei pacchetti.** Qui Docker si riavvia e con lui tutti i container (1–2 minuti).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; sudo apt-get update -q; sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q --only-upgrade -o Dpkg::Options::=--force-confold containerd.io docker-buildx-plugin docker-ce-cli docker-ce-rootless-extras docker-ce docker-compose-plugin google-cloud-cli google-cloud-ops-agent google-compute-engine google-guest-agent google-osconfig-agent; dpkg-query -W containerd.io docker-ce google-guest-agent google-cloud-ops-agent; sudo docker ps --format "{{.Names}} {{.Status}}"'
```

- **Atteso:** l'elenco dei pacchetti aggiornati, le versioni nuove e i tre container `Up` (`domhouse-broker`, `engine-dev`, `engine-lab-01`).
- `--force-confold`: i file di configurazione già sulla VM restano come sono.
- **Da verificare:** che l'aggiornamento di `google-guest-agent` (che gestisce gli accessi di OS Login) non chiuda il collegamento in corso. Se il blocco si interrompe a metà, rilancialo: `apt-get` riprende da dove era.
- **Ritorno indietro:** le versioni di P0.2 con `sudo apt-get install -y --allow-downgrades <pacchetto>=<versione di P0.2>`; per tutto il disco, la copia di P10.1.

**P10.3 Il riavvio.**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo systemctl reboot'
```

- **Atteso:** il collegamento si chiude, a volte con un errore di gcloud: è normale. **Aspetta 3 minuti** prima di P11.

## P11. Dopo il riavvio: tutto è tornato da solo (sola lettura)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='uname -r; uptime; ls /var/run/reboot-required 2>&1; findmnt -n -o TARGET,OPTIONS /mnt/domhouse-tls; sudo nft list tables; sudo nft list table inet domhouse_broker | grep -c comment; sudo docker ps --format "{{.Names}} {{.Status}}"; for p in 8100 8169; do curl -s -m 5 http://10.198.0.2:$p/api/v1/health | python3 -c "import json,sys; h=json.load(sys.stdin); print(h[\"apartment_id\"], h[\"status\"], h[\"connector\"][\"status\"])"; done; sudo bash /opt/domhouse/broker-vm.sh status | grep -E "scartati|connessioni|^broker"; sudo bash /opt/domhouse/host-vm.sh check; sudo rm -f /opt/domhouse/.metadata-checked; sudo bash /opt/domhouse/engine-vm.sh check-all > /dev/null; sudo journalctl -t domhouse-check --since "-3min" --no-pager | grep -E "engine|metadata|motori|broker"; true'
```

| Riga | Atteso |
|---|---|
| `uname -r`, `uptime` | il kernel nuovo (`6.1.0-56-cloud-amd64` o più nuovo), acceso da pochi minuti; `reboot-required` non c'è più |
| disco delle chiavi | `/mnt/domhouse-tls` montato, `nosuid,nodev,noexec` |
| `nft list tables` | `inet domhouse_metadata` (caricata prima di Docker) e `inet domhouse_broker` |
| conteggio dei `comment` di `domhouse_broker` | `4`: le due regole del limite (D-209) e le due dell'uscita (C2) |
| `docker ps` | `domhouse-broker`, `engine-dev`, `engine-lab-01` tutti `Up` (il broker `healthy`) |
| salute | `dev ok … up` e `lab-01 ok … up` |
| broker | «connessioni sulla porta TLS: N» con N ≥ 1 (la Plug ricollegata; se 0, aspetta un minuto e rilancia), «broker ok cert_days=…» |
| `host-vm.sh check` | come in P6: i valori nuovi valgono anche dopo il riavvio |
| controllo | «engine ok dev», «engine ok lab-01», «domhouse-check: 2 motori, 0 muti», «metadata blocked reti=4» |

- Nell'app di staging e in quella di produzione: i dispositivi di `dev` e la Plug di `lab-01` in linea.
- **Se qualcosa non torna, fermati:** il ritorno completo è la copia di P10.1 (si crea un disco dalla copia e lo si mette al posto di quello di avvio, con la memoria storica).

## P12. Pulizia della cartella di lavoro (scrive sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='rm -rf ~/passo3; ls -la ~'
```

- `/opt/domhouse/prima-passo3` e la copia `langbrain-dev-prima-passo3` restano: sono il ritorno indietro. Si tolgono dopo una settimana senza problemi.

## Da incollare alla memoria storica

L'uscita di ogni blocco, in particolare: le versioni di P0.2, le prove di P0.3 e P3.1, l'elenco di P9.1 e la tabella di P11.
