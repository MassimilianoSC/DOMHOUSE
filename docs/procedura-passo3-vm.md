# Passo 3 sulla VM: le correzioni del controllo di sicurezza (17 novembre)

| Stato | Preparata | Codice | Quando | Chi lancia | Comandi |
|---|---|---|---|---|---|
| **Pronta, corretta dopo la revisione indipendente** (17 novembre: «eseguibile dopo correzioni», tutte fatte). Nessun passo provato sul vero | o1, 17 novembre 2026 | `26510e6` (`b722e1e`, `1f0db35`, `9ace3fd`, `929d948` e la correzione di `host-vm.sh`) | **dopo la fine della sessione dei due Shelly** (D-213); fra l'inizio e la fine di quella sessione niente sulla VM. **P3 e P10 mai fra le 22:15 e le 23:15 UTC** (backup notturno alle 22:30 e copia del disco alle 23:00). Il giorno e l'ora li decide il committente | il committente, un blocco alla volta, in Git Bash, con la memoria storica in chat | P0–P12 |

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
| sysctl, H5, H6 | `kptr_restrict` e `ptrace_scope` a 1, `LLMNR=no`, sshd senza inoltri e con 3 tentativi | `929d948`, `26510e6` | P5, P6 |
| H2 | la cartella dell'utente OS Login: file vecchi via, cartella a 700 | — | P7 |
| H3/C7 | l'utente vecchio `m_scardovellicrac`: fuori da docker e adm, bloccato | — | P8 |
| H7 | le immagini vecchie del motore (tenute quelle in uso e le due precedenti) | `9ace3fd` | P9 |
| H1, pacchetti | gli 11 pacchetti di Docker e Google, poi il riavvio | — | P10 |

**Regole:**

1. Un blocco alla volta; **incolla alla memoria storica l'uscita di ogni blocco.**
2. **Se un'uscita non torna, fermati.**
3. Ogni passo che scrive ha accanto il ritorno indietro, come blocco completo.
4. Un comando che finisce con `grep` e non trova righe esce con 1, e gcloud lo mostra come un guasto del collegamento («plink.exe exited with return code [1]»): per questo i blocchi che finiscono con `grep` hanno `; true` in fondo, e sotto `set -e` il `grep` ha `|| true`. Conta solo il testo.
5. **Dopo questa procedura, `publish-all.sh` solo con un commit che contiene `26510e6`:** con uno più vecchio rimetterebbe sulla VM l'`engine-vm.sh` di prima.

## P0. Controlli prima (sola lettura)

**P0.1 Sul PC: i file da portare sono quelli del commit.**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
git log --oneline -1 26510e6 && git merge-base --is-ancestor 26510e6 HEAD && git diff --quiet 26510e6 -- scripts/engine-vm.sh scripts/broker-vm.sh scripts/host-vm.sh engine/broker/compose.yaml engine/broker/mosquitto.conf && echo "file uguali a 26510e6"
```

- **Atteso:** la riga di `26510e6` e «file uguali a 26510e6». Se manca la seconda riga, fermati.

**P0.2 Sulla VM: lo stato di partenza.**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='uname -r; ls /var/run/reboot-required; grep domhouse-tls /etc/fstab; findmnt -n -o TARGET,OPTIONS /mnt/domhouse-tls; sudo docker network inspect -f "{{range .IPAM.Config}}{{.Subnet}}{{end}}" domhouse-broker_default; sudo nft list tables; dpkg-query -W containerd.io docker-buildx-plugin docker-ce-cli docker-ce-rootless-extras docker-ce docker-compose-plugin google-cloud-cli google-cloud-ops-agent google-compute-engine google-guest-agent google-osconfig-agent; echo "aggiornabili: $(apt list --upgradable 2>/dev/null | grep -c upgradable)"; echo "immagini del motore: $(sudo docker images --format "{{.Repository}}" | grep -c domotica/engine)"; true'
```

