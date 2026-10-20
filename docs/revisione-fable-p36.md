# Revisione avversaria di P-36 (Fable, 16 ottobre 2026)

Rapporto integrale di Fable, lanciato dalla memoria storica (D-58, D-69) con il testo di `docs/prompt-revisione-fable.md`.
Codice esaminato: HEAD `fe5056b` (codice di `7d9caae`), sola lettura, albero pulito prima e dopo. Le decisioni prese sui
rilievi sono in `docs/registro.md` (D-70 e sezione 2).

---

## 1. Per il committente

**Non pubblicare ancora.** Due cose gravi e quattro di media importanza.

1. **Grave.** Un utente qualsiasi di un'organizzazione, anche in sola lettura, può leggere e in parte comandare gli
   appartamenti di un'altra organizzazione scrivendo un indirizzo «truccato» (con `..` codificato) dentro il percorso del
   proprio appartamento. Dimostrato in prova locale. In produzione con il motore reale non cambia appartamento, ma
   permette a un operatore cose riservate agli amministratori o al sistema.
2. **Grave (solo staging).** Il motore simulato è raggiungibile da internet con una chiave fissa scritta nei file del
   progetto (`staging-mock-key`): si leggono e si scrivono i dati simulati di tutti gli appartamenti senza entrare
   nell'app.
3. **Medio.** Se un amministratore toglie i permessi a un utente entrato per invito, lo stream già aperto nel suo browser
   continua a ricevere gli eventi.
4. **Medio.** Su un dispositivo condiviso, se la sessione di una persona viene chiusa da fuori e poi entra un'altra
   persona, le notifiche della prima continuano ad arrivare su quel dispositivo, anche di un'altra organizzazione.
5. **Medio.** Qualunque amministratore può far cancellare l'account del gestore della piattaforma (la cui email è
   visibile a tutti gli utenti) e «catturarlo» nella propria organizzazione con un invito che si accetta da solo.
6. **Medio.** Il codice Italianway è «chi primo arriva»: un'organizzazione che conosce il codice di un appartamento
   altrui può riceverne le prenotazioni.

## 2. I 14 punti

| # | Punto | Esito | Gravità | Riferimento |
|---|---|---|---|---|
| 1 | Tenant scelto dal client | Nessuna falla sulle rotte di organizzazione (tenant sempre da `CurrentUser.tenant_id`); ma vedi F1. | – | `bff/auth.py::resolve_user`, `_from_claims` |
| 2 | ID altrui nelle rotte | **F1** traversal `..` nel proxy, dimostrata. Rotte admin in sé corrette. | Alta | `bff/routes/apartments.py::proxy`, `bff/instances.py::call`, `base_url` |
| 3 | Claim vecchi | Nessuna falla per account con claim. Note basse: `token_revoked` fail-open; finestra record/claim; claim di `set_claims.py` prevalgono. | Bassa | `bff/accounts.py::token_revoked`, `set_role_claim` |
| 4 | Invito solo dall'email | Nessun furto d'invito (migrazione solo con email verificata, uid deterministico). Note: account senza record arruolato senza consenso (parte di F5); enumerazione (L2). | Bassa | `bff/auth.py::_from_claims`, `bff/invites.py::create_invitation` |
| 5 | Eliminazione Firebase globale | **F5**. | Media | `bff/accounts.py::delete_account`, `bff/routes/admin.py::delete_user`, `bff/routes/apartments.py::me` |
| 6 | Log senza tenant agli admin | Nessuna falla. | – | `bff/routes/admin.py::webhook_logs`, `bff/routes/webhooks.py::italianway` |
| 7 | Italianway | Unicità coperta; attribuzione **F6**. | Media | `bff/routes/admin.py::create_apartment`, `patch_apartment`, `remove_apartment` |
| 8 | URL e segreti | Nessuna falla per gli admin; **F2** in staging; note L7, L8. | Alta (staging) | `bff/instances.py`, `bff/main.py::create_app`, `bff/cloudrun.staging.yaml` |
| 9 | Riuso di ID | Nessuna falla. Nota L10. | – | `bff/routes/admin.py::remove_apartment` |
| 10 | Stream dopo revoca | **F3**. Push coperte. Nota L9. | Media | `bff/auth.py::still_sees`, `bff/accounts.py::set_role_claim` |
| 11 | Token push residui | **F4**. | Media | `frontend/src/lib/push.ts::syncPushToken`, `bff/routes/push.py::unsubscribe` |
| 12 | Dati nel browser | Nessuna falla in ciò che è stato letto; non provato nel browser. | – | `frontend/src/lib/session.ts::clearUserData` |
| 13 | Piattaforma nei dati | Nessuna falla nelle rotte `/app/platform/*`. Note L4, L7. | Bassa | `bff/routes/platform.py` |
| 14 | Concorrenza | Nessuna falla oltre i limiti dichiarati; note L8. | Bassa | `bff/routes/platform.py::create_tenant`, `rename_tenant`, `create_tenant_apartment` |

