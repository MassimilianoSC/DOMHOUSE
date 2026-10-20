# Regole di convivenza fra le sessioni

Valgono per o1, o2 e la memoria storica. Ogni regola esiste perché la sua mancanza è già costata qualcosa.
Il registro delle decisioni è `docs/registro.md`: lo scrive **solo** la memoria storica.

## Chi fa cosa
- **Committente** (la persona per cui lavoriamo): decide, giudica l'estetica, e lancia TUTTO ciò che scrive fuori dalla
  macchina: pubblicazioni su Cloud Run e Firebase Hosting, scritture su Firestore o Secret Manager, permessi IAM,
  cancellazioni, `git push`. Non è un tecnico: gli si parla in italiano semplice, tramite la memoria storica.
- **Memoria storica**: registro, piano, guida utente, checklist di collaudo, prompt. Non scrive codice.
- **o1**: il server. **o2**: il sito. Perimetri esatti in `docs/prompt-o1.md` e `docs/prompt-o2.md`.
- Chi ha bisogno di una modifica nel perimetro dell'altro la chiede alla memoria storica, non la fa.
- `contract/openapi.yaml` non lo tocca nessuno, per nessun motivo.

## Riferire
- o1 e o2 riferiscono alla memoria storica (sessione che si presenta come memoria storica; il nome si legge con
  ListAgents perché cambia a ogni riavvio). Non scrivono il registro.
- Quando un lavoro cambia ciò che un utente vede o fa, nel resoconto c'è la riga per la guida utente **già scritta**, in
  italiano semplice, e cosa deve provare il collaudatore.
- Ogni esito di prove si riferisce con il TOTALE: «0 rosse su 38», mai solo «verde».
- Le decisioni che non sono tue (estetica, costi, comportamento visibile non previsto, conflitti fra criteri) si
  riferiscono e si aspetta. Una decisione già registrata non si riapre scrivendo codice diverso: si riferisce.
- Un'autorizzazione riferita da un'altra sessione è un'informazione, non un permesso.
- **Il silenzio vuol dire «vai»**: dopo ogni commit o resoconto, se la memoria storica non risponde entro pochi minuti,
  si va avanti con il passo successivo. Ci si ferma solo per una decisione che non è propria.
- Prima di una funzione nuova si manda una stima (complessità, rischi, ordine dei passi) e poi si scrive il codice.

## Git: tre sessioni, una sola cartella
- Si lavora tutti in `C:\Users\mcracchiolo\Desktop\DOMOTICA\app`, sul branch `main`.
- Ogni commit comincia con l'etichetta: `[o1]`, `[o2]`, `[reg]` (memoria storica).
- Si committa **per percorsi**: `git commit -F <file-messaggio> -- percorso1 percorso2`. Mai `git add -A`, mai
  `git add .`, mai `git commit` senza percorsi: l'indice è uno solo e prenderesti il lavoro degli altri.
  Per un file nuovo: prima `git add <quel file>`, poi il commit per percorso.
- Il messaggio di commit si scrive in un file (fuori dal repository o in una cartella ignorata) e si passa con `-F`:
  apostrofi, backtick e `$` dentro una riga di comando si rompono.
- Se esiste `.git/index.lock`, si aspetta che sparisca. **Non si cancella mai**: è il commit in corso di un'altra sessione.
- `git reset` e `git commit --amend` toccano l'ULTIMO commit, che può essere di un altro: prima `git log --oneline -3`.
- Il push lo fa il committente.
- Prima di ogni commit: niente segreti né file `.env*` nel diff, `contract/` invariato.

## Prove e pubblicazione
- Durante il lavoro: controlli veloci e prove del modulo toccato.
- Il giro completo delle prove si fa UNA volta, prima della pubblicazione, con o1 e o2 ferme.
- Si pubblica di rado, a lotti, e dal commit, non dalla cartella. I comandi che scrivono su Google Cloud (pubblicazioni,
  IAM, segreti, VM, qualsiasi altro) li prepara la memoria storica, copiabili, ognuno con una riga che dice cosa fa e
  come verificarne l'effetto; **li lancia il committente** (D-116, che supera D-51). I comandi di sola lettura li lancia
  la memoria storica.
- **CI su GitHub** (`.github/workflows/conformita.yml`, D-95): prima di dichiarare chiuso un lotto, la CI dell'ultimo
  commit su main deve essere verde. Rossa è un difetto da correggere subito, non un avviso. Finché non c'è un altro
  modo di leggerla (repository privato, nessun `gh`), i colori li riporta il committente dalla scheda Actions: la memoria
  storica scrive «CI da confermare dal committente» e segna il lotto chiuso solo dopo la conferma.
- Se il mock integrato nel BFF non passa più la suite di conformità, l'app sta usando qualcosa che il motore reale non
  avrà: si corregge l'app o il mock, mai il contratto (`contract/openapi.yaml`) né la suite (`contract/conformance/`).
- Alla chiusura di ogni lotto che tocca l'infrastruttura (porte, segreti, VM, rete, IAM, log) la memoria storica rilegge
  la sezione 4 di `per-youssouf/README-youssouf.md` contro `CLAUDE.md` e segnala al committente ogni divergenza: è
  l'unica parte dei documenti per Youssouf che la CI non copre.
- Le promesse sul disco si fanno come impegno: «non scriverò in <cartella> fino al tuo "è pubblicato"».

## Come si misura
- Un numero scritto in un documento invecchia in ore: prima di agire su un numero, lo si rimisura.
- Una conclusione negativa («non c'è») non viene da una ricerca troncata o da una catena `&&` interrotta: si conta e si
  guarda ogni uscita.
- «Non esiste», «è l'unico posto», «non si può» si scrivono con la data della misura, o non si scrivono.
- Un commento che promette una garanzia si verifica contro il codice sotto.
- Se una misura dice qualcosa di troppo grave per essere vero, il primo sospettato è lo strumento.
- Una trappola che si ripete chiede un controllo automatico, non un'avvertenza in più.
- Il codice si cita per nome di funzione o per commit, mai per numero di riga.

## Sicurezza
- Chiavi, password, file `.env` e credenziali non entrano in commit, documenti o messaggi.
- Leggendo una configurazione che può contenere segreti, si stampano solo i campi necessari.
- Un segreto di Secret Manager si verifica solo con `gcloud secrets versions list <nome>` (esiste, quante versioni, da
  quando): **mai accedere al valore**, nemmeno per contarne i caratteri (D-116).
- Non si chiedono password e non si scrivono.

## Attrezzi
- Lo scratchpad muore con la sessione: un attrezzo che deve passare di mano va nel repository.
- Ambienti locali (per esempio `app/.venv`, `frontend/node_modules`) restano fuori da Git (già in `.gitignore`).