| Riga | Atteso |
|---|---|
| `uname -r` | `6.1.0-54-cloud-amd64`, poi `/var/run/reboot-required` |
| fstab | la riga di `/mnt/domhouse-tls` **con `nofail` e con `x-systemd.before=docker.service`** (le scrive `broker-vm.sh prepare-tls-disk`). **Se manca una delle due, fermati:** senza `nofail` il riavvio di P10 si bloccherebbe senza quel disco; senza `x-systemd.before` il broker potrebbe partire prima del disco |
| `findmnt` | `/mnt/domhouse-tls` con `nosuid,nodev,noexec` |
| rete del broker | `172.19.0.0/16` (la sceglie Docker; P3 la porta a `172.30.84.0/24`) |
| `nft list tables` | fra le altre `inet domhouse_broker` e `inet domhouse_metadata` |
| `dpkg-query` | undici righe pacchetto–versione: **sono le versioni per tornare indietro in P10** |
| aggiornabili, immagini | circa 11 e circa 20 |

**P0.3 La prova rossa di C2: oggi il broker può aprire collegamenti in uscita.**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker exec domhouse-broker wget -q -T 5 -O /dev/null http://10.198.0.2:8100/api/v1/health; echo "dal broker verso il motore dev: uscita $?"; sudo docker exec domhouse-broker wget -S -T 5 -O /dev/null http://1.1.1.1 2>&1 | head -3; true'
```

- **Atteso:**
  1. «uscita 0»: il broker raggiunge il motore `dev`;
  2. verso `1.1.1.1` (un indirizzo, così il nome non dipende dal DNS): «Connecting to 1.1.1.1» e una riga `HTTP/1.1 3…` della risposta. Il collegamento parte: è la prova rossa.
- Dopo P3 la prima uscita deve diventare diversa da 0 e la seconda dire «timed out» senza riga `HTTP/`.
- **Se risponde «not found»:** l'immagine del broker non ha `wget` (Mosquitto su Alpine, con busybox: dovrebbe averlo). Incollalo: la prova si fa in un altro modo.
- **Se la prima uscita è diversa da 0 ma non dice «not found», fermati e incolla:** oggi il collegamento dovrebbe riuscire.

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

Tiene una copia dei file di prima in `/opt/domhouse/prima-passo3` (**solo la prima volta**: un rilancio non la sovrascrive) e toglie i ritorni a capo di Windows.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; B=/opt/domhouse/prima-passo3; if ! sudo test -e $B/mosquitto.conf; then sudo mkdir -p $B; sudo cp -p /opt/domhouse/engine-vm.sh /opt/domhouse/broker-vm.sh $B/; sudo cp -p /opt/domhouse/_broker/compose.yaml $B/broker-compose.yaml; sudo cp -p /opt/domhouse/_broker/mosquitto.conf $B/mosquitto.conf; echo "copia di prima fatta"; else echo "copia di prima già presente: non la tocco"; fi; cd ~/passo3; sed -i "s/\r*$//" engine-vm.sh broker-vm.sh host-vm.sh broker/compose.yaml broker/mosquitto.conf; sudo install -m 755 engine-vm.sh /opt/domhouse/engine-vm.sh; sudo install -m 755 broker-vm.sh /opt/domhouse/broker-vm.sh; sudo install -m 644 broker/compose.yaml /opt/domhouse/_broker/compose.yaml; sudo install -m 644 broker/mosquitto.conf /opt/domhouse/_broker/mosquitto.conf; sha256sum /opt/domhouse/engine-vm.sh /opt/domhouse/broker-vm.sh /opt/domhouse/_broker/compose.yaml /opt/domhouse/_broker/mosquitto.conf ~/passo3/host-vm.sh; sudo ls -l $B'
```

- **Atteso:** «copia di prima fatta» (o «già presente» a un rilancio), poi cinque impronte che **cominciano** così (i file di `26510e6` senza i ritorni a capo di Windows):

| File | Impronta, primi 16 caratteri |
|---|---|
| `/opt/domhouse/engine-vm.sh` | `acafc1859f8bf195` |
| `/opt/domhouse/broker-vm.sh` | `f76a99304f7c2cb2` |
| `/opt/domhouse/_broker/compose.yaml` | `770bc201245e573e` |
| `/opt/domhouse/_broker/mosquitto.conf` | `75dd2800364f848f` |
| `~/passo3/host-vm.sh` | `ba553299c538b1b3` |