## 3. Le falle

### F1 — Traversal nel proxy verso l'istanza (ALTA)
- **Dove**: `bff/routes/apartments.py::proxy` controlla solo `apartment_id` e il primo segmento `top`;
  `bff/instances.py::call` concatena `base_url(apt) + "/" + path`; httpx rimuove i segmenti `..` prima di inviare;
  uvicorn passa il percorso già decodificato, quindi `%2e%2e` arriva come `..`.
- **Scenario**: il lettore `lettura@demo.it` (org A) chiama
  `GET /app/apartments/apt-rimini-01/instance/%2e%2e/%2e%2e/%2e%2e/apt-altra-01/api/v1/devices` → il BFF chiama
  `/mock/apt-altra-01/api/v1/devices` con la chiave del mock (uguale per tutti) → 200 con i dispositivi dell'org B.
- **Misurato in-process**: diretto → 404; via traversal → 200 per admin e lettore di A; `POST %2e%2e/v1/_test/state` da
  operatore → 204 (diretto 403).
- **In produzione**: non cambia appartamento, ma esce da `/api/v1` ed elude `PROXY_BLOCKED` (`bookings`, `stream`), il
  controllo «solo admin» su `_test` e il filtro funzioni.
- **Correzione proposta**: 404 per ogni `path` con segmenti vuoti, `.` o `..`; lista bianca del primo segmento (prefissi
  del contratto); prove con `%2e%2e` e `..` letterale, anche sui `top` bloccati.

### F2 — Motore simulato raggiungibile da internet con chiave fissa (ALTA in staging)
- **Dove**: `bff/main.py::create_app` monta il mock su `/mock` dell'app pubblica con `INSTANCE_MODE=mock`;
  `bff/mock_instance/app.py::contract_guard` accetta `X-API-Key == INSTANCE_API_KEY_FALLBACK`;
  `bff/cloudrun.staging.yaml` fissa `staging-mock-key`; Cloud Run ha invoker pubblico.
- **Scenario**: `GET https://<bff>/mock/apt-rimini-01/api/v1/decisions` con quella chiave e gli header del contratto →
  decisioni (con le email degli utenti), dispositivi, approvazioni, prenotazioni; con POST comanda. Senza chiave
  `/health` e `/version` per qualunque id, e un simulatore creato per ogni id richiesto (memoria che cresce).
- **Correzione proposta**: non esporre il mock sull'app pubblica (app separata solo su 127.0.0.1, oppure rifiutare le
  richieste con `X-Forwarded-For`), chiave generata a caso all'avvio.

### F3 — Stream che sopravvive al declassamento di un utente senza claim (MEDIA)
- **Dove**: `bff/auth.py::still_sees` tiene il ruolo della richiesta; `bff/accounts.py::set_role_claim` non revoca chi
  non ha claim (il caso normale: chi entra per invito); `bff/routes/admin.py::patch_user`.
- **Scenario**: admin entrato per invito con stream aperto, declassato a lettore senza appartamenti → lo stream continua
  finché il browser lo tiene aperto. Misurato in-process.
- **Correzione proposta**: in `still_sees` usare anche il ruolo riletto; in `patch_user` revocare le sessioni anche senza
  claim quando il ruolo scende; rovesciare `apartment_scope_test::test_still_sees_keeps_the_request_role`.

### F4 — Notifiche della persona precedente su un dispositivo condiviso (MEDIA)
- **Dove**: `frontend/src/lib/push.ts::syncPushToken` (proprietario diverso → dimentica il token solo in locale),
  `frontend/src/auth/AuthProvider.tsx::signedOut` (non chiama `disablePush`), `bff/routes/push.py::unsubscribe` (toglie
  il token solo al chiamante).
