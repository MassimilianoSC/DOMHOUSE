# Cosa manca per la produzione vera

*Elenco chiesto dal committente il 21 ottobre 2026 (D-133). È la lista che decide quando si smette di chiamare l'app «pilota».
Si aggiorna a ogni lotto; lo stato di ogni voce è quello del registro. «Da verificare» = non ancora controllato.*

> **Colonne di stato riallineate il 22 novembre 2026** (controllo del registro; lo stato di ogni giorno è in
> `cose-da-fare.md`).
>
> **Aggiornato il 10 novembre 2026** dopo l'analisi indipendente P-82, che aveva trovato voci superate. Le voci
> cambiate citano la decisione; le altre restano come al 21 ottobre e vanno rilette con il registro.

## A. Codice (poco)

| Voce | Stato | Chi |
|---|---|---|
| Passo 7 del motore: conferma a consumo, collegamenti del catalogo, connector giù/su, parametri per appartamento (D-131, D-133) | fatto, online con il lotto 19 (21 ottobre) | o1 |
| Passo 8: approvazioni da fonti vere (check-out con presenza, consumo a casa vuota, D-137), con coda e scadenza persistente | fatto, lotto 20 in pubblicazione (21 ottobre) | o1 |
| Passo 9: assistente vero con Gemini, limiti, tetto di spesa, regole fisse del prompt (D-132) | fatto (`bff/ai_gateway.py`, modello D-187) | o1, o2 |
| Passo 10: stato di salute completo e allarmi dai log dei container sulla VM (D-148: VM muta, motore muto, errori, backup mancato, disco) | fatto: comandi E2.2, E2.3 e M3b lanciati il 22 ottobre, cinque allarmi «Motori: …» attivi | o1, comandi del committente |
| Passo 11: riassunto settimanale per il gestore con push e pagina (D-133) | fatto (`bff/weekly_summary.py`) | o1, o2 |
| Passo 12: regole configurabili dall'app, prima a mano poi proposte dall'assistente (D-133) | fatto (D-151) | o1, o2 |
| Etichette, testi e guida per ogni cosa nuova che l'utente vede | continuo | o2, memoria storica |

## B. Operazioni e decisioni