- Se un'impronta è diversa, **fermati**: il file copiato non è quello del commit.
- Il broker gira ancora con la configurazione di prima: la nuova vale da P3.
- **Ritorno indietro:**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; B=/opt/domhouse/prima-passo3; sudo install -m 755 $B/engine-vm.sh /opt/domhouse/engine-vm.sh; sudo install -m 755 $B/broker-vm.sh /opt/domhouse/broker-vm.sh; sudo install -m 644 $B/broker-compose.yaml /opt/domhouse/_broker/compose.yaml; sudo install -m 644 $B/mosquitto.conf /opt/domhouse/_broker/mosquitto.conf; echo "file di prima rimessi"'
```

## P3. Il broker: la rete nuova, l'uscita chiusa, TLS 1.2 (scrive sulla VM; il broker si ferma meno di un minuto)

Non fra le 22:15 e le 23:15 UTC.

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
- **Se si ferma dopo «il broker si ferma un momento»** (per esempio «network rm» con «active endpoints»: la prova oraria dei metadati di P4 può avere in quell'istante un container di pochi secondi sulla rete del broker), **rilancia P3 una volta**: `network` riparte da dove era (rete ancora vecchia: la rifà; rete già tolta: la crea compose). Non serve fermare il controllo orario: la prova dura al massimo 30 secondi, una volta all'ora. Se si ferma di nuovo, incolla.

**P3.1 Controllo, dopo un minuto (sola lettura).**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo docker exec domhouse-broker wget -q -T 5 -O /dev/null http://10.198.0.2:8100/api/v1/health; echo "dal broker verso il motore dev: uscita $?"; sudo docker exec domhouse-broker wget -S -T 5 -O /dev/null http://1.1.1.1 2>&1 | head -3; sudo bash /opt/domhouse/broker-vm.sh status | grep -E "scartati|connessioni|^broker"; for p in 8100 8169; do curl -s -m 5 http://10.198.0.2:$p/api/v1/health | python3 -c "import json,sys; h=json.load(sys.stdin); print(h[\"apartment_id\"], h[\"status\"], h[\"connector\"][\"status\"])"; done; true'
```

- **Atteso:**
  1. verso il motore `dev`: uscita **diversa da 0**; verso `1.1.1.1`: «timed out», **nessuna** riga `HTTP/`. È la prova verde di C2;
  2. «collegamenti in uscita dal broker scartati: 2» o più; «collegamenti scartati dal limite: …» come prima;
  3. «connessioni sulla porta TLS: N» con **N ≥ 1**: la Plug (e gli Shelly della sessione delle 14:00) ricollegati. Se è 0, aspetta un altro minuto e rilancia: i dispositivi ritentano da soli;
  4. «broker ok cert_days=…»;
  5. `dev ok … up` e `lab-01 ok … up`: il connector di `lab-01` è ricollegato sulla rete interna.
- Nell'app di staging, `lab-01`: la Plug in linea.
- **Ritorno indietro** (il broker si riavvia di nuovo; la rete resta su `172.30.84.0/24`, che non dà fastidio). Se P3 si era fermato dopo la rimozione del container, il ritorno lo ricrea prima del riavvio:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; B=/opt/domhouse/prima-passo3; sudo install -m 755 $B/broker-vm.sh /opt/domhouse/broker-vm.sh; sudo install -m 644 $B/broker-compose.yaml /opt/domhouse/_broker/compose.yaml; sudo install -m 644 $B/mosquitto.conf /opt/domhouse/_broker/mosquitto.conf; sudo bash /opt/domhouse/broker-vm.sh limit; sudo docker inspect domhouse-broker > /dev/null 2>&1 || sudo docker compose --env-file /opt/domhouse/_broker/broker.settings -f /opt/domhouse/_broker/compose.yaml up -d; sudo bash /opt/domhouse/broker-vm.sh restart'
```

- Il `limit` di prima riscrive la tabella senza le due catene dell'uscita; `restart` fa rileggere `mosquitto.conf`.
- **Da verificare:** il compose di prima non dice la sottorete; se `compose up` segnala che la rete esistente (`172.30.84.0/24`) è diversa da quella attesa, incolla l'uscita: la rete si toglie e si ricrea con la memoria storica.

## P4. La prova dei metadati da tutte le reti (scrive sulla VM solo l'ora dell'ultimo controllo)

`engine-vm.sh` è già quello nuovo (P2): si forza la prova oraria.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo rm -f /opt/domhouse/.metadata-checked; sudo bash /opt/domhouse/engine-vm.sh check-all > /dev/null; sudo journalctl -t domhouse-check --since "-3min" --no-pager | grep metadata; true'
```

