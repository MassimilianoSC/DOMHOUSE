# Cosa manca per la produzione vera

*Elenco chiesto dal committente il 21 ottobre 2026 (D-133). È la lista che decide quando si smette di chiamare l'app «pilota».
Si aggiorna a ogni lotto; lo stato di ogni voce è quello del registro. «Da verificare» = non ancora controllato.*

## A. Codice (poco)

| Voce | Stato | Chi |
|---|---|---|
| Passo 7 del motore: conferma a consumo, collegamenti del catalogo, connector giù/su, parametri per appartamento (D-131, D-133) | in corso | o1 |
| Passo 8: approvazioni da fonti vere, con coda e scadenza persistente | da fare (1 giornata) | o1 |
| Passo 9: assistente vero con Gemini, limiti, tetto di spesa, regole fisse del prompt (D-132) | da fare (3–4 giornate) | o1, o2 per i testi |
| Passo 10: stato di salute completo e allarmi dai log dei container sulla VM | da fare (1 giornata) | o1, comandi GCP del committente |
| Passo 11: riassunto settimanale per il gestore con push e pagina (D-133) | da fare, dopo il 9 (2–3 giornate) | o1, o2 |
| Passo 12: regole configurabili dall'app, prima a mano poi proposte dall'assistente (D-133) | da progettare dopo l'11 | o1, o2 |
| Etichette, testi e guida per ogni cosa nuova che l'utente vede | continuo | o2, memoria storica |

## B. Operazioni e decisioni

| Voce | Stato | Chi |
|---|---|---|
| **Dispositivi**: connector Shelly con catalogo, laboratorio, messa in servizio nei due appartamenti pilota | aspetta il via del cliente (D-114) | Youssouf, revisione di o1 |
| **Ingresso dei dispositivi su GCP** (Cloud Run di ingresso, bilanciatore o cloud Shelly; firewall, certificato, dominio) | dipendenza esterna: la scelta di Youssouf (P-65) | Youssouf progetta, noi realizziamo, comandi del committente |
| **Un motore per ogni appartamento vero** sulla VM: segreto `langbrain-api-key-<id>` (P-62, punto 2), istanza con `engine-vm.sh install`, appartamento nell'app con ID uguale, verifica di connessione | procedura pronta (`docs/motore-vm.md`); da fare per ogni appartamento | committente con i comandi preparati |
| **Segreto Italianway**: `italianway-webhook-secret` ha ancora un valore provvisorio, da sostituire con quello concordato con Italianway, e il webhook va provato con loro | da fare | committente con Italianway, o1 per la prova |
| **Monitoraggio e allarmi**: oggi ci sono i controlli e gli allarmi del BFF (lotto 11); mancano gli allarmi della VM (log dei container, «nessun log da 10 minuti», D-104) | passo 10 | o1 prepara, committente lancia |
| **Avvisi di spesa** su Google Cloud: l'API dei budget non è attiva, nessun avviso di spesa | da fare (comando del committente) | memoria storica prepara |
| **Una sola istanza del server** (`maxScale 1`) perché i dimostrativi stanno in memoria: va bene per il pilota; per più traffico serve decidere se spostare i dimostrativi su un motore della VM (D-97 lo prevede) e permettere più istanze | decisione | committente |
| **Ambiente unico**: oggi «staging» e «prod» sono lo stesso servizio Cloud Run e lo stesso Firestore; i dati dei dimostrativi e quelli veri convivono. Per la produzione vera: progetto o ambiente separato, oppure regola scritta che accetta la convivenza | decisione | committente |
| **Copie di sicurezza di Firestore** (dati dell'app: utenti, organizzazioni, appartamenti, prenotazioni, registro attività) | da verificare se esistono esportazioni pianificate | memoria storica verifica, comando del committente |
| **Verifica in due passaggi** all'accesso: non attiva, richiede il passaggio a Identity Platform (D-17: dopo il pilota) | decisione | committente |
| **Email dal dominio del prodotto** al posto di Gmail (D-93: rinviata), e dominio dell'app al posto di `web.app` | decisione | committente |
| **Procedura di assistenza al gestore**: l'«accesso di assistenza» esiste nell'app (D-86); manca la procedura scritta (chi risponde, come, tempi, come si usa l'accesso di assistenza, cosa si registra) | da scrivere | memoria storica con il committente |
| **Informativa e contratto per i gestori**: conservazione dei dati (D-94) già nell'app e nella guida; informativa privacy e condizioni d'uso del servizio | da verificare / da scrivere | committente |
| **Collaudo finale**: i collaboratori con la checklist (tutte le sezioni), poi la prova da un capo all'altro con un relè vero (connector di Youssouf, laboratorio) e con i due appartamenti pilota | a fine implementazione | collaboratori, Youssouf, committente |
| **Accordi**: accettazione della proposta da parte del cliente; accordo con Youssouf (la «soglia contrattuale» del piano, §7) | in corso | committente |

## C. Cosa è già a posto

Contratto fissato e controllato dalla CI; motore sulla VM con riavvio automatico, backup giornaliero di SQLite provato e snapshot del
disco; server in modalità reale collegato alla VM dalla rete interna; chiavi in Secret Manager, nessun segreto nel repository;
conservazione dei dati automatica (D-94); registro attività, sospensione, accesso di assistenza, pseudonimi; guida e checklist
aggiornate a ogni lotto; giro completo di prove (con il controllo Linux) e CI a ogni lotto.
