# Guida all'app DOMHOUSE

Tutto quello che l'app sa fare, spiegato passo per passo e diviso per ruolo. Non servono conoscenze tecniche.
*Versione del 22 ottobre 2026 (lotto 30), ambiente di prova.*

> **Ambiente di prova.** Oggi gli appartamenti sono simulati: nessun dispositivo reale viene acceso o spento. In alto
> su ogni pagina una fascia gialla dice «Ambiente di prova» · «i dati sono separati da quelli veri». Gli appartamenti
> simulati ripartono dallo stato iniziale ogni volta che il server dell'app viene riavviato, per esempio a un
> aggiornamento.

## Come leggere questa guida

- I testi fra «virgolette basse» sono quelli esatti che vedi nell'app: pulsanti, etichette, messaggi.
- Dove dentro le virgolette trovi tre puntini «…», l'app mette un nome, una data, un numero o un indirizzo email.
- «Tocca» e «premi» vogliono dire la stessa cosa: sul telefono tocchi, sul computer fai clic.
- La guida è divisa per ruolo. Chi ha **sola lettura** legge la parte 4. L'**operatore** legge le parti 4 e 5.
  L'**amministratore** legge le parti 4, 5 e 6. Il **gestore della piattaforma** (HQE) legge la parte 7. Le parti 1 e 2
  e tutte quelle dalla 9 in poi valgono per tutti.
- Alcune pagine dell'appartamento («Approvazioni», «Decisioni», «Consumi», «Programmazione», «Regole», «Assistente»)
  compaiono solo se la funzione è attiva per quell'appartamento (lo decide l'amministratore nella scheda «Funzioni»).
  «Riepiloghi» c'è sempre.

## 1. Che cos'è DOMHOUSE

DOMHOUSE è l'app con cui chi gestisce appartamenti in affitto breve controlla riscaldamento, clima e consumi di ogni
appartamento, anche da lontano. Ogni **appartamento** ha dei **dispositivi** (caldaia, climatizzatore, prese,
sensori di temperatura, umidità, finestre, movimento e misuratori di consumo) collegati a un **sistema domotico**
che li legge e li comanda. Dentro il sistema domotico lavora un **motore**: la parte automatica che applica le
**regole** (per esempio «finestra aperta spegne il clima»), prepara la casa prima dell'arrivo degli ospiti e la
mette a riposo dopo la partenza, seguendo le **prenotazioni** che arrivano dal sistema Italianway.

L'appartamento ha sempre una **modalità**: «comfort» quando ci sono o stanno per arrivare gli ospiti, «eco» per
consumare meno, «casa vuota» quando non c'è nessuno. Chi lavora nell'app può cambiarla a mano, **forzarla** per un
po' di tempo (una **forzatura** blocca gli automatismi per 30 minuti, 2 ore o 6 ore) oppure **programmarla** a un
orario. Tutto quello che succede, fatto da una persona o dal motore, finisce nelle **Decisioni**, lo storico
dell'appartamento. Quando il motore non vuole decidere da solo (per esempio spegnere un apparecchio che consuma a casa
vuota) apre un'**approvazione**: una richiesta che aspetta il tuo sì o il tuo no. L'**assistente** è una chat in
italiano a cui puoi chiedere lo stato, i consumi o un comando. Il **Simulatore** serve a provare tutto questo su
appartamenti finti, detti «Dimostrativo».

Le persone che usano l'app appartengono a un'**organizzazione** (oggi Flatsharing) e hanno un **ruolo**: sola lettura,
operatore o amministratore. Sopra le organizzazioni c'è il **gestore della piattaforma** (HQE), che le crea e collega gli
appartamenti ai sistemi domotici.

### Chi fa cosa nel servizio

*Decisione del 16 ottobre 2026.*

1. **Flatsharing**, il gestore degli appartamenti, installa sensori e dispositivi nell'appartamento e lo comunica a HQE.
2. **HQE** prepara il sistema domotico dell'appartamento e lo attiva nell'app da «Organizzazioni», inserendo anche il
   codice Italianway (il codice con cui arrivano le prenotazioni).
3. Da quel momento l'appartamento compare nell'elenco di Flatsharing. L'amministratore di Flatsharing gli dà nome e
   indirizzo, sceglie le funzioni attive e decide chi può vederlo.

L'amministratore **non può creare da solo un appartamento, né cambiarne il collegamento al sistema domotico o il codice
Italianway**: lo fa solo HQE. È una garanzia: nessuno può collegare un appartamento a un sistema che non è il suo, né
ricevere le prenotazioni di una struttura altrui. Vale anche nell'ambiente di prova. Il gestore della piattaforma, da
solo, non vede dispositivi, consumi, decisioni né utenti delle organizzazioni: può entrarci solo con un **accesso di
assistenza** a tempo, che l'amministratore vede e può chiudere (parte 8).

## 2. Primi passi, uguali per tutti

### Ricevere l'invito ed entrare

Non ci si registra da soli: si entra sempre con un invito di un amministratore (o di HQE per il primo amministratore
di un'organizzazione).

1. Ricevi un'email con oggetto «Invito a DOMHOUSE». Dentro ci sono il nome dell'organizzazione, il tuo ruolo e chi ti
   ha invitato. Controlla anche lo spam.
2. Se la tua email è un account Google (per esempio Gmail): premi «Apri l'app», poi «Accedi con Google» e scegli quello
   stesso indirizzo.
3. Altrimenti premi «Scegli la password» nell'email e scegli una password. Il link vale 1 ora. Poi apri l'app, compila
   «Email» e «Password» e premi «Accedi».
4. Se il link è scaduto, nella pagina di accesso premi «Password dimenticata?» (vedi sotto).
5. Al primo accesso, se il tuo indirizzo non risulta confermato, l'app mostra «Conferma il tuo indirizzo: abbiamo inviato
   un link a …. Aprilo e poi accedi di nuovo.» e ti fa uscire: apri il link nell'email e accedi di nuovo.
6. Entrato, vedi «Appartamenti» (oppure «Organizzazioni» se sei un gestore della piattaforma senza organizzazione).

Indirizzo dell'ambiente di prova: [https://domotica-poc-511707.web.app](https://domotica-poc-511707.web.app). La pagina
di accesso si chiama «Accedi» e sotto dice «Area riservata ai gestori degli appartamenti».

Se l'accesso non riesce, l'avviso in alto dice cosa fare e sotto mostra un «Codice» copiabile: toccalo (compare
«Copiato») e mandalo all'assistenza HQE insieme alla segnalazione. Quel codice non è l'«ID richiesta» delle altre
pagine. Se chiudi tu la finestra di Google, non compare nulla. I messaggi possibili sono nella parte 11.

Solo nell'ambiente di sviluppo tecnico esiste un «Accesso di sviluppo» con la frase «Modalità sviluppo: scegli un
utente di prova, nessuna password richiesta.»: nell'ambiente di prova e in quello vero non c'è.

### Password dimenticata

1. Nella pagina «Accedi» premi «Password dimenticata?».
2. Leggi «Inserisci la tua email: ti mandiamo un link per scegliere una nuova password.», compila «Email» e premi
   «Invia il link». «Torna all'accesso» riporta al modulo.
3. Leggi «Se … ha un account, riceverai a breve un'email con il link. Controlla anche lo spam.». La frase è la stessa
   anche se l'indirizzo non è registrato: è voluto.
4. Apri il link nell'email e scegli la nuova password, poi accedi.

### Installare l'app sul telefono o sul computer

L'app si aggiunge alla schermata Home e si apre a schermo intero come un'app normale. La voce «Installa l'app» è in
fondo alla barra laterale (sul telefono nel menu a tre righe) e in Impostazioni, con la frase «Aggiungi l'app alla
schermata Home: si apre a schermo intero e riceve le notifiche.».

1. **Su Android con Chrome:** premi «Installa l'app» e poi «Installa» nella finestra del browser; oppure apri il menu di
   Chrome e scegli «Installa app» (l'app lo spiega così: «Su Android: apri il menu di Chrome e scegli «Installa app».»).
2. **Su iPhone e iPad:** apri il sito con Safari, tocca Condividi e poi «Aggiungi alla schermata Home». L'app lo spiega
   così: «Su iPhone: apri il sito in Safari, tocca Condividi e poi «Aggiungi alla schermata Home». Le notifiche push
   funzionano solo dall'app installata.».
3. **Su computer:** con Chrome o Edge premi «Installa l'app» oppure l'icona «Installa» nella barra degli indirizzi.
   L'app lo spiega così: «Usa Chrome o Edge: nella barra degli indirizzi compare l'icona «Installa». Su Android apri il
   menu di Chrome e scegli «Installa app».».
4. Quando l'app è installata, in Impostazioni compare «App installata su questo dispositivo» e la voce «Installa
   l'app» sparisce dal menu. Il pulsante «Installa» compare solo se il browser lo permette; con altri browser restano le
   istruzioni scritte. Installare l'app non attiva da sola le notifiche: vedi «Notifiche sul telefono».

### Muoversi nell'app

- **Su computer** c'è la barra laterale a sinistra con le pagine generali («Appartamenti», «Amministrazione» per gli
  amministratori, «Organizzazioni» per i gestori della piattaforma, «Impostazioni», «Esci») e, quando sei dentro un
  appartamento, le sue pagine («Panoramica», «Approvazioni», «Decisioni», «Consumi», «Riepiloghi», «Programmazione»,
  «Regole», «Assistente», «Simulatore» solo per gli amministratori sui dimostrativi).
- **Sul telefono** premi il pulsante con le tre righe in alto a sinistra («Apri il menu»): si apre il menu con le stesse
  pagine. Si chiude con la X («Chiudi il menu»), toccando fuori, con il tasto Esc o scegliendo una pagina. Se le schede
  di una pagina non stanno nello schermo, la loro barra scorre in orizzontale.
- La pagina aperta è evidenziata. In fondo al menu c'è **il tuo nome** in grassetto (quello scelto nelle Impostazioni)
  con sotto l'email in piccolo; se non hai scelto un nome, solo l'email. Sotto ci sono i tuoi ruoli, per esempio
  «Amministratore · Flatsharing» e, se sei anche di HQE, «Gestore della piattaforma».
- Nell'ambiente di prova, sopra il contenuto, resta sempre la fascia gialla «Ambiente di prova» · «i dati sono separati
  da quelli veri».

### Capire gli esiti: avvisi verdi, rossi e «ID richiesta»

- Un'azione riuscita mostra un avviso verde in alto (per esempio «Azione approvata», «Regole aggiornate»).
- Un errore mostra un avviso rosso con il messaggio e, se c'è, il pulsante «ID richiesta»: toccalo per copiare
  l'identificativo completo (compare «Copiato»). Il pulsante ne mostra solo l'inizio; passandoci sopra con il puntatore
  leggi il valore intero. Comunicalo all'assistenza insieme alla segnalazione e usalo nella ricerca delle Decisioni.
- Dove c'è «Riprova», premilo dopo aver risolto il problema indicato.
- Le eliminazioni chiedono sempre conferma.
- Se apri un indirizzo che non esiste leggi «Pagina non trovata» e «L'indirizzo non corrisponde a nessuna schermata.».
  Se apri una pagina di una funzione spenta leggi «Funzione non disponibile su questa istanza» e «Questa sezione non è
  attiva per l'appartamento o l'istanza non la implementa ancora.».
- I messaggi comuni a tutte le pagine («Server non raggiungibile», «Operazione non riuscita», «Errore …», «Richiesta non
  accettata dal server: ricarica la pagina e riprova.», «Sessione non valida o scaduta») sono spiegati nella parte 11.

### Impostazioni

La pagina «Impostazioni» è uguale per tutti i ruoli e ha questi riquadri.

- **«Profilo»**: «Email», «Ruolo», «Piattaforma» (solo se sei gestore della piattaforma), «Organizzazione»,
  «Appartamenti» (quali appartamenti vedi: «tutti gli appartamenti», i nomi, «… appartamenti» oppure «nessun
  appartamento»), «Ambiente». Durante un accesso di assistenza il profilo mostra l'organizzazione assistita.
- **«Account»**: «Nome visualizzato» (al massimo 80 caratteri) e «Salva»; compare «Nome aggiornato». È il nome che
  vedono i colleghi nelle Decisioni, nelle approvazioni, nei registri e in fondo al menu.
- **«Password ed email»** (solo per chi entra con email e password):
  «Cambia password» chiede «Password attuale», «Nuova password» e «Ripeti la nuova password» (almeno 8 caratteri);
  compare «Password cambiata». «Email di accesso» spiega «Oggi accedi con …. Il nuovo indirizzo diventa attivo quando
  apri il link che ti mandiamo lì.»: compila «Nuova email» e «Password attuale», premi «Cambia email» e apri il link
  nella nuova casella; intanto leggi «Link inviato a …: aprilo per completare il cambio». Chi entra con Google legge
  «Accedi con Google: password ed email si gestiscono dal tuo account Google.». Il ruolo di gestore della piattaforma è
  legato all'email: dopo un cambio di email va riassegnato da HQE.
- **«Sicurezza»**: «Esci da tutti i dispositivi» («Chiude la sessione su tutti i telefoni e computer, compreso questo.
  Su ogni dispositivo dovrai accedere di nuovo.») chiede «Uscire da tutti i dispositivi?» e conferma con «Sei uscito da
  tutti i dispositivi». «Elimina il mio account» («Elimina il tuo account e il tuo accesso all'app. L'operazione non si
  può annullare.») chiede conferma con «Eliminare definitivamente il tuo account?» e spiega: «Vengono cancellati il tuo
  accesso, il tuo nome, la tua email e le tue preferenze di notifica. Resta quello che hai fatto (decisioni,
  approvazioni, registro attività), ma al posto del tuo nome comparirà «utente rimosso». Per rientrare servirà un nuovo
  invito.». Compare «Account eliminato». Non è permesso all'ultimo amministratore («Sei l'unico amministratore: nomina
  un altro amministratore prima di eliminare il tuo account») né all'ultimo gestore della piattaforma («Sei l'ultimo
  gestore della piattaforma: nomina un altro gestore prima di eliminare il tuo account»). Nell'ambiente di prova
  l'eliminazione toglie le autorizzazioni di prova e conserva l'identità di accesso condivisa con il sito vero; nel sito
  vero cancella anche quella.
- **«Notifiche»**: quali avvisi ricevere sul telefono, per categoria, con quattro interruttori: «Approvazioni
  richieste» («Quando il motore chiede il tuo consenso»), «Dispositivi e istanza offline» («Dispositivo offline oltre la
  soglia della regola, istanza non raggiungibile, antigelo non attivo»), «Prenotazioni» («Avvisi sulle prenotazioni che
  cambiano il programma dell'appartamento») e «Riepilogo» («Ogni lunedì, solo se la settimana ha qualcosa da
  segnalare»). Sono tutti attivi dall'inizio; ogni cambio mostra «Preferenze salvate» e, se non riesce, l'interruttore
  torna com'era. Le scelte valgono per le notifiche sul telefono: gli avvisi dentro l'app compaiono comunque. Sotto c'è
  l'attivazione sul dispositivo (vedi «Notifiche sul telefono»). Il riquadro non compare a un gestore della piattaforma
  senza organizzazione: le notifiche sono legate agli appartamenti.
- **«Installa l'app»** con le istruzioni per iPhone, Android e computer (vedi sopra).
- **«Lingua»**: «Italiano», unica lingua disponibile; il selettore è disattivato.
- In fondo **«Esci»**: torni alla pagina «Accedi», i tuoi dati e le conversazioni con l'assistente vengono tolti da
  quel dispositivo e le notifiche su quel dispositivo si spengono. Se rientri tu, si riaccendono da sole.

Un gestore della piattaforma che non fa parte di nessuna organizzazione vede i riquadri «Account» e «Sicurezza», ma il
salvataggio del nome e «Esci da tutti i dispositivi» rispondono «Account non abilitato: mancano tenant o ruolo»;
«Elimina il mio account» funziona.

### Notifiche sul telefono

Le notifiche arrivano anche ad app chiusa, se le attivi su quel dispositivo.

1. In «Impostazioni» › «Notifiche», riquadro «Notifiche push su questo dispositivo», premi «Attiva su questo
   dispositivo» e consenti le notifiche quando il telefono o il browser lo chiede. Compare «Notifiche attive su questo
   dispositivo». «Dispositivi registrati: …» conta i tuoi dispositivi con le notifiche accese.
2. Se rifiuti il permesso leggi «Permesso non concesso: su questo dispositivo le notifiche restano spente.». Se le
   notifiche sono bloccate dal telefono o dal browser leggi «Le notifiche per questo sito sono bloccate. Per riceverle
   consenti le notifiche nelle impostazioni del browser o del telefono, poi torna qui.». Se le hai tolte dopo averle
   attivate leggi «Le notifiche su questo dispositivo sono state tolte dalle impostazioni del browser o del telefono.
   Premi «Attiva su questo dispositivo» per riattivarle.».
