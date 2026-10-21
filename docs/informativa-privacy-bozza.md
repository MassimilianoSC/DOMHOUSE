# Informativa sul trattamento dei dati personali — app DOMHOUSE (BOZZA)

*Bozza scritta dalla memoria storica il 21 ottobre 2026 (D-142, P-70) sulla base del censimento in
`docs/proposta-p68-accesso-e-dati-personali.md`. Da far approvare al consulente del titolare prima dell'uso. Le parti
fra «da completare» vanno riempite dal titolare. I riferimenti normativi sono al Regolamento (UE) 2016/679 (GDPR).*

---

## 1. Chi tratta i dati

**Titolare del trattamento** (chi decide perché e come si usano i dati): l'organizzazione che gestisce gli appartamenti e
usa l'app, oggi **Flatsharing** («da completare»: ragione sociale, sede, email di contatto; eventuale responsabile della
protezione dei dati).

**Responsabile del trattamento** (chi tratta i dati per conto del titolare, su suo incarico): **HQE** («da completare»:
ragione sociale, sede, email di contatto), che gestisce la piattaforma DOMHOUSE, il sistema domotico degli appartamenti e
l'assistenza.

**Sub-responsabili** (fornitori usati da HQE): Google Cloud EMEA Limited (archiviazione, server, accesso, notifiche),
con i dati conservati a Milano (`europe-west8`) per database e server; l'accesso all'app (Firebase Authentication) e le
notifiche sul telefono (Firebase Cloud Messaging) sono servizi globali di Google, quindi i dati relativi possono essere
trattati anche fuori dall'Unione europea, con le clausole contrattuali standard previste da Google Cloud. Le email di
invito partono da una casella Gmail di HQE.

**Italianway** (il canale di prenotazione) invia al sistema gli eventi delle prenotazioni: è un titolare autonomo per i
dati degli ospiti, che il sistema non riceve (vedi sezione 3).

## 2. A chi si rivolge questa informativa

- alle **persone che usano l'app** (amministratori, operatori, utenti in sola lettura dell'organizzazione);
- al **personale di HQE** che accede all'app come gestore della piattaforma o con un accesso di assistenza;
- agli **ospiti degli appartamenti**, per chiarezza: dei loro dati il sistema tratta solo il codice della prenotazione,
  le date e il numero di persone, senza nome, email, telefono o documenti.

## 3. Quali dati e perché

| Dati | Di chi | Perché (finalità) | Base giuridica |
|---|---|---|---|
| Email, nome visualizzato, ruolo, organizzazione, appartamenti assegnati, preferenze di notifica, identificativi tecnici delle notifiche sul telefono | utenti dell'app | far funzionare l'accesso e i permessi; mandare gli avvisi scelti | esecuzione del contratto di servizio con l'organizzazione; per i dipendenti e collaboratori, legittimo interesse dell'organizzazione a gestire l'accesso ai propri sistemi |
| Registro delle operazioni: chi ha fatto cosa nell'app (inviti, ruoli, appartamenti, accessi di assistenza, sospensioni), con i motivi scritti | utenti e personale di HQE | sicurezza, tracciabilità, verifica di eventuali abusi | legittimo interesse del titolare e del responsabile alla sicurezza del servizio |
| Decisioni e approvazioni del sistema domotico: chi ha approvato o respinto, con nota; chi ha impostato una forzatura; testo delle richieste all'assistente | utenti dell'app | far funzionare il controllo degli appartamenti e lasciarne la storia leggibile ai colleghi | esecuzione del contratto |
| Codice della prenotazione, date di arrivo e partenza, numero di ospiti, stato del soggiorno | prenotazioni (nessun dato identificativo degli ospiti) | preparare l'appartamento all'arrivo, metterlo in risparmio alla partenza, rendiconti dei consumi | esecuzione del contratto |
| Stato attuale dei sensori (finestra aperta o chiusa, ultimo movimento rilevato) e consumi elettrici per dispositivo e ora | appartamenti (dati tecnici, non riferiti a una persona identificata) | regole automatiche, avvisi, rendiconti | esecuzione del contratto |
| Log tecnici del server: identificativo dell'utente (non l'email), organizzazione, appartamento, errori; **log di richiesta di Cloud Run con l'indirizzo IP** di chi usa l'app, l'indirizzo chiamato e l'ora | utenti dell'app | funzionamento, diagnosi dei problemi, sicurezza | legittimo interesse alla sicurezza e alla continuità del servizio |
| Accessi di assistenza: chi di HQE è entrato in un'organizzazione, quando e perché | personale di HQE | assistenza, con traccia visibile agli amministratori dell'organizzazione | esecuzione del contratto; legittimo interesse alla trasparenza |