- **Scenario**: Anna (org A) attiva le notifiche su un tablet; la sua sessione cade da fuori; Bruno (org B) entra sul
  tablet; le approvazioni di A continuano ad arrivare al tablet, anche come avviso nell'app.
- **Correzione proposta**: `unsubscribe` toglie il token a ogni utente che lo possiede; il sito, trovato un token di un
  altro proprietario, chiama `pushApi.unsubscribe(token)` e `deleteToken` prima di dimenticarlo.

### F5 — Account del gestore della piattaforma cancellabile e «catturabile»; email del gestore visibile (MEDIA)
- **Dove**: `bff/accounts.py::delete_account`, `bff/routes/admin.py::delete_user`, `bff/invites.py::create_invitation`
  (nessun controllo su `platform_members`), `bff/auth.py::_from_claims` (migrazione senza consenso),
  `bff/routes/apartments.py::me` e `bff/routes/admin.py::get_tenant` (`created_by`, `first_admin_email` a ogni utente).
- **Scenario**: l'admin di A legge l'email del gestore in `/app/me`, lo invita, cancella l'invito → l'account Firebase
  del gestore viene eliminato; oppure aspetta che l'invito migri e il gestore diventa membro di A senza consenso.
- **Correzione proposta**: `create_invitation` rifiuta (neutro) le email in `platform_members`; non cancellare mai un
  account Firebase con email verificata o di un gestore (al più revocare le sessioni); togliere `created_by` e
  `first_admin_email` dalle risposte di `/app/me` e `/app/admin/tenant`.

### F6 — Codice Italianway «chi primo arriva» (MEDIA, richiede decisione)
- **Dove**: `bff/routes/admin.py::create_apartment`, `patch_apartment` (unicità, non appartenenza), `remove_apartment`
  (libera il codice), `bff/routes/webhooks.py::italianway`.
- **Scenario**: l'admin di B salva il codice di una struttura di A prima di A, o dopo la cancellazione dell'appartamento
  di A → i webhook vanno a B (prenotazioni, ospiti, date); A riceve «già in uso» senza sapere da chi.
- **Correzione proposta**: il codice lo imposta o conferma la piattaforma (come il collegamento, D-64); in alternativa
  non liberarlo alla cancellazione e registrare ogni rivendicazione nei log di piattaforma.

### Falle minori (BASSA)
- **L1** `bff/routes/admin.py::patch_tenant` rinomina senza normalizzazione né controllo dei doppioni (D-61a aggirata).
- **L2** Enumerazione: l'invito risponde diversamente se l'email è di un'altra organizzazione; crea account Firebase e
  manda email a indirizzi arbitrari; «Identificativo non disponibile» enumera gli id. Accettato in parte da D-63.
- **L3** `bff/accounts.py::token_revoked` fail-open se l'API Auth non risponde (fino a 1 ora durante un guasto).
- **L4** `bff/instances.py::verify` restituisce alla piattaforma il corpo intero di `/health` del motore (elenco
  dispositivi), oltre l'anagrafica tecnica di D-64.
- **L5** Ruolo di piattaforma assegnato per email senza conferma; un gestore può togliere qualunque altro (D-57).
- **L6** Cambio email in Firebase più un invito per la nuova email in un'altra organizzazione → due record con la stessa
  email; la cancellazione dell'invito può eliminare l'account dell'altro utente.
- **L7** Fiducia totale nel gestore della piattaforma (può ricollegare un appartamento verso un server proprio): modello
  scelto, da registrare come assunzione.
- **L8** Concorrenza: due creazioni di piattaforma con lo stesso collegamento passano entrambe; rinomine concorrenti
  lasciano claim di nome orfani; un arresto fra claim del nome/invito e creazione del tenant lascia un invito orfano.
- **L9** `bff/auth.py::_known_tenants` cache per processo mai svuotata: la futura sospensione (D-62) dovrà invalidarla.
- **L10** `remove_apartment` non cancella i timer `push._offline_timers` (innocuo, stesso tenant).

## 4. Prove deboli o mancanti
- `apartment_scope_test::test_still_sees_keeps_the_request_role` sancisce F3.
- `firebase_flows_test::test_delete_by_email_skips_accounts_with_claims` considera desiderata la cancellazione di un
  account senza claim (il caso di F5).
