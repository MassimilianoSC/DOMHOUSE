# Guida all'app DOMHOUSE

Per chi usa l'app e per chi la collauda. Non servono conoscenze tecniche.
*Versione del 16 ottobre 2026, ambiente di prova (staging).*

L'app serve a chi gestisce appartamenti in affitto breve: vedere e comandare riscaldamento, clima e luci, controllare i
consumi, approvare le azioni proposte dal sistema automatico e gestire chi può accedere.

> **Ambiente di prova.** Oggi gli appartamenti sono simulati: nessun dispositivo reale viene acceso o spento. Lo stato
> degli appartamenti simulati riparte da zero ogni volta che l'app viene aggiornata.

---

## Chi fa cosa nel servizio

*Decisione del 16 ottobre 2026, attiva dal 16 ottobre.*

**Attivare un nuovo appartamento**
1. **Flatsharing**, il gestore degli appartamenti, installa sensori e dispositivi nell'appartamento e lo comunica a
   HQE.
2. **HQE** prepara il sistema domotico dell'appartamento e lo attiva nell'app, inserendo anche il codice Italianway
   (il codice con cui arrivano le prenotazioni).
3. Da quel momento l'appartamento compare nell'elenco di Flatsharing. L'amministratore di Flatsharing gli dà nome e
   indirizzo, sceglie le funzioni attive e decide chi può vederlo.

L'amministratore di Flatsharing **non può creare da solo un appartamento, né cambiarne il collegamento al sistema
domotico o il codice Italianway**: lo fa solo HQE. È una garanzia di sicurezza: nessuno può collegare un appartamento a
un sistema che non è il suo, né ricevere le prenotazioni di una struttura altrui. Vale anche nell'ambiente di prova: gli appartamenti
**simulati** per il collaudo li crea HQE, da Organizzazioni.

**Organizzazioni**
- Ogni azienda che usa l'app è un'**organizzazione** separata, con i suoi utenti e i suoi appartamenti: nessuna vede
  quelli delle altre. Oggi c'è una sola organizzazione, **Flatsharing**.
- Chi ha il ruolo di **gestore della piattaforma** (oggi HQE) crea nuove organizzazioni dall'app, dà loro un nome e
  invita via email il primo amministratore. Può dare lo stesso ruolo ad altre persone, sempre dall'app.
- Il gestore della piattaforma vede l'elenco delle organizzazioni e i dati di base dei loro appartamenti (nome e
  collegamento al sistema domotico). **Non vede** dispositivi, consumi, decisioni né utenti delle organizzazioni.
- Gli amministratori delle organizzazioni continuano a usare l'app esattamente come oggi.

## Parole usate in questa guida

- **Codice Italianway**: il codice con cui il sistema di prenotazioni Italianway riconosce una struttura. L'app lo usa
  per far arrivare a ogni appartamento le sue prenotazioni (ospiti e date). Chi lo inserisce decide dove vanno quelle
  prenotazioni: per questo lo inserisce solo HQE.
- **Collegamento al sistema domotico**: l'indirizzo del sistema che comanda davvero i dispositivi di un appartamento.
  Nell'ambiente di prova è `mock://builtin`, cioè un sistema simulato.
- **Organizzazione**: un'azienda che usa l'app, con i suoi utenti e i suoi appartamenti (oggi Flatsharing).
- **Gestore della piattaforma**: chi gestisce il servizio per tutte le organizzazioni (oggi HQE).

## Novità del 20 e 21 ottobre 2026

*Attive dal 21 ottobre 2026. Le sezioni 5 e 7 le descrivono per esteso.*

- **Regole complete** (sezione 5, Regole): otto regole automatiche con interruttore e valori modificabili, dall'antigelo
  all'antimuffa a casa vuota, fino all'avviso di dispositivo offline.
- **Caldaia**: lo stato è «Riscaldamento abilitato» / «Riscaldamento disabilitato», il pulsante «Attiva» / «Disattiva»;
  «sta scaldando ora» quando il misuratore segna più di 30 W. Il termostato la regola da solo intorno alla temperatura
  voluta; a casa vuota l'antigelo la accende sotto la soglia.
- **Forzature**: prima di forzare con una finestra aperta l'app avvisa; durante la forzatura la finestra aperta non spegne
  il clima e la regola riparte alla scadenza.
- **Decisioni**: ogni decisione mostra il tipo di azione in italiano. Tre tipi nuovi: «Collegamento ai dispositivi
  perso», «Collegamento ai dispositivi ripristinato», «Comando non verificato: misuratore offline».
- **Comandi confermati dal consumo**: l'accensione o lo spegnimento di un climatizzatore comandato a infrarosso è
  confermata dal suo misuratore entro una decina di secondi; se il misuratore non risponde, il comando risulta «non
  verificato».
- **Approvazioni che il sistema fa da solo**: «Mettere l'appartamento a vuoto dopo il check-out» (se c'è stato movimento
  dopo l'orario di partenza) e «Spegnere …» di un apparecchio che consuma a casa vuota (sezione 5, Approvazioni).
- **Notifiche «Prenotazioni»**: nuova categoria di avvisi, per le prenotazioni che cambiano il programma
  dell'appartamento (per esempio una disdetta dopo il pre-arrivo).
- **Consumi veri**: i numeri vengono dai misuratori, ora per ora; sotto il grafico «Consumi disponibili dal …»; nell'Excel
  le ore prima di quella data restano vuote.
- **Simulatore**: nei dimostrativi c'è il «Misuratore clima» separato dal climatizzatore, e la sezione «Movimento» con il
  pulsante «Simula movimento».