Il sistema domotico degli appartamenti non riceve mai l'email o il nome degli utenti: riceve uno pseudonimo che solo
il server dell'app sa ricondurre alla persona, e solo all'interno della stessa organizzazione.

Non ci sono profilazione, decisioni automatizzate con effetti giuridici sulle persone, geolocalizzazione, né
strumenti di tracciamento o analisi nell'app.

## 4. Per quanto tempo

| Dati | Conservazione |
|---|---|
| Account, profilo, preferenze, appartamenti assegnati | finché l'account esiste |
| Registro delle operazioni e accessi di assistenza | 24 mesi, poi cancellazione automatica |
| Decisioni e approvazioni del sistema domotico | 24 mesi |
| Richieste all'assistente e comandi | 90 giorni |
| Eventi dei sensori (movimento, finestre) | 1 ora; resta solo lo stato attuale |
| Consumi elettrici | 24 mesi |
| Prenotazioni (codice, date, numero di ospiti) | 12 mesi dopo la partenza; le notifiche ricevute dal canale di prenotazione 90 giorni |
| Log tecnici del server e log di richiesta di Cloud Run (con indirizzo IP) | 30 giorni (conservazione predefinita di Google Cloud) |
| Copie di sicurezza | database dell'app: copia giornaliera conservata 14 giorni; sistema domotico: copia giornaliera conservata 7 giorni, più una copia del disco del server conservata 30 giorni. Un dato cancellato può restare nelle copie di sicurezza fino a questi termini |

## 5. Chi vede i dati

- Gli **amministratori** di un'organizzazione vedono email, nome e ruolo dei colleghi della stessa organizzazione e il
  registro delle operazioni con i loro nomi. Operatori e utenti in sola lettura vedono i nomi dei colleghi solo accanto
  alle decisioni e alle approvazioni.
- Il **gestore della piattaforma** (HQE) vede le organizzazioni e i dati di base dei loro appartamenti; non vede
  dispositivi, consumi, decisioni né gli utenti delle organizzazioni, salvo l'email del primo amministratore e, nel
  registro, i soli ruoli. Un accesso di assistenza, chiesto dall'organizzazione, dà a una persona di HQE i diritti di un
  operatore per un tempo limitato, con traccia visibile agli amministratori.
- Nessuna organizzazione vede dati di un'altra.
- Chi ha accesso tecnico al progetto Google Cloud (HQE) può leggere i log tecnici.

## 6. I tuoi diritti

Hai diritto di accedere ai tuoi dati, correggerli, chiederne la cancellazione o la limitazione, opporti al trattamento
basato sul legittimo interesse e ricevere i dati che hai fornito in un formato leggibile. Puoi rivolgerti al titolare
(«da completare»: email) e, se ritieni che il trattamento violi la legge, proporre reclamo al Garante per la protezione
dei dati personali (www.garanteprivacy.it).

Nell'app, da **Impostazioni**: puoi cambiare nome, email e password; chiudere tutte le sessioni («Esci da tutti i
dispositivi»); scegliere quali avvisi ricevere; **eliminare il tuo account** («Elimina il mio account»): vengono
cancellati accesso, nome, email e preferenze; quello che hai fatto resta nel registro con la dicitura «utente rimosso».
Se è un amministratore a toglierti dall'organizzazione, l'accesso si chiude subito e le tue tracce restano nel registro
per 24 mesi: per farle cancellare prima, elimina tu stesso l'account o chiedilo al titolare.

## 7. Come sono protetti i dati

Accesso con password (o account Google) e sessioni revocabili; ruoli con permessi minimi; dati e server nell'Unione
europea (Milano) salvo quanto detto in sezione 1; collegamenti cifrati; chiavi e credenziali custodite nel servizio
dedicato di Google Cloud, mai nel codice; cancellazione automatica alle scadenze della sezione 4; copie di sicurezza
giornaliere; pseudonimi verso il sistema domotico. È prevista la **verifica in due passaggi** all'accesso (codice da
un'app di autenticazione), obbligatoria per amministratori e gestore della piattaforma, prima dell'uso con appartamenti
veri.

## 8. Aggiornamenti

Questa informativa viene aggiornata quando cambiano i dati trattati o i fornitori. Versione: bozza del 21 ottobre 2026.