- `frontend/src/lib/push.test.ts` verifica solo l'oblio locale del token (F4); `SignOut.test.tsx` solo in modalità dev,
  non copre la caduta di sessione imposta da fuori.
- `backend_isolation_test::test_other_tenant_apartment_is_404` solo percorsi letterali, niente `..`/`%2e%2e`/`%2f` (F1);
  nessuna prova sull'esposizione di `/mock` (F2).
- `routes_test::test_platform_module_has_no_way_into_organisation_data` controlla solo nomi nell'AST;
  `test_no_organisation_route_takes_a_tenant_from_the_client` vede solo parametri dichiarati, non letture di `Request`.
- `backend_platform_test::...test_organisation_admin_uses_it_platform_does_not_see_inside` non controlla cosa
  restituisce `verify` alla piattaforma (L4).
- Prove su collegamento e codice Italianway: unicità sì, attribuzione e concorrenza di `link_in_use` no.
- Nessuna mutazione sulla costruzione del percorso del proxy.
- `repository_suite_test.py` usa `get_event_loop().run_until_complete`: nello stesso processo dopo file con
  `asyncio.run()` dà 15 rosse (Python 3.13.2); `run_tests.py` lo isola, ma il file è fragile.

## 5. Non verificato
- Front end di Cloud Run con `%2e%2e` nel percorso (verificato fino a Starlette/httpx in-process e, leggendo, uvicorn).
- Firebase vero (email_verified dopo il link di scelta password, sostituzione di account, `tokens_valid_after`).
- Firestore vero o emulatore (filtro IS_NULL, transazioni fra più istanze).
- Sito nel browser (cache back/forward, service worker).
- Se il repository Git è pubblico; quali percorsi esistono sul motore reale fuori da `/api/v1`.

## 6. Cosa ha lanciato Fable
- Due script in-process nella propria cartella temporanea (traversal F1, ruolo vecchio F3), con repository in memoria e
  autenticazione dev.
- `pytest` su 10 file senza servizi esterni: 94 verdi, 15 rosse (artefatto del loop di `repository_suite_test.py`), 16
  saltate; `repository_suite_test.py` da solo: 16 verdi, 16 saltate.
- `git status` vuoto a fine revisione.

---

## Verifica delle correzioni D-70 (Fable, 16 ottobre 2026, su `74fc030`)