- **Atteso:** «metadata blocked reti=4» (le reti di `dev` e `lab-01` e le due del broker). Nessuna riga «metadata OPEN» né «metadata probe failed».
- **Ritorno indietro** (l'`engine-vm.sh` di prima):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo install -m 755 /opt/domhouse/prima-passo3/engine-vm.sh /opt/domhouse/engine-vm.sh && echo "engine-vm.sh di prima rimesso"'
```

## P5. sysctl, LLMNR e sshd (scrive sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash ~/passo3/host-vm.sh apply'
```

- **Atteso:** le tre sezioni (sysctl, systemd-resolved, sshd), «sshd ricaricato» e la riga che chiede `confirm`.
- Il ritorno da solo si arma **prima** di ricaricare sshd: se non si arma, lo script toglie il file di sshd, non ricarica e lo dice.
- **Da qui hai 10 minuti per P6.** Se non arriva `confirm`, il file di sshd si toglie da solo (è voluto: vuol dire che il collegamento nuovo non è riuscito).
- **Non rilanciare P5 senza la memoria storica.**

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
- **Se il collegamento non riesce** («Too many authentication failures» o simili): **non rilanciare a ripetizione.** Aspetta 10 minuti: il file di sshd si toglie da solo. Poi lancia **solo il controllo**, non `confirm`, e incolla tutto alla memoria storica:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/host-vm.sh check'
```

- **Se `confirm` risponde «niente da confermare: il file di sshd è già stato tolto»:** il ritorno da solo è scattato prima della conferma. Le righe di sshd del controllo tornano quelle di prima; incolla e decidi con la memoria storica se rifare P5.
- **Ritorno indietro di P5** (toglie i tre file e rimette i due valori di sysctl di prima):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/host-vm.sh undo; sudo bash /opt/domhouse/host-vm.sh check'
```

## P7. La cartella dell'utente OS Login (scrive sulla VM)

Via i file vecchi (copie del 10–12 novembre, una prova con chiavi, la storia dei comandi, le credenziali di gcloud dell'account della VM) e il catalogo copiato in C2 (quello vero sta in `/data/lab-01`). `~/passo3` e `~/agente` restano.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='cd ~ && rm -rf broker-files compose.yaml engine-vm.sh prova-gemini.sh catalog-lab-01.yaml .bash_history .config/gcloud && chmod 700 ~ && stat -c "%a %n" ~ && ls -la ~'
```

- **Atteso:** `700 /home/m_scardovellicrac_gmail_com`, e nell'elenco nessuno dei file tolti.
- **Ritorno indietro** (solo i permessi; i file tolti non tornano: sono copie vecchie di file che stanno nel repository o in `/opt/domhouse`, e le credenziali di gcloud si rifanno da sole se servono):

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='chmod 755 ~ && stat -c "%a %n" ~'
```

## P8. L'utente vecchio `m_scardovellicrac` (scrive sulla VM)

Non si cancella (non si potrebbe tornare indietro): esce dai gruppi `docker` e `adm` e dai quattro dati dall'immagine di ottobre (`dip`, `video`, `plugdev`, `lxd`: risposta 1159 = a, 19 novembre), non ha più una shell e l'account è scaduto. Si può rilanciare.

**Mai toccato:** l'utente OS Login `m_scardovellicrac_gmail_com`, quello con cui ci si collega, e l'account dell'app (nota del committente, 19 novembre).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='set -e; for g in docker adm dip video plugdev lxd; do sudo gpasswd -d m_scardovellicrac "$g" || true; done; sudo usermod -s /usr/sbin/nologin -e 1 m_scardovellicrac; id m_scardovellicrac; getent passwd m_scardovellicrac; sudo chage -l m_scardovellicrac | grep -i "account expires" || true'
```

- **Atteso:** sei «Removing user m_scardovellicrac from group …» (a un rilancio «is not a member»); `id` con solo il suo gruppo (`groups=1003(m_scardovellicrac)`); la shell `/usr/sbin/nologin`; «Account expires: Jan 02, 1970».
- **Ritorno indietro:**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo usermod -aG docker,adm,dip,video,plugdev,lxd -s /bin/bash -e "" m_scardovellicrac && id m_scardovellicrac' < /dev/null
```

## P9. Le immagini vecchie del motore (scrive sulla VM)

**P9.1 L'elenco (sola lettura):**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh prune-images'
```

- **Atteso:** «tengo …:d368f0d (in uso)», «tengo …:f4c6a20 (in uso)», due «tengo … (per tornare indietro)», poi le righe «da togliere …» e «prova a secco: niente tolto». **Incolla l'elenco e aspetta l'ok della memoria storica.**

**P9.2 La pulizia, dopo l'ok:**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo bash /opt/domhouse/engine-vm.sh prune-images apply'
```

- **Atteso:** una riga «tolta …» per ognuna delle «da togliere» di P9.1.
- **Ritorno indietro:** non serve. Le immagini restano in Artifact Registry: `engine-vm.sh update <appartamento> <immagine>` la riscarica se un giorno serve.

## P10. Pacchetti di Docker e Google, poi il riavvio (scrive sulla VM; il fermo più lungo)

Non fra le 22:15 e le 23:15 UTC.

**P10.1 Una copia del disco di avvio (scrive su Google Cloud).** Il disco delle chiavi (`langbrain-dev-tls`) non ha copie per scelta (C-12) e il riavvio non lo tocca.

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute disks snapshot langbrain-dev --zone=europe-west8-a --snapshot-names=langbrain-dev-prima-passo3 --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com
```

- **Atteso:** «Creating snapshot(s) langbrain-dev-prima-passo3…done.»
- La si cancella dopo una settimana senza problemi, con il comando che prepara la memoria storica.

**P10.2 L'aggiornamento dei pacchetti, staccato dal collegamento.** Gira come servizio di systemd sulla VM: se l'aggiornamento di `google-guest-agent` o un guasto di IAP chiude il collegamento, `apt-get` va avanti lo stesso. Docker si riavvia e con lui tutti i container (1–2 minuti).

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo systemd-run --unit=domhouse-passo3-pacchetti --collect -E DEBIAN_FRONTEND=noninteractive /bin/bash -c "apt-get update -q -o DPkg::Lock::Timeout=300 && apt-get install -y -q --only-upgrade -o DPkg::Lock::Timeout=300 -o Dpkg::Options::=--force-confold containerd.io docker-buildx-plugin docker-ce-cli docker-ce-rootless-extras docker-ce docker-compose-plugin google-cloud-cli google-cloud-ops-agent google-compute-engine google-guest-agent google-osconfig-agent"'
```

- **Atteso:** «Running as unit: domhouse-passo3-pacchetti.service». Il blocco finisce subito: l'aggiornamento continua sulla VM.
- `--force-confold`: i file di configurazione già sulla VM restano come sono.

**P10.2b Seguire l'aggiornamento (sola lettura): ripeti ogni minuto finché la prima riga dice `inactive`.**

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='systemctl is-active domhouse-passo3-pacchetti; sudo journalctl -u domhouse-passo3-pacchetti --no-pager | tail -8; dpkg-query -W containerd.io docker-ce google-guest-agent google-cloud-ops-agent; sudo docker ps --format "{{.Names}} {{.Status}}"; true'
```

- **Mentre lavora:** `active` e le ultime righe di `apt-get`.
- **Alla fine:** `inactive` (con `--collect` il servizio sparisce quando ha finito, anche `failed` si legge così); nel registro «Setting up docker-ce …» e niente «E:»; le versioni nuove; i tre container `Up` (`domhouse-broker`, `engine-dev`, `engine-lab-01`).
- **Se il registro finisce con un errore** («E: …», «dpkg was interrupted», «Sub-process /usr/bin/dpkg returned an error») **o i container non ripartono:** dpkg è rimasto a metà. Lancia una volta:

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='sudo DEBIAN_FRONTEND=noninteractive dpkg --configure -a; sudo DEBIAN_FRONTEND=noninteractive apt-get install -f -y -q -o Dpkg::Options::=--force-confold; sudo systemctl start docker; sudo docker ps --format "{{.Names}} {{.Status}}"; true'
```

  poi rilancia P10.2 e di nuovo P10.2b. Se i container restano giù, incolla tutto alla memoria storica prima di riavviare.
- **Ritorno indietro dei pacchetti:** il comando lo prepara la memoria storica con le versioni di P0.2 (`apt-get install --allow-downgrades` con le versioni esatte); per tutto il disco, la copia di P10.1.

**P10.3 Il riavvio, solo con P10.2b finito e i tre container `Up`.**

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
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='uname -r; uptime; ls /var/run/reboot-required 2>&1; systemctl --failed --no-legend; systemctl is-active domhouse-broker-limit domhouse-metadata-block; findmnt -n -o TARGET,OPTIONS /mnt/domhouse-tls; sudo nft list tables; sudo nft list table inet domhouse_broker | grep -c comment; sudo docker ps --format "{{.Names}} {{.Status}}"; for p in 8100 8169; do curl -s -m 5 http://10.198.0.2:$p/api/v1/health | python3 -c "import json,sys; h=json.load(sys.stdin); print(h[\"apartment_id\"], h[\"status\"], h[\"connector\"][\"status\"])"; done; sudo bash /opt/domhouse/broker-vm.sh status | grep -E "scartati|connessioni|^broker"; sudo bash /opt/domhouse/host-vm.sh check; id m_scardovellicrac; sudo rm -f /opt/domhouse/.metadata-checked; sudo bash /opt/domhouse/engine-vm.sh check-all > /dev/null; sudo journalctl -t domhouse-check --since "-3min" --no-pager | grep -E "engine|metadata|motori|broker"; true'
```

| Riga | Atteso |
|---|---|
| `uname -r`, `uptime` | il kernel nuovo (`6.1.0-56-cloud-amd64` o più nuovo), acceso da pochi minuti; `reboot-required` non c'è più |
| `systemctl --failed` | nessuna riga |
| `is-active` | `active` e `active`: il limite del broker (D-209, con l'uscita C2) e il blocco dei metadati (E-31) ricaricati all'avvio |
| disco delle chiavi | `/mnt/domhouse-tls` montato, `nosuid,nodev,noexec` |
| `nft list tables` | `inet domhouse_metadata` (caricata prima di Docker) e `inet domhouse_broker` |
| conteggio dei `comment` di `domhouse_broker` | `4`: le due regole del limite (D-209) e le due dell'uscita (C2) |
| `docker ps` | `domhouse-broker`, `engine-dev`, `engine-lab-01` tutti `Up` (il broker `healthy`) |
| salute | `dev ok … up` e `lab-01 ok … up` |
| broker | «connessioni sulla porta TLS: N» con N ≥ 1 (la Plug ricollegata; se 0, aspetta un minuto e rilancia), «broker ok cert_days=…» |
| `host-vm.sh check` | come in P6: i valori nuovi valgono anche dopo il riavvio |
| `id m_scardovellicrac` | solo il suo gruppo, come in P8 (`groups=1003(m_scardovellicrac)`) |
| controllo | «engine ok dev», «engine ok lab-01», «domhouse-check: 2 motori, 0 muti», «metadata blocked reti=4» |

- Nell'app di staging e in quella di produzione: i dispositivi di `dev` e la Plug di `lab-01` in linea.
- **La parte VM di A1:** oggi si installa **dopo** questa finestra, quindi non c'è. Se fosse già installata, si aggiunge `systemctl is-active domhouse-agent-lettore domhouse-agent-esecutore` (atteso: due `active`).
- **Se qualcosa non torna, fermati:** il ritorno completo è la copia di P10.1 (si crea un disco dalla copia e lo si mette al posto di quello di avvio, con la memoria storica).

## P12. Pulizia della cartella di lavoro (scrive sulla VM)

```bash
# Git Bash
cd /c/Users/mcracchiolo/Desktop/DOMOTICA/app
gcloud compute ssh langbrain-dev --zone=europe-west8-a --tunnel-through-iap --project=domotica-poc-511707 --account=m.scardovellicrac@gmail.com --command='rm -rf ~/passo3; ls -la ~'
```

- `/opt/domhouse/prima-passo3` e la copia `langbrain-dev-prima-passo3` restano: sono il ritorno indietro. Si tolgono dopo una settimana senza problemi.

## Da incollare alla memoria storica

L'uscita di ogni blocco, in particolare: le versioni di P0.2, le prove di P0.3 e P3.1, le impronte di P2, l'elenco di P9.1, ogni P10.2b e la tabella di P11.
