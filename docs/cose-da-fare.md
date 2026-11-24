# A che punto siamo e cosa resta da fare

*Elenco unico, chiesto dal committente il 22 novembre 2026. Alla domanda «a che punto siamo» o «cosa resta da fare» si
risponde da qui. Il dettaglio resta nelle fonti della colonna «Dettaglio».*

**Aggiornato:** 23 novembre 2026 (sera), 09:31 (memoria storica).

## 1. Dove siamo oggi

| Cosa | Stato |
|---|---|
| **Produzione** | pubblicata il 23 novembre, 11:19, da `3417dcf` (revisione `domotica-bff-00037-267`); motore `dev` a `engine:3417dcf` dal 23 novembre |
| **Staging** | pubblicato il 23 novembre, 11:19, da `3417dcf` (revisione `domotica-bff-staging-00029-qtv`); `lab-01` ancora a `engine:9576073` (aggiornamento del motore a parte); immagine approvata per le creazioni `engine:3417dcf` |
| **Solo nello staging** | creazione degli appartamenti dall'app, credenziali dei dispositivi, «Prova l'agente» (in produzione con la seconda VM, voce 26); tutto il resto è anche in produzione dal 23 novembre |
| **Piano generale** (§15 del documento 1 dell'Autonomia) | passi 1–4 fatti; 5, 7, 10 e 14 in parte; gli altri aperti |
| **Ultima domanda al committente** | 1283 |

## 2. Cose da fare

Colonna «Condizione per partire»: «tempo morto» = si fa mentre si aspettano risposte di Y o di L. Colonna «Chi»: MS = memoria storica; C = committente; Y = Youssouf; L = Leonardo (Italianway); cliente = il cliente.

### A. Prossimi passi

| N. | Cosa | Condizione per partire | Chi | Stato | Dettaglio |
|---|---|---|---|---|---|
| 1 | Resoconto settimanale del rodaggio della produzione; il primo lunedì del mese anche la routine delle dipendenze (aggiornamenti di VM, Mosquitto, firmware degli Shelly, librerie), la prima il 23 novembre come punto di partenza | ogni lunedì fino alla consegna | MS | fatto il 23 novembre (settimana 16–22 novembre) con la prima routine delle dipendenze; dal 30 novembre anche il controllo che ci siano tutti i backup di Firestore e gli snapshot del disco della settimana (1278); prossimo il 30 novembre; la routine delle dipendenze il primo lunedì di dicembre (7 dicembre) | registro, D-210, 1222 |
| 2 | A6 G3: eliminazione vera di `test-a2-02` (senza ritorno indietro), poi G4–G5 | dal 28 novembre 2026, 12:53 | C, un passo alla volta | aperto | `procedura-installazione-a6.md` |
| 3 | Togliere le copie per tornare indietro: `prima-passo3` e la sua copia del disco, `prima-e38`, `~/e38`, quelle di A1, `~/a2`, `prima-a7`, `~/a7`, `prima-a5`, `~/a5` | una settimana senza problemi dopo ciascuna installazione (A7 e A5: dal 28 novembre) | MS prepara, C lancia | aperto | registro, 17–21 novembre |
| 5 | A3 Q8: «Rigenera» degli Shelly di `lab-01`, poi distruzione del vecchio segreto `langbrain-shelly-lab-01-devices` | con Y e gli Shelly accesi in ufficio | C, Y | aperto | `procedura-installazione-a3.md` |
| 47 | Verifiche dal vivo in sola lettura dell'attacco da fuori (12: memoria e limiti di Cloud Run, istanze, firewall della VM, impostazioni di Firebase…) | 3 e 9 dopo la pubblicazione | MS, C | in parte: 10 su 12 fatti il 22 novembre, la 6 (F-16) chiusa il 23 novembre con i comandi 5–6 (7, 8, 10 con il committente: Firebase a posto salvo «creazione» ed «eliminazione» attive e non usate, da spegnere dopo la verifica di o1; regole del database a posto; intestazioni a posto salvo CSP e Permissions-Policy, rinforzo di o2); la 3 (F-7) chiusa il 23 novembre nello staging (404 «Endpoint inesistente» per `%3F` e `%23`); resta la 9 (con i registri di un giorno di uso dell'assistente nello staging; tempo morto) | `VERIFICHE-DAL-VIVO.md` |
| 49 | Prova di ripristino completa su copie: dati dell'app in un database nuovo, dati di un motore su un motore di prova, fotografia del disco accesa come VM temporanea; tempi e dati persi misurati; procedura «cosa fare se» | prima della produzione; tempo morto | MS prepara, C lancia, o1 | bozza fatta il 23 novembre (`DOMOTICA/procedure-bozze/procedura-prova-ripristino-bozza.md`); decisioni 1273–1279 prese (VM temporanea in zona b, script di confronto di o1, prova anche della copia dell'ultima ora, protezione dalla cancellazione accesa prima e lasciata, controllo delle copie nel resoconto del lunedì e allarme prima della produzione, copie fuori progetto come limite noto); restano gli script di o1 e una rilettura indipendente | `produzione-cosa-manca.md` D.2 |
| 50 | Dipendenze, parte automatica: aggiornamenti di sicurezza della VM da soli con riavvio a orario fisso, Dependabot con la CI, controllo delle immagini con email | tempo morto | o2 (repository), o1, MS prepara, C lancia | Dependabot e controllo «difetti-noti» nella CI fatti (ramo `o2-dipendenze`, `c851597`); prima del push o2 aggiorna firebase (grpc-js, grave) e react-router; strumenti di sviluppo del sito (vitest, vite) da aggiornare a parte; aggiornamenti automatici della VM e controllo delle immagini dopo (o1, C) | `produzione-cosa-manca.md` D.2 |
| 51 | Manuale di manutenzione per il cliente (cosa fa il sistema da solo, email che arrivano e cosa fare, controlli mensili) | tempo morto; si consegna con la voce 27 | MS | bozza fatta il 22 novembre, parti «da completare» con le voci 49, 50, 54 | `manuale-manutenzione-bozza.md` |
| 52 | Sicurezza in appartamento: analisi scritta dei rischi (Wi-Fi, accesso fisico, Bluetooth), poi prova al banco da un portatile sul Wi-Fi del banco | prova: con Y in ufficio | Y e C | analisi fatta il 22 novembre (10 rischi, 8 prove; rischio aperto: sensore Bluetooth finto); prova da fare | `analisi-sicurezza-appartamento.md` |
| 53 | Usabilità dell'Autonomia: lettura da esperto di pagine e guida, poi prova con uno o due colleghi su compiti veri nello staging (fogli di compiti e domande della memoria storica) | lettura: tempo morto; prova: con i colleghi disponibili | MS, colleghi, C | lettura fatta il 22 novembre (53 punti: 10 alti, 31 medi, 12 bassi; voci 56–57); prova con i colleghi da fare | `DOMOTICA/revisione-usabilita/LETTURA-ESPERTO.md` |
| 54 | Prova dei ritorni indietro nello staging per ogni pezzo (server, sito, un motore, broker, agente), con i tempi; tabella «come si torna indietro» per il manuale (voce 51) | tempo morto | MS prepara, C lancia | deciso (1225 = a) | `produzione-cosa-manca.md` D.2 |
| 58 | Rinforzi del giro successivo (esclusi dal giro del 22 novembre): (a) in Firebase spegnere «Abilita creazione» ed «Abilita eliminazione», dopo che il server crea l'account dei gestori nuovi (o1, ramo a parte), il sito ha un testo per `auth/admin-restricted-operation` (o2) e la prova dal vivo con due Gmail di prova è passata; (b) CSP e Permissions-Policy (o2, ramo a parte) | dopo il giro di oggi; Firebase vale per staging e produzione insieme | o1, o2, C | (a) FATTO il 22 novembre su richiesta del committente: «Abilita creazione» ed «Abilita eliminazione» spente, prove dal vivo passate (invito con password e con Google entrano; Google senza invito rifiutato, nessun account nuovo); restano la pubblicazione di `b7921f3` (fino ad allora un gestore nuovo va creato a mano) e il testo del sito per `auth/admin-restricted-operation`; (b) CSP in Report-Only sul ramo `o2-csp-intestazioni` (`0f1bc6a`), da provare nello staging | `VERIFICHE-DAL-VIVO.md`, registro 22 novembre |
| 59 | Pulizia prima della consegna: elenco degli account Firebase con un comando in sola lettura di o1 (data di creazione, ultimo accesso, ruoli, utente nell'app); togliere gli account di prova («+prova1», «+prova3», l'invito in sospeso a «+prova4» del 23 novembre, l'account Google prestato) e quelli non più usati | prima della consegna (voce 27) | o1, C | aperto | registro, 22 novembre |
| 61 | Le richieste di aggiornamento aperte da Dependabot al primo push (circa otto: pip di bff, Actions, Docker, il gruppo del sito con 25 aggiornamenti…): valutarle una alla volta con le prove, unire quelle sicure, chiudere le altre; più il salto di react-router 6 → 7 come lavoro a parte | giro successivo; nessuna si unisce da sola | o1, o2 | aperto | GitHub, richieste «[deps]» |
| 62 | Aggiornare il motore di `lab-01` nello staging da `engine:9576073` alla versione di `main` (le due correzioni di `engine/api.py` e `engine/config.py`, come il motore `dev` il 23 novembre); prima controllo in lettura che `lab-01` non imposti `ASK_DAILY_LIMIT` sopra 100 | tempo morto; non con Y che usa `lab-01` | MS prepara, C lancia | aperto | registro, 23 novembre |
| 63 | Prova al banco 1.4: cambiare a distanza la rete di riserva di uno Shelly (`WiFi.SetConfig` con nome e password di una rete nuova, mandato dalla VM); poi, se c'è Y, spegnere la rete 1 per vedere se lo Shelly passa alla rete nuova; alla fine rimettere come riserva l'hotspot di Y (la password la scrive Y) | quando c'è una seconda rete a 2,4 GHz diversa da HQPlus-IoT e dall'hotspot di Y, con la password nota (hotspot di un collega, rete degli ospiti; sul telefono del committente l'hotspot non si trova); tempo morto | C lancia, Y | aperto (saltata il 24 novembre, risposta del committente) | `comandi-a2/y-prove-wifi.sh riserva <id>`; registro, 24 novembre |
| 64 | Decisioni nate dalle prove al banco del 24 novembre: (1) come riportare gli Shelly sulla rete 1 dopo un guasto (da soli non tornano, con un riavvio sì; una rete di riserva senza internet li lascia fuori linea): riavvio mandato dalla VM, script sullo Shelly (proposta di Y) oppure lasciarli sulla riserva; (2) da dove prendere i file del firmware per i kit (servizio di Shelly, indirizzo da chiedere per ogni modello e versione, oppure copia su un nostro server); (3) cosa fa il motore se lo stesso sensore BLU è abbinato a due ponti del catalogo; (4) soglia «segnale debole» a −80 dBm (proposta provvisoria di Y) | prima del catalogo dei dispositivi (A4) e delle guide del kit (A9) | C decide, Y e o1 propongono | aperto | email di Y del 24 novembre; registro, 24 novembre |
| 56 | Difetto: un appartamento creato dall'app non può ricevere il codice Italianway dopo la creazione (il modulo dice «Si può aggiungere anche dopo», il server rifiuta con `created_from_app`) | subito (D-198), dopo i lavori in corso | o1 (rotta), o2 (sito) | pubblicato il 23 novembre; prova dal vivo alla prossima creazione di un appartamento nello staging (Q2 della checklist) | `LETTURA-ESPERTO.md` 1.2 |
| 57 | Correzioni dell'usabilità, punti alti: guida (cosa fare se uno Shelly non si collega e non ci sono accessi rifiutati; come si apre la pagina dello Shelly), testi delle schermate (messaggi di creazione senza azione, «Pronto» che sembra «collegato», «Stato dei dispositivi» vuoto senza catalogo, finestra «Elimina» che non dice nulla di Shelly e caldaia), documento 3 allineato su chi crea ed elimina (dipende da 19.3); poi i 43 medi e bassi | punti alti: adesso; medi e bassi: tempo morto | MS e o2 concordano testi coerenti fra app e guida (1238), C per 19.3 | testi nel sito, pubblicati nello staging il 23 novembre; guida scritta con le stesse parole il 23 novembre; restano le parole del firmware con Y (pagina dello Shelly), la 19.3 e i medi e bassi | `LETTURA-ESPERTO.md` |
| 55 | Lungo periodo: elenco delle misure con le soglie, poi misure su `lab-01` nel resoconto del lunedì | elenco: tempo morto; misure: dopo che Y lascia gli Shelly di `lab-01` sempre accesi | MS, Y | elenco fatto il 22 novembre (16 misure, soglie da tarare); misure dopo che Y lascia accesi gli Shelly | `misure-lungo-periodo.md` |

### B. Obblighi prima del primo appartamento vero

| N. | Cosa | Condizione per partire | Chi | Stato | Dettaglio |
|---|---|---|---|---|---|
| 7 | Prova di carico (P-84) | di notte, prima del passaggio in produzione | C lancia | strumento pronto | `procedura-prova-di-carico.md` |
| 8 | Verifica in due passaggi all'accesso (P-69) | nessuna | o2, o1, MS, comandi di C | decisa (1263–1267); 23 novembre: upgrade a Identity Platform fatto e TOTP acceso sul progetto (P-69 passi 1–4); restano i passi 5–11 (verifiche dal vivo e pulizia con --spegni), poi il codice; prima di estenderla a tutti: l'email automatica di attivazione contiene %DISPLAY_NAME% e non si modifica (regola 1246); il codice di oggi non scrive mai il nome dell'invito in Firebase (o2, 297dd4e), ma gli account creati da inviti prima del 23 novembre possono averlo: due script di o1 (elenco in sola lettura, poi rimozione del nome) da lanciare prima dell'obbligo | registro, P-69 |
| 9 | Il sito resta vecchio dopo una pubblicazione (P-92, con E-29): avviso «versione nuova — Aggiorna» con ricaricamento automatico, più `index.html` sempre dalla rete (tolto il gestore fetch) | deciso (1227 = a); poi verifica sul telefono del committente | o2, poi C | in staging e produzione dal 23 novembre; sul telefono del committente la versione nuova arriva dopo una chiusura e riapertura (staging e, alle 11:39, anche produzione: casella «dispositivo condiviso» visibile); resta da vedere alla prossima pubblicazione il ricaricamento da solo o l'avviso «È disponibile una versione nuova» (G4, G5) | registro, P-92 |
| 11 | Procedura di assistenza al gestore: approvata (1234, 1235); da convertire in HTML | prima della produzione | MS | approvata; HTML fatto il 22 novembre (`procedura-assistenza-gestore.html`, da rigenerare se cambia: `python docs/strumenti/guida_html.py --source docs/procedura-assistenza-gestore.md --template docs/strumenti/procedura_modello.html --output docs/procedura-assistenza-gestore.html`); da rileggere dopo la risposta 19.2 del cliente | `procedura-assistenza-gestore.md` |
| 12 | Informativa privacy approvata dal consulente del titolare; condizioni d'uso (P-70) | il consulente | C | bozza fatta | `informativa-privacy-bozza.md` |
| 13 | Notifiche push provate su telefoni veri (P-11) | telefoni veri | C, colleghi | in parte | registro, P-11; `limiti-noti.md` |
| 14 | Email dal dominio del prodotto e indirizzo dell'app (P-53): il dominio lo sceglie il cliente nel passo 8 (1233 = a), poi o1 collega e MS prepara i comandi | dopo la risposta del cliente (voce 19) | cliente, poi o1, MS, C | in attesa del cliente | registro, P-53 |
| 15 | Stagione del riscaldamento per appartamento (E1, 1231 = a): due date proposte secondo la zona climatica di legge, modificabili dall'amministratore; fuori stagione niente caldaia per il comfort, antigelo sempre attivo. Caldaia rotta con il comando che funziona (E2, 1232 = a): avviso «la temperatura non risale» se la stanza resta sotto l'antigelo per un tempo regolabile con la caldaia comandata accesa | prima del primo appartamento vero | o1, o2 | unita in main il 23 novembre (`ba4833b`, con le correzioni di Python 3.11 e la chiusura ordinata del motore); CI #140 verde su `280abb1`; pubblicata nello staging il 24 novembre alle 12:35 (`5593086`); mancano aggiornamento di `lab-01` (voce 62), verifiche, testi di guida e checklist (`testi-guida/stagione-guida-checklist.md`) | `limiti-noti.md`, P-90 |
| 16 | Collaudo finale: checklist con i colleghi, relè vero, appartamenti | a fine implementazione | colleghi, Y, C | aperto | `checklist-collaudo.md` |

### C. Piano generale (Autonomia e primo appartamento)

| N. | Cosa | Condizione per partire | Chi | Stato | Dettaglio |
|---|---|---|---|---|---|
| 17 | Passo 5: prove al banco 1–7 (Matter via MQTT sulla 2.x; seconda rete Wi-Fi; orologio del ponte; versione dei sensori BLU; portata e sensori per ponte; antigelo con lo script; impianto vero) | Y in ufficio; la 6 solo se il cliente la sceglie; la 7 con caldaia e split veri | Y | in parte: foglio del 23 novembre, risultati di Y del 24 novembre (email delle 12:32): fatte 1.1–1.3, 1.6, 1.7, 2.1, 2.2, 3.1–3.5; la 1.5 fatta dal committente dalla VM (`comandi-a2/y-prove-wifi.sh`); la 1.4 rimandata (voce 63); restano 2.3, 4.1 (anche questa va mandata dalla VM), 4.2, 5.1, 6.1–6.3; decisioni nate dai risultati: voce 64 | documento 2 dell'Autonomia; registro, 24 novembre |
| 18 | Passo 7: richiudere le righe «da verificare» del documento 2 | dopo il 17 | MS | in parte | documento 2 dell'Autonomia |
| 19 | Passo 8: risposta scritta del cliente alle domande della tabella «Domande per il cliente» qui sotto (19.1–19.15) | il documento 3 è completo e consegnato (la proposta di progetto del 12 novembre è un'altra cosa) | MS prepara, C consegna, cliente risponde | domande scritte nel documento 3, §8 punti 1–14 (23 novembre; copia di prima `3-DA-CONSEGNARE-AL-CLIENTE.prima-del-23-nov.md`); restano §9 «Tempi e costi» (committente) e §10, e le righe «da verificare» del documento 2 (voce 18, dopo le prove al banco) | documento 3 dell'Autonomia |
| 20 | Passo 6: messaggio a L, poi segreto e formato delle prenotazioni di Italianway (P-9, P-10) | contratto di vendita firmato | C, L | aperto | `da-inviare/messaggio-italianway-per-leonardo.md` |
| 21 | Passo 9: lavori per il primo appartamento (infrarossi, Italianway vero, relè della caldaia, revisione del codice) | dopo il passo 8; infrarossi dopo l'acquisto | o1, o2, Y | aperto | §15 |
| 22 | Passo 11: A4, catalogo dei dispositivi, con il collaudo guidato | dopo il passo 5 | o1, o2, Y | aperto | §15, documento 2 riga 20 |
| 23 | Passo 14: guide per preparare il kit (A9) | dopo la prova al banco 7 | MS, Y | in parte (soglia A8 online) | §15 |
| 24 | Passo 12: primo appartamento attivato da noi | dopo i passi 8 e 9 e le voci 6–16 | tutti | aperto | §15.3 |
| 25 | Passo 13: mese di prove del primo appartamento | dopo il passo 12 | tutti | aperto | §15 |
| 26 | Passo 15: seconda VM (A10), poi la produzione allineata allo strumento A | poco prima della produzione; prima del secondo appartamento | o1, C | aperto | `produzione-cosa-manca.md` B |
| 27 | Passo 16: fatturazione e passaggio dei poteri al cliente (P-81, E1–E8) | prima della consegna | C, cliente | aperto | `produzione-cosa-manca.md` E |
| 28 | Passo 17: secondo appartamento attivato dal cliente, con noi accanto. **Qui abbiamo finito** | dopo tutto il resto | cliente | aperto | documento 3, §7 |

### C bis. Domande per il cliente (voce 19)

*Vanno nel documento 3 dell'Autonomia; ogni risposta scritta del cliente chiude la sua riga.*

| N. | Domanda | Da dove viene | Stato |
|---|---|---|---|
| 19.1 | Responsabilità: chi risponde di che cosa, fra cliente e HQE | piano, passo 8 | scritta nel documento 3, §8 punto 1 (23 novembre) |
| 19.2 | Assistenza ai gestori: chi la fa, con quali tempi | piano, passo 8 | scritta nel documento 3, §8 punto 2 (23 novembre) |
| 19.3 | Chi crea ed elimina gli appartamenti, e con quale numero massimo (nota tecnica: una rotta nuova di creazione per il cliente deve passare da `creation.create` e dal suo controllo dell'identificativo, prova da estendere) | D-232 | scritta nel documento 3, §8 punto 3 (23 novembre) |
| 19.4 | Chi prepara i kit dei dispositivi | piano, passo 8 | scritta nel documento 3, §8 punto 4 (23 novembre) |
| 19.5 | Relè della caldaia: una delle tre possibilità, anche «resta com'era» | §15.3, punto 4 | scritta nel documento 3, §8 punto 5 (23 novembre) |
| 19.6 | Una rete Wi-Fi solo per i dispositivi, separata da quella degli ospiti | decisione 6 della proposta | scritta nel documento 3, §8 punto 6 (23 novembre) |
| 19.7 | Fatturazione: quale strada | P-81 | scritta nel documento 3, §8 punto 14 (23 novembre) |
| 19.8 | Climatizzatori dual split (due unità su un misuratore) | P-90, S8 | scritta nel documento 3, §8 punto 8 (23 novembre) |
| 19.9 | Acquisto del trasmettitore a infrarossi e di un climatizzatore su cui provarlo | decisione 1141 | scritta nel documento 3, §8 punto 7 (23 novembre) |
| 19.10 | Antigelo: minuti di attesa e sensore H&T muto | risposte di Youssouf | scritta nel documento 3, §8 punto 5 (23 novembre) |
| 19.11 | Manutenzione dopo la consegna: del cliente; assistenza HQE facoltativa a pagamento | 1222 | scritta nel documento 3, §8 punto 13 (23 novembre) |
| 19.12 | Check-out con movimento: tenere la domanda al gestore come oggi, o passare sempre a casa vuota come nella proposta | P-88, 1229 | scritta nel documento 3, §8 punto 9 (23 novembre) |
| 19.13 | Consumi alti durante le pulizie: le pulizie usano prese comandate? | 1230 | scritta nel documento 3, §8 punto 10 (23 novembre) |
| 19.14 | Dominio dell'app e delle email (il marchio del cliente) | P-53, 1233 | scritta nel documento 3, §8 punto 12 (23 novembre) |
| 19.15 | Quante persone collegate insieme all'app prevedete? Oggi il limite è circa 600 in produzione (200 per istanza, fino a 3 istanze) | rilettura dei bassi, B-9 | scritta nel documento 3, §8 punto 11 (23 novembre) |

### D. Manutenzione e residui

| N. | Cosa | Condizione per partire | Chi | Stato | Dettaglio |
|---|---|---|---|---|---|
| 29 | Rimettere il permesso DNS per il rinnovo del certificato | quando `cert_days` scende a 35 (primi di gennaio 2027) | MS prepara, C lancia | aperto | `procedura-permesso-dns.md` |
| 30 | Leggere le novità di Mosquitto 3.0 | prima di aggiornare il broker | o1 | letto il 23 novembre (3.0 non uscita; servono i plugin al posto di tre opzioni; broker già 2.1.2): resta il passaggio ai plugin, provato nello staging, prima di aggiornare il broker; conviene fissare il digest della 2.1.4 (corregge anche i controlli di max_packet_size) | `limiti-noti.md` |
| 31 | Riverificare il fermo E-27 con stream aperti | da decidere | o1 | aperto | `limiti-noti.md` |
| 32 | P-82: benestare di Y su «PER SCARANTINO», poi consegna al cliente | Y | C, Y | in parte | registro, P-82 |
| 33 | Colonne superate allineate (§15.1, documento 2, `produzione-cosa-manca.md`, `limiti-noti.md`, tabelle degli errori e P): restano due verifiche con o1 | nessuna | MS | fatto il 22 novembre; resta da verificare con o1 una riga di `limiti-noti.md` (risposte a nome di un altro dispositivo attive sulla VM); R1 chiusa il 22 novembre | controllo del 22 novembre |

### E. Idee e decisioni senza scadenza

| N. | Cosa | Condizione per partire | Chi | Stato | Dettaglio |
|---|---|---|---|---|---|
| 34 | App in inglese (P-85, P-19) | decisione | C | stima consegnata | registro |
| 35 | Ruolo «Ospite» (P-87) | manca la stima di o1 | C | idea | registro |
| 36 | Modello di vendita A e B (P-86) | — | C | idea | registro |
| 37 | Motore a eventi (P-89) | dopo la prova di carico | C | aperto | registro |
| 38 | Messa in servizio dall'app per il tecnico del cliente (P-91) | prima del secondo appartamento | C, Y | aperto | registro |
| 39 | Istruzioni per iPhone con le schermate (P-74) | quando c'è un iPhone | MS | aperto | registro |
| 40 | Riepilogo giornaliero per i gestori (P-55) | dopo P-53 | o1, o2 | aperto | registro |
| 41 | Misura della durata dello stream attraverso Hosting (P-46) | con l'ok del committente (`lab-01` ora c'è) | o1 | aperto | registro |
| 42 | App negli store Android e iOS | decisione | C | domanda del 21 novembre | registro, 22 novembre |
| 43 | Autonomia «spinta»: opzioni 2 e 3, scrittura automatica delle credenziali | decisione; «non si fa ora» (16 novembre) | C | non pianificata | documento 1, §13–14 |

## 3. Come si tiene aggiornato

1. **Ogni commit [reg]** che apre, chiude o cambia lo stato di una voce aggiorna questo file nello stesso commit.
2. **Una voce nuova** in qualsiasi fonte (punto P, errore «da pubblicare», riga D.2, passo del piano, limite da
   correggere) entra qui subito.
3. **Ogni lunedì**, con il resoconto settimanale, la memoria storica rilegge le fonti e corregge le differenze.
4. **Una voce chiusa** si toglie da qui; resta nel registro.
5. **Documenti da consegnare** ad altri (cliente, utenti, tester, Leonardo, Youssouf, Luca, consulente): elenco a parte in
   `DOMOTICA/da-consegnare/ELENCO.md` (risposta 1272 = a). Alla domanda «cosa resta» si risponde anche da lì.
5. **Fonti del dettaglio:** `registro.md`; §15 di `documenti-interni/autonomia/1-INTERNO-analisi-e-stime.md`;
   `documenti-interni/autonomia/2-INTERNO-da-confermare-prima-della-consegna.md`; `produzione-cosa-manca.md`;
   `limiti-noti.md`.