- **Chiuse**: F1 (31 varianti del traversal rifiutate: `%2e%2e`, `%2E%2E`, `%2f`, `%252e`, `%5c`, `;`, maiuscole, percorso
  vuoto, `%3f`, `%23`, overlong, `//`, URL assoluto, `_test` e `stream` via traversal; i percorsi legittimi passano),
  F3, F4 server, F5, L1, L4, L6, L8. F4 sito chiusa per lo scenario. F2 chiusa su Cloud Run con una sola barriera
  (l'header `X-Forwarded-For`, che Cloud Run aggiunge ma la documentazione letta non garantisce).
- **N1 (media, preesistente)**: `bff/mock_instance/app.py::contract_guard` non scatta quando il mock è montato sotto
  `/mock` (Starlette passa il percorso completo, la regex legge `mock` come appartamento): chiave, actor e funzioni
  mai controllati. Nel lotto 4 online il mock era aperto senza chiave. Correzione: regex sul percorso relativo al mount;
  prova «loopback con chiave sbagliata → 401».
- **N2 (media-bassa, regressione del sito)**: `AuthProvider.tsx::loadMe` chiama `signedOut` per ogni errore di `/app/me`
  (anche rete e 5xx), che ora chiama `disablePush`: le notifiche si spengono in silenzio. Correzione: `disablePush` solo
  su 401/403 e `onAuthStateChanged(null)`. Residuo: `forgetToken()` avviene prima di `deleteToken` presso FCM.
- **N3 (media, regressione)**: `bff/routes/account.py::delete_account` («Elimina il mio account») ora tiene l'identità
  Firebase degli account verificati e risponde 204. Correzione: cancellazione vera quando la chiede il titolare.
- **N4 (bassa)**: un gestore della piattaforma non è invitabile in nessuna organizzazione, nemmeno come primo
  amministratore (`create_tenant` → 409); resta `scripts/set_claims.py`.
- **N5 (bassa)**: in `patch_user` `revoke_sessions` è fuori dal `try`: 500 a record già cambiato se Firebase fallisce.
- **N6 (cosmetica)**: la versione del contratto non si vede più nell'esito della verifica (`VerifyBadge`).
- **Prove**: su una copia mutata senza le correzioni F1 e F3, 25 rosse su 48; le altre prove nuove rosse per lettura.
  Nell'albero vero 12 suite in-process: 146 verdi, 16 saltate (Firestore).
- Decisioni: D-71 in `docs/registro.md`.

---

## Ultima verifica (Fable, 16 ottobre 2026, su `bf386e3`)

- **Esito: il lotto 5 si può pubblicare.** Chiuse N1 (chiave del mock controllata anche nel loopback; due barriere
  indipendenti), N2, N3, N5, N6, D-73 nel sito (`5a3ffba`), D-72 (28 casi: admin rifiutato con `null`, `""`, maiuscole,
  spazi, caratteri invisibili, `external_ids` nel corpo, creazione in staging; rotte di piattaforma negate ai non
  gestori), D-73 nel server (gestori che si eliminano insieme: ne resta sempre uno). Nessuna regressione.
- Prove nuove rosse su un secondo mutante senza le correzioni: 8 su 8 attese.
- Note minori: (1) con `BFF_ROOT_PATH` non vuoto le barriere del mock potrebbero non scattare (oggi vuoto ovunque);
  (2) webhook con `X-Correlation-Id` non UUID → 400 dal mock in staging; (3) vecchio modulo in cache che rimanda il
  codice Italianway → 403, sparisce con il sito nuovo; (4) un gestore senza organizzazione non può eliminare il proprio
  account dall'app.
- Decisione: D-75 in `docs/registro.md`.

---

## Lotto 9: accesso di assistenza, lato server (Fable, 16 ottobre 2026, su `c29d6f4`)

- **Esito: sicuro, nessuna falla grave.** 86 sonde in-process: senza un accesso aperto da sé nessuno entra (utente,
  admin, gestore senza accesso, accesso usato in un'altra organizzazione: 403); dentro, il gestore è operatore (tutte le
  rotte `/app/admin/*` e il simulatore 403); non diventa mai membro e non riceve notifiche; lo stream si chiude a
  scadenza, chiusura, sospensione e revoca del ruolo.
- Da correggere (bassa o media-bassa): (1) accesso che resta «attivo» per l'organizzazione dopo la rimozione del
  gestore o la cancellazione del suo account, senza voce di chiusura, con email e nome conservati; (2) nel registro
  dell'admin l'apertura non mostra la persona; (3) chiusura doppia contemporanea; (4) voce «scaduto» persa se la prima
  scrittura fallisce; (5) ruolo letto dal record invece che fissato a operatore.
- Note: sospensione → `tenant_suspended` (documentazione da allineare); dopo «Chiudi accesso» lo stream può restare
  fino a circa 50 s; «Chiudi accesso» non è un veto; per D-87 lo pseudonimo va legato alla persona, non al record di
  organizzazione.
- Prove deboli: manca una guardia che imponga `resolve_own_user` su `/app/me` e `/app/push/*`.
- Decisione: D-88.

---

## Lotto 9: accesso di assistenza, lato sito (Fable, 16 ottobre 2026, su `82e09bc`)

- **Esito: sicuro, nessuna falla grave.** Entrata e uscita svuotano la scheda come un cambio di utente (cache, stato
  live, Assistente), lo stream si chiude, `X-Support-Tenant` non va mai su piattaforma e notifiche, la modalità vive
  solo nella scheda, l'uscita scatta su ogni 403, allo scadere e con «Esci», senza buttare fuori dall'app; l'avviso
  dell'admin viene dal profilo della sua organizzazione.
- Da rifinire (bassa): intestazione mandata anche sulle rotte del proprio account (il server la ignora); «Chiudi
  accesso» da Organizzazioni stando dentro non fa uscire subito; «Elimina il mio account» in assistenza non chiude
  l'accesso; «Termina» fallito sul server senza avviso. Note: snapshot dello store che arriva dopo lo svuotamento;
  avvisi dell'organizzazione assistita visibili fino a 10 s; avvisi nascosti per dispositivo e non per persona; corsa
  di un 403 durante una lettura in volo; intestazioni dello stream calcolate una volta sola.
- Decisione: D-89.

---

## Lotto 9: P-51, campi delle risposte per ruolo (Fable, 16 ottobre 2026, su `0b42d5a`)

- **Esito:** nessuna fuga fra organizzazioni, nessuno pseudonimo arriva al sito; lettori e operatori non ricevono
  indirizzi del motore né nomi dei segreti (scansione di 32 rotte × 5 ruoli).
- **Da togliere subito:** nomi dei segreti di Secret Manager nei messaggi di «Verifica connessione» dell'admin
  (`last_check.error`, `verify.error`); messaggio del 422 `secret_name_not_allowed` (ramo morto); `GET ask/{id}` per il
  lettore (legge le domande all'assistente degli altri); campi inutili (`tenant_id`, `created_at`, `external_ids`
  dell'elenco admin; `instance_features`, `reachable` del riepilogo).
- **Fughe da decidere (privacy):** (1) il gestore della piattaforma vede le email delle persone di un'organizzazione nel
  registro attività; (4) i dati degli ospiti nel corpo grezzo delle prenotazioni (admin e piattaforma), conservati
  senza scadenza; anche le chiamate non autenticate restano salvate.
- **Accettate o da registrare:** oracolo 201/409 dell'invito (D-63); l'operatore in assistenza vede le email dei membri
  (D-86).
- **Da valutare, a basso costo:** dettagli di salute dell'istanza non usati; campi tecnici dei soggiorni e del registro;
  rotta `version` solo per l'admin; riscrittura degli pseudonimi anche nei testi liberi del motore.
- Nota: una prima sonda ha chiamato per errore il BFF locale di un'altra sessione sulla porta 8000 (circa 20 richieste
  respinte con 404, nessun effetto).

---

## Lotto 9: revisione finale (Fable, 16 ottobre 2026, `8d3a580`→`588fe31`)

- **Esito: pubblicabile dopo due correzioni piccole**; isolamento, sospensione, pseudonimo, lista bianca
  dell'intestazione e correzioni D-88/D-89/D-90 reggono (17 mutazioni mirate, sonde in-process).
- **F1** (media-bassa): su Firestore «togliere un gestore» non chiude i suoi accessi di assistenza (`list_support_access`
  senza filtri diventa un filtro IS_NULL); le prove in memoria non lo vedono.
- **F2** (media-bassa): l'oscuramento dei dati degli ospiti lavora per nome di campo: dati personali in campi chiamati
  `guests`, `id`, `status`, `sent_at` passerebbero.
- **F3, F4** (bassa): residuo GDPR se l'email è cambiata dopo l'invito; voce «accesso aperto» senza accesso se la
  seconda scrittura fallisce.
- Minori: sospensione che non chiude gli accessi attivi; attore delle chiusure nelle altre organizzazioni; persone non
  più membri ancora risolte nel registro; indirizzo nel testo dell'errore SMTP nei log; `mail_limits` senza scadenza;
  nota tecnica su `X-Actor` in assistenza da allineare (fatto).
- Prove deboli: cinque comportamenti coperti solo dalle prove e2e.
- Decisione: D-91.

---

## Lotto 12: appartamenti dimostrativi e ripristino (Fable, 17 ottobre 2026, `5e55d21` + `5edb787`)

- **Esito: pubblicabile in staging.** Motore simulato in produzione irraggiungibile da internet (100 richieste con 25
  percorsi × 4 forme dell'intestazione: tutte 404 tranne `/mock` → 307); chiave casuale per processo, non fissata nei
  file di Cloud Run; nessun admin può rendere simulato un appartamento; simulatore e ripristino negati ad altre
  organizzazioni (404), operatori e lettori (403) e all'operatore di assistenza; il ripristino tocca solo l'appartamento
  scelto; nessuna regressione (234 prove in-process, 14 mutazioni su 15 catturate).
- **F1 (media), da chiudere prima della produzione:** un appartamento `mock://` con codice Italianway (permesso in
  staging) riceverebbe in produzione le prenotazioni vere: il divieto D-98 vale solo alla creazione e al ricollegamento.
- **Basse:** N1 `/mock` senza barra → 307 da internet; N2 notifiche del dimostrativo ferme dopo il ripristino; N3 un
  `bff/.env` locale finirebbe nell'immagine; N4 nel sito il passaggio da `mock://` a motore vero lascia «simulato»; N5
  testo della conferma sui soggiorni.
- Prove deboli: cancellazione dei task del simulatore non provata davvero (mutazione sopravvissuta), webhook F1, immagine.
- Decisione: D-99.