- **Riepilogo settimanale**: ogni lunedì mattina l'app prepara per ogni appartamento il riepilogo della settimana appena
  finita: consumi confrontati con le settimane prima, dispositivi spenti da più di un giorno, approvazioni scadute senza
  risposta, finestre aperte spesso con il clima acceso. Se c'è qualcosa da segnalare arriva l'avviso «Riepilogo»
  (pagina «Riepiloghi» dell'appartamento).
- **Assistente vero** (dopo la pubblicazione): risponde leggendo stati, consumi e Decisioni e agisce con le stesse regole
  di un operatore (sezione 5, Assistente).
- **Ambiente di prova** (dopo la separazione degli ambienti): i dimostrativi passano nel sito di prova, con la fascia
  gialla in alto; il sito vero resta per gli appartamenti veri (sezione 7).

---

## Novità del 16 ottobre 2026

*Novità controllate da una revisione di sicurezza indipendente e attive dal 16 ottobre 2026.*

- **Organizzazioni**: arriva la gestione di più organizzazioni (vedi «Chi fa cosa» e la sezione 6b).
- **Codice Italianway**: lo inserisce solo HQE, quando attiva l'appartamento. L'amministratore lo vede ma non lo
  cambia: se è sbagliato, scrive all'assistenza.
- **Nome dell'organizzazione**: lo cambia solo HQE.
- **Cambio di ruolo**: quando un amministratore cambia il ruolo di una persona, l'app la fa uscire da tutti i
  dispositivi entro un minuto; rientrando ha il ruolo nuovo. Se intanto stava guardando un appartamento che non può più
  vedere, la pagina smette di aggiornarsi.
- **Notifiche su un dispositivo condiviso**: se la sessione di una persona viene chiusa, anche da un altro dispositivo,
  quel telefono o computer smette di ricevere le sue notifiche; chi entra dopo non le riceve mai. Se l'app si apre senza
  rete, o il server ha un problema passeggero, le notifiche restano attive.
- **«Elimina il mio account»** cancella davvero l'account di accesso. Non è permesso all'ultimo gestore della
  piattaforma, come già non lo è all'ultimo amministratore.
- **Nell'ambiente di prova**, per provare le prenotazioni in arrivo da Italianway serve un gestore della piattaforma,
  perché solo lui inserisce il codice Italianway.
- **HQE non si può invitare come utente** di un'organizzazione: se una persona di HQE deve essere anche amministratore
  di un'organizzazione, HQE assegna a quella persona il ruolo di amministratore con una procedura tecnica.
- **Nome dell'app**: l'app si chiama **DOMHOUSE**. Sul telefono il nuovo nome compare sotto l'icona entro qualche
  giorno; se vuoi vederlo subito, disinstalla l'app e installala di nuovo.
- **Nuovi appartamenti solo da HQE**, anche nell'ambiente di prova: in Amministrazione non ci sono più «Nuovo
  appartamento» né il cestino.
- **Prenotazioni ricevute** e **Prenotazioni non attribuite**: le schede «Webhook» di Amministrazione e di
  Organizzazioni hanno un nuovo nome e righe leggibili.
- **Notifiche al rientro**: quando la stessa persona rientra sullo stesso dispositivo, le notifiche si riaccendono da
  sole.
- **Elenco organizzazioni**: nuovo nome della prima scheda della pagina Organizzazioni.
- **Registro attività** in Amministrazione e in Organizzazioni: chi ha fatto cosa.
- **Sospensione delle organizzazioni** e **accesso di assistenza HQE** a tempo, visibile all'amministratore.
- **Privacy**: chi elimina il proprio account compare come «utente rimosso»; il sistema domotico riceve un codice
  anonimo al posto dell'email; i dati personali degli ospiti non vengono salvati; ogni ruolo riceve solo i dati che
  gli servono.
- **Barra laterale** con tutti i tuoi ruoli.
- **Menu a tre righe sul telefono**, al posto della barra in basso: tutte le pagine in un solo menu.
- **Conservazione dei dati**: oltre i termini della sezione 7b i dati si cancellano da soli.
- **Appartamenti dimostrativi**: etichetta «Dimostrativo», Simulatore solo su di loro (anche con gli appartamenti
  veri) e pulsante per ripristinare lo stato iniziale.
- **Rendiconti dei consumi in Excel**, mensili e per soggiorno, con l'importo in euro dal prezzo per kWh.
- **Sicurezza**: chiusi alcuni modi tecnici con cui un utente avrebbe potuto vedere dati di appartamenti di altre
  organizzazioni o raggiungere il sistema simulato da internet. Per chi usa l'app non cambia nulla.

---

## 1. Entrare nell'app

Indirizzo: **https://domotica-poc-511707.web.app**

**Il primo accesso** avviene sempre da un invito. Si riceve un'email «Invito a DOMHOUSE» con il pulsante
«Apri l'app».
- Se la tua email è un account Google (per esempio Gmail), tocca **«Accedi con Google»** e scegli quell'account.
- Altrimenti usa il pulsante **«Scegli la password»** dell'email. Il link vale 1 ora. Poi entra con email e password.
- Se il link è scaduto, nella pagina di accesso usa **«Password dimenticata?»**.
- L'email può finire nello spam.

**Password dimenticata.** Nella pagina di accesso tocca «Password dimenticata?», scrivi la tua email e tocca
«Invia il link». Il messaggio di conferma è lo stesso anche se l'email non è registrata: è voluto.

**Messaggi che puoi vedere all'accesso**
| Messaggio | Cosa significa | Cosa fare |
|---|---|---|
| «Accesso non riuscito: controlla email e password» | Email o password sbagliate | Riprova o usa «Password dimenticata?» |
| «Non hai i permessi per accedere. Chiedi un invito.» | L'account esiste ma nessuno ti ha invitato | Chiedi un invito a un amministratore |
| «Conferma il tuo indirizzo: abbiamo inviato un link a…» | Il tuo indirizzo email non è ancora confermato | Apri il link nell'email, poi accedi di nuovo |
| «Impossibile caricare il profilo, riprova tra poco» | Il server non risponde | Riprova dopo qualche minuto |
| «La tua organizzazione non è attiva: contatta HQE.» | La tua organizzazione è stata sospesa o non è ancora pronta | Contatta HQE |

---

## 2. Installare l'app sul telefono o sul computer

L'app si può aggiungere alla schermata Home: si apre a schermo intero come un'app normale.
- **Su computer:** in fondo alla barra laterale c'è «Installa l'app» (sul telefono è nel menu a tre righe). Con Chrome o Edge si apre la finestra di
  installazione; con altri browser compaiono le istruzioni.
- **Su Android con Chrome:** Impostazioni > «Installa l'app» > «Installa», oppure menu di Chrome > «Installa app».
- **Su iPhone:** apri il sito con Safari, tocca Condividi e poi «Aggiungi alla schermata Home».
- Se l'app è già installata, in Impostazioni compare «App installata su questo dispositivo».

---

## 3. Chi può fare cosa

| Ruolo | Cosa vede | Cosa può fare |
|---|---|---|
| **Amministratore** | Tutto, compresi Amministrazione e Simulatore (sugli appartamenti dimostrativi) | Tutto, compresa la gestione di utenti, appartamenti e funzioni |
| **Operatore** | Tutto tranne Amministrazione e Simulatore | Comandare dispositivi, cambiare modalità, programmare, approvare, modificare regole, usare l'assistente |
| **Sola lettura** | Tutto tranne Amministrazione e Simulatore | Solo guardare: i pulsanti sono disattivati e compare «Il tuo ruolo consente solo la lettura» |

Alcune schermate (Approvazioni, Decisioni, Consumi, Programmazione, Regole, Assistente) compaiono solo se la funzione è
attiva per quell'appartamento.

**Come muoversi.** Su computer c'è la barra laterale a sinistra. Sul telefono le pagine si aprono dal pulsante con le tre
righe in alto a sinistra («Apri il menu»): si apre il menu con tutte le pagine, generali e dell'appartamento in cui sei;
la pagina aperta è evidenziata e in fondo trovi il tuo nome, il ruolo e «Esci». Per chiuderlo tocca fuori dal menu o la
X («Chiudi il menu»); si chiude anche scegliendo una pagina. In fondo alla barra laterale (o al menu), sotto l'email, ci sono i tuoi ruoli: per esempio
«Amministratore · Flatsharing» e, se hai anche il ruolo di HQE, «Gestore della piattaforma». Quando le schede di una
pagina non stanno sullo schermo del telefono, la loro barra scorre in orizzontale.

**Esiti delle azioni.** Il successo è un avviso verde in alto. L'errore è un avviso rosso con il messaggio e un
**«ID richiesta»** copiabile: in caso di problemi, comunicalo insieme alla segnalazione. Le eliminazioni chiedono sempre
conferma.

---

## 4. Appartamenti

La prima schermata mostra una scheda per appartamento: nome, indirizzo, stato (Online, Non raggiungibile, oppure
scheda grigia se disattivato), occupazione (vuoto, occupato, prenotato), modalità, campanella con le approvazioni in
attesa, prossimo check-in e check-out, consumo di oggi in kWh. Tocca una scheda per aprire l'appartamento.

Gli amministratori vedono la nota «Per un nuovo appartamento scrivi all'assistenza HQE.». Chi è anche gestore della
piattaforma vede invece «+ Appartamento», che apre Organizzazioni con gli appartamenti della sua organizzazione. Se non
c'è ancora nessun appartamento, la pagina dice a chi rivolgersi: all'assistenza HQE (amministratori), a Organizzazioni
(gestori), a un amministratore della propria organizzazione (operatori e lettori).

Se l'amministratore ti ha assegnato solo alcuni appartamenti, vedi solo quelli. Se apri l'indirizzo di un altro
appartamento compare «Appartamento non disponibile» con il pulsante «Torna agli appartamenti». Se non hai appartamenti
assegnati leggi «Nessun appartamento assegnato al tuo account». In Impostazioni > Profilo la riga «Appartamenti» dice
quali appartamenti vedi.

---

## 5. Dentro un appartamento

### Panoramica
- In alto: nome, occupazione, «In tempo reale» (oppure «Riconnessione…»), check-in e check-out, dispositivi online.
- Striscia di stato del sistema dell'appartamento: In salute, Degradata o Ferma.
- **Modalità** comfort, eco o vuoto: dopo la scelta compare una rotellina finché il sistema conferma. Non compare un
  avviso verde: la conferma è la scelta che si illumina.
- **Forza per…** 30 minuti, 2 ore o 6 ore: compare «Forzatura … attiva fino alle …» con «Annulla forzatura». Finché la
  forzatura è attiva, un cambio di modalità programmato (per esempio il check-out) non la interrompe: aspetta la sua fine e
  si esegue allora, e nelle Decisioni compare «rimandata per la forzatura». Se nell'appartamento c'è una finestra aperta,
  prima di partire l'app avvisa: «Finestra aperta in Soggiorno: durante la forzatura il clima resta acceso.» (con il nome della stanza), con «Annulla» e
  «Forza comunque». Durante la forzatura la finestra aperta non spegne il clima (nelle Decisioni compare «Finestra: regola
  sospesa», con l'ora in cui la regola riparte); alla sua scadenza la regola riparte e, se la finestra è ancora aperta,
  spegne, con una decisione che spiega entrambi i motivi.
- **Dispositivi** raggruppati per stanza: interruttori Acceso/Spento, temperatura con − e +, modo del climatizzatore,
  velocità della ventola, letture di potenza, consumi, temperatura, umidità, finestre e movimento. Per la caldaia lo stato è
  **«Riscaldamento abilitato» / «Riscaldamento disabilitato»** e il pulsante «Attiva» / «Disattiva»: il termostato del
  sistema la accende e la spegne da solo intorno alla temperatura voluta (si vede dalle Decisioni), e se ha un misuratore
  che segna più di 30 W compare «sta scaldando ora». A casa vuota l'antigelo la accende sotto la soglia anche se è
  disabilitata.
- Sotto ogni comando compare l'esito: «in corso», poi «eseguito», oppure l'errore. Un dispositivo offline ha i comandi
  disattivati.
- Menu ⋮ di un dispositivo > «Rinomina o sposta» per cambiare nome o stanza.
- Mentre guardi un appartamento possono arrivare avvisi: nuova approvazione, dispositivo offline, sistema non
  raggiungibile o di nuovo raggiungibile.

### Approvazioni
Azioni che il sistema propone e che aspettano un sì o un no. Ogni scheda mostra cosa propone, perché, il tempo
rimasto (rosso sotto i 5 minuti) e cosa succede alla scadenza. Si può aggiungere una nota e toccare «Approva» o
«Respingi». Il filtro «In attesa» / «Tutte» mostra anche quelle già decise.
- Richieste che il sistema fa da solo: **«Mettere l'appartamento a vuoto dopo il check-out»**, quando all'ora del
  risparmio dopo la partenza il sensore di movimento ha visto qualcuno dopo l'orario di partenza (senza risposta entro
  il tempo viene approvata e l'appartamento va a vuoto); **«Spegnere …»** con il nome dell'apparecchio, quando
  l'appartamento è vuoto e quell'apparecchio consuma oltre una soglia da più di tanti minuti (mai la caldaia, mai
  durante una forzatura; senza risposta viene respinta e l'apparecchio resta acceso, salvo un'impostazione diversa
  dell'appartamento; dopo un no, nessuna nuova richiesta finché il consumo non scende e risale). Le proposte
  dell'assistente, senza risposta, vengono respinte. Soglie e tempi li imposta chi gestisce il sistema domotico.

### Decisioni
Lo storico di tutto ciò che è stato fatto, da chi (motore automatico, regola, gestore, assistente, sistema) e con quale
esito. Filtri per autore, dispositivo e **Periodo** (tutto lo storico, ultimi 7, 30 o 90 giorni); «Carica altri» per
andare indietro.
- Ogni decisione mostra il **tipo di azione** in italiano (per esempio «Modalità», «Forzatura scaduta», «Programma:
  spostata», «Prenotazione annullata», «Disdetta dopo il pre-arrivo») e sotto la spiegazione; passando sopra il tipo
  compare il codice tecnico. Un'azione nuova non ancora tradotta mostra il codice. La ricerca trova anche il tipo.
- Tre tipi da conoscere: «Collegamento ai dispositivi perso» vuol dire che il sistema non riesce più a parlare con i
  dispositivi dell'appartamento (i comandi vengono rifiutati finché non torna), «Collegamento ai dispositivi ripristinato»
  che è tornato; «Comando non verificato: misuratore offline» che un comando al climatizzatore è partito, ma il misuratore
  che di solito conferma l'accensione o lo spegnimento non risponde, quindi il sistema non può sapere se ha funzionato.
- Il campo di ricerca cerca in tutto lo storico (almeno 90 giorni): nel motivo, nell'azione, in chi ha deciso, nel
  dispositivo, nei valori e nei codici. Procede a blocchi di 1.000 decisioni, dalle più recenti alle più vecchie: leggi
  «Ricerca in corso…» e poi «Risultati: N · cercato fino al <data>». Per andare più indietro premi «Cerca più indietro»;
  quando lo storico è finito leggi «cercato in tutto lo storico disponibile».
- Per trovare subito l'operazione di un errore, incolla l'**ID richiesta** completo: la ricerca va su tutto lo storico
  in un colpo solo.
- Periodo, Chi e Dispositivo rendono la ricerca più veloce. Se i risultati superano 3.000 l'app chiede di restringere.
- Le decisioni che arrivano mentre una ricerca è in corso non entrano in quella ricerca: cancella la parola per vedere
  l'elenco aggiornato.

### Consumi
Periodo: Oggi, 7 giorni, 30 giorni o «Soggiorno in corso» (solo se c'è un ospite). Totale in kWh, grafico, consumi per
dispositivo e, durante un soggiorno, il confronto con il soggiorno precedente.
- I numeri vengono dai misuratori dell'appartamento, ora per ora. Le ore in cui un misuratore non ha mandato dati contano
  zero; se un misuratore resta scollegato per qualche ora, il consumo di quel periodo viene ripartito in parti uguali
  sulle ore mancanti. Le «ore di clima evitate» non sono ancora calcolate e compaiono come «non calcolate»: il calcolo
  vero arriverà quando l'appartamento avrà almeno quattro settimane di consumi registrati.
- Sotto il grafico, «Consumi disponibili dal …» (giorno e mese) dice da quando ci sono dati misurati: è la prima ora con un
  consumo maggiore di zero, quindi se nei primi giorni tutto è rimasto spento la data può essere un po' più tarda del
  collegamento. Senza nessun dato la riga non compare. Negli appartamenti dimostrativi i consumi prima dell'avvio del
  sistema sono un profilo di esempio, uguale a ogni riavvio, dal 1° gennaio 2026.

**Rendiconto in Excel** (in fondo alla pagina, per tutti, sugli appartamenti che vedi): scegli il mese (gli ultimi 12) e
premi «Scarica Excel». Il file (per esempio `consumi-apt-001-2026-10.xlsx`) ha quattro fogli: Riepilogo (totale kWh,
prezzo e importo in euro), Giornaliero, Orario e Dispositivi. Con il periodo «Soggiorno», «Excel del soggiorno» scarica
il rendiconto dall'ora esatta di arrivo a quella di partenza, del soggiorno in corso o del precedente: serve per
riaddebitare l'energia all'ospite. Il file non contiene dati personali degli ospiti. Se manca il prezzo per kWh, il
file dice «prezzo non impostato» e riporta solo i kWh. In testa c'è «Consumi disponibili dal …» (data e ora) e le ore
precedenti restano vuote, non a zero; se tutto il periodo cade prima di quella data il file lo dice e i totali
restano vuoti; senza nessun dato misurato compare «Nessun consumo misurato finora». Se il file non si può preparare (funzione non attiva, sistema
domotico non raggiungibile, soggiorno non ancora iniziato), compare il motivo.

### Riepiloghi
Ogni lunedì dalle 8 del mattino (ora dell'appartamento) trovi il riepilogo della settimana appena finita, da lunedì a
domenica: voce «Riepiloghi» nel menu dell'appartamento, elenco delle settimane dalla più recente («Settimana dal … al …»
con «N segnalazioni» oppure «Nessuna novità»); finché non c'è nessun riepilogo compare «Nessun riepilogo ancora. Ogni
lunedì mattina arriva quello della settimana appena finita.» I riepiloghi restano consultabili per 12 mesi; in alto nella
pagina di una settimana c'è «calcolato il …» con data e ora. Ogni riepilogo dice,
con frasi già pronte:
- se i consumi sono stati alti. Le notti con ospiti si confrontano con le notti con ospiti delle 4 settimane prima, quelle
  senza ospiti con quelle senza ospiti, sia in totale sia per ogni misuratore (riquadro «Consumi a parità di occupazione»,
  con gli stati «Nella norma», «Alto», «Confronto non disponibile», «Nessuna notte»). «Alto» vuol dire almeno il 30 % sopra
  il valore tipico delle settimane prima e almeno 5 kWh in più nella settimana, così una piccola differenza non fa scattare
  l'avviso. Se nelle settimane prima non c'erano notti di quel tipo il riepilogo scrive «confronto non disponibile», mai un
  allarme. Nelle prime 5 settimane dopo che l'appartamento ha iniziato a misurare i consumi veri scrive «dati
  insufficienti» con la data da cui i consumi sono disponibili;
- quali dispositivi sono spenti o non rispondono da più di 24 ore;
- quali approvazioni sono scadute senza che nessuno rispondesse;
- quali finestre sono rimaste aperte almeno 3 volte con il clima spento dalla regola.
Una settimana senza niente da segnalare ha il riepilogo «Settimana senza novità» e non manda avvisi.

### Programmazione
Azioni programmate («In programma») e storico degli ultimi 7 giorni. «Nuova azione» per programmare un cambio di
modalità o un comando a un dispositivo a un orario (ora dell'appartamento). «Sposta» per cambiare orario, «Annulla
azione» per toglierla. Le azioni nate da una prenotazione si ricalcolano quando la prenotazione cambia. Se una
prenotazione viene annullata dopo che l'appartamento è già stato preparato per l'arrivo, il sistema lo rimette da solo a
«vuoto» (salvo un'altra prenotazione per lo stesso giorno), lo scrive nelle Decisioni e manda l'avviso «Prenotazioni».

### Regole
Le regole automatiche dell'appartamento, con interruttore e valori. Quelle con «Non modificabile» non si cambiano.
Le otto regole (valori di partenza e limiti):
- **Finestra aperta spegne il clima**: dopo 5 minuti di finestra aperta (da 1 a 30).
- **Limiti del setpoint**: la temperatura chiesta resta fra 16 e 24 °C.
- **Antigelo a casa vuota**: accende la caldaia sotto 8 °C (da 5 a 12), anche se è disabilitata.
- **Antimuffa a casa vuota**: avviso sopra il 65 % di umidità (da 50 a 80), una volta al giorno.
- **Pre-arrivo**: prepara l'appartamento 2 ore prima del check-in (da 0 a 6).
- **Risparmio al check-out**: mette l'appartamento a vuoto 30 minuti dopo il check-out (da 0 a 180).
- **Pausa minima del compressore**: 3 minuti fra uno spegnimento e la riaccensione del clima (non modificabile).
- **Avviso dispositivo offline**: avviso dopo 15 minuti senza contatto (da 5 a 120).
Modificando compare in basso «N regole modificate» con «Salva le modifiche» o «Annulla le modifiche». Un valore fuori
dai limiti viene segnalato sotto il campo.

### Assistente
Si scrive una richiesta in italiano (per esempio «Spegni il clima del soggiorno») e si tocca Invia. L'assistente risponde,
oppure chiede un'approvazione con il link «Vai alle approvazioni». Se dopo 30 secondi non risponde compare «Nessuna
risposta dall'assistente: riprova». La conversazione resta solo in quella scheda del browser.
- L'assistente legge stati, consumi, programmazioni e Decisioni dell'appartamento (sa rispondere a «perché si è spento
  il clima?») e può fare solo ciò che un operatore fa dall'app: modalità, comandi ai dispositivi, programmazioni. Non
  tocca regole, utenti e appartamenti, e non riceve mai dati personali degli ospiti.
- Con ospiti presenti, spegnere il clima o la caldaia o cambiare modalità passa da un'approvazione; più azioni in una
  richiesta («spegni clima e caldaia») diventano un'approvazione ciascuna, in coda.
- L'esito lo scrive il sistema, non il modello: «Fatto: …» solo quando il dispositivo ha confermato; altrimenti
  «Comando inviato: …, l'esito arriva nell'app», «Serve la tua approvazione: …» oppure «Programmato: …». Se non sa una
  cosa lo dice e rimanda all'app.
- Limiti: 50 domande al giorno per appartamento («Limite di 50 domande al giorno raggiunto per questo appartamento:
  riprova domani»); un tetto di spesa mensile per tutto il servizio, raggiunto il quale compare «Limite mensile
  raggiunto, riprova dal mese prossimo». Anche gli appartamenti dimostrativi usano l'assistente vero.
Chi ha il ruolo «Sola lettura» non fa domande all'Assistente e non vede quelle dei colleghi.

### Simulatore (solo amministratori, solo sugli appartamenti «Dimostrativo»)
Gli appartamenti dimostrativi (etichetta viola «Dimostrativo» accanto al nome, in ogni elenco) usano un sistema domotico
simulato: servono per le prove e per le dimostrazioni, anche quando ci saranno gli appartamenti veri. Su questi
appartamenti gli amministratori vedono la voce «Simulatore» («Provoca eventi su questo appartamento dimostrativo: lo
vedono solo gli amministratori.»); su un appartamento vero la voce non c'è. Il Simulatore serve a provare l'app senza
dispositivi veri: aprire e chiudere finestre, mettere offline un dispositivo, generare
un'approvazione, inviare un evento di prenotazione (arrivo, partenza, ospiti) e vedere le azioni programmate che ne
nascono. La sezione «Movimento» ha un pulsante «Simula movimento» per ogni sensore di movimento: un clic fa come se
una persona passasse davanti al sensore (il sistema registra l'ora, come con un sensore vero) e accanto al nome si
aggiorna «ultimo movimento»; serve, per esempio, a provare la richiesta «Mettere l'appartamento a vuoto dopo il
check-out». La prenotazione di prova fa lo stesso percorso di una prenotazione vera arrivata da Italianway, fino al sistema
domotico dell'appartamento; ripetere lo stesso invio non la duplica.

**Ripristina lo stato iniziale** (in fondo al Simulatore): «Riporta l'appartamento dimostrativo com'era all'inizio, per
ricominciare una prova da capo.» Il pulsante rosso «Ripristina…» chiede conferma. Tornano come all'inizio dispositivi e
loro stati, modalità, forzatura, regole, approvazioni, programmazione, decisioni e comandi. Vengono cancellati tutti i
soggiorni di quell'appartamento, anche quelli arrivati da Italianway. Restano nome, indirizzo e impostazioni
dell'appartamento, prezzi, codice Italianway, utenti, registro attività ed elenco delle prenotazioni ricevute; i consumi
non cambiano. Vale solo per quell'appartamento e non si può annullare. Dopo l'avviso
«Stato iniziale ripristinato» l'app rilegge tutto; gli altri dispositivi aperti su quell'appartamento si aggiornano da
soli. Se l'appartamento è collegato a un sistema domotico vero in modalità di prova, il pulsante è disattivato («Il
ripristino è disponibile solo con il motore simulato integrato.»). Anche senza ripristino, gli appartamenti
dimostrativi tornano allo stato iniziale ogni volta che l'app viene aggiornata.

---

## 6. Amministrazione (solo amministratori)

**Utenti**
- «Invita un utente»: email, nome e ruolo, poi «Invita». La persona riceve l'email di invito.
- Possibili esiti: «Invito inviato a …»; «… l'email non è partita. Riprova con «Reinvia»»; «L'invio email non è attivo:
  avvisa tu …». Se alla stessa persona sono partite troppe email in poco tempo, l'invito resta registrato ma l'email
  non parte: riprova più tardi con «Reinvia».
- Chi non è ancora entrato ha l'etichetta «in attesa del primo accesso» e il pulsante «Reinvia».
- **Quali appartamenti vede ogni utente** (operatori e lettori): premi «Appartamenti» accanto all'utente, scegli
  «Tutti gli appartamenti» oppure spunta solo quelli che servono, poi «Salva». Nel modulo «Invita un utente» la stessa
  scelta compare sotto, già impostata su «Tutti gli appartamenti». Gli amministratori vedono sempre tutto e per loro la
  scelta non compare. Accanto a ogni utente l'elenco riassume cosa vede: «tutti gli appartamenti», i nomi, oppure
  «N appartamenti» (passa con il mouse per leggere i nomi). Se togli tutte le caselle l'utente non vedrà nessun
  appartamento: l'app chiede conferma. Serve per sospendere un accesso senza cancellare l'utente. Caso tipico: il
  proprietario di un immobile, invitato come «Sola lettura», che vede solo il suo appartamento. Un utente limitato vede,
  riceve notifiche e può agire solo sui suoi appartamenti. Se gli togli un appartamento mentre lo sta guardando, entro
  mezzo minuto la sua pagina smette di aggiornarsi e compare «Appartamento non disponibile».
- Il ruolo si cambia dal menu accanto al nome: entro un minuto la persona viene fatta uscire da tutti i dispositivi
  e, rientrando, ha il ruolo nuovo. Il cestino rimuove l'utente e il suo
  accesso. Non si può cambiare ruolo né eliminare se stessi.
- Le persone di HQE (gestori della piattaforma) non si possono invitare: l'app risponde che l'email non
  può essere invitata. Il nome dell'organizzazione lo cambia solo HQE.

**Appartamenti:** «Modifica», interruttore Attivo e «Verifica connessione» per controllare che il sistema
dell'appartamento risponda. I nuovi appartamenti li aggiunge HQE (gestore della piattaforma), anche nell'ambiente di
prova: in Amministrazione non ci sono «Nuovo appartamento» né il cestino. «Modifica» cambia nome, indirizzo, fuso orario
e «Attivo»; le funzioni si scelgono nella scheda Funzioni e chi lo vede nella scheda Utenti. Il collegamento al sistema
domotico e il codice Italianway si vedono ma non si cambiano: se vanno cambiati, scrivi all'assistenza. Puoi sempre
premere «Verifica connessione» e leggere l'esito dell'ultima verifica; se non riesce, avvisa l'assistenza. Per avere un
nuovo appartamento, o per toglierne uno, scrivi all'assistenza HQE.

**Prezzo dell'energia** (in cima ad Amministrazione > Appartamenti, solo per l'amministratore): «Prezzo per kWh (€)»,
per esempio 0,25, poi «Salva». Serve per l'importo in euro nei rendiconti Excel e vale per tutti gli appartamenti. Per un
appartamento se ne può impostare uno diverso da «Modifica» («Prezzo per kWh di questo appartamento (€)»; vuoto = quello
dell'organizzazione). Ogni appartamento dice quale prezzo vale. Si scrive un numero da 0 a 10, con la virgola o il
punto; svuotando il campo il prezzo viene tolto. Ogni cambio resta nel Registro attività.

**Funzioni:** quali schermate sono attive per tutta l'organizzazione, con eventuali eccezioni per singolo appartamento.
Ogni interruttore ha un nome in italiano (Panoramica, Dispositivi, Comandi, Consumi, Programmazione, Regole,
Approvazioni, Decisioni, Assistente) e sotto, in piccolo, il nome tecnico della funzione.

**Prenotazioni ricevute:** le ultime 100 comunicazioni di prenotazione arrivate da Italianway per i tuoi appartamenti,
e se sono state trasmesse al sistema domotico che gestisce l'appartamento.
- In cima, la sintesi: «Ultime 24 ore: N ricevute, N trasmesse, N con problemi».
- Ogni riga comincia con una frase, per esempio «Prenotazione creata · Milano Centro · dal 1 dic 2026 al 3 dic 2026».
  Gli eventi sono: Prenotazione creata, modificata o cancellata, Check-in, Check-out.
- Sotto c'è l'esito, con una spunta verde o una X rossa, e poi la data e l'ora di ricezione:

| Esito | Cosa vuol dire |
|---|---|
| «Ricevuta e trasmessa al motore» (verde) | Tutto a posto: il sistema domotico l'ha ricevuta, anche se l'aveva già. |
| «Ricevuta ma il motore non l'ha accettata (riprovato N volte)» | Il sistema domotico non ha risposto o ha dato errore, anche dopo i tentativi. Avvisa l'assistenza. |
| «Ricevuta ma non trasmessa: appartamento disattivato» | L'appartamento è spento con l'interruttore Attivo. |
| «Ricevuta ma non trasmessa: formato non riconosciuto» | Il messaggio di Italianway non si è potuto leggere. Avvisa l'assistenza. |
| «Ricevuta ma rifiutata: firma non valida» e «Ricevuta: appartamento non riconosciuto» | Qui non compaiono quasi mai: queste comunicazioni non si possono attribuire a nessuna organizzazione e le vede HQE. |
| «Ricevuta ma non trasmessa» | Qualsiasi altro caso. Avvisa l'assistenza. |

- Se il messaggio non si può interpretare, la frase diventa «Evento ricevuto, formato non riconosciuto».
- «Dettagli tecnici» apre, per ogni riga, i dati per l'assistenza: firma, codice di risposta, «Codice Italianway»,
  «Ospiti» (il numero), identificativi (l'identificativo di correlazione si può copiare), inoltro e tentativi, corpo
  grezzo. Nel corpo grezzo i dati personali degli ospiti (nomi, email, telefoni) non ci sono: compare «\[oscurato\]»,
  oppure «\[corpo non JSON, N byte\]». L'app non salva i dati personali degli ospiti.
- Date e ore sono nel fuso orario italiano.
- Le prove fatte con il Simulatore non passano da qui e non compaiono in questa scheda.

**Registro attività:** «Chi ha fatto cosa nella tua organizzazione: inviti, ruoli, appartamenti, funzioni e accessi di
assistenza.» Ogni voce è una frase con la data, dalla più recente; «Carica altri» mostra le 50 successive. Esempio:
«Anna Rossi ha cambiato il ruolo di bruno@… da «Sola lettura» a «Operatore»». Chi ha eliminato il proprio account
compare come «utente rimosso».

**Accesso di assistenza HQE.** Quando HQE apre un accesso di assistenza alla tua organizzazione, in cima a ogni pagina
compare «L'assistenza HQE (nome (email)) ha accesso alla tua organizzazione fino al …, con i permessi di un operatore.»
con il motivo. «Chiudi accesso» lo termina subito (chiede conferma); la X nasconde solo l'avviso. Chiudere un accesso
non impedisce a HQE di aprirne uno nuovo se serve: anche quello comparirà qui. Durante l'accesso la persona di HQE
vede e comanda come un operatore, ma non gestisce utenti, appartamenti né funzioni. Apertura, chiusura e scadenza
restano nel Registro attività.

**Avvisi email (per gli amministratori del progetto):** se il server dell'app non risponde per 5 minuti arriva
un'email «BFF non raggiungibile»; quando torna su arriva l'email di chiusura.

---

## 6b. Organizzazioni (solo per il gestore della piattaforma)

Chi ha il ruolo di gestore della piattaforma (HQE) vede nel menu la voce **Organizzazioni**. Gli amministratori delle
organizzazioni non la vedono. La pagina ha quattro schede: **Elenco organizzazioni**, **Gestori della piattaforma**,
**Prenotazioni non attribuite** e **Registro attività**.
- **Nuova organizzazione** (in Elenco organizzazioni): scrivi il nome e l'email della persona che la amministrerà. Quella persona riceve un'email
  per entrare; una volta dentro invita da sola gli altri utenti. Due organizzazioni non possono avere lo stesso nome.
- **Reinvia invito:** se l'email non è partita o la persona non la trova. Il pulsante sparisce quando l'amministratore
  è entrato. **Rinomina** cambia il nome dell'organizzazione.
- **Istanza simulata (appartamento dimostrativo)**: casella nella creazione e in «Collegamento». Con il motore simulato
  integrato (`mock://builtin`) è sempre accesa. Con un sistema domotico vero si accende per prove e dimostrazioni: gli
  amministratori vedono il Simulatore e ogni elenco segna l'appartamento «Dimostrativo». Con gli appartamenti veri
  (produzione) un appartamento dimostrativo non può avere un codice Italianway, così nessuna prenotazione vera finisce
  in un appartamento finto. Passando dal motore simulato a un motore vero l'appartamento torna reale; per tenerlo
  dimostrativo, lascia accesa la casella «Istanza simulata». Ogni cambio resta nel Registro attività.
- **Appartamenti** di un'organizzazione: «Nuovo appartamento» chiede un identificativo che non si potrà più cambiare,
  il nome, il collegamento al sistema domotico (nell'ambiente di prova `mock://builtin`) e il codice Italianway. È
  l'unico posto da cui si creano appartamenti, anche per il collaudo. In produzione, prima di usarlo, HQE crea la chiave di accesso al sistema domotico dell'appartamento (la procedura è
  nelle note tecniche per il team del motore); poi
  si preme «Verifica connessione». «Modifica collegamento» cambia indirizzo, porta e codice Italianway; «Elimina» toglie
  l'appartamento a tutti gli utenti dell'organizzazione.
- **Sospendi / Riattiva** (in Elenco organizzazioni): «Sospendi» chiede il motivo, obbligatorio, che resta nel Registro
  attività. I suoi utenti escono dall'app con «La tua organizzazione è sospesa: l'app non è disponibile. Per
  informazioni contatta l'assistenza HQE.» e non possono rientrare; le notifiche si fermano. Le prenotazioni
  continuano ad arrivare al sistema domotico degli appartamenti, così gli ospiti non subiscono la sospensione.
  L'organizzazione mostra l'etichetta «Sospesa» e «Sospesa il … Motivo: …»; «Riattiva» chiede conferma. Se tu stesso
  sei membro dell'organizzazione sospesa resti dentro Organizzazioni, per poterla riattivare.
- **Accesso di assistenza** (in Elenco organizzazioni): per entrare nei dati di un'organizzazione quando c'è un
  problema. Scegli la durata (da 1 a 24 ore) e scrivi il motivo, obbligatorio e visibile all'amministratore, poi «Apri
  l'accesso». Con «Entra come assistenza» lavori dentro l'organizzazione con i permessi di un operatore: l'app si
  svuota come a un cambio di utente e in alto compare «Stai lavorando come assistenza in … fino alle …, con i permessi
  di un operatore.» con «Termina». Alla fine (Termina, scadenza, chiusura da parte dell'amministratore o sospensione)
  compare «L'accesso di assistenza a … è finito: ora vedi di nuovo la tua area.». Non c'è per un'organizzazione
  sospesa. Se la chiusura sul server non riesce, compare «Chiusura dell'accesso sul server non riuscita: chiudilo da
  Organizzazioni.». Tutto resta nel Registro attività, con il tuo nome.
- **Registro attività:** con «Registro di» scegli un'organizzazione, oppure «Azioni della piattaforma» (gestori
  nominati e tolti). Per le persone delle organizzazioni vedi solo il ruolo, non il nome né l'email: per esempio «Un
  amministratore ha invitato un utente come «Sola lettura»».
- **Gestori della piattaforma:** aggiungi un altro gestore scrivendo la sua email; diventa gestore quando entra
  nell'app con quell'email. «Togli» gli toglie il ruolo; deve restare sempre almeno un gestore.
- **Prenotazioni non attribuite:** le prenotazioni arrivate da Italianway che non si possono assegnare a nessuna
  organizzazione (codice Italianway sconosciuto o collegato a più appartamenti, firma non valida, formato non
  riconosciuto); utile per capire un codice Italianway sbagliato. Gli amministratori non le vedono. Le righe sono leggibili come in «Prenotazioni ricevute»; al posto del nome
  dell'appartamento compare il codice Italianway ricevuto.
- Il gestore della piattaforma non vede dispositivi, consumi, decisioni né utenti delle organizzazioni, se non durante
  un accesso di assistenza aperto.

### Amministrazione e Organizzazioni a confronto

Chi è sia amministratore di un'organizzazione sia gestore della piattaforma vede tutte e due le voci. Le schede hanno
nomi simili ma fanno cose diverse:

| Amministrazione (l'amministratore, per la sua organizzazione) | Organizzazioni (il gestore della piattaforma, per tutte) |
|---|---|
| **Appartamenti:** l'uso di ogni giorno: nome, indirizzo, attivo o no, «Verifica connessione». | **Appartamenti** (dentro ogni organizzazione): la parte tecnica: creare, collegare al sistema domotico, codice Italianway, eliminare, «Verifica connessione». |
| **Utenti:** le persone della propria organizzazione, con ruolo e appartamenti visibili. | **Gestori della piattaforma:** le persone di HQE che gestiscono il servizio. Della singola organizzazione il gestore vede solo il primo amministratore («Reinvia invito»). |
| **Funzioni:** quali schermate sono attive. | Nessuna scheda corrispondente. |
| **Prenotazioni ricevute:** le prenotazioni arrivate ai propri appartamenti. | **Prenotazioni non attribuite:** le prenotazioni che non corrispondono a nessun appartamento. Le due schede non si sovrappongono. |
| **Registro attività:** chi ha fatto cosa, con i nomi. | **Registro attività:** cosa è successo in un'organizzazione, con i soli ruoli; più le azioni della piattaforma. |
| Avviso dell'accesso di assistenza, con «Chiudi accesso». | **Accesso di assistenza** (in Elenco organizzazioni): aprirlo, entrare, chiuderlo. |
| Nessuna scheda corrispondente. | **Elenco organizzazioni:** creare un'organizzazione, rinominarla, invitare il primo amministratore. |

L'unico punto in comune è «Verifica connessione», presente in tutte e due le schede Appartamenti.

## 7. Impostazioni

- **Profilo:** email, ruolo, organizzazione, ambiente.
- **Account:** nome visualizzato, modificabile.
- **Password ed email** (solo per chi entra con email e password): «Cambia password» chiede la password attuale e la
  nuova, di almeno 8 caratteri. «Cambia email» manda un link al nuovo indirizzo: il cambio avviene quando lo apri. Chi
  entra con Google gestisce password ed email dal proprio account Google.
- **Sicurezza:** «Esci da tutti i dispositivi» chiude la sessione su tutti i telefoni e computer. «Elimina il mio
  account» è definitivo, e non è permesso all'ultimo amministratore, né all'ultimo gestore della piattaforma; per un
  altro gestore toglie anche il ruolo di gestore e chiude i suoi accessi di assistenza. La conferma spiega: «Vengono
  cancellati il tuo accesso, il tuo nome, la tua email e le tue preferenze di notifica. Resta quello che hai fatto
  (decisioni, approvazioni, registro attività), ma al posto del tuo nome comparirà «utente rimosso». Per rientrare
  servirà un nuovo invito.» Se invece è un amministratore a toglierti dall'organizzazione, il tuo accesso si chiude
  subito e quello che hai fatto resta nel registro attività per 24 mesi con il tuo nome visibile ai colleghi
  amministratori; per far cancellare nome ed email prima, elimina tu stesso l'account o chiedilo al gestore.
- **Notifiche:** quali avvisi ricevere, per categoria: «Approvazioni richieste», «Dispositivi e istanza offline» e
  «Prenotazioni» (avvisi sulle prenotazioni che cambiano il programma dell'appartamento, per esempio una disdetta dopo
  che l'appartamento è stato preparato per l'arrivo) e «Riepilogo» (il riepilogo settimanale, ogni lunedì, solo se la
  settimana ha qualcosa da segnalare), tutte attive dall'inizio; «Decisioni del motore» (riepilogo delle
  azioni automatiche, solo in app) è spenta finché non la attivi. Le notifiche sul telefono sono attive anche
  nell'ambiente di prova (vedi sotto). Se in un ambiente non lo fossero, la scheda direbbe «Notifiche sul telefono non
  attive in questo ambiente»: gli avvisi (nuove approvazioni, dispositivi offline, istanza non raggiungibile,
  prenotazioni annullate) compaiono in alto nello schermo solo mentre l'app è aperta sulla pagina di un appartamento.
- **Installa l'app** e **Lingua** (per ora solo italiano). In fondo «Esci».
- **Ambiente di prova:** nel sito di prova, in alto su ogni pagina, una fascia gialla dice «Ambiente di prova · i dati
  sono separati da quelli veri». Il sito vero non ce l'ha: se la vedi, quello che fai non tocca gli appartamenti veri.
  Gli appartamenti dimostrativi stanno solo nel sito di prova.

### Notifiche sul telefono
- Premi «Attiva su questo dispositivo» e consenti le notifiche quando il telefono o il browser lo chiede. Se va a buon
  fine compare «Notifiche attive su questo dispositivo».
- Se rifiuti il permesso compare «Permesso non concesso: su questo dispositivo le notifiche restano spente.»
- Se le notifiche sono bloccate, la scheda spiega di consentirle nelle impostazioni del browser o del telefono.
- **Su iPhone e iPad** le notifiche arrivano solo all'app installata: se apri il sito da Safari senza installarlo, la
  scheda lo dice e non mostra il pulsante. Installa l'app, aprila dall'icona e attivale da qui.
- Se togli il permesso dalle impostazioni del telefono o del browser, la scheda lo segnala e propone di riattivarle.
- Se il browser non può ricevere notifiche, gli avvisi compaiono solo dentro l'app.
- Le notifiche arrivano anche ad app chiusa. Toccandone una si apre l'app sulla pagina giusta (Approvazioni, la
  Panoramica dell'appartamento, o le Decisioni per una prenotazione annullata).
- Con l'app aperta, una notifica compare come avviso in alto con il pulsante «Apri» (su iPhone arriva sempre anche come
  notifica del telefono). Se stai già guardando quell'appartamento non compare un secondo avviso.
- «Disattiva» ferma le notifiche su quel dispositivo e mostra «Notifiche disattivate su questo dispositivo».
- Quando premi «Esci» (o «Esci da tutti i dispositivi») quel telefono o computer smette di ricevere le tue notifiche.
  **Quando rientri tu**, sullo stesso dispositivo, si riaccendono da sole e compare «Notifiche riattivate su questo
  dispositivo, come prima della tua uscita.». Se nel frattempo il browser non dà più il permesso, compare invece
  «Notifiche non riattivate: il browser non ne dà più il permesso. Puoi riattivarle da Impostazioni › Notifiche.».
  Non si riaccendono se le avevi spente tu da Impostazioni. Su un telefono condiviso ognuno ritrova le sue. Se un'altra persona accede dallo
  stesso dispositivo, non riceve le tue notifiche e non vede nessun dato della tua sessione, nemmeno per un istante.
  Lo stesso vale quando la sessione viene chiusa da un'altra parte (per esempio con «Esci da tutti i
  dispositivi» da un altro telefono, o per un cambio di ruolo). Se l'app si apre senza rete le notifiche restano attive.
  Le conversazioni con l'Assistente si cancellano quando esci.

---

## 7b. Per quanto tempo l'app conserva i dati

*Decisione del 17 ottobre 2026.* Oltre questi termini i dati si cancellano da soli (entro circa un giorno):

| Dati | Per quanto tempo |
|---|---|
| Prenotazioni e presenze degli ospiti | 12 mesi dopo il check-out |
| Consumi | 24 mesi (li conserva il sistema domotico dell'appartamento) |
| Riepiloghi settimanali | 12 mesi |
| Registro attività e storico degli accessi di assistenza | 24 mesi |
| Prenotazioni ricevute da Italianway (senza dati personali degli ospiti) | 90 giorni, e al massimo le ultime 100 |

Utenti, organizzazioni e appartamenti restano finché non vengono tolti. Chi elimina il proprio account viene cancellato
subito (vedi Impostazioni > Sicurezza).

## 8. Segnalare un problema

Per ogni problema annota:
1. cosa stavi facendo, passo per passo;
2. cosa ti aspettavi e cosa è successo;
3. l'**ID richiesta**, se compare;
4. dispositivo e browser (per esempio «iPhone, Safari» o «PC, Chrome»), data e ora;
5. uno screenshot, se possibile.