3. **Su iPhone e iPad** le notifiche arrivano solo all'app installata: aprendo il sito da Safari la scheda dice «Su
   iPhone e iPad le notifiche arrivano solo all'app installata: aggiungila alla schermata Home (vedi «Installa l'app»
   qui sotto), aprila dall'icona e attivale da qui.».
4. Se il browser non può ricevere notifiche leggi «Questo browser non può ricevere notifiche push: gli avvisi compaiono
   in alto nello schermo mentre l'app è aperta sulla pagina di un appartamento.».
5. «Disattiva» le ferma su quel dispositivo: «Notifiche disattivate su questo dispositivo».
6. Toccando una notifica si apre l'app sulla pagina giusta: «Approvazioni», la «Panoramica» dell'appartamento, le
   «Decisioni» (prenotazione annullata, antigelo non attivo) o il riepilogo della settimana. Se l'app è già aperta, la
   notifica compare come avviso in alto con il pulsante «Apri» (su iPhone arriva comunque come notifica del telefono);
   se stai già guardando quell'appartamento non compare un secondo avviso. Se non sei collegato, prima devi accedere e
   poi aprire la pagina da solo.
7. La scheda ricorda: «Quando esci da questo dispositivo le notifiche si spengono; quando rientri tu, si riaccendono da
   sole.». Al rientro leggi «Notifiche riattivate su questo dispositivo, come prima della tua uscita.» oppure, se il
   browser non dà più il permesso, «Notifiche non riattivate: il browser non ne dà più il permesso. Puoi riattivarle da
   Impostazioni › Notifiche.». Non si riaccendono se le avevi spente tu con «Disattiva». Un'altra persona che accede
   dallo stesso telefono non riceve le tue notifiche e non vede nulla della tua sessione; un calo di rete non le spegne.
8. In un ambiente senza notifiche sul telefono la scheda dice «Notifiche sul telefono non attive in questo ambiente» e
   «Gli avvisi compaiono in alto nello schermo mentre l'app è aperta sulla pagina di un appartamento.».

Le notifiche che puoi ricevere, con il nome dell'appartamento davanti:

| Categoria | Notifica | Quando arriva | Dove porta |
|---|---|---|---|
| «Approvazioni richieste» | «…: approvazione richiesta», con la proposta oppure «Il motore chiede il tuo consenso» | Quando il motore apre una richiesta (non per quelle in coda dietro un'altra) | «Approvazioni» |
| «Dispositivi e istanza offline» | «…: dispositivo offline», «… non risponde da oltre … minuti» | Dopo i minuti della regola «Avviso dispositivo offline» (15 all'inizio); regola spenta, niente avviso | «Panoramica» |
| «Dispositivi e istanza offline» | «…: istanza non raggiungibile», «Il connettore domotico risulta fermo» | Sistema domotico fermo oltre la stessa soglia; una volta per episodio | «Panoramica» |
| «Dispositivi e istanza offline» | «…: antigelo non attivo», «Sensore di temperatura mancante: antigelo non attivo» | A casa vuota, caldaia senza sensore utilizzabile; subito, una volta per episodio | «Decisioni» |
| «Prenotazioni» | «…: prenotazione annullata, appartamento rimesso a vuoto» | Disdetta dopo che l'appartamento era già stato preparato per l'arrivo | «Decisioni» |
| «Riepilogo» | «…: riepilogo della settimana», con la prima segnalazione e «E altre … voci.» | Il lunedì mattina, solo se la settimana ha qualcosa da segnalare | Il riepilogo di quella settimana |

Le notifiche arrivano solo per gli appartamenti che vedi. Un gestore della piattaforma in accesso di assistenza non
riceve quelle dell'organizzazione assistita.

### Uscire

«Esci» è nel menu e in fondo alle Impostazioni. Chiude la sessione su quel dispositivo, toglie dalla scheda i tuoi
dati e le conversazioni con l'assistente e spegne le notifiche su quel dispositivo. Se eri in un accesso di assistenza,
lo chiude. Per chiudere tutte le sessioni usa «Esci da tutti i dispositivi» nelle Impostazioni.

## 3. Chi può fare cosa

| Ruolo | Pagine che vede | Che cosa può fare |
|---|---|---|
| «Sola lettura» | «Appartamenti», «Impostazioni», tutte le pagine dell'appartamento tranne «Simulatore» | Guardare tutto, scaricare i rendiconti Excel, gestire il proprio account e le proprie notifiche. Non comanda, non approva, non scrive all'assistente. |
| «Operatore» | Come sola lettura | In più: cambiare modalità, forzare, comandare i dispositivi, approvare, programmare, cambiare le regole, usare l'assistente. |
| «Amministratore» | Come l'operatore, più «Amministrazione» e «Simulatore» sui dimostrativi | In più: invitare e gestire gli utenti, nome e indirizzo degli appartamenti, funzioni, prezzi, copia delle regole, Simulatore. Vede tutti gli appartamenti dell'organizzazione. |
| «Gestore della piattaforma» (HQE) | «Organizzazioni», «Impostazioni» e, se fa parte anche di un'organizzazione, le pagine del suo ruolo lì | Crea le organizzazioni e i loro primi amministratori, nomina altri gestori, crea e collega gli appartamenti, sospende e riattiva, apre accessi di assistenza. Da solo non vede dispositivi, consumi, decisioni né utenti. |
| Accesso di assistenza | «Appartamenti», «Organizzazioni», «Impostazioni» e tutte le pagine dell'appartamento | Un gestore della piattaforma dentro un'organizzazione per 1–24 ore, con i permessi di un operatore, su tutti i suoi appartamenti. |

Gli operatori e chi ha sola lettura vedono solo gli appartamenti che l'amministratore ha assegnato loro (oppure tutti,
se così impostato). Gli amministratori vedono sempre tutti.

## 4. Sola lettura: che cosa vedi

Chi ha il ruolo «Sola lettura» vede le stesse pagine dell'operatore. I pulsanti che cambiano qualcosa sono disattivati
e, passandoci sopra, compare «Il tuo ruolo consente solo la lettura». Questa parte descrive che cosa c'è in ogni pagina:
vale anche per operatori e amministratori.

### Appartamenti: che cosa vedi

La prima schermata, «Appartamenti», mostra «… appartamenti nel tuo account» e una scheda per appartamento.

- Nome, indirizzo e stato: «Online», «Non raggiungibile» oppure «Disattivato» (scheda grigia).
- L'etichetta «Dimostrativo» accanto al nome degli appartamenti finti usati per le prove.
- L'occupazione: «vuoto» (nessuno), «occupato» (ospiti dentro, dopo il check-in effettivo), «prenotato» (c'è una
  prenotazione ma non è stato comunicato l'arrivo).
- La modalità («Comfort», «Eco», «Casa vuota») e, se ci sono richieste aperte, una campanella con il numero.
- Quattro dati: «Prossimo check-in», «Prossimo check-out», «Oggi» (consumo di oggi in kWh, non un importo) e
  «Approvazioni in attesa». I dati si aggiornano ogni 20 secondi; un valore mancante è un trattino.
- Tocca una scheda per aprire l'appartamento («Apri …»).

Se non c'è nessun appartamento la pagina lo dice: «Nessun appartamento configurato» con «Per un nuovo appartamento
scrivi all'assistenza HQE.» (amministratori) o «Per un nuovo appartamento rivolgiti a un amministratore della tua
organizzazione.» (operatori e lettori). Se l'amministratore non ti ha assegnato appartamenti leggi «Nessun
appartamento assegnato al tuo account» e «Chiedi a un amministratore di assegnartene uno.»: il tuo account esiste
ancora. Se apri l'indirizzo di un appartamento che non puoi vedere leggi «Appartamento non disponibile», «Non esiste o
non è tra quelli assegnati al tuo account.» e il pulsante «Torna agli appartamenti». Un gestore della piattaforma con
una propria organizzazione vede il pulsante «Appartamento», che apre Organizzazioni (parte 7).

### Panoramica: che cosa vedi

- **In alto**: il nome, l'occupazione, «In tempo reale» (la pagina si aggiorna da sola) oppure «Riconnessione…» (sta
  ricollegandosi: non prendere per buono un valore vecchio), «Check-in», «Check-out», «Prenotazione» e «…/… dispositivi
  online».
- **La striscia di salute**: «In salute», «Degradata» o «Ferma»; «Connettore» «attivo» o «fermo», «… dispositivi
  connessi», «Modello» (lo stato dell'assistente), «Contratto» e «Ultimo evento …». Se il sistema domotico non risponde
  compare «Istanza non raggiungibile». Se la versione del sistema non è compatibile leggi «Versione del contratto non
  compatibile» e «L'istanza dichiara il contratto …: questa app supporta solo la versione 1.x. Contatta il supporto
  tecnico.».
- **«Modalità»**: la modalità attuale fra «comfort», «eco» e «casa vuota».
- **«Forza per…»**: se c'è una forzatura in corso leggi «Forzatura … attiva fino alle …» e «ancora …».
- **«Dispositivi»**, raggruppati per stanza («Senza stanza» per quelli senza): per ogni dispositivo lo stato e le
  letture. Prese e interruttori: «Acceso» o «Spento». Caldaia: «Riscaldamento abilitato» o «Riscaldamento disabilitato»
  e, se il suo misuratore segna più di 30 W, «sta scaldando ora». Climatizzatore: acceso o spento, «Modo» («caldo»,
  «freddo», «deumidifica», «ventilazione»), «Ventola» («auto», «bassa», «media», «alta»), «Temperatura» desiderata con
  «da … a … °C». Sensori: «Potenza» (in W, cioè quanto consuma adesso), «Oggi» (kWh di oggi), «Temperatura», «Umidità»,
  contatto finestra «Aperta» o «Chiusa» «da …», movimento «Movimento rilevato» o «Nessun movimento» (passando sopra
  leggi la data precisa).
- Un dispositivo che non risponde mostra «Dispositivo offline», «Visto …» e «Il dispositivo non è raggiungibile: i
  comandi sono disattivati». Una capacità che l'app non gestisce è segnata «non supportata» («Capacità non gestita
  dall'app: …»). Senza dispositivi leggi «Nessun dispositivo su questa istanza».
- **Sotto ogni comando** compare l'esito: «in corso», «eseguito», «errore» o «nessuna risposta», con il motivo
  («dispositivo offline», «rifiutato dal dispositivo», «bloccato da una regola», «bloccato da un'azione prioritaria»,
  «fuori dai limiti», «nessuna conferma», «errore interno») e un «ID richiesta» copiabile. Un climatizzatore comandato
  a infrarosso può risultare «non verificato» («Lo split non conferma l'esecuzione: lo stato mostrato è quello
  richiesto»).
- Mentre guardi un appartamento possono comparire avvisi in alto: «Nuova approvazione richiesta», «… è offline»,
  «Istanza domotica non raggiungibile», «Istanza domotica di nuovo raggiungibile». Compaiono anche se hai spento la
  categoria nelle notifiche.

### Approvazioni: che cosa vedi

«Approvazioni» («Azioni che il motore esegue solo con il tuo consenso») elenca le richieste. Il filtro «In attesa»
mostra quelle aperte; «Tutte» anche quelle decise negli ultimi 7 giorni. Ogni scheda mostra chi la propone («Motore
AI», «Regola», «Assistente», «Modulo»), la descrizione, «Perché il motore lo propone», «Azione proposta», lo stato («in
attesa», «approvata», «respinta», «scaduta»), «… rimasti» (in rosso sotto i 5 minuti) oppure «scaduta», la frase su
cosa succede alla scadenza («Alla scadenza verrà respinta», «Alla scadenza verrà eseguita» o «Alla scadenza resta in
attesa») e, dopo la decisione, «approvata da … …» o «respinta da … …» con la nota. Se non c'è nulla: «Nessuna
approvazione in attesa» o «Nessuna approvazione negli ultimi 7 giorni». La pagina si aggiorna ogni 30 secondi. C'è una
sola richiesta aperta per volta: le altre aspettano in coda e si aprono dopo.

### Decisioni: che cosa vedi

«Decisioni» («Tutto ciò che il motore e i gestori hanno fatto, e perché») è lo storico dell'appartamento, conservato
per 24 mesi. Ogni riga mostra data, chi ha deciso («Motore AI», «Regola «…»», «Gestore», «Assistente», «Sistema»; una
persona che ha eliminato l'account compare come «utente rimosso»), su cosa («appartamento», «dispositivo», «regole»,
«programmazione»), il tipo di azione in italiano (per esempio «Modalità», «Forzatura scaduta», «Programma: spostata»,
«Prenotazione annullata», «Disdetta dopo il pre-arrivo», «Antigelo: caldaia accesa», «Regolazione automatica
disattivata», «Antigelo non attivo»), il valore prima e dopo, il motivo, l'esito («applicata», «respinta», «in attesa
di approvazione», «non riuscita», «informativa») e l'«ID richiesta». Passando sopra il tipo compare il codice tecnico;
un'azione nuova non ancora tradotta mostra il codice.

- **Filtri**: «Chi», «Dispositivo» («Tutti i dispositivi»), «Periodo» («Tutto lo storico», «Ultimi 7 giorni», «Ultimi
  30 giorni», «Ultimi 90 giorni»). Si combinano. «Carica altri» mostra le righe precedenti. Se nulla corrisponde:
  «Nessuna decisione per i filtri scelti».
- **Ricerca**: scrivi nel campo «Cerca parole o un ID richiesta…». Cerca nel motivo, nell'azione, in chi ha deciso, nel
  dispositivo, nei valori e nei codici, a blocchi di 1.000 decisioni dalle più recenti: leggi «Ricerca in corso…», poi
  «Risultati: … · cercato fino al … (… decisioni esaminate)». Premi «Cerca più indietro» per continuare; alla fine leggi
  «Risultati: … · cercato in tutto lo storico disponibile (… decisioni esaminate)». Oltre 3.000 risultati compare
  «Raggiunti … risultati: restringi la ricerca con Periodo, Chi o Dispositivo.». Le decisioni nuove non entrano in una
  ricerca già iniziata: cancella la parola per vedere l'elenco aggiornato.
- **Ricerca per «ID richiesta»**: incolla l'identificativo completo copiato da un errore: la ricerca ignora i filtri e
  guarda tutto lo storico in un colpo solo («Ricerca per ID richiesta in tutto lo storico · risultati: …»). Un pezzo
  dell'identificativo fa invece una ricerca di parole.
- **Tipi da conoscere**: «Collegamento ai dispositivi perso» (il sistema non parla più con i dispositivi: i comandi
  vengono rifiutati finché non torna) e «Collegamento ai dispositivi ripristinato»; «Comando non verificato: misuratore
  offline» (il comando al climatizzatore è partito ma il misuratore che lo conferma non risponde); «Finestra: regola
  sospesa» (durante una forzatura). Le accensioni e gli spegnimenti ordinari del termostato della caldaia non sono tutti
  registrati: trovi quelli dell'antigelo e i problemi del sensore.

### Consumi: che cosa vedi e che cosa scarichi

«Consumi» («Energia elettrica misurata dai dispositivi») mostra i kWh misurati dai misuratori, ora per ora.

- Scegli il periodo: «Oggi» (da mezzanotte), «7 giorni», «30 giorni» (compreso oggi) oppure «Soggiorno in corso», che
  compare solo con ospiti dentro e una prenotazione conosciuta dall'app. Leggi «Totale periodo» in «kWh» e «Ore di clima
  evitate», oggi sempre «non calcolate». I numeri si aggiornano ogni minuto.
- Il grafico «Consumo per ora» (oggi) o «Consumo per giorno» (periodi più lunghi), con i valori al passaggio del
  puntatore, e «Per dispositivo». Le ore senza letture contano zero. Senza dati: «Nessun dato nel periodo».
- Sotto il grafico, «Consumi disponibili dal …» dice da quando ci sono misure: è la prima ora con un consumo maggiore di
  zero. Senza nessun dato la riga non compare. Nei dimostrativi i consumi prima dell'avvio sono un profilo di esempio
  dal 1° gennaio 2026.
- Con «Soggiorno in corso» leggi «Dal check-in del … a ora» e «… ospiti» e, se c'è un soggiorno precedente conosciuto
  dall'app, il riquadro «Soggiorno precedente» con date, ospiti, kWh e la percentuale «rispetto al precedente». Il
  confronto è fra i totali, senza correggere per durata o numero di ospiti; se il precedente era zero non c'è
  percentuale. Un soggiorno molto lungo (oltre 31 giorni) può non mostrare il grafico: «Periodo non valido: massimo 31
  giorni per richiesta».
