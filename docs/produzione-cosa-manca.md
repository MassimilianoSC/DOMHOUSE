# Cosa manca per la produzione vera

*Elenco chiesto dal committente il 21 ottobre 2026 (D-133). È la lista che decide quando si smette di chiamare l'app «pilota».
Si aggiorna a ogni lotto; lo stato di ogni voce è quello del registro. «Da verificare» = non ancora controllato.*

> **Aggiornato il 10 novembre 2026** dopo l'analisi indipendente P-82, che aveva trovato voci superate. Le voci
> cambiate citano la decisione; le altre restano come al 21 ottobre e vanno rilette con il registro.

## A. Codice (poco)

| Voce | Stato | Chi |
|---|---|---|
| Passo 7 del motore: conferma a consumo, collegamenti del catalogo, connector giù/su, parametri per appartamento (D-131, D-133) | fatto, online con il lotto 19 (21 ottobre) | o1 |
| Passo 8: approvazioni da fonti vere (check-out con presenza, consumo a casa vuota, D-137), con coda e scadenza persistente | fatto, lotto 20 in pubblicazione (21 ottobre) | o1 |
| Passo 9: assistente vero con Gemini, limiti, tetto di spesa, regole fisse del prompt (D-132) | fatto (`bff/ai_gateway.py`, modello D-187) | o1, o2 |
| Passo 10: stato di salute completo e allarmi dai log dei container sulla VM (D-148: VM muta, motore muto, errori, backup mancato, disco) | fatto lato codice (lotto 23, 21 ottobre); comandi a fine piano (`docs/motore-vm.md` E2) | o1, comandi del committente |
| Passo 11: riassunto settimanale per il gestore con push e pagina (D-133) | fatto (`bff/weekly_summary.py`) | o1, o2 |
| Passo 12: regole configurabili dall'app, prima a mano poi proposte dall'assistente (D-133) | da progettare dopo l'11 | o1, o2 |
| Etichette, testi e guida per ogni cosa nuova che l'utente vede | continuo | o2, memoria storica |

## B. Operazioni e decisioni

| Voce | Stato | Chi |
|---|---|---|
| **Dispositivi**: connector Shelly con catalogo, laboratorio, messa in servizio nei due appartamenti pilota | aspetta il via del cliente (D-114) | Youssouf, revisione di o1 |
| **Ingresso dei dispositivi su GCP** (Cloud Run di ingresso, bilanciatore o cloud Shelly; firewall, certificato, dominio) | deciso e installato: MQTT con broker sulla VM, `mqtt.dh-lab.eu:8883`, indirizzo pubblico con firewall sulla sola 8883 (D-196, D-209, D-212); manca la prova con uno Shelly vero | Youssouf progetta, noi realizziamo, comandi del committente |
| **Un motore per ogni appartamento vero** sulla VM: segreto `langbrain-api-key-<id>` (P-62, punto 2), istanza con `engine-vm.sh install`, appartamento nell'app con ID uguale, verifica di connessione | procedura pronta (`docs/motore-vm.md`); da fare per ogni appartamento | committente con i comandi preparati |
| **Segreto Italianway**: `italianway-webhook-secret` ha ancora un valore provvisorio, da sostituire con quello concordato con Italianway, e il webhook va provato con loro | da fare | committente con Italianway, o1 per la prova |
| **Monitoraggio e allarmi**: controlli e allarmi del BFF (lotto 11); allarmi dei motori sulla VM pronti nel codice (passo 10, D-148): si attivano con i tre comandi di `docs/motore-vm.md` E2 | comandi a fine piano | committente lancia |
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
| **Accordi**: accettazione della proposta da parte del cliente; accordo con Youssouf (la «soglia contrattuale» del piano, §7) | in corso | committente |

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
| **Sicurezza dentro la VM** (compromissione e movimenti laterali) | se un motore, il broker o un dispositivo sono ostili, fin dove arrivano? | **deciso (risposta 1130 = a):** pochi agenti in sola lettura più un verificatore, dopo l'applicazione delle correzioni di E-31, E-32 ed E-33 e prima del primo appartamento vero |
| **Prova di carico** (P-84) | quante persone e appartamenti regge il sistema insieme? | prevista, procedura pronta (`docs/procedura-prova-di-carico.md`); da fare |
| **Attacco da fuori al sito e al server** | accessi non autorizzati, iniezioni, CORS, limiti di frequenza, sessioni: cosa può fare uno sconosciuto da internet? | da analizzare |
| **Ripristino vero dalle copie** | se si perde il database o il disco della VM, si torna indietro davvero, in quanto tempo e con quali dati? | da analizzare (o1 ha stimato una prova di ripristino sul motore di produzione) |
| **Dipendenze e aggiornamenti di sicurezza** | librerie, immagini dei container e firmware degli Shelly con difetti noti: chi li controlla e quando? | da analizzare |
| **Dati personali** | l'informativa e i trattamenti sono corretti per il titolare? | bozza pronta; manca il consulente del titolare |
| **Sicurezza in appartamento** | un ospite sulla rete Wi-Fi di casa può aprire la pagina di uno Shelly o disturbare i dispositivi? | da analizzare (collegata alla rete solo per i dispositivi, decisione 6 della proposta) |
| **Usabilità per chi non è tecnico** | gestori, operatori e cliente capiscono l'app e le guide senza aiuto? | in parte (collaudo dei colleghi, D-200); da analizzare per l'Autonomia |
| **Aggiornamenti e ritorni indietro** | una pubblicazione sbagliata si annulla davvero, anche sui motori e sul broker? | da analizzare |
| **Lungo periodo con dispositivi veri** | batterie, orologi, disconnessioni, firmware dopo settimane | coperto dal mese di prove del primo appartamento; da scrivere cosa si misura |

**Regola da qui in avanti:** quando un controllo trova un difetto di un tipo nuovo, si aggiunge una riga in D.2 per quel
tipo, e si valuta se ripetere quel controllo su tutto il sistema.