| Voce | Stato | Chi |
|---|---|---|
| **Dispositivi**: connector Shelly con catalogo, laboratorio, messa in servizio nei due appartamenti pilota | aspetta il via del cliente (D-114) | Youssouf, revisione di o1 |
| **Ingresso dei dispositivi su GCP** (Cloud Run di ingresso, bilanciatore o cloud Shelly; firewall, certificato, dominio) | deciso e installato: MQTT con broker sulla VM, `mqtt.dh-lab.eu:8883`, indirizzo pubblico con firewall sulla sola 8883 (D-196, D-209, D-212); provato con la Plug (tappa B, 13 novembre) e con gli Shelly Gen4 di `lab-01` con TLS | Youssouf progetta, noi realizziamo, comandi del committente |
| **Un motore per ogni appartamento vero** sulla VM: segreto `langbrain-api-key-<id>` (P-62, punto 2), istanza con `engine-vm.sh install`, appartamento nell'app con ID uguale, verifica di connessione | procedura pronta (`docs/motore-vm.md`); da fare per ogni appartamento | committente con i comandi preparati |
| **Segreto Italianway**: `italianway-webhook-secret` ha ancora un valore provvisorio, da sostituire con quello concordato con Italianway, e il webhook va provato con loro | da fare | committente con Italianway, o1 per la prova |
| **Monitoraggio e allarmi**: controlli e allarmi del BFF (lotto 11); allarmi dei motori sulla VM pronti nel codice (passo 10, D-148): si attivano con i tre comandi di `docs/motore-vm.md` E2 | fatto il 22 ottobre; in più gli allarmi di A7 (memoria e numero dei motori, 21 novembre) | — |
| **Avvisi di spesa** su Google Cloud | fatto: budget di 50 € con avvisi al 50, 90 e 100 % (D-134), più quello precedente da 100 € | memoria storica prepara |
| **Istanze del server** | risolto: fino a 3 istanze in produzione, dimostrativi tolti dalla produzione, notifiche e lavori a orario senza doppioni (D-201, D-202) | — |
| **Ambienti separati** | risolto: staging e produzione sono due servizi Cloud Run e due database Firestore nello stesso progetto (D-134, D-136); la produzione si pubblica solo con il commit dello staging (D-203) | — |
| **Copie di sicurezza di Firestore** (dati dell'app: utenti, organizzazioni, appartamenti, prenotazioni, registro attività) | esistono: copia giornaliera conservata 14 giorni (verificato il 21 ottobre, D-134) | nessuno |
| **Verifica in due passaggi** all'accesso: passaggio a Identity Platform e codice via app di autenticazione, obbligatoria per amministratori e gestore della piattaforma (D-141, P-69; SMS solo se i gestori reali lo chiederanno) | decisa; da fare dopo P-67 e prima del primo appartamento vero (3–3,5 giornate) | o2, o1, memoria storica, comandi del committente |
| **Email dal dominio del prodotto** al posto di Gmail (D-93: rinviata), e dominio dell'app al posto di `web.app` | decisione | committente |
| **Procedura di assistenza al gestore**: l'«accesso di assistenza» esiste nell'app (D-86); manca la procedura scritta (chi risponde, come, tempi, come si usa l'accesso di assistenza, cosa si registra) | da scrivere | memoria storica con il committente |
| **Informativa e contratto per i gestori**: conservazione dei dati (D-94) già nell'app e nella guida; informativa privacy in bozza (`docs/informativa-privacy-bozza.md`, P-70: titolare l'organizzazione che gestisce gli appartamenti, responsabile HQE) da far approvare al consulente del titolare; condizioni d'uso del servizio da scrivere | bozza dell'informativa fatta; dati societari e condizioni d'uso | committente |
| **Dati personali, due correzioni** (D-142, P-71) | fatte (log di accesso del server spento, pulizia dei file di ripristino sulla VM) | — |
| **Collaudo finale**: i collaboratori con la checklist (tutte le sezioni), poi la prova da un capo all'altro con un relè vero (connector di Youssouf, laboratorio) e con i due appartamenti pilota | a fine implementazione | collaboratori, Youssouf, committente |
| **Accordi**: accettazione della proposta da parte del cliente; accordo con Youssouf (la «soglia contrattuale» del piano, §7) | proposta di progetto inviata al cliente il 12 novembre; la «soglia contrattuale» con Youssouf è decaduta | committente |
| **Allineare la produzione con lo strumento A (Autonomia)**: oggi l'agente della VM (A1) e le sue code esistono **solo per lo staging** (code `domhouse-staging-*`, variabili `AGENT_*` solo in `bff/cloudrun.staging.yaml`, agente con `AMBIENTE=staging`; sulla VM condivisa la produzione non manda ordini, §5.4). Per la produzione: seconda VM (A10, passo 15 del piano), poi `agent-gcp.sh prod` con i suoi controlli e gli elenchi chiusi degli ammessi, variabili `AGENT_*` in `bff/cloudrun.yaml`, agente installato sulla VM di produzione, prova con il pulsante | da fare con A10 (richiesta del committente del 17 novembre: «non ci dimenticheremo di allineare la produzione») | o1, comandi del committente |

## C. Cosa è già a posto

Contratto fissato e controllato dalla CI; motore sulla VM con riavvio automatico, backup giornaliero di SQLite provato e snapshot del
disco; server in modalità reale collegato alla VM dalla rete interna; chiavi in Secret Manager, nessun segreto nel repository;
conservazione dei dati automatica (D-94); registro attività, sospensione, accesso di assistenza, pseudonimi; guida e checklist
aggiornate a ogni lotto; giro completo di prove (con il controllo Linux) e CI a ogni lotto.

## D. Controlli fatti e controlli ancora da analizzare

*Aggiunta il 15 novembre 2026 su richiesta del committente (risposta 1130). Motivo: tre difetti di sicurezza dentro
la VM (E-31, E-32, E-33) non erano stati trovati da nessuno dei controlli precedenti, perché nessuno aveva il compito
di cercarli. Un tipo di controllo mai fatto è un punto cieco, anche quando gli altri controlli sono stati molti.*

### D.1 Controlli già fatti

| Controllo | Quando | Cosa guardava | Cosa NON guardava |
|---|---|---|---|
| **Revisione avversaria di P-36** (Fable) | 16 ottobre | il codice delle organizzazioni multiple, da avversario | il resto del sistema |
| **Analisi del design** | 23 ottobre | coerenza del progetto (`docs/analisi-design-2026-10-23.md`) | il codice e l'infrastruttura |
| **Spiegazione operativa P-82** | 10 novembre | il percorso dal sensore all'interfaccia; ha trovato 5 difetti veri, anche se non era il suo scopo | non era una revisione |
| **Revisione del codice con agenti indipendenti P-83** | 10–11 novembre | errori del codice di sito, server e motore, con verifiche; in più l'infrastruttura **vista da fuori**: permessi di Google, firewall, segreti, account | la separazione **dentro** la VM: cosa raggiunge un programma compromesso |
| **Revisione per scenari P-90** | 13 novembre | il comportamento nei casi della vita reale (finestra, prenotazioni, telecomando, limiti): errori di logica | la sicurezza |
| **Revisioni delle pull request di Youssouf**, con revisori indipendenti e mutazioni | 11–15 novembre | il codice del connector, una modifica alla volta, e la forza delle sue prove | il resto del sistema |
| **Revisioni indipendenti delle procedure** (tappa B e altre) | 13 novembre | che i comandi dati al committente siano giusti e sicuri | il codice |
| **Revisione di sicurezza del progetto dello strumento A**, due letture | 15 novembre | il progetto dell'Autonomia, da avversario; ha trovato **per caso** E-31, E-32 ed E-33, che esistevano già | il codice esistente, salvo dove serviva al progetto |
| **Prove automatiche**: giro completo (circa 2700 prove: server, Firestore, broker, motore, conformità, sito, browser, Linux) e CI sul contratto | a ogni lotto | che il codice faccia quello che le prove descrivono | quello che le prove non descrivono |
| **Prove a mano nello staging** e checklist di collaudo | a ogni lotto, 13 novembre | quello che vede chi usa l'app | sicurezza e carico |
| **Prove sull'infrastruttura**: due istanze del server (9 nov), spegnimento e riaccensione della VM (11 nov), certificato del broker rinnovato e revocato (10 nov), scansione delle porte da fuori (10 nov) | 9–11 novembre | che il sistema regga quelle situazioni | la compromissione di un pezzo |
| **Prove con dispositivi veri**: tappa A (verifiche 1 e 2), tappa B (la Plug vista e comandata dall'app) | 11–13 novembre | il collegamento vero fra app e dispositivi | il lungo periodo e gli appartamenti veri |
| **Produzione in rodaggio**, con il rapporto settimanale | dal 9 novembre | come si comporta la produzione nel tempo | i casi che in rodaggio non capitano |

### D.2 Obbligo prima della produzione vera: analizzare i tipi di controllo non ancora fatti

**Prima del primo appartamento vero**, per ognuno dei tipi qui sotto la memoria storica, con o1 e o2, scrive in questa
sezione: se va fatto, con quale ampiezza, chi lo fa, oppure perché non serve. Il committente decide. Nessun tipo resta
senza una decisione scritta. Il primo è già deciso.

| Tipo di controllo | Domanda a cui risponde | Stato |
|---|---|---|
| **Sicurezza dentro la VM** (compromissione e movimenti laterali) | se un motore, il broker o un dispositivo sono ostili, fin dove arrivano? | **fatto il 17 novembre** (risposta 1130 = a, passo 3 del piano): pochi agenti in sola lettura più un verificatore, dopo le correzioni di E-31, E-32 ed E-33; esito «nessun problema grave» (`DOMOTICA/controllo-vm-17nov/ESITO-CONTROLLO-SICUREZZA-VM.md`) |
| **Prova di carico** (P-84) | quante persone e appartamenti regge il sistema insieme? | prevista, procedura pronta (`docs/procedura-prova-di-carico.md`); da fare |
| **Attacco da fuori al sito e al server** | accessi non autorizzati, iniezioni, CORS, limiti di frequenza, sessioni: cosa può fare uno sconosciuto da internet? | **deciso (risposta 1219 = a, 22 novembre):** revisione da avversario in sola lettura (mappa delle porte del server, tre revisori indipendenti, un verificatore), poi per ogni difetto confermato una prova automatica che rifà l'attacco e la correzione; esito nella guida, parte 1 |
| **Ripristino vero dalle copie** | se si perde il database o il disco della VM, si torna indietro davvero, in quanto tempo e con quali dati? | **deciso (risposta 1221 = a, 22 novembre):** prova completa su copie che non toccano niente di vero (dati dell'app in un database nuovo e confronto; dati di un motore su un motore di prova; fotografia del disco accesa come VM temporanea e poi cancellata), con tempi e dati persi misurati e la procedura «cosa fare se»; si fa prima della produzione, nei tempi morti in attesa di Youssouf o di L |
| **Dipendenze e aggiornamenti di sicurezza** | librerie, immagini dei container e firmware degli Shelly con difetti noti: chi li controlla e quando? | **deciso (risposta 1222 = a, 22 novembre):** (1) automatico dove è sicuro: aggiornamenti di sicurezza della VM ogni notte con riavvio a orario fisso, Dependabot su GitHub con la CI, controllo delle immagini su Google Cloud con email; il firmware degli Shelly solo dopo una prova; (2) manuale di manutenzione per il cliente, consegnato con il passaggio dei poteri; (3) responsabilità della manutenzione dopo la consegna scritta nella proposta al cliente (del cliente; assistenza HQE facoltativa a pagamento); (4) fino alla consegna, routine mensile della memoria storica con il resoconto del lunedì. (1) e (2) nei tempi morti |
| **Dati personali** | l'informativa e i trattamenti sono corretti per il titolare? | bozza pronta; manca il consulente del titolare |
| **Sicurezza in appartamento** | un ospite sulla rete Wi-Fi di casa può aprire la pagina di uno Shelly o disturbare i dispositivi? | **deciso (risposta 1223 = a, 22 novembre):** analisi scritta dei rischi (Wi-Fi, accesso fisico, Bluetooth) con le difese già decise, poi prova al banco con Youssouf da un portatile sul Wi-Fi del banco (pagine degli Shelly, comandi, sensore finto); ciò che passa diventa un difetto o una regola della guida del kit. Collegata alla rete solo per i dispositivi, decisione 6 della proposta |
| **Usabilità per chi non è tecnico** | gestori, operatori e cliente capiscono l'app e le guide senza aiuto? | in parte (collaudo dei colleghi, D-200); da analizzare per l'Autonomia |
| **Aggiornamenti e ritorni indietro** | una pubblicazione sbagliata si annulla davvero, anche sui motori e sul broker? | da analizzare |
| **Lungo periodo con dispositivi veri** | batterie, orologi, disconnessioni, firmware dopo settimane | coperto dal mese di prove del primo appartamento; da scrivere cosa si misura |

**Regola da qui in avanti:** quando un controllo trova un difetto di un tipo nuovo, si aggiunge una riga in D.2 per quel
tipo, e si valuta se ripetere quel controllo su tutto il sistema.

## E. Da fare alla consegna al cliente (passaggio del progetto)

*Sezione aggiunta il 17 novembre 2026 su richiesta del committente: «è bene che queste informazioni siano salvate in un
file (del tipo: da fare alla vendita al cliente)». È il dettaglio della voce P-81 del registro e del passo 16 del piano
generale. Si fa prima della consegna; fino ad allora paga e amministra il committente.*

**Chi ha i poteri oggi:** una sola persona, il committente (`m.scardovellicrac@gmail.com`). Alla consegna i poteri passano
a una persona del cliente.

| N. | Che cosa passa | Oggi | Alla consegna | Stato |
|---|---|---|---|---|
| E1 | **Proprietario del progetto Google Cloud** (`domotica-poc-511707`) | il committente | la persona del cliente | da fare |
| E2 | **Chi può mandare ordini all'agente sulla VM** (Autonomia, A1): elenco `PERSONE_AMMESSE` in `scripts/agent-gcp.sh` | solo il committente | la persona del cliente: si cambia il nome e si rilancia `agent-gcp.sh`, i cui controlli verificano il nuovo elenco. I sette account di Google e Firebase ammessi con la risposta 1151 restano | da fare |
| E3 | **Accesso alla VM** (OS Login e tunnel IAP) | il committente | la persona del cliente | da fare |
| E4 | **Firebase** (accessi all'app, sito, notifiche) | il committente | la persona del cliente | da fare |
| E5 | **GitHub** (repository `MassimilianoSC/DOMHOUSE`, Youssouf collaboratore) | il committente | da decidere: passaggio del repository o copia per il cliente | da fare |
| E6 | **Fatturazione** (account di fatturazione Google Cloud o organizzazione del cliente; budget e avvisi di spesa da rifare; i crediti non passano) | paga il committente | paga il cliente | da fare (P-81) |
| E7 | **Email degli allarmi** | `m.cracchiolo@hqe.it` | probabilmente il cliente | da decidere (P-81) |
| E8 | **Elenchi chiusi dei «robot» di Google ammessi** in `scripts/agent-gcp.sh`: chi può impersonare il server (7, risposta 1151) e chi può pubblicare sulla coda degli ordini (5, risposta 1152). I nomi contengono il numero del progetto (444239063209) | scritti per il progetto di oggi | se il progetto resta lo stesso, non cambiano; se il cliente usa un progetto nuovo, cambiano tutti: si rilancia `agent-gcp.sh`, che si ferma e mostra i nomi nuovi, e si decide di nuovo | da verificare alla consegna |
| E9 | **Ruolo `cloudbuild.builds.builder` tolto al vecchio robot di Cloud Build** (`<numero>@cloudbuild.gserviceaccount.com`, risposta 1152): le nostre costruzioni usano `domotica-build@` | tolto il 17 novembre | se il cliente usa un progetto nuovo, ripetere (il vecchio robot riceve quel ruolo alla creazione) | da ripetere solo con un progetto nuovo |

**Da decidere con il cliente:**

1. chi è la sua persona con i poteri;
2. se il committente resta con un accesso di assistenza, e con quali poteri (D-225);
3. quando si fa il passaggio e come si verifica che tutto funzioni dopo.