- **«Rendiconto in Excel»** (per tutti i ruoli): «Consumi del mese scelto: riepilogo, giorno per giorno, ora per ora e
  per dispositivo, con l'importo in euro se è impostato il prezzo per kWh.». Scegli «Mese del rendiconto» (gli ultimi
  12, compreso quello in corso) e premi «Scarica Excel». Il file ha i fogli «Riepilogo», «Giornaliero», «Orario» e
  «Dispositivi». L'importo è kWh per il prezzo dell'appartamento o dell'organizzazione; senza prezzo il file dice
  «prezzo non impostato». Nel soggiorno in corso e nel confronto c'è «Excel del soggiorno»: il rendiconto dall'ora
  esatta di arrivo a quella di partenza (o a ora), con identificativo del soggiorno, numero di ospiti e stato, senza
  nomi o contatti degli ospiti; al massimo un anno. In testa al file «Consumi disponibili dal» dice da quando ci sono
  misure: le ore precedenti restano vuote (non a zero); «…: ore precedenti vuote», «…: nessun dato nel periodo» e
  «Periodo in corso: i dati arrivano fino al momento della generazione» spiegano i buchi; senza nessuna misura compare
  «Nessun consumo misurato finora».

### Riepiloghi: che cosa vedi

«Riepiloghi» («Il riepilogo di ogni settimana, pronto il lunedì mattina») c'è sempre, anche senza la funzione Consumi.

- L'elenco delle settimane, dalla più recente: «Settimana dal … al …» con «… segnalazioni», «1 segnalazione» o
  «Nessuna novità». Finché non ce n'è nessuno: «Nessun riepilogo ancora. Ogni lunedì mattina arriva quello della
  settimana appena finita.». L'elenco mostra al massimo 20 settimane; i riepiloghi restano conservati 12 mesi.
- Apri una settimana: «Riepilogo della settimana», «calcolato il …», le frasi già pronte oppure «Settimana senza
  novità». «Tutti i riepiloghi» torna all'elenco.
- Il riquadro «Consumi a parità di occupazione» («kWh per notte confrontati con la mediana delle stesse notti nelle 4
  settimane prima»): «Notti con ospiti» e «Notti vuote» con «… notti», «… per notte», «mediana prima …», lo stato «Nella
  norma», «Alto», «Confronto non disponibile» o «Nessuna notte», e «Per dispositivo». «Alto» vuol dire almeno il 30 %
  sopra il valore tipico delle 4 settimane prima e almeno 5 kWh in più. Nelle prime 5 settimane di misure vere leggi
  «dati insufficienti: servono 5 settimane di consumi veri», con «, disponibili dal …».
- Le segnalazioni: «… è offline da più di 24 ore.» (offline, non semplicemente spento), «Approvazione scaduta senza
  risposta: ….», «… aperta … volte con il clima spento dalla regola.» (almeno 3 volte nella settimana).
- Il riepilogo si prepara ogni lunedì dalle 8 del mattino, ora dell'appartamento; il controllo passa ogni ora, quindi
  può arrivare un po' dopo le 8. Se il sistema domotico non risponde, riprova al giro dopo. La notifica «Riepilogo» parte
  solo se c'è almeno una segnalazione: apri la pagina anche senza notifica.

### Programmazione: che cosa vedi

«Programmazione» («Azioni pianificate dal motore e dal gestore»): «In programma» e «Storico (ultimi 7 giorni)», con
aggiornamento ogni 30 secondi. Ogni riga ha l'orario (ora dell'appartamento), l'azione, l'origine («prenotazione»,
«gestore», «assistente»), il tipo («pre-arrivo», «check-out», «casa vuota», «manuale») e lo stato («in programma»,
«eseguita», «annullata», «non riuscita»). Senza azioni: «Nessuna azione in programma». Le azioni nate da una
prenotazione hanno la nota «Ricalcolata a ogni modifica della prenotazione».

### Regole: che cosa vedi

«Regole» («Automatismi del motore: attiva, disattiva e regola i parametri entro i limiti») mostra le otto regole con
interruttore, descrizione, valori e limiti «da … a …», e «Ultima modifica …». La regola «Pausa minima del compressore»
è segnata «Non modificabile» («Questa regola è fissata dal motore: puoi solo vederla»). Le regole, i loro valori e che
cosa fanno davvero sono nella parte 10. Gli operatori e gli amministratori possono anche modificarle (parte 5).

### Assistente per chi ha sola lettura

La pagina «Assistente» compare anche a chi ha sola lettura, se la funzione è attiva, ma non si possono inviare
richieste e non si vedono le domande dei colleghi: il server le rifiuta. Resta visibile solo una conversazione
eventualmente già presente in quella scheda del browser.

### Il tuo account

Anche con sola lettura gestisci tutto quello che riguarda te: nome, password, email, notifiche, installazione, uscita
da tutti i dispositivi ed eliminazione dell'account (parte 2, «Impostazioni»).

## 5. Operatore: che cosa puoi fare

L'operatore vede tutto quello della parte 4 e in più comanda. Le stesse cose le fa anche l'amministratore e chi lavora
con un accesso di assistenza.

### Panoramica: modalità, forzature e dispositivi

**Cambiare modalità.** Sotto «Modalità» tocca «comfort», «eco» o «casa vuota». La scelta si illumina quando il
sistema conferma (non c'è un avviso verde) e nelle Decisioni compare «Modalità» con prima e dopo, per esempio «comfort →
casa vuota». Che cosa fa ogni modalità è nella parte 10: in breve, comfort scalda alla temperatura di comfort, eco
abbassa la caldaia e spegne il clima, casa vuota spegne il clima e tiene solo l'antigelo. I comandi partono solo ai
dispositivi online; il cambio di modalità non garantisce che ogni singolo comando riesca: controlla gli esiti sotto i
dispositivi e le Decisioni. Un cambio di modalità fatto a mano non chiede conferma, anche con ospiti dentro.

**Forzare per un po'.** Sotto «Forza per…» premi «30 min», «2 h» o «6 h». Compare «Forzatura … attiva fino alle …» con
«ancora …» e il pulsante «Annulla forzatura». La forzatura tiene la modalità attuale e sospende gli automatismi del
comfort: la regola della finestra aperta non spegne il clima (nelle Decisioni «Finestra: regola sospesa», con l'ora in
cui riparte), la regolazione automatica del clima si ferma, un cambio di modalità programmato (per esempio il check-out)
aspetta la fine della forzatura (nelle Decisioni «Azione rimandata», «rimandata per la forzatura»). L'antigelo resta
attivo. Se c'è una finestra aperta, prima di partire l'app avvisa con «Finestra aperta» e «Finestra aperta in …: durante
la forzatura il clima resta acceso.» (o «Finestre aperte in …: …»): scegli «Forza comunque» o «Annulla». Alla fine
(«Forzatura scaduta» nelle Decisioni) o con «Annulla forzatura» («Forzatura annullata») le regole ripartono: se la
finestra è ancora aperta oltre la soglia, il clima si spegne subito.

**Comandare i dispositivi** (solo online e con la funzione «Comandi» attiva):

- Prese e interruttori: tocca l'interruttore («Accendi …» / «Spegni …»); lo stato diventa «Acceso» o «Spento».
- Caldaia: «Attiva …» / «Disattiva …» abilita o disabilita il riscaldamento («Riscaldamento abilitato» /
  «Riscaldamento disabilitato»). Abilitato vuol dire «può scaldare»: è il termostato del sistema che accende e spegne
  davvero la caldaia intorno alla temperatura voluta, usando il sensore della stanza. Senza un sensore utilizzabile la
  caldaia segue il tuo comando così com'è, senza regolazione (parte 10).
- Temperatura desiderata di caldaia e climatizzatore: «Diminuisci temperatura» e «Aumenta temperatura» accanto a
  «Temperatura», a passi di 0,5 °C, entro «da … a … °C». Fuori dai limiti il comando è rifiutato («Il setpoint deve
  essere tra … e …»).
- Climatizzatore: interruttore, «Modo» («caldo», «freddo», «deumidifica», «ventilazione») e «Ventola» («auto»,
  «bassa», «media», «alta»). Dopo uno spegnimento la riaccensione aspetta la pausa del compressore (3 minuti all'inizio):
  un comando automatico viene rimandato, uno tuo può essere rifiutato se manca più di qualche secondo.
- Dopo ogni comando leggi l'esito: «in corso», «eseguito», «errore» o «nessuna risposta», con il motivo. Un
  climatizzatore a infrarosso viene confermato dal suo misuratore entro una decina di secondi (consumo su di almeno
  20 W per l'accensione, sotto 15 W per lo spegnimento); se il misuratore non risponde l'esito è «non verificato».
- Un comando tuo su un climatizzatore o sulla caldaia toglie quel dispositivo alla regolazione automatica della modalità
  fino al prossimo cambio di modalità: il sistema non va mai contro il comando di una persona.
- «Azioni per …» (menu con i tre puntini) › «Rinomina o sposta» apre «Modifica dispositivo» («Cambia il nome visibile o
  la stanza. La configurazione del dispositivo non viene toccata.»): «Nome» (da 1 a 60 caratteri), «Stanza» (una stanza
  esistente), «Salva» o «Annulla»; compare «Dispositivo aggiornato». Funziona anche con la funzione Comandi spenta.

### Approvazioni: approvare o respingere

1. Apri la notifica oppure «Approvazioni» › «In attesa».
2. Leggi la descrizione, «Perché il motore lo propone», «Azione proposta», il tempo rimasto e la frase sulla scadenza.
3. Se vuoi, scrivi una «Nota (facoltativa)» («Perché approvi o respingi…», al massimo 500 caratteri).
4. Premi «Approva» (compare «Azione approvata») o «Respingi» («Azione respinta»). La richiesta passa a «approvata» o
   «respinta» con «… da … …» e la nota; la successiva in coda si apre.
5. Controlla l'esito vero in Panoramica e nelle Decisioni: un'azione approvata può non partire se nel frattempo il
   dispositivo è diventato irraggiungibile. Se una richiesta è già stata decisa da un collega leggi «L'approvazione è già
   stata decisa».

Alla scadenza (30 minuti all'inizio): le richieste dell'assistente vengono respinte; «Mettere l'appartamento a vuoto
dopo il check-out» viene eseguita; «Spegnere …» di un apparecchio che consuma a casa vuota viene respinta, salvo
un'impostazione diversa dell'appartamento. Nelle Decisioni compare «Approvazione scaduta».

### Programmazione: aggiungere, spostare, annullare

- **«Nuova azione»** apre «Programma un'azione» («L'azione verrà eseguita dal motore all'orario indicato (ora di …).»).
  Compila «Quando» (un orario futuro, nel fuso dell'appartamento) e «Cosa fare»: «Cambia modalità» con «Modalità»
  («comfort», «eco», «casa vuota») oppure «Comando a un dispositivo» con «Dispositivo» e «Comando»: per le prese
  «Accendi» o «Spegni»; per clima e caldaia «Spegni» oppure «Imposta temperatura» con «Temperatura (°C)», che accende
  anche l'apparecchio. Premi «Salva»: compare «Azione programmata». Un orario passato dà «L'orario deve essere nel
  futuro». Un cambio di modalità programmato durante una forzatura aspetta la sua fine.
- **«Sposta»** su una voce in programma apre «Sposta l'azione»: cambia «Quando» e premi «Salva» («Orario aggiornato»).
  Il modulo parte da un'ora dopo adesso, non dall'orario salvato: controlla la data. Si possono spostare anche le azioni
  nate da una prenotazione; una modifica della prenotazione può ricalcolarle.
- **«Annulla azione»** chiede «Annullare questa azione programmata?» e mostra «Azione annullata»; la voce resta nello
  storico. Solo per le azioni ancora «in programma»; una voce già eseguita o annullata risponde «L'azione è già stata
  eseguita o annullata».

### Regole: cambiare i valori e chiedere una proposta

- **A mano**: cambia gli interruttori e i campi numerici delle regole modificabili («Minuti», «Minimo (°C)», «Massimo
  (°C)», «Temperatura in comfort (°C)», «Temperatura in eco (°C)», «Raffrescamento in comfort (°C)», «Temperatura (°C)»,
  «Umidità (%)», «Ore prima del check-in», «Minuti dopo il check-out», «Minuti di presenza dopo il check-out»). In basso
  compare «… regole modificate» con «Salva le modifiche» e «Annulla le modifiche» (riporta i campi ai valori salvati).
  Un valore fuori dai limiti è segnalato sotto il campo («Valore fuori dai limiti (…–…)»), così come «Il minimo non può
  superare il massimo», «La temperatura eco non può superare quella comfort» e «La temperatura di raffrescamento deve
  essere più alta di quella comfort»: finché c'è un errore il salvataggio resta disattivato. Dopo «Salva le modifiche»
  leggi «Regole aggiornate»; la modifica è nelle Decisioni («Regole aggiornate»). I nuovi limiti minimo e massimo si
  applicano subito ai climatizzatori. Le nuove temperature delle modalità valgono dal prossimo cambio di modalità e, in
  comfort, dalla regolazione automatica del clima.
- **«Chiedi all'assistente»** (in alto nella pagina Regole): «Scrivi che cosa vuoi cambiare: l'assistente prepara la
  modifica, tu la controlli e la applichi. Niente cambia finché non premi «Applica».». Scrivi in italiano (esempio
  «la finestra aperta spegne dopo 10 minuti»; al massimo 500 caratteri, contatore «…/… caratteri») e premi «Proponi».
  Leggi «Preparo la proposta…», poi «Modifiche proposte»: regola, campo, valore prima e dopo (per esempio «Finestra
  aperta spegne il clima, Minuti da 5 a 10», «Stato» «attiva» o «spenta») e la spiegazione. Premi «Applica» («Regole
  aggiornate come proposto») o «Scarta». Se la richiesta non riguarda le regole o è fuori dai limiti, l'assistente lo
  dice e non propone nulla. Frasi semplici capite subito: «finestra 10 minuti», «antigelo 10 gradi», «spegni la regola
  dell'antimuffa», «presenza al check-out 45 minuti», «setpoint da 18 a 25», «comfort 22», «eco 17», «raffrescamento 26».
  «temperatura 22» da sola fa chiedere «È la temperatura comfort, eco, di raffrescamento o un limite (minimo o massimo)?
  Scrivilo, per esempio «comfort 22» o «massimo 24».». Per le frasi più articolate risponde il modello; se non risponde
  in tempo leggi «L'assistente non ha risposto in tempo: riprova con una frase più breve, oppure cambia la regola a mano
  qui sotto.». Una proposta non mostra mai valori che il salvataggio rifiuterebbe (eco non sopra comfort, raffrescamento
  sopra comfort). Al massimo 20 richieste al giorno per appartamento, per tutti gli utenti insieme («Hai già chiesto 20
  proposte oggi per questo appartamento: riprova domani o cambia le regole a mano»). Se hai modifiche a mano non salvate,
  «Applica» è disattivato: «Salva o annulla prima le modifiche fatte a mano». Se nel frattempo qualcuno ha cambiato le
  regole leggi «Le regole sono cambiate nel frattempo: rifai la richiesta»; se sono già così, «Le regole sono già così:
  non c'è niente da cambiare». La modifica applicata è nelle Decisioni e nel «Registro dell'organizzazione» con il tuo
  nome («… ha modificato le regole dell'appartamento … su proposta dell'assistente»); quello che hai scritto non viene
  conservato.

Il riquadro «Applica le stesse regole ad altri appartamenti» è riservato agli amministratori (parte 6).

### Assistente: chiedere e comandare in italiano

«Assistente» («Chiedi in italiano: spegnere, impostare una temperatura, programmare un'azione»).

1. Scrivi nel campo («Es. «Spegni il clima del soggiorno»», al massimo 500 caratteri) e premi «Invia», oppure tocca un
   suggerimento: «Spegni il clima del soggiorno», «Porta il soggiorno a 21 gradi», «Alle 18 metti il clima a 22 gradi»,
   «Spegni la caldaia».
2. Leggi «Sto elaborando…», poi la risposta con lo stato «risposto», «richiede approvazione» o «non riuscita». Se dopo
   30 secondi non c'è risposta leggi «Nessuna risposta dall'assistente: riprova».
3. L'assistente legge stati, dispositivi, consumi (fino a 31 giorni per volta), programmazioni e Decisioni (le ultime
   50) e risponde a domande come «perché si è spento il clima?». Non riceve mai dati personali degli ospiti. Se non sa,
   risponde «Non lo so: guarda nell'app.». Ogni domanda è a sé: non ricorda la chat precedente.
4. Può fare solo quello che fa un operatore: cambiare modalità, comandare prese, clima e caldaia, programmare. Non tocca
   regole (rimanda alla pagina Regole), utenti e appartamenti. L'esito lo scrive il sistema, non il modello: «Fatto: ….»
   solo quando il dispositivo ha confermato; «Comando inviato: …, l'esito arriva nell'app.» se la conferma non è ancora
   arrivata; «Non riuscito: … (…).» o «Non fatto: … (…).» con il motivo; «Programmato: ….» per un'azione a orario.
   Sotto la risposta compaiono le etichette «Comando» e «Programmazione» con gli identificativi. Controlla sempre in
   Panoramica.
5. **Con ospiti dentro**, spegnere il clima o la caldaia e cambiare modalità non avviene da solo: l'assistente chiede in
   chat, per esempio «Spengo climatizzatore soggiorno con ospiti presenti? Rispondi Sì o No qui sotto, oppure dalla
   pagina Approvazioni.», con i pulsanti «Sì» e «No», «Scade alle …» e il link «Vai alle approvazioni». È la stessa
   richiesta della pagina Approvazioni: la tua risposta compare lì e nelle Decisioni con il tuo nome; senza risposta
   entro 30 minuti è respinta. Due o più azioni in una stessa richiesta («spegni clima e caldaia») chiedono una conferma
   ciascuna, in coda, anche senza ospiti; se davanti c'è un'altra approvazione da decidere leggi «In attesa: prima va
   decisa l'approvazione aperta.». Dopo il clic leggi «Approvato: il comando parte, l'esito arriva nell'app» o
   «Respinto» e poi «Ora: …» per la successiva. Riaprendo la conversazione leggi «Approvata da te alle …», «Respinta da
   te alle …», «Già decisa: approvata», «Già decisa: respinta» (un collega ha deciso) o «Scaduta». Chi gestisce il
   sistema domotico può impostare la conferma in altro modo: sempre, oppure solo per più azioni insieme.
6. **Programmare con ospiti** (dal lotto 30): se chiedi un'azione a un orario in cui, secondo le prenotazioni, ci
   saranno ospiti e l'azione tocca il loro comfort (cambio di modalità, clima o caldaia spenti), l'assistente chiede
   «Programmo …, con ospiti presenti a quell'ora? Rispondi Sì o No qui sotto, oppure dalla pagina Approvazioni.»; in
   Approvazioni la richiesta si legge «Programmare …». Con «Sì» l'azione compare in Programmazione all'ora chiesta, con
   origine «assistente»; con «No» o senza risposta non viene programmata. Accendere qualcosa non chiede conferma; il
   controllo si fa quando chiedi, non all'ora dell'azione. L'orario deve essere almeno 30 secondi avanti; senza fuso è
   l'ora dell'appartamento.
7. «Svuota conversazione» pulisce la vista («Nessuna conversazione in questa sessione»): non cancella le richieste né
   le Decisioni. La conversazione resta solo in quella scheda del browser (ultime 50 richieste per appartamento) e sparisce
   quando esci.
8. Limiti: 50 domande al giorno per appartamento («Limite di … domande al giorno raggiunto per questo appartamento:
   riprova domani.») e un tetto di spesa mensile per tutto il servizio («Limite mensile raggiunto, riprova dal mese
   prossimo»). Se l'assistente non ce la fa in tempo leggi «Non sono riuscito a rispondere in tempo: riprova, oppure fai
   dall'app.» oppure «L'assistente non è disponibile ora, riprova più tardi» o «Non sono riuscito a rispondere: riprova.».
   Se aveva già proposto delle azioni le esegue comunque e te lo scrive.

Sui dimostrativi senza il modello configurato risponde un riconoscitore semplice: capisce «spegni …», «… a 21 gradi» e
«alle 18 …» (se l'ora è già passata, programma per domani); se nomini la caldaia con ospiti dentro chiede l'approvazione
per spegnerla («Spegnere la caldaia con ospiti presenti richiede la tua approvazione.», oppure «C'è già un'approvazione
in attesa: decidi prima quella.»); altrimenti risponde «Non ho capito. Posso spegnere, impostare una temperatura o
programmare un'azione.» o «Indica la temperatura, ad esempio «porta il soggiorno a 21 gradi».».

## 6. Amministratore: che cosa puoi fare in più

L'amministratore fa tutto quello delle parti 4 e 5 su tutti gli appartamenti dell'organizzazione e in più ha la pagina
«Amministrazione» («Utenti, appartamenti e funzioni della tua organizzazione»), la copia delle regole e il Simulatore.

### Amministrazione: le cinque schede

«Appartamenti» (aperta all'inizio), «Utenti», «Funzioni», «Prenotazioni ricevute», «Registro dell'organizzazione».
Riguardano solo la tua organizzazione. Chi non è amministratore non vede la pagina («Operazione riservata agli
amministratori» se ci prova dal server).

### Utenti: invitare, ruoli, appartamenti visibili, rimuovere

- **«Invita un utente»** («L'utente riceve un'email con il link all'app: entra con Google o sceglie una password. Il
  ruolo decide cosa può fare.»): compila «Email», «Nome», «Ruolo» («Amministratore», «Operatore», «Sola lettura») e, per
  operatore e sola lettura, «Appartamenti visibili» («Tutti gli appartamenti» oppure le caselle). Premi «Invita». Esiti:
  «Invito inviato a …»; «Invito registrato, ma l'email a … non è partita. Riprova con «Reinvia».»; «Invito registrato.
  L'invio email non è attivo: avvisa tu …». L'invito resta registrato anche se l'email non parte. Una persona può stare
  in una sola organizzazione («È già un utente della tua organizzazione»); le persone di HQE non si possono invitare
  («Questa email non può essere invitata»).
- **Elenco**: email, nome, ruolo, «… dispositivi push» (i dispositivi con le notifiche accese), appartamenti visibili;
  «in attesa del primo accesso» finché la persona non entra; «tu» accanto a te.
- **«Reinvia»** su chi è in attesa: stessi esiti dell'invito. Le email hanno dei limiti: al massimo 3 ogni 10 minuti e
  10 ogni 24 ore per destinatario, 50 ogni ora per organizzazione; oltre, l'invito resta e l'email non parte: riprova
  più tardi. Se la persona è già entrata: «L'utente ha già effettuato l'accesso».
- **Cambiare ruolo**: il selettore «Ruolo» accanto alla persona; compare «Ruolo aggiornato». La persona viene fatta
  uscire da tutti i dispositivi entro circa un minuto e rientra con il ruolo nuovo. Non puoi cambiare il tuo («Non puoi
  togliere a te stesso il ruolo di amministratore») e deve restare un amministratore («Deve restare almeno un
  amministratore nell'organizzazione»). Chi diventa amministratore vede tutti gli appartamenti.
- **Appartamenti visibili**: premi «Appartamenti» accanto a un operatore o a un lettore; si apre «Appartamenti di …»
  («Scegli quali appartamenti vede questo utente. Gli amministratori vedono sempre tutti gli appartamenti.»): «Tutti gli
  appartamenti» oppure le caselle, poi «Salva» («Appartamenti aggiornati»). Senza nessuna casella leggi «Nessun
  appartamento scelto: l'utente non vedrà nessun appartamento finché non ne assegni almeno uno.» e devi confermare
  «Nessun appartamento scelto: … non vedrà nessun appartamento finché non ne assegni almeno uno. Confermi?»: serve a
  sospendere un accesso senza cancellare la persona. Caso tipico: il proprietario di un immobile, invitato come «Sola
  lettura», che vede solo il suo appartamento. Un utente limitato vede, riceve notifiche e agisce solo sui suoi
  appartamenti; se gli togli un appartamento mentre lo guarda, entro mezzo minuto la pagina smette di aggiornarsi e
  compare «Appartamento non disponibile».
- **«Elimina»** sulla persona chiede «Rimuovere l'utente …?» e mostra «Utente rimosso»: toglie accesso e notifiche; le
  sue azioni restano nei registri per 24 mesi con il nome. Non puoi eliminare te stesso («Non puoi eliminare il tuo stesso
  account»). Una persona rimossa non può più entrare nelle Impostazioni per cancellare da sola nome ed email: se serve,
  lo chiede a HQE.

### Appartamenti: anagrafica, attivo, verifica connessione, prezzo

- Ogni scheda mostra nome, «Indirizzo», «Fuso orario», «URL istanza», «ID Italianway», «Ultima verifica» («mai
  eseguita», «riuscita il …», «non riuscita il …»), «Funzioni», il prezzo che vale («Prezzo dell'energia: … (solo per
  questo appartamento)» o «Prezzo dell'energia: … (dell'organizzazione)») e «Dimostrativo». L'identificativo
  dell'appartamento si copia toccandolo. Non ci sono «Nuovo appartamento» né cestino: «I nuovi appartamenti li aggiunge
  il gestore della piattaforma (HQE): per averne uno, scrivi all'assistenza.».
- **«Modifica»** apre «Modifica appartamento»: «Nome», «Indirizzo», «Fuso orario», «Attivo», «Prezzo per kWh di questo
  appartamento (€)» («Lascia vuoto per usare quello dell'organizzazione (…).»), poi «Salva» («Appartamento salvato»).
  «Collegamento al sistema domotico» e codice Italianway si vedono ma non si cambiano: «Il collegamento al sistema
  domotico lo imposta il gestore della piattaforma (HQE). Se va cambiato, scrivi all'assistenza.», «Il codice Italianway
  lo imposta il gestore della piattaforma (HQE). Se va cambiato, scrivi all'assistenza.». Un fuso non valido dà «Fuso
  orario non valido». Il fuso salvato qui vale per gli orari mostrati e scritti dall'app; il motore dell'appartamento usa
  il fuso con cui è stato configurato da HQE.
- **«Attivo»** (nella scheda o in Modifica): spento, l'appartamento compare «Disattivato» nell'elenco, le operazioni
  rispondono «Appartamento disattivato» e le prenotazioni non vengono inoltrate. Non spegne i dispositivi né gli
  automatismi del sistema domotico.
- **«Verifica connessione»**: controlla che il sistema domotico risponda; leggi «Connessione OK» o «Problema di
  connessione» («Se la verifica non riesce, avvisa l'assistenza.») e «Ultima verifica». Un esito negativo è un risultato,
  non un errore dell'app. Messaggi possibili: «Istanza non raggiungibile», «Chiave dell'istanza non configurata:
  contatta l'assistenza HQE».
- **«Prezzo dell'energia»** (in cima): «Serve per l'importo in euro nei rendiconti Excel dei consumi. Vale per tutti
  gli appartamenti; per un appartamento puoi impostarne uno diverso da «Modifica».». Compila «Prezzo per kWh (€)» (da 0
  a 10, al massimo 4 decimali, virgola o punto; esempio 0,25) e premi «Salva» («Prezzo dell'energia salvato»). Campo
  vuoto = prezzo tolto («non impostato»); zero è un prezzo valido. Errore: «Scrivi un numero da 0 a 10 con al massimo 4
  decimali, per esempio 0,25.». Ogni cambio resta nel «Registro dell'organizzazione».

### Funzioni

«Funzioni dell'organizzazione …» («Disattiva qui una funzione per nasconderla in tutti gli appartamenti; ogni
appartamento può avere un'eccezione.»): nove interruttori, Panoramica, Dispositivi, Comandi, Consumi, Programmazione,
Regole, Approvazioni, Decisioni, Assistente, ciascuno con sotto il nome tecnico. Ogni cambio si salva subito
(«Funzioni aggiornate»); «Ripristina tutte» riaccende tutto. Per ogni appartamento c'è lo stesso elenco con «eredita
dall'organizzazione» oppure «eccezione per questo appartamento»; «Torna all'organizzazione» toglie l'eccezione.
L'eccezione sostituisce la scelta dell'organizzazione e può anche riaccendere una funzione spenta per tutti. Riepiloghi
non ha interruttore: c'è sempre. Una funzione che il sistema domotico non ha resta comunque non disponibile.

### Prenotazioni ricevute

«Le ultime 100 comunicazioni di prenotazione arrivate da Italianway per i tuoi appartamenti, e se sono state trasmesse
al motore che gestisce l'appartamento.» Si aggiorna ogni 30 secondi; le prove del Simulatore non passano da qui.

- In cima: «Ultime 24 ore: … ricevute, … trasmesse, … con problemi» (calcolato sulle 100 righe disponibili).
- Ogni riga: una frase come «Prenotazione creata · Milano Centro · dal 1 dic 2026 al 3 dic 2026» (eventi: «Prenotazione
  creata», «Prenotazione modificata», «Prenotazione cancellata», «Check-in», «Check-out»; se il messaggio non si legge,
  «Evento ricevuto, formato non riconosciuto»), poi l'esito e la data di ricezione (fuso italiano). Senza righe:
  «Nessuna prenotazione ricevuta».
- «Dettagli tecnici» apre, per l'assistenza: «firma valida» o «firma non valida», «Codice di risposta», «Codice
  Italianway», «Ospiti» (il numero), gli identificativi (l'«ID richiesta» si copia), «Inoltro a /bookings» o «non
  inoltrato», «… tentativi», «Corpo grezzo». I dati personali degli ospiti sono oscurati. Non c'è un pulsante per
  ritrasmettere.

| Esito | Che cosa vuol dire |
|---|---|
| «Ricevuta e trasmessa al motore» | Tutto a posto: il sistema domotico l'ha ricevuta, anche se l'aveva già. |
| «Ricevuta ma il motore non l'ha accettata», «… (riprovato 1 volta)», «… (riprovato … volte)» | Il sistema domotico non ha risposto o ha dato errore, anche dopo i tentativi. Avvisa l'assistenza. |
| «Ricevuta ma non trasmessa: appartamento disattivato» | L'appartamento è spento con l'interruttore «Attivo». |
| «Ricevuta ma non trasmessa: formato non riconosciuto» | Il messaggio di Italianway non si è potuto leggere. Avvisa l'assistenza. |
| «Ricevuta ma rifiutata: firma non valida», «Ricevuta: appartamento non riconosciuto» | Qui quasi mai: queste comunicazioni non si possono attribuire a nessuna organizzazione e le vede HQE in «Prenotazioni non attribuite». |
| «Ricevuta ma non trasmessa» | Qualsiasi altro caso. Avvisa l'assistenza. |

### Registro dell'organizzazione

«Chi ha fatto cosa nella tua organizzazione: inviti, ruoli, appartamenti, funzioni e accessi di assistenza.» Ogni voce
è una frase con la data, dalla più recente, 50 per volta («Carica altri»): per esempio «Anna Rossi ha cambiato il ruolo
di bruno@… da «Sola lettura» a «Operatore»», «… ha copiato le regole da «…» all'appartamento …», «… ha modificato le
regole dell'appartamento … su proposta dell'assistente», «… ha aperto un accesso di assistenza a … fino al …». Senza
voci: «Nessuna attività registrata». Chi ha eliminato il proprio account compare come «Utente rimosso». Le modifiche
delle regole fatte a mano sono nelle Decisioni, non qui. Conservazione 24 mesi. Prima si chiamava «Registro attività».

### Copiare le regole su altri appartamenti

Nel riquadro «Applica le stesse regole ad altri appartamenti», in fondo alla pagina «Regole» («Copia le regole salvate
di questo appartamento (attive o spente e valori) sugli appartamenti che scegli. Prima vedi che cosa cambia in
ciascuno, poi confermi.»):

1. Salva o annulla prima le modifiche fatte a mano.
2. Scegli gli appartamenti di destinazione o «Seleziona tutti» (al massimo 100 per volta, stessa organizzazione) e premi
   «Vedi che cosa cambia» («Preparo l'anteprima…»). Senza altri appartamenti leggi «Nessun altro appartamento nella tua
   organizzazione».
3. Leggi «Che cosa cambia copiando le regole di «…»»: per ciascuno i valori che cambieranno, oppure «Già uguale, nessuna
   modifica», «Appartamento disattivato: non verrà toccato», «Motore non raggiungibile: non verrà toccato», «Non
   applicabile a questo appartamento». Se un appartamento ha valori personalizzati leggi «Ha regole personalizzate che
   verranno sovrascritte: …». L'anteprima controlla anche che eco non superi comfort e che il raffrescamento sia sopra
   comfort. Si copiano solo le regole modificabili e i valori che esistono nella destinazione.
4. Premi «Copia su … appartamenti» (o «Copia su 1 appartamento»); «Annulla» abbandona. Leggi «Copia in corso…» e
   «Esito della copia», appartamento per appartamento: «Regole copiate», «Regole cambiate dopo l'anteprima: non toccato»,
   «Appartamento disattivato: non toccato», «Motore non raggiungibile: non toccato», «Già uguale, nessuna modifica».
   «Chiudi» chiude gli esiti. Se le regole di partenza sono cambiate: «Le regole dell'appartamento di partenza sono
   cambiate: rifai l'anteprima».
5. Ogni appartamento toccato ha una riga nelle sue Decisioni e nel «Registro dell'organizzazione».

### Simulatore

Gli appartamenti dimostrativi (etichetta «Dimostrativo» in ogni elenco) usano un sistema domotico simulato: servono per
le prove e le dimostrazioni, anche accanto agli appartamenti veri. Su di loro gli amministratori vedono «Simulatore»
(«Provoca eventi su questo appartamento dimostrativo: lo vedono solo gli amministratori.»); su un appartamento vero la
voce non c'è e l'indirizzo dà «Pagina non trovata».

- **«Finestre»** («Apri una finestra: dopo i minuti della regola «finestra aperta» clima e caldaia si spengono»):
  l'interruttore di ogni sensore mostra «aperta» o «chiusa» («Finestra aperta», «Finestra chiusa»). Senza sensori:
  «Nessun sensore finestra».
- **«Movimento»** («Simula il passaggio di una persona davanti al sensore: il motore registra l'ora del movimento, come
  con un sensore vero»): «Simula movimento» per ogni sensore («Movimento simulato su …»), con «ultimo movimento …» o
  «nessun movimento». Serve a provare «Mettere l'appartamento a vuoto dopo il check-out». Senza sensori: «Nessun
  sensore di movimento».
- **«Connettività dispositivi»** («Metti un dispositivo offline: i comandi vengono rifiutati e scatta l'avviso oltre la
  soglia»): interruttore «online» / «offline» per ogni dispositivo («Dispositivo online», «Dispositivo offline»).
  Tornare online prima della soglia annulla l'avviso.
- **«Approvazione»** («Fa nascere una richiesta reale di approvazione dal motore»): «Richiedi un'approvazione» crea una
  richiesta vera di spegnimento del primo apparecchio con misuratore («Approvazione generata»); se non ce n'è, «Nessun
  apparecchio con misuratore da proporre nell'appartamento».
- **«Evento prenotazione»** («Prenotazione di prova come se arrivasse da Italianway: fa lo stesso percorso di una
  prenotazione vera fino al motore dell'appartamento. Ripetere lo stesso invio non la duplica.»): «Tipo evento»
  («Prenotazione creata», «Prenotazione modificata», «Prenotazione annullata», «Check-in effettivo», «Check-out
  effettivo»), «ID prenotazione», «Check-in», «Check-out», «Ospiti»; «Invia evento». Leggi «Evento prenotazione
  inoltrato» e «… azioni programmate». Ripremendo «Invia evento» senza cambiare nulla leggi «Evento già elaborato
  (idempotente)»: è lo stesso evento, non viene duplicato; cambiando un campo è un evento nuovo. Il check-out deve
  venire dopo il check-in («Il check-out deve essere successivo al check-in»). Queste prove non compaiono in
  «Prenotazioni ricevute».
- **«Ripristina lo stato iniziale»** («Riporta l'appartamento dimostrativo com'era all'inizio, per ricominciare una
  prova da capo.»): il pulsante «Ripristina…» chiede «Ripristinare lo stato iniziale di «…»?» e spiega «Tornano come
  all'inizio: dispositivi e loro stati, modalità, forzatura, regole, approvazioni, programmazione, decisioni e comandi.
  Vengono cancellati tutti i soggiorni di questo appartamento, anche quelli arrivati da Italianway. Restano: nome,
  indirizzo e impostazioni dell'appartamento, prezzi, codice Italianway, utenti, registro attività ed elenco delle
  prenotazioni ricevute. I consumi non cambiano. Vale solo per questo appartamento simulato e non si può annullare.».
  Premi «Ripristina» o «Annulla»; compare «Stato iniziale ripristinato» e tutti i dispositivi aperti su
  quell'appartamento si aggiornano. Con un sistema domotico vero segnato dimostrativo il pulsante è disattivato («Il
  ripristino è disponibile solo con il motore simulato integrato.»).

### L'avviso di assistenza HQE

Quando HQE apre un accesso di assistenza alla tua organizzazione, in cima a ogni pagina compare «L'assistenza HQE (…)
ha accesso alla tua organizzazione fino al …, con i permessi di un operatore.» e «Motivo: …». «Chiudi accesso» chiede
«Chiudere l'accesso di assistenza di …? Potrà rientrare solo con un nuovo accesso.» e mostra «Accesso di assistenza
chiuso». «Nascondi l'avviso» nasconde solo il messaggio. L'avviso si aggiorna ogni 2 minuti. Durante l'accesso la
persona di HQE vede e comanda come un operatore su tutti gli appartamenti, ma non gestisce utenti, appartamenti né
funzioni. Apertura, chiusura e scadenza restano nel «Registro dell'organizzazione».

## 7. Gestore della piattaforma HQE: Organizzazioni

Chi ha il ruolo di gestore della piattaforma vede nel menu «Organizzazioni» («Le organizzazioni che usano l'app e i
gestori della piattaforma»). Chi non ha il ruolo, aprendo l'indirizzo, vede «Pagina non trovata»; se il ruolo gli viene
tolto mentre è nella pagina legge «Non hai più accesso a questa pagina: il ruolo di gestore della piattaforma ti è stato
tolto.». La pagina ha quattro schede: «Elenco organizzazioni», «Gestori della piattaforma», «Prenotazioni non
attribuite», «Registro della piattaforma». Un gestore senza organizzazione entra direttamente qui; se fa parte anche di
un'organizzazione ha anche le pagine del suo ruolo lì, e se quella organizzazione è sospesa legge «La tua organizzazione
«…» è sospesa: le sue pagine non sono disponibili finché non la riattivi da qui.».

### Elenco organizzazioni

- Ogni scheda: nome, «Creata il …», «Primo amministratore» con «in attesa del primo accesso», «attivo» o «nessun
  amministratore invitato», l'etichetta «Sospesa» e gli accessi di assistenza aperti. Senza organizzazioni: «Nessuna
  organizzazione».
- **«Nuova organizzazione»** («L'organizzazione nasce con il suo primo amministratore: riceve un'email per entrare, poi
  invita gli altri utenti.»): «Nome dell'organizzazione», «Email del primo amministratore», «Nome del primo
  amministratore (facoltativo)», «Crea». Esiti: «Organizzazione «…» creata. Invito inviato a …», «Organizzazione «…»
  creata, ma l'email a … non è partita: usa «Reinvia invito».», «Organizzazione «…» creata. L'invio email non è attivo:
  avvisa tu …». Errori: «Scrivi il nome dell'organizzazione», «Esiste già un'organizzazione con questo nome», «Questa
  email non può essere invitata».
- **«Reinvia invito»** finché il primo amministratore non è entrato («Invito inviato di nuovo a …», «L'email a … non è
  partita: riprova più tardi.», «L'invio email non è attivo: avvisa tu …»; «L'amministratore ha già effettuato
  l'accesso»).
- **«Rinomina»** apre «Rinomina l'organizzazione»: «Nome dell'organizzazione», «Salva» («Nome aggiornato»). Solo HQE
  cambia il nome.
- **«Sospendi»** apre «Sospendere «…»?» («I suoi utenti escono dall'app e non possono rientrare finché non la riattivi;
  le notifiche si fermano. Le prenotazioni continuano ad arrivare al motore degli appartamenti.»): compila «Motivo
  (obbligatorio, resta nel registro attività)» e premi «Sospendi l'organizzazione» («Organizzazione «…» sospesa»). La
  scheda mostra «Sospesa» e «Sospesa il …. Motivo: …». Gli utenti vedono «La tua organizzazione è sospesa: l'app non è
  disponibile. Per informazioni contatta l'assistenza HQE.»; gli accessi di assistenza si chiudono; i dispositivi non
  vengono spenti. Se è la tua organizzazione resti dentro Organizzazioni per poterla riattivare.
- **«Riattiva»** chiede «Riattivare «…»? I suoi utenti potranno di nuovo entrare nell'app.» («Organizzazione «…»
  riattivata»). Gli accessi di assistenza chiusi dalla sospensione non riaprono da soli.
- **«Accesso di assistenza»** e **«Entra come assistenza»**: parte 8.
- **«Appartamenti»** nella scheda dell'organizzazione: la parte tecnica (sotto).

### Appartamenti di un'organizzazione: la parte tecnica

L'elenco mostra identificativo, nome, collegamento, porta, fuso, codice Italianway, stato, ultima verifica e
«Dimostrativo»; senza appartamenti, «Nessun appartamento in questa organizzazione». Da qui non si aprono Panoramica,
dispositivi o consumi.

- **«Nuovo appartamento»** apre «Nuovo appartamento per …» («L'identificativo non si potrà più cambiare: usa minuscole,
  numeri e trattini; deve essere unico su tutta la piattaforma. Nome, stato e funzioni li gestirà poi l'amministratore
  dell'organizzazione.»): «ID» (da 3 a 64 caratteri, minuscole, numeri e trattini, per esempio apt-milano-01, mai
  riutilizzabile), «Nome» (fino a 120 caratteri), «URL istanza» (nell'ambiente di prova «In questo ambiente usa
  mock://builtin»), «Porta» (da 1 a 65535, facoltativa), «Fuso orario» (Europe/Rome all'inizio), «ID Italianway» (fino
  a 120 caratteri; «Decide a quale appartamento arrivano le prenotazioni di Italianway. Vuoto = nessun codice.»),
  «Attivo», «Istanza simulata (appartamento dimostrativo)»; «Salva». Leggi «Appartamento … creato» e, con un sistema
  domotico vero, «Prima di usarlo: crea la chiave dell'istanza e poi premi Verifica connessione.»: la chiave la prepara il
  responsabile tecnico fuori dall'app. Non c'è il campo Indirizzo: lo mette l'amministratore. Errori: «Identificativo
  non disponibile», «Collegamento già usato da un altro appartamento», «Codice Italianway già in uso», «Fuso orario non
  valido», «Indirizzo non valido: deve cominciare con http:// o https://», «In questo ambiente di prova scrivi
  mock://builtin nel campo URL istanza».
- **«Modifica collegamento»** apre «Collegamento di «…»» («Qui cambi il collegamento al sistema domotico e il codice
  Italianway: nome, stato e funzioni dell'appartamento li gestisce l'amministratore dell'organizzazione.»): «URL
  istanza», «Porta», «ID Italianway», «Salva» («Collegamento aggiornato»). Un indirizzo senza http diventa http; poi
  verifica la connessione. Il codice Italianway deve essere unico su tutta la piattaforma.
- **«Istanza simulata (appartamento dimostrativo)»** («Per prove e dimostrazioni: gli amministratori
  dell'organizzazione vedono il Simulatore di questo appartamento, e ogni elenco lo segna «Dimostrativo».»): con il
  motore simulato integrato è sempre accesa («Con il motore simulato integrato (mock://) l'istanza è sempre simulata.»).
  Passando a un sistema domotico vero l'appartamento torna reale, salvo lasciare accesa la casella. Nel sito vero non si
  possono creare appartamenti con il motore simulato integrato («I dimostrativi stanno nell'ambiente di prova: in
  produzione solo appartamenti veri») e un tale appartamento non può avere un codice Italianway («In produzione un
  appartamento dimostrativo non può avere un codice Italianway»); un sistema domotico vero segnato dimostrativo può
  averlo. Ogni cambio del tipo resta nel registro («… ha segnato l'appartamento … come istanza simulata»).
- **Com'è il dimostrativo all'inizio**: nel campo «URL istanza» scrivi `mock://builtin?variante=vuoto` (nessun ospite,
  casa fredda) oppure `mock://builtin?variante=occupato` (soggiorno in corso, comfort). Senza variante parte vuoto se
  l'identificativo contiene «bologna», occupato altrimenti. Per cambiarla a un dimostrativo esistente salva il nuovo
  collegamento e fai premere «Ripristina» nel Simulatore a un amministratore. Un valore sbagliato dà «Variante
  sconosciuta: scrivi mock://builtin?variante=vuoto oppure mock://builtin?variante=occupato».
- **«Verifica connessione»**: «Connessione OK» o «Problema di connessione», con «Ultima verifica» condivisa con
  l'amministratore; il gestore legge anche i problemi della chiave («Chiave dell'istanza non trovata in Secret Manager:
  crea il segreto …», «Chiave dell'istanza non leggibile dal server: manca il permesso su …»).
- **«Elimina»** chiede «Eliminare l'appartamento … («…») dell'organizzazione …? Sparirà per tutti i suoi utenti.
  L'istanza domotica non viene toccata.» e mostra «Appartamento … eliminato». L'identificativo non si può riusare.

### Gestori della piattaforma

«I gestori della piattaforma creano le organizzazioni e il loro primo amministratore. Aggiungi l'email di una persona:
il ruolo vale quando entra nell'app con quella email, anche se oggi non ha ancora un account.» Compila «Email» e premi
«Aggiungi gestore» («… è ora gestore della piattaforma: il ruolo vale quando entra con questa email.»); accanto a ogni
gestore «già entrato» o «non ancora entrato». Non parte un'email. «Togli» chiede «Togliere il ruolo di gestore della
piattaforma a …?» (o «Togliere il ruolo di gestore della piattaforma a te stesso? Perderai l'accesso a questa pagina.»)
e mostra «Ruolo di gestore tolto a …»; chiude i suoi accessi di assistenza, non il suo eventuale ruolo in
un'organizzazione. Deve restare almeno un gestore («È l'ultimo gestore della piattaforma: nomina prima qualcun altro»).

### Prenotazioni non attribuite

«Prenotazioni arrivate da Italianway che non si possono assegnare a nessuna organizzazione: codice Italianway
sconosciuto o collegato a più appartamenti, firma non valida, formato non riconosciuto. Gli amministratori delle
organizzazioni non le vedono.» Le ultime 100, con le stesse frasi, esiti e «Dettagli tecnici» di «Prenotazioni
ricevute»; al posto del nome dell'appartamento c'è «codice Italianway …». Serve a scoprire un codice sbagliato. Non c'è
un pulsante per assegnarle o ritrasmetterle.

### Registro della piattaforma

«Chi ha fatto cosa in un'organizzazione, oppure le azioni della piattaforma (gestori nominati e tolti).» Con «Registro
di» scegli un'organizzazione oppure «Azioni della piattaforma»; «Carica altri» mostra le 50 successive. Delle persone
delle organizzazioni vedi solo il ruolo («Un amministratore», «Un operatore», «Un lettore», «Un utente»), non il nome né
l'email: per esempio «Un amministratore ha invitato un utente come «Sola lettura»». Le azioni dei gestori restano con il
nome («… (gestore della piattaforma)»). Conservazione 24 mesi. Prima si chiamava «Registro attività».

### Email che riceve il gestore

- Avviso sulla spesa dell'assistente: oggetto «DOMHOUSE: assistente all'… % del tetto mensile», con mese, spesa e
  tetto; parte una volta al mese all'80 % del tetto condiviso (20 € al mese all'inizio), solo se l'invio email è
  configurato. Raggiunto il tetto, l'assistente risponde «Limite mensile raggiunto, riprova dal mese prossimo». Il tetto
  non si cambia dall'app.
- Avvisi di monitoraggio del servizio, ai responsabili indicati nella configurazione: «BFF non raggiungibile» (server
  dell'app fermo per 5 minuti, con l'email di chiusura quando torna), «BFF: scrittura non riuscita», «Motori: VM muta»,
  «Motori: motore muto o giù», «Motori: righe di errore», «Motori: backup mancato», «Motori: disco della VM oltre
  l'80 %». Non si impostano dalle preferenze personali.

### Amministrazione e Organizzazioni a confronto

Chi è sia amministratore di un'organizzazione sia gestore della piattaforma vede tutte e due le voci.

| Amministrazione (l'amministratore, per la sua organizzazione) | Organizzazioni (il gestore della piattaforma, per tutte) |
|---|---|
| «Appartamenti»: l'uso di ogni giorno: nome, indirizzo, attivo o no, prezzo, «Verifica connessione». | «Appartamenti» dentro ogni organizzazione: la parte tecnica: creare, collegare al sistema domotico, codice Italianway, eliminare, «Verifica connessione». |
| «Utenti»: le persone della propria organizzazione, con ruolo e appartamenti visibili. | «Gestori della piattaforma»: le persone di HQE. Della singola organizzazione il gestore vede solo il primo amministratore («Reinvia invito»). |
| «Funzioni»: quali schermate sono attive. | Nessuna scheda corrispondente. |
| «Prenotazioni ricevute»: le prenotazioni arrivate ai propri appartamenti. | «Prenotazioni non attribuite»: quelle che non corrispondono a nessun appartamento. Le due schede non si sovrappongono. |
| «Registro dell'organizzazione»: chi ha fatto cosa, con i nomi. | «Registro della piattaforma»: cosa è successo in un'organizzazione, con i soli ruoli; più le azioni della piattaforma. |
| L'avviso dell'accesso di assistenza, con «Chiudi accesso». | «Accesso di assistenza» in «Elenco organizzazioni»: aprirlo, entrare, chiuderlo. |
| Nessuna scheda corrispondente. | «Elenco organizzazioni»: creare, rinominare, sospendere, riattivare, invitare il primo amministratore. |

## 8. Accesso di assistenza

È il modo in cui HQE entra nei dati di un'organizzazione quando c'è un problema: a tempo, con un motivo, visibile
all'amministratore. Non serve un'approvazione preventiva.

1. Il gestore della piattaforma, in «Elenco organizzazioni», premi «Accesso di assistenza» sulla scheda: si apre
   «Accesso di assistenza a «…»» («Per il tempo scelto lavori dentro l'organizzazione con i permessi di un operatore.
   L'amministratore lo vede subito e può chiuderlo; apertura e chiusura restano nel registro attività.»). Scegli
   «Durata» (da 1 a 24 ore, 2 all'inizio), scrivi «Motivo (obbligatorio, lo vede l'amministratore)» e premi «Apri
   l'accesso». Leggi «Accesso di assistenza a «…» aperto fino al …»; la scheda mostra «Accesso di assistenza aperto fino
   al …» o, per un collega, «Accesso di assistenza di … aperto fino al …». Un gestore può avere un solo accesso aperto per
   organizzazione («Hai già un accesso di assistenza aperto in questa organizzazione»); con un'organizzazione sospesa
   non si apre («L'organizzazione è sospesa»).
2. Premi «Entra come assistenza» (solo chi ha aperto quell'accesso). L'app si svuota come a un cambio di utente e in
   alto compare la fascia «Stai lavorando come assistenza in «…» fino alle …, con i permessi di un operatore.» con
   «Termina». Vedi «Appartamenti» dell'organizzazione assistita e lavori come un operatore su tutti; il profilo mostra
   l'organizzazione assistita, ma nome, password e notifiche restano i tuoi e le notifiche dell'organizzazione assistita
   non ti arrivano.
3. Intanto l'amministratore vede l'avviso descritto nella parte 6 e può premere «Chiudi accesso».
4. Per finire premi «Termina», oppure «Chiudi accesso» dalla scheda in Organizzazioni («Accesso di assistenza chiuso»).
   Alla scadenza, alla chiusura dell'amministratore, a una sospensione o se ti viene tolto il ruolo di gestore l'accesso
   finisce da solo: leggi «L'accesso di assistenza a «…» è finito: ora vedi di nuovo la tua area.» e i dati
   dell'organizzazione assistita vengono tolti dalla scheda. Se la chiusura non riesce leggi «Chiusura dell'accesso sul
   server non riuscita: chiudilo da Organizzazioni.». Anche «Esci» chiude l'accesso.
5. Tutto resta nel registro: «… ha aperto un accesso di assistenza a … fino al …», «… ha chiuso l'accesso di
   assistenza a …», «L'accesso di assistenza a … è scaduto».

## 9. Passo per passo

### Arriva un ospite

1. La prenotazione arriva da Italianway (o dal Simulatore, nei dimostrativi). In «Programmazione» compare l'azione
   «pre-arrivo» con origine «prenotazione»: comfort 2 ore prima del check-in (il numero di ore è nella regola
   «Pre-arrivo»). Nelle Decisioni leggi «Prenotazione creata».
2. All'ora del pre-arrivo il motore mette l'appartamento in «comfort»: la caldaia chiede la temperatura di comfort; il
   climatizzatore, se nella stanza c'è un sensore, scalda o raffresca da solo. Nella scheda l'occupazione è «prenotato».
3. Quando Italianway comunica l'arrivo effettivo («Check-in» nelle Decisioni) l'occupazione diventa «occupato». Da ora
   l'assistente chiede conferma prima di spegnere clima o caldaia o cambiare modalità.
4. Se vuoi scaldare prima o cambiare qualcosa, usa «Modalità» o i comandi in Panoramica, oppure l'assistente.
5. Se la prenotazione viene annullata dopo il pre-arrivo, il motore rimette l'appartamento a «casa vuota» (salvo un
   altro soggiorno in corso o un altro pre-arrivo già eseguito), lo scrive nelle Decisioni («Disdetta dopo il
   pre-arrivo») e manda la notifica «Prenotazioni». Se c'è una forzatura, aspetta la sua fine.

### L'ospite è partito

1. All'orario di partenza della prenotazione più i «Minuti dopo il check-out» della regola «Risparmio al check-out» (30
   all'inizio), in «Programmazione» c'è l'azione «check-out» verso «casa vuota».
2. A quell'ora, se il sensore di movimento ha visto qualcuno dopo l'orario di partenza negli ultimi «Minuti di presenza
   dopo il check-out» (30 all'inizio), il motore non va a casa vuota da solo: apre la richiesta «Mettere l'appartamento
   a vuoto dopo il check-out» (nella frase del motore «a vuoto» vuol dire la modalità casa vuota), con il sensore,
   i minuti dal movimento e l'orario di partenza, e manda la notifica «Approvazioni richieste».
3. Premi «Approva» se l'ospite è davvero andato via, «Respingi» se è ancora dentro. Senza risposta entro 30 minuti la
   richiesta viene approvata e l'appartamento va a casa vuota.
4. Senza movimento l'appartamento passa a «casa vuota» da solo: clima spento, caldaia sull'antigelo. Con una forzatura
   attiva il cambio aspetta la sua fine.
5. In «Consumi» puoi scaricare «Excel del soggiorno» per riaddebitare l'energia.

### Un dispositivo va offline

1. In Panoramica il dispositivo mostra «Dispositivo offline» e «Visto …»; i suoi comandi sono disattivati («Il
   dispositivo non è raggiungibile: i comandi sono disattivati»). Mentre guardi l'appartamento compare l'avviso «… è
   offline».
2. Se resta offline oltre i minuti della regola «Avviso dispositivo offline» (15 all'inizio), nelle Decisioni compare
   «Dispositivo offline» e, a chi ha la categoria «Dispositivi e istanza offline» attiva, arriva la notifica «…:
   dispositivo offline», «… non risponde da oltre … minuti». Se torna prima, niente avviso. Con la regola spenta non
   arriva nulla.
3. Un comando a un dispositivo offline risponde «Il dispositivo non è raggiungibile; riprova quando torna online».
4. Se è l'intero sistema domotico a non rispondere, la striscia di salute dice «Ferma» e «Istanza non raggiungibile»,
   compare l'avviso «Istanza domotica non raggiungibile» e, dopo la stessa soglia, la notifica «…: istanza non
   raggiungibile», «Il connettore domotico risulta fermo». Nelle Decisioni: «Collegamento ai dispositivi perso» e poi
   «Collegamento ai dispositivi ripristinato». Non arriva una notifica di ritorno online.
5. Nel riepilogo del lunedì un dispositivo ancora offline da più di 24 ore compare come «… è offline da più di 24 ore.».
6. Se il problema continua, l'amministratore prova «Verifica connessione» in Amministrazione e avvisa l'assistenza.

### Approvare una richiesta

Vedi la parte 5, «Approvazioni: approvare o respingere». In breve: notifica o «Approvazioni» › «In attesa»; leggi
descrizione, motivo e scadenza; nota facoltativa; «Approva» o «Respingi»; controlla l'esito in Panoramica e nelle
Decisioni. Alle richieste dell'assistente puoi rispondere anche in chat con «Sì» o «No».

### Chiedere qualcosa all'assistente

1. Apri «Assistente» e scrivi, per esempio, «perché si è spento il clima?», «quanto abbiamo consumato ieri?», «spegni
   la caldaia» o «alle 18 metti la casa in eco». Premi «Invia».
2. Leggi la risposta. Per una domanda ottieni una spiegazione presa da stati, consumi e Decisioni. Per un comando leggi
   l'esito scritto dal sistema: «Fatto: ….», «Comando inviato: …, l'esito arriva nell'app.», «Non riuscito: … (…).» o
   «Programmato: ….».
3. Se con ospiti dentro chiedi di spegnere clima o caldaia o di cambiare modalità, o se programmi un'azione per un'ora
   in cui ci saranno ospiti, rispondi «Sì» o «No» alla domanda in chat.
4. Controlla in Panoramica o in Programmazione che sia successo davvero.

### Cambiare le temperature delle modalità

1. Apri «Regole» e trova «Limiti del setpoint». Sotto «Minimo (°C)» e «Massimo (°C)» ci sono «Temperatura in comfort
   (°C)», «Temperatura in eco (°C)» e «Raffrescamento in comfort (°C)».
2. Scrivi i valori entro i limiti di ogni campo: comfort da 16 a 26 (21 all'inizio), eco da 10 a 22 (18 all'inizio),
   raffrescamento da 22 a 28 (25 all'inizio). Eco non può superare comfort; il raffrescamento deve essere più alto di
   comfort: altrimenti leggi sotto il campo «La temperatura eco non può superare quella comfort» o «La temperatura di
   raffrescamento deve essere più alta di quella comfort» e il salvataggio resta disattivato.
3. Premi «Salva le modifiche» e leggi «Regole aggiornate».
4. I nuovi valori agiscono dal prossimo cambio di modalità e, in comfort, dalla regolazione automatica del clima. Per
   applicarli subito scegli di nuovo la modalità in Panoramica.
5. In alternativa scrivi in «Chiedi all'assistente» «comfort 22» o «eco 17», premi «Proponi» e poi «Applica».

### Invitare un collega

1. Apri «Amministrazione» › «Utenti». In «Invita un utente» compila «Email», «Nome» e «Ruolo». Per operatore o sola
   lettura scegli «Appartamenti visibili»: tutti oppure solo quelli che servono.
2. Premi «Invita» e leggi l'esito: «Invito inviato a …» oppure un messaggio sull'email non partita (l'invito resta: usa
   «Reinvia» più tardi).
3. Il collega apre l'email «Invito a DOMHOUSE» (anche nello spam), entra con «Accedi con Google» o sceglie la password
   con «Scegli la password» (link valido 1 ora; se scaduto, «Password dimenticata?»). Se serve conferma l'indirizzo e
   accede di nuovo.
4. Al primo accesso sparisce «in attesa del primo accesso». Il collega vede solo gli appartamenti assegnati; può
   installare l'app e attivare le notifiche da «Impostazioni».

### Provare l'app con il Simulatore

1. Apri un appartamento con l'etichetta «Dimostrativo» e la pagina «Simulatore» (solo amministratori).
2. **Finestra**: in «Finestre» apri un sensore. Dopo i minuti della regola «Finestra aperta spegne il clima» clima e
   caldaia si spengono; nelle Decisioni leggi la regola. Richiudi la finestra.
3. **Dispositivo offline**: in «Connettività dispositivi» metti un dispositivo «offline»: i comandi vengono rifiutati e
   dopo i minuti della regola arriva l'avviso. Rimettilo «online».
4. **Approvazione**: premi «Richiedi un'approvazione» e vai in «Approvazioni» per decidere.
5. **Prenotazione**: in «Evento prenotazione» scegli «Prenotazione creata», un «ID prenotazione», «Check-in» e
   «Check-out» futuri, «Ospiti» e premi «Invia evento»: leggi «… azioni programmate» e vai in «Programmazione». Poi invia
   «Check-in effettivo» con lo stesso identificativo: l'occupazione diventa «occupato». Per provare la partenza, invia
   «Check-out effettivo» o aspetta l'ora del check-out più i minuti della regola; con «Simula movimento» in «Movimento»
   provochi la richiesta «Mettere l'appartamento a vuoto dopo il check-out».
6. **Ricominciare**: «Ripristina…» in fondo riporta l'appartamento allo stato iniziale.

### Creare un'organizzazione e un appartamento (HQE)

1. «Organizzazioni» › «Elenco organizzazioni» › «Nuova organizzazione»: «Nome dell'organizzazione», «Email del primo
   amministratore», eventuale nome; «Crea». Leggi l'esito dell'invito.
2. Il primo amministratore entra come nella parte 2. Finché non entra puoi usare «Reinvia invito».
3. Nella scheda dell'organizzazione premi «Appartamenti» › «Nuovo appartamento»: «ID» definitivo, «Nome», «URL
   istanza», eventuale «Porta», «Fuso orario», «ID Italianway» (deve essere quello giusto: decide dove vanno le
   prenotazioni), «Attivo», «Istanza simulata (appartamento dimostrativo)»; «Salva».
4. Con un sistema domotico vero leggi «Prima di usarlo: crea la chiave dell'istanza e poi premi Verifica connessione.»:
   la chiave la prepara il responsabile tecnico fuori dall'app. Poi premi «Verifica connessione» e vai avanti solo con
   «Connessione OK».
5. L'amministratore completa in «Amministrazione» › «Appartamenti»: «Indirizzo», prezzo, funzioni, e assegna
   l'appartamento agli utenti.
6. Per un dimostrativo l'amministratore prova il Simulatore. Nel sito vero non si creano dimostrativi con il motore
   simulato integrato.

### Quando qualcosa non funziona

1. Leggi il testo esatto dell'avviso e cercalo nella parte 11. Un pulsante disattivato per chi ha sola lettura non è un
   guasto.
2. Se c'è «Riprova», usalo dopo aver risolto il problema indicato. Per un comando già approvato o con esito incerto
   controlla prima Panoramica e Decisioni, per non ripetere l'azione alla cieca.
3. Tocca «ID richiesta» («Copiato») e incollalo nella ricerca delle Decisioni: trovi subito l'operazione. All'accesso
   copia invece il «Codice».
4. Annota appartamento, azione e passi, cosa è comparso, data e ora, telefono o computer e browser; se puoi, una
   schermata (parte 13).
5. Amministratore: prova «Verifica connessione» in Amministrazione e comunica «Ultima verifica». Per una prenotazione,
   apri «Dettagli tecnici».
6. Se serve, HQE apre un accesso di assistenza (parte 8).

### Una giornata tipo dell'operatore

1. Apri «Appartamenti»: controlla «Approvazioni in attesa», «Prossimo check-in», «Prossimo check-out», lo stato e il
   consumo «Oggi».
2. Apri l'appartamento: in Panoramica guarda «In tempo reale», la salute, l'occupazione, le finestre e i dispositivi
   offline. Con «Riconnessione…» aspetta.
3. In «Programmazione» controlla pre-arrivo, check-out e azioni manuali; aggiungi o sposta solo se serve.
4. Per intervenire usa la modalità o la scheda del dispositivo; con «Forza per…» ricorda che i cambi programmati
   aspettano la fine della forzatura.
5. Controlla gli esiti; per capire un comportamento cerca nelle «Decisioni».
6. Decidi le richieste in «Approvazioni». Usa l'«Assistente» per domande e comandi.
7. Guarda «Consumi» e, il lunedì, «Riepiloghi» anche senza notifica.

## 10. Cosa fa il sistema da solo

### Le tre modalità e le loro temperature

| Modalità | Caldaia | Climatizzatore |
|---|---|---|
| «comfort» | Abilitata alla «Temperatura in comfort (°C)» (21 all'inizio); il termostato la accende e spegne intorno a quel valore. | Con un sensore di temperatura nella stessa stanza: scalda alla temperatura di comfort quando la stanza è sotto, raffresca alla «Raffrescamento in comfort (°C)» (25 all'inizio) quando è sopra, fra le due lo lascia com'è; al cambio di modalità e poi ogni minuto. Senza sensore nella stanza non lo tocca e scrive una volta «Regolazione automatica disattivata». |
| «eco» | Abilitata alla «Temperatura in eco (°C)» (18 all'inizio). | Spento. |
| «casa vuota» | Abilitata alla temperatura dell'«Antigelo a casa vuota» (8 °C all'inizio). | Spento. |

Le tre temperature si regolano per appartamento nella regola «Limiti del setpoint» (parte 9). I valori chiesti restano
sempre entro i limiti del dispositivo. La regolazione automatica del clima ogni minuto rispetta l'isteresi (0,5 °C) e
il tempo minimo fra due cambi (5 minuti), non agisce durante una forzatura né con una finestra aperta e regola finestra
attiva, e non va mai contro un comando di una persona: un clima che hai comandato tu resta com'è fino al prossimo
cambio di modalità. Ogni cambio automatico è una decisione con la temperatura letta, per esempio «…: 19 °C, sotto
21 °C: scalda».

### Le otto regole

Tutte partono attive. Sette si modificano dall'app, una no.

| Regola | Descrizione nell'app | Valori di partenza e limiti | Che cosa fa davvero |
|---|---|---|---|
| «Finestra aperta spegne il clima» | «Spegne clima e caldaia se una finestra resta aperta più dei minuti indicati.» | «Minuti»: 5, da 1 a 30 | Spegne clima e riscaldamento di tutto l'appartamento, non solo della stanza. Sospesa durante una forzatura; alla fine riparte. L'antigelo è più forte. |
| «Limiti del setpoint» | «Limita la temperatura impostabile da ospiti e app. In comfort la caldaia e il clima scaldano fino alla temperatura comfort; il clima raffresca sopra quella di raffrescamento, se nella stanza c'è un sensore di temperatura. In eco la caldaia sta alla temperatura eco.» | «Minimo (°C)»: 16, da 7 a 20; «Massimo (°C)»: 24, da 20 a 28; «Temperatura in comfort (°C)»: 21, da 16 a 26; «Temperatura in eco (°C)»: 18, da 10 a 22; «Raffrescamento in comfort (°C)»: 25, da 22 a 28 | Minimo e massimo valgono per i climatizzatori: un comando fuori intervallo è rifiutato, i comandi automatici vengono riportati dentro. La caldaia usa i limiti del suo dispositivo. Spegnere l'interruttore di questa regola oggi non toglie i limiti. Le tre temperature guidano le modalità. |
| «Antigelo a casa vuota» | «Con la casa vuota mantiene almeno questa temperatura.» | «Temperatura (°C)»: 8, da 5 a 12 | A casa vuota accende la caldaia sotto la soglia e la spegne sopra la soglia più 0,5 °C, anche se il riscaldamento è disabilitato («Antigelo: caldaia accesa», «Antigelo: caldaia spenta»). Serve un sensore: senza, «Antigelo non attivo». |
| «Antimuffa a casa vuota» | «Con la casa vuota deumidifica sopra questa soglia.» | «Umidità (%)»: 65, da 50 a 80 | Oggi scrive solo «Avviso antimuffa» nelle Decisioni, al massimo una volta al giorno, a casa vuota; durante una forzatura scrive che è sospesa. Non comanda la deumidificazione, anche se la descrizione lo dice. |
| «Pre-arrivo» | «Porta la casa in comfort prima dell'arrivo degli ospiti.» | «Ore prima del check-in»: 2, da 0 a 6 | Ogni prenotazione creata o modificata programma il comfort. Cambiare le ore vale per le prenotazioni che arrivano o cambiano dopo: le azioni già in programma non vengono ricalcolate. |
| «Risparmio al check-out» | «Passa a casa vuota dopo il check-out; se il sensore ha visto qualcuno negli ultimi minuti indicati, chiede prima a te.» | «Minuti dopo il check-out»: 30, da 0 a 180; «Minuti di presenza dopo il check-out»: 30, da 5 a 180 | Programma casa vuota dopo la partenza. Con movimento recente apre la richiesta «Mettere l'appartamento a vuoto dopo il check-out»; senza risposta la approva. |
| «Pausa minima del compressore» | «Pausa minima tra spegnimento e riaccensione del compressore.» | «Minuti»: 3; «Non modificabile» (chi gestisce il sistema può impostare da 1 a 15) | Dopo uno spegnimento la riaccensione del clima aspetta; un comando automatico viene rimandato, uno di una persona o dell'assistente può essere rifiutato se manca più di qualche secondo. |
| «Avviso dispositivo offline» | «Avvisa quando un dispositivo resta offline oltre i minuti indicati.» | «Minuti»: 15, da 5 a 120 | Dopo la soglia scrive «Dispositivo offline» nelle Decisioni e manda la notifica; la stessa soglia vale per il sistema domotico fermo. Il ritorno online prima della soglia annulla tutto. |

### Caldaia e clima, con e senza sensore

- «Riscaldamento abilitato» vuol dire che la caldaia può scaldare. Il termostato del sistema accende e spegne davvero la
  caldaia intorno alla temperatura voluta, con un'isteresi di 0,5 °C e almeno 5 minuti fra due cambi, usando il sensore
  di temperatura collegato. Con il misuratore sopra 30 W leggi «sta scaldando ora».
- **Senza un sensore utilizzabile** (manca o è offline) la caldaia non si accende mai da sola: la temperatura chiesta da
  una modalità (comfort, eco o antigelo) la lascia spenta, con una decisione per episodio, «…: sensore di temperatura
  mancante, regolazione automatica disattivata» (in comfort ed eco) oppure «…: sensore di temperatura mancante, antigelo
  non attivo» (a casa vuota, tipo «Antigelo non attivo», con notifica nella categoria «Dispositivi e istanza offline»).
  Un comando di una persona o programmato viene invece eseguito così com'è, senza regolazione («…: …; segue il comando
  manuale senza regolazione»). Quando il sensore torna leggi «…: sensore di nuovo disponibile, regolazione ripresa».
- Il climatizzatore in comfort segue il sensore della sua stanza (sopra). Senza sensore nella stanza lo comandi solo tu.
- Un comando tuo su caldaia o clima toglie quel dispositivo alla regolazione della modalità fino al prossimo cambio di
  modalità, anche dopo un riavvio del sistema.

### Prenotazioni: pre-arrivo, check-out, disdette

- Ogni prenotazione creata o modificata da Italianway programma il pre-arrivo in comfort e, dopo il check-out, il
  ritorno a casa vuota. Le azioni hanno origine «prenotazione» e si ricalcolano a ogni modifica («Ricalcolata a ogni
  modifica della prenotazione»).
- Una disdetta annulla le azioni aperte. Se il pre-arrivo era già stato eseguito, programma il ritorno a casa vuota
  («Disdetta dopo il pre-arrivo») e manda la notifica «Prenotazioni», salvo un altro soggiorno in corso o un altro
  pre-arrivo già eseguito.
- Un cambio di modalità programmato durante una forzatura aspetta la sua fine («Azione rimandata»). Dopo un riavvio del
  sistema, un'azione in ritardo di oltre 30 minuti viene saltata («Programma: saltata»).
- L'occupazione «occupato» richiede il check-in effettivo comunicato da Italianway; la sola prenotazione dà «prenotato».

### Approvazioni automatiche

- «Mettere l'appartamento a vuoto dopo il check-out»: dopo la partenza, se c'è stato movimento. Senza risposta viene
  approvata.
- «Spegnere …» con il nome dell'apparecchio, «… consuma … W da oltre … minuti con l'appartamento vuoto»: a casa vuota,
  senza forzatura, un apparecchio spegnibile con misuratore (mai la caldaia) consuma oltre 300 W per più di 15 minuti
  (valori impostati da chi gestisce il sistema). Senza risposta viene respinta e l'apparecchio resta acceso, salvo
  impostazione diversa; dopo un no, nessuna nuova richiesta finché il consumo non scende e risale.
- Le richieste dell'assistente, senza risposta, vengono respinte.
- Una sola richiesta aperta per volta: le altre aspettano in coda. La scadenza è 30 minuti all'inizio (chi gestisce il
  sistema può impostare da 5 a 720).

### Comandi confermati dal consumo

L'accensione o lo spegnimento di un climatizzatore comandato a infrarosso è confermata dal suo misuratore entro una
decina di secondi: consumo su di almeno 20 W per l'accensione, sotto 15 W per lo spegnimento. Se il misuratore è
offline il comando risulta «non verificato» e nelle Decisioni compare «Comando non verificato: misuratore offline».
Una conferma di invio non prova sempre l'effetto fisico: in caso di dubbio guarda le letture del dispositivo.

### Il riepilogo settimanale

Ogni lunedì dalle 8 (ora dell'appartamento) il sistema prepara, per ogni appartamento attivo, il riepilogo della
settimana da lunedì a domenica: consumi per notte con ospiti e per notte vuota confrontati con la mediana delle 4
settimane prima («Alto» solo con almeno il 30 % in più e almeno 5 kWh di eccedenza), dispositivi offline da più di 24
ore, approvazioni scadute senza risposta, finestre aperte almeno 3 volte con il clima spento dalla regola. Se c'è
almeno una segnalazione arriva la notifica «Riepilogo». Una settimana senza novità ha il riepilogo «Settimana senza
novità» e non manda avvisi.

### Valori impostati fuori dall'app

Alcuni valori li imposta il responsabile tecnico del sistema domotico, non l'app: la pausa del compressore (3 minuti, da
1 a 15) e la breve attesa finale (7 secondi); l'isteresi del termostato (0,5 °C) e il tempo minimo fra due cambi (5
minuti); le soglie di conferma dal misuratore (20 W e 15 W); la scadenza delle approvazioni (30 minuti) e le soglie del
consumo a casa vuota (300 W, 15 minuti); il ritardo oltre il quale un'azione programmata viene saltata dopo un riavvio
(30 minuti); quando l'assistente chiede conferma (con ospiti, sempre, oppure solo per più azioni insieme); il numero di
domande al giorno all'assistente (50) e il tetto mensile di spesa (20 €).

### Per quanto tempo l'app conserva i dati

*Decisione del 17 ottobre 2026.* Oltre questi termini i dati si cancellano da soli, entro circa un giorno.

| Dati | Per quanto tempo |
|---|---|
| Prenotazioni e presenze degli ospiti | 12 mesi dopo il check-out |
| Decisioni dell'appartamento | 24 mesi |
| Consumi | 24 mesi (li conserva il sistema domotico dell'appartamento) |
| Richieste all'assistente | 90 giorni |
| Riepiloghi settimanali | 12 mesi |
| Registro dell'organizzazione, registro della piattaforma e accessi di assistenza | 24 mesi |
| Prenotazioni ricevute da Italianway (senza dati personali degli ospiti) | 90 giorni, e al massimo le ultime 100 |

Utenti, organizzazioni e appartamenti restano finché non vengono tolti. Chi elimina il proprio account viene cancellato
subito. I dati personali degli ospiti non vengono salvati; il sistema domotico riceve un codice anonimo al posto
dell'email di chi comanda.

## 11. Problemi e messaggi

### All'accesso

| Cosa vedi | Cosa significa | Cosa fare |
|---|---|---|
| «Accesso non riuscito: controlla email e password» | Email o password sbagliate | Riprova o usa «Password dimenticata?» |
| «Troppi tentativi: riprova tra qualche minuto» | Troppi tentativi in poco tempo | Aspetta qualche minuto |
| «Connessione assente: riprova» | Il telefono o il computer non ha rete | Controlla la connessione |
| «Il browser ha bloccato la finestra di Google: consenti le finestre pop-up per questo sito e riprova» | Il browser ha bloccato la finestra di accesso di Google | Consenti le finestre pop-up e riprova |
| «Accesso con Google non attivo: avvisa l'assistenza HQE», «Accesso con Google non riuscito» | L'accesso con Google non è disponibile o è fallito | Riprova; se continua, avvisa l'assistenza con il «Codice» |
| «Questo indirizzo del sito non è autorizzato per l'accesso: avvisa l'assistenza HQE» | Il sito è aperto da un indirizzo non previsto | Avvisa l'assistenza |
| «Firebase non è ancora configurato su questo ambiente» | L'ambiente non è pronto per l'accesso | Avvisa l'assistenza |
| «Non hai i permessi per accedere. Chiedi un invito.» | L'account esiste ma nessuno ti ha invitato in questo ambiente (un invito nell'ambiente di prova non vale nel sito vero) | Chiedi un invito a un amministratore |
| «Conferma il tuo indirizzo: abbiamo inviato un link a …. Aprilo e poi accedi di nuovo.» | Il tuo indirizzo non è ancora confermato | Apri il link nell'email, poi accedi di nuovo |
| «Devi confermare il tuo indirizzo email, ma l'invio del link non è riuscito. Riprova tra qualche minuto.» | L'email di conferma non è partita | Riprova tra qualche minuto |
| «Impossibile caricare il profilo, riprova tra poco» | Il server non risponde | Riprova dopo qualche minuto |
| «La tua organizzazione non è attiva: contatta HQE.» | L'organizzazione non è ancora pronta | Contatta HQE |
| «La tua organizzazione è sospesa: l'app non è disponibile. Per informazioni contatta l'assistenza HQE.» | HQE ha sospeso la tua organizzazione | Contatta l'assistenza HQE |
| «Indirizzo email non valido» | L'email scritta non è un indirizzo | Correggi l'indirizzo |

### In tutte le pagine

| Cosa vedi | Cosa significa | Cosa fare |
|---|---|---|
| «Server non raggiungibile» | L'app non raggiunge il server | Controlla la rete e premi «Riprova» |
| «Operazione non riuscita», «Errore …» | Il server ha risposto con un errore senza spiegazione | Riprova; se continua, copia l'«ID richiesta» e segnala |
| «Richiesta non accettata dal server: ricarica la pagina e riprova.» | La pagina è vecchia rispetto al server | Ricarica la pagina |
| «Accesso richiesto», «Sessione non valida o scaduta» | La sessione è finita | Accedi di nuovo |
| «Organizzazione non attiva», «Organizzazione sospesa: contatta l'assistenza HQE» | La tua organizzazione non è disponibile | Contatta HQE |
| «L'accesso di assistenza è scaduto o è stato chiuso» | L'accesso di assistenza è finito | Torni alla tua area; se serve, aprine uno nuovo |
| «Il tuo ruolo consente solo la lettura» | Hai il ruolo sola lettura | Chiedi a un operatore o a un amministratore |
| «Operazione riservata agli amministratori», «Operazione riservata ai gestori della piattaforma» | Serve un ruolo più alto | Chiedi a chi ha quel ruolo |
| «Appartamento inesistente», «Appartamento non disponibile» | L'appartamento non esiste o non è fra i tuoi | «Torna agli appartamenti»; chiedi l'assegnazione a un amministratore |
| «Appartamento disattivato» | L'amministratore ha spento «Attivo» | Chiedi all'amministratore |
| «Funzione non disponibile su questa istanza» | La funzione è spenta o il sistema domotico non la ha | Chiedi all'amministratore (scheda «Funzioni») |
| «Istanza non raggiungibile» | Il sistema domotico dell'appartamento non risponde | Aspetta; se continua, «Verifica connessione» e assistenza |
| «Versione del contratto non compatibile» | Il sistema domotico è di una versione non supportata | Contatta il supporto tecnico |
| «Pagina non trovata» | L'indirizzo non esiste, oppure non hai il ruolo per quella pagina | Torna al menu |

### Sui comandi e in Panoramica

| Cosa vedi | Cosa significa | Cosa fare |
|---|---|---|
| «Il dispositivo non è raggiungibile; riprova quando torna online», «dispositivo offline» | Il dispositivo è offline | Aspetta che torni online |
| «Collegamento ai dispositivi non disponibile; riprova quando torna» | Il sistema non parla con i dispositivi | Aspetta «Collegamento ai dispositivi ripristinato» nelle Decisioni |
| «Il setpoint deve essere tra … e …», «fuori dai limiti» | Temperatura fuori dai limiti | Scegli un valore nell'intervallo «da … a … °C» |
| «rifiutato dal dispositivo» | Il dispositivo non ha accettato il comando | Riprova; controlla il dispositivo |
| «bloccato da una regola», «bloccato da un'azione prioritaria» | Una regola (per esempio finestra aperta o pausa del compressore) o un'azione più importante ha bloccato il comando | Leggi il motivo nelle Decisioni; riprova dopo |
| «nessuna conferma», «non verificato», «nessuna risposta» | Il comando è partito ma non è stato confermato | Controlla le letture del dispositivo |
| «errore interno» | Un errore del sistema domotico | Copia l'«ID richiesta» e segnala |
| «Modalità non valida» | Modalità non riconosciuta | Scegli «comfort», «eco» o «casa vuota» |
| «Il nome deve avere da 1 a 60 caratteri», «Stanza inesistente», «Dispositivo inesistente» | Dati della rinomina non validi | Correggi nome o stanza |

### In Approvazioni, Programmazione, Regole, Assistente e Simulatore

| Cosa vedi | Cosa significa | Cosa fare |
|---|---|---|
| «L'approvazione è già stata decisa», «Approvazione inesistente» | Un collega ha già deciso, o la richiesta non c'è più | Rileggi l'elenco |
| «note troppo lunga» | La nota supera 500 caratteri | Accorcia la nota |
| «L'orario deve essere nel futuro» | L'orario scelto è passato | Scegli un orario futuro |
| «Azione programmata inesistente», «L'azione è già stata eseguita o annullata» | La voce non è più in programma | Rileggi l'elenco |
| «Valore fuori dai limiti (…–…)», ««…»: … deve essere tra … e …» | Un valore della regola è fuori dai limiti | Correggi il valore |
| «Il minimo non può superare il massimo», «La temperatura eco non può superare quella comfort», «La temperatura di raffrescamento deve essere più alta di quella comfort» | Le temperature non sono coerenti | Correggi i valori |
| «La regola «…» non è modificabile» | Regola fissata dal sistema | Non si cambia dall'app |
| «Salva o annulla prima le modifiche fatte a mano» | Hai modifiche non salvate nella pagina Regole | «Salva le modifiche» o «Annulla le modifiche», poi «Applica» |
| «Le regole sono cambiate nel frattempo: rifai la richiesta», «Le regole dell'appartamento di partenza sono cambiate: rifai l'anteprima» | Qualcuno ha cambiato le regole | Rifai la proposta o l'anteprima |
| «Le regole sono già così: non c'è niente da cambiare» | La proposta non cambia nulla | Niente da fare |
| «Al massimo 500 caratteri», «Scrivi che cosa vuoi cambiare», «Scrivi una richiesta», «text obbligatorio, massimo 500 caratteri» | Testo vuoto o troppo lungo | Scrivi una frase più corta |
| «Hai già chiesto 20 proposte oggi per questo appartamento: riprova domani o cambia le regole a mano» | Limite giornaliero delle proposte | Cambia la regola a mano o riprova domani |
| «L'assistente non ha risposto in tempo: riprova con una frase più breve, oppure cambia la regola a mano qui sotto.» | Il modello non ha risposto in tempo | Riprova con una frase più breve |
| «Nessuna risposta dall'assistente: riprova», «Non sono riuscito a rispondere in tempo: riprova, oppure fai dall'app.», «L'assistente non è disponibile ora, riprova più tardi», «Non sono riuscito a rispondere: riprova.» | L'assistente non ha risposto | Riprova o usa i comandi dell'app |
| «Limite di … domande al giorno raggiunto per questo appartamento: riprova domani.» | Limite giornaliero dell'assistente | Usa i comandi dell'app |
| «Limite mensile raggiunto, riprova dal mese prossimo» | Tetto di spesa del servizio raggiunto | Usa i comandi dell'app; HQE riceve un'email |
| «Nessun altro appartamento nella tua organizzazione», «Scegli almeno un appartamento di destinazione», «Al massimo 100 appartamenti alla volta», «Solo gli amministratori possono copiare le regole» | Condizioni della copia delle regole | Correggi la scelta |
| «Il simulatore è riservato agli amministratori», «Questo appartamento non è un'istanza simulata» | Il Simulatore non è disponibile qui | Solo amministratori, solo dimostrativi |
| «Il check-out deve essere successivo al check-in» | Date della prenotazione di prova invertite | Correggi le date |
| «Nessun apparecchio con misuratore da proporre nell'appartamento» | Nessun apparecchio adatto alla prova | Usa un altro dimostrativo |
| «Il ripristino è disponibile solo con il motore simulato integrato.» | Il ripristino non è possibile su un sistema vero | Nessuna azione |

### In Amministrazione e Organizzazioni

| Cosa vedi | Cosa significa | Cosa fare |
|---|---|---|
| «È già un utente della tua organizzazione», «Questa email non può essere invitata» | La persona è già dentro, oppure è di HQE | Non invitare; per HQE serve la procedura tecnica |
| «Gli amministratori vedono sempre tutti gli appartamenti» | Non si limitano gli appartamenti di un amministratore | Cambia ruolo se serve |
| «Utente inesistente», «L'utente ha già effettuato l'accesso» | Il reinvio non è possibile | Rileggi l'elenco |
| «Non puoi togliere a te stesso il ruolo di amministratore», «Non puoi eliminare il tuo stesso account», «Deve restare almeno un amministratore nell'organizzazione» | Protezioni sul proprio ruolo e sull'ultimo amministratore | Chiedi a un altro amministratore |
| «Ruolo non aggiornato, riprova tra poco», «Rimozione non riuscita, riprova tra poco», «Eliminazione non riuscita, riprova tra poco» | Errore passeggero | Riprova |
| «Fuso orario non valido», «Funzione sconosciuta», «Appartamento inesistente: …» | Dati non validi | Correggi |
| «Prezzo non valido: da 0 a 10 € al kWh, al massimo 4 decimali» | Prezzo fuori formato | Scrivi per esempio 0,25 |
| «Chiave dell'istanza non configurata: contatta l'assistenza HQE» | Manca la chiave del sistema domotico | Avvisa l'assistenza |
| «Scrivi il nome dell'organizzazione», «Esiste già un'organizzazione con questo nome», «Organizzazione inesistente» | Nome mancante, duplicato o organizzazione non trovata | Correggi |
| «L'organizzazione è già sospesa», «L'organizzazione non è sospesa», «Scrivi il motivo della sospensione» | Stato o motivo non coerenti | Rileggi la scheda |
| «La durata va da 1 a 24 ore», «Scrivi il motivo dell'accesso di assistenza», «L'organizzazione è sospesa», «Hai già un accesso di assistenza aperto in questa organizzazione», «Accesso non aperto: riprova tra poco» | Condizioni dell'accesso di assistenza | Correggi o riprova |
| «Accesso di assistenza inesistente» | L'accesso è già chiuso | Niente da fare |
| «Identificativo non disponibile», «Collegamento già usato da un altro appartamento», «Codice Italianway già in uso» | Valori già usati o non riusabili | Scegli valori diversi |
| «Indirizzo non valido: deve cominciare con http:// o https://», «In questo ambiente di prova scrivi mock://builtin nel campo URL istanza», «I dimostrativi stanno nell'ambiente di prova: in produzione solo appartamenti veri» | Collegamento non ammesso in questo ambiente | Correggi il collegamento |
| «Ha già il ruolo di gestore della piattaforma», «Non è un gestore della piattaforma», «È l'ultimo gestore della piattaforma: nomina prima qualcun altro» | Condizioni sui gestori | Rileggi l'elenco |

### Nelle Impostazioni e nelle notifiche

| Cosa vedi | Cosa significa | Cosa fare |
|---|---|---|
| «La password deve avere almeno … caratteri», «Le due password non coincidono», «Password troppo debole: usa almeno 8 caratteri» | La nuova password non va bene | Scegline una più lunga e ripetila uguale |
| «Password attuale non corretta» | Hai sbagliato la password attuale | Riprova |
| «Questa email è già usata da un altro account» | Il nuovo indirizzo è di un altro account | Usa un altro indirizzo |
| «Per sicurezza esci e accedi di nuovo, poi riprova» | L'operazione richiede un accesso recente | «Esci», accedi e riprova |
| «Operazione non riuscita, riprova» | Errore passeggero | Riprova |
| «Sei l'unico amministratore: nomina un altro amministratore prima di eliminare il tuo account», «Sei l'ultimo gestore della piattaforma: nomina un altro gestore prima di eliminare il tuo account» | Non puoi lasciare l'organizzazione o la piattaforma senza nessuno | Nomina prima un altro |
| «Account non abilitato: mancano tenant o ruolo» | Il tuo account non appartiene a nessuna organizzazione in questo ambiente | Chiedi un invito; un gestore senza organizzazione non può salvare nome e preferenze |
| «Permesso non concesso: su questo dispositivo le notifiche restano spente.», «Attivazione delle notifiche non riuscita: riprova tra poco.» | Le notifiche non si sono attivate | Consenti il permesso e riprova |
| «Notifiche non riattivate: il browser non ne dà più il permesso. Puoi riattivarle da Impostazioni › Notifiche.» | Al rientro il browser non permette più le notifiche | Consenti le notifiche e premi «Attiva su questo dispositivo» |

## 12. Parole usate in questa guida

| Parola | Che cosa vuol dire |
|---|---|
| Accesso di assistenza | Ingresso temporaneo (da 1 a 24 ore) di un gestore della piattaforma in un'organizzazione, con i permessi di un operatore, motivo visibile all'amministratore. |
| Ambiente di prova | Il sito con dati separati da quelli veri, con la fascia gialla «Ambiente di prova». Non è un ruolo. |
| Antigelo | Protezione a casa vuota: la caldaia si accende sotto la soglia, se c'è un sensore. |
| Antimuffa | Oggi solo un avviso di umidità sopra soglia a casa vuota; non deumidifica. |
| Approvazione | Una richiesta che aspetta il sì o il no di una persona prima di un'azione; alla scadenza segue quanto scritto nella scheda. |
| Avviso nell'app | Messaggio temporaneo in alto nella pagina aperta; non è una notifica sul telefono. |
| Capacità | Una cosa che un dispositivo sa fare o misurare: interruttore, clima, riscaldamento, temperatura, umidità, contatto, movimento, potenza. |
| Casa vuota | La modalità per l'appartamento senza ospiti: clima spento, caldaia sull'antigelo. Nella scheda, «vuoto» indica invece l'occupazione. |
| Check-in, check-out | Arrivo e partenza previsti dalla prenotazione; l'arrivo e la partenza effettivi sono comunicazioni a parte di Italianway. |
| Codice Italianway | Il codice con cui il sistema di prenotazioni Italianway riconosce una struttura: decide a quale appartamento arrivano le prenotazioni. Lo inserisce solo HQE. |
| Collegamento al sistema domotico | L'indirizzo («URL istanza») del sistema che comanda davvero i dispositivi; nell'ambiente di prova `mock://builtin`. |
| Comfort | La modalità con gli ospiti: caldaia e clima alla temperatura di comfort; raffrescamento sopra la temperatura di raffrescamento. |
| Connettore | Il collegamento con cui il sistema domotico legge e comanda i dispositivi; «Connettore» «attivo» o «fermo» nella striscia di salute. |
| Decisione | Una riga dello storico: chi ha fatto o proposto cosa, su cosa, perché, con quale esito. |
| Dimostrativo | Appartamento finto per prove e dimostrazioni, con l'etichetta «Dimostrativo» e il Simulatore. |
| Eccezione per appartamento | Una scelta del singolo appartamento che sostituisce quella dell'organizzazione (funzioni o prezzo). |
| Eco | La modalità di risparmio: clima spento, caldaia alla temperatura di eco. |
| Forzatura | Un periodo (30 minuti, 2 ore, 6 ore) in cui la modalità resta e gli automatismi del comfort sono sospesi; l'antigelo resta. |
| Gestore della piattaforma | Chi gestisce il servizio per tutte le organizzazioni (HQE): crea organizzazioni e collega gli appartamenti. |
| ID richiesta | L'identificativo copiabile di un'operazione, per cercarla nelle Decisioni o aiutare l'assistenza. |
| Isteresi | La piccola differenza di temperatura (0,5 °C) che evita accensioni e spegnimenti continui intorno alla soglia. |
| Istanza | Il sistema domotico che gestisce un appartamento, vero o simulato. |
| kWh | L'energia consumata in un periodo; l'importo dipende dal prezzo per kWh. |
| Mediana | Il valore centrale dei consumi delle stesse notti nelle settimane prima, usato dal riepilogo. |
| Modalità | La scelta complessiva dell'appartamento: «comfort», «eco», «casa vuota». |
| Motore | La parte automatica del sistema domotico: applica regole, modalità, programmi e comandi. |
| Non verificato | Lo stato mostrato è quello richiesto, senza una conferma del misuratore. |
| Notifica push | Avviso del telefono o del browser che arriva anche ad app chiusa. |
| Occupazione | Lo stato della prenotazione: «vuoto», «occupato», «prenotato». |
| Offline | Dispositivo o collegamento non raggiungibile; non vuol dire spento. |
| Organizzazione | Un'azienda che usa l'app, con i suoi utenti e i suoi appartamenti (oggi Flatsharing). |
| Pausa del compressore | L'attesa di protezione (3 minuti) prima di riaccendere il climatizzatore. |
| Pre-arrivo | La preparazione automatica in comfort prima del check-in. |
| Proposta di regole | L'anteprima delle modifiche suggerita dall'assistente nella pagina Regole; cambia solo con «Applica». |
| Raffrescamento in comfort | La temperatura sopra la quale, in comfort, il climatizzatore raffresca (25 °C all'inizio). |
| Regola | Un automatismo già previsto dal motore, con interruttore e valori; dall'app non se ne creano di nuovi. |
| Regolazione automatica del clima | In comfort, il controllo ogni minuto dei climatizzatori secondo il sensore della stanza. |
| Rendiconto Excel | Il file scaricabile con riepilogo, consumi per giorno, ora e dispositivo e importi. |
| Riscaldamento abilitato | La caldaia può scaldare secondo il termostato; non vuol dire che stia scaldando adesso. |
| Setpoint | La temperatura desiderata, diversa da quella misurata. |
| Simulatore | La pagina, solo per amministratori, per provocare eventi sugli appartamenti dimostrativi. |
| Soggiorno | Il periodo fra arrivo e partenza di una prenotazione conosciuta dall'app. |
| W | La potenza in questo istante; non è il consumo del giorno. |

## 13. Segnalare un problema

Per ogni problema annota:

1. cosa stavi facendo, passo per passo;
2. cosa ti aspettavi e cosa è successo, con il testo esatto dell'avviso;
3. l'«ID richiesta», se compare (o il «Codice» della pagina di accesso);
4. dispositivo e browser (per esempio «iPhone, Safari» o «PC, Chrome»), data e ora;
5. una schermata, se possibile.

## 14. Novità

### 22 ottobre 2026 (lotto 30)

- **Temperature delle modalità regolabili** per appartamento, nella regola «Limiti del setpoint»: «Temperatura in
  comfort (°C)», «Temperatura in eco (°C)», «Raffrescamento in comfort (°C)»; i valori incoerenti vengono segnalati anche
  prima del salvataggio.
- **Clima in comfort regolato in continuo**: con il sensore della stanza il climatizzatore scalda o raffresca da solo,
  ogni minuto, mai contro un comando di una persona; senza sensore «Regolazione automatica disattivata».
- **Caldaia senza sensore**: non si accende più da sola; a casa vuota «Antigelo non attivo» con notifica.
- **Programmazioni dell'assistente con ospiti**: conferma in chat se all'ora programmata ci saranno ospiti.
- **Il tuo nome nel menu**, in grassetto, con sotto l'email.
- **Notifiche: quattro voci**: tolta «Decisioni del motore».
- **Due registri con nomi diversi**: «Registro dell'organizzazione» e «Registro della piattaforma».
- **Proposte delle regole**: l'assistente capisce «comfort 22», «eco 17», «raffrescamento 26»; «temperatura 22» da sola
  chiede quale temperatura.
- **Simulatore**: ripremere «Invia evento» senza cambiare nulla mostra «Evento già elaborato (idempotente)».
- **«Casa vuota»**: la modalità si chiama così (prima «vuoto»); «vuoto» è l'occupazione.
- **Assistente**: dopo «Sì» o «No» la chat dice com'è andata; riaprendo, «Approvata da te alle …» o «Respinta da te alle
  …»; «Già decisa» solo se ha deciso un'altra persona.

### 20 e 21 ottobre 2026

- Regole complete (otto regole con interruttore e valori); caldaia con «Riscaldamento abilitato» / «Riscaldamento
  disabilitato», «sta scaldando ora» e termostato automatico; avviso prima di forzare con finestra aperta.
- Decisioni con il tipo di azione in italiano e i tipi «Collegamento ai dispositivi perso», «Collegamento ai
  dispositivi ripristinato», «Comando non verificato: misuratore offline».
- Comandi del climatizzatore confermati dal misuratore; approvazioni automatiche «Mettere l'appartamento a vuoto dopo il
  check-out» e «Spegnere …»; notifiche «Prenotazioni».
- Consumi veri ora per ora con «Consumi disponibili dal …»; Simulatore con «Misuratore clima» e «Simula movimento».
- Riepilogo settimanale ogni lunedì con la pagina «Riepiloghi» e la notifica «Riepilogo».
- Assistente vero che legge stati, consumi e Decisioni; ambiente di prova separato con la fascia gialla.
- Regole proposte dall'assistente nella pagina Regole; copia delle regole su altri appartamenti; «Minuti di presenza
  dopo il check-out».
- Schede degli appartamenti tutte nello schermo del telefono.

### 16 ottobre 2026

- Organizzazioni: più organizzazioni separate, gestite dal gestore della piattaforma (HQE); codice Italianway e nome
  dell'organizzazione solo da HQE; nuovi appartamenti solo da HQE, anche nell'ambiente di prova.
- Cambio di ruolo con uscita da tutti i dispositivi entro un minuto; notifiche su dispositivo condiviso al sicuro;
  notifiche riattivate al rientro.
- «Elimina il mio account» cancella davvero l'accesso; non per l'ultimo amministratore né per l'ultimo gestore.
- Nome dell'app DOMHOUSE; barra laterale con i ruoli; menu a tre righe sul telefono.
- «Prenotazioni ricevute» e «Prenotazioni non attribuite»; registro attività; sospensione delle organizzazioni; accesso
  di assistenza a tempo.
- Privacy: «utente rimosso», codice anonimo al sistema domotico, nessun dato personale degli ospiti; conservazione dei
  dati a termine.
- Appartamenti dimostrativi con etichetta, Simulatore e ripristino; rendiconti Excel mensili e per soggiorno.
