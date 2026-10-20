# Prompt: revisione avversaria della gestione di più organizzazioni (P-36)

Da dare a Fable, che lavora in VS Code nella cartella del progetto. Revisione **in sola lettura**, prima della
pubblicazione del lotto 5 (decisioni D-58 e D-69: la lancia la memoria storica). Scritto dalla memoria storica il 16 ottobre 2026.

---

```text
Sei un revisore di sicurezza avversario. Il tuo compito è TROVARE i modi in cui un utente di un'organizzazione può
vedere, modificare o ricevere dati di un'altra organizzazione, oppure ottenere permessi che non dovrebbe avere, nella
funzione «gestione di più organizzazioni» appena scritta. Non devi confermare che funziona: devi provare a romperla.

Lavori nella cartella C:\Users\mcracchiolo\Desktop\DOMOTICA\app, branch main, dove lavorano anche altre sessioni che
scrivono codice. Quindi: NON modificare né creare file, NON fare commit, NON lanciare comandi che scrivono fuori dal
computer (gcloud, firebase, git push), NON avviare server, NON lanciare il giro completo delle prove. Puoi leggere
tutto e puoi lanciare prove singole in sola lettura (per esempio pytest su un file di tests/ contro il codice, se non
richiede servizi esterni) dichiarando cosa hai lanciato. Il rapporto lo scrivi nella tua risposta, non in un file.

## Contesto da leggere per primo
- CLAUDE.md, docs/regole-convivenza.md, bff/API.md (sezioni «Piattaforma», «Appartamenti per utente», «Chiave
  dell'istanza», «URL istanza»).
- docs/registro.md: decisioni D-41, D-43, D-45 (permessi per appartamento), D-56, D-57, D-61a, D-62, D-63, D-64,
  D-65, D-66, D-67 (organizzazioni e piattaforma), D-59 (pulizia del browser), D-60 (chiave dell'istanza).
- Analisi di partenza di un altro modello: docs/prompt-analisi-organizzazioni.md (la domanda) e il riassunto in D-56.

## Il modello di sicurezza dichiarato (verificalo, non fidarti)
- Ogni utente appartiene a UNA sola organizzazione (tenant_id) con un ruolo (admin, operator, viewer) e
  opzionalmente una lista di appartamenti (apartment_ids, assente = tutti, lista vuota = nessuno).
- Le rotte delle organizzazioni passano da resolve_user (bff/auth.py) e get_tenant_apartment; un appartamento fuori
  organizzazione o fuori lista risponde 404 identico a un appartamento inesistente.
- Il ruolo di piattaforma («gestore della piattaforma») sta in platform_members (chiave email normalizzata, vale solo
  con email verificata) e si controlla con require_platform / resolve_identity, separati da resolve_user. Le rotte
  /app/platform/* (bff/routes/platform.py) vedono SOLO anagrafiche: organizzazioni, primo amministratore, gestori,
  webhook non attribuiti, anagrafica tecnica degli appartamenti. Non devono mai dare accesso a proxy, stream,
  prenotazioni, decisioni, consumi o utenti delle organizzazioni.
- In produzione (INSTANCE_MODE=real) solo la piattaforma crea, collega e cancella appartamenti; la chiave dell'istanza
  è sempre langbrain-api-key-<apartment_id>.
- Inviti, nomi delle organizzazioni e identificativi degli appartamenti sono protetti da doppio clic e concorrenza con
  scritture atomiche; un identificativo cancellato non si riusa.
- Nel sito (frontend/) all'uscita o al cambio di utente si svuotano cache delle richieste, stato degli appartamenti,
  conversazioni dell'Assistente, e il token push viene tolto all'utente che esce.

## Cosa fare
1. Per ciascuno dei 14 punti qui sotto, cerca attivamente un modo di aggirare la protezione, leggendo il codice
   (bff/, frontend/src) e le prove (tests/, frontend/src/**/*.test.*). Per ogni punto dai un esito:
   «NESSUNA FALLA TROVATA» (e come l'hai verificato), «FALLA» (scenario concreto passo per passo, gravità alta/media/
   bassa, file e funzione), oppure «NON VERIFICABILE» (perché).
2. Cerca anche falle FUORI dai 14 punti: rotte nuove senza protezione, campi che finiscono nelle risposte sbagliate,
   messaggi d'errore che rivelano dati di altre organizzazioni, gestione delle email (maiuscole, spazi, email non
   verificata), ruolo di piattaforma assegnabile o revocabile da chi non dovrebbe, ultimo gestore, organizzazione
   senza record, cancellazione e riuso.
3. Valuta se le prove esistenti coprono davvero ciò che dichiarano: una prova che passerebbe anche con il difetto non
   vale. Indica le prove deboli.

## I 14 punti (dall'analisi di Sol)
1. Tenant scelto dal client senza verifica dell'autorizzazione.
2. ID di utenti o appartamenti altrui nelle route amministrative.
3. Claim vecchi che ripristinano tenant o ruoli superati.
4. Invito riconosciuto soltanto dall'email globale.
5. Eliminazione Firebase globale dopo la rimozione da una sola organizzazione.
6. Log senza tenant mostrati agli amministratori.
7. Identificativi Italianway duplicati o attribuibili all'organizzazione sbagliata.
8. URL del motore e segreti configurati verso risorse altrui.
9. Riuso di ID con prenotazioni, cache o buffer precedenti.
10. Stream, hub o notifiche che continuano dopo revoca o sospensione.
11. Token push residui dopo un cambio account.
12. Dati nel browser riutilizzati dopo un cambio di organizzazione.
13. Accesso di assistenza scaduto o privo dell'identità dell'operatore reale (la versione minima non ha assistenza:
    verifica che NON esista un modo di entrare nei dati di un'organizzazione dal ruolo di piattaforma).
14. Richieste concorrenti che aggirano i controlli preliminari.

## Mappa delle prove fornita da chi ha scritto il codice
(vedi in fondo a questo file: la usi come punto di partenza da smentire, non come prova)

## Cosa restituire
1. In cima, per il committente (non tecnico), al massimo 10 righe in italiano semplice: si può pubblicare o no, e
   cosa va corretto prima.
2. Tabella dei 14 punti con esito, gravità e riferimento al codice (file e funzione, mai numeri di riga).
3. Le falle trovate fuori dai 14 punti.
4. Le prove deboli o mancanti.
5. Cosa non hai potuto verificare e perché.
Scrivi tutto in italiano. Dove dici «non esiste» o «non è possibile», indica come l'hai verificato.
```

---

## Mappa delle prove (da o1, 16 ottobre, dopo D-68)

Commit di P-36. Server: `165b630`, `b974724`, `122a8f4`, `6a448bb`, `7d9caae` (D-68). Sito: `9804bd9`, `6a49e96`,
`efb593b`, `02dabc7`, `be06ce6`, `065b7af`, `c5aa497`, `74d3fd6`, `6d3d36a`, `6eb822f`, `9e0eb9b`. Giro completo su
`7d9caae`: 0 rosse su 442, 0 saltati. Prova nel browser di o2 su `6eb822f`: 4 percorsi su 4.

Formato: file::prova → cosa verifica · cosa resta secondo chi l'ha scritto.

1. **Tenant scelto dal client — coperto.** routes_test::test_no_organisation_route_takes_a_tenant_from_the_client (nessuna
   rotta di organizzazione riceve tenant/tenant_id da percorso, query, header o corpo); routes_test::
   test_every_platform_route_requires_the_platform_role e ::test_organisation_routes_never_use_the_platform_role;
   backend_isolation_test::test_lists_hold_only_own_tenant e ::test_me_and_tenant_are_own. Resta: nulla di noto.
2. **ID altrui nelle rotte amministrative — coperto.** backend_isolation_test::test_other_tenant_apartment_is_404 (12
   rotte, 404 identico all'inesistente), ::test_other_tenant_stream_is_404, ::test_admin_cannot_touch_other_tenant_apartment,
   ::test_admin_cannot_touch_other_tenant_users, ::test_admin_cannot_give_other_tenant_apartment; backend_test::
   test_unknown_apartment_tenant_isolation; backend_platform_test::TestApartments::test_refusals. Mutazione: controllo
   del tenant tolto → 25 rosse su 33. Resta: nulla di noto.
3. **Claim vecchi — coperto con Firebase finto.** firebase_flows_test::test_role_change_updates_claims_and_revokes_sessions,
   ::test_failed_claim_update_leaves_the_record_as_it_was, ::test_stale_claims_after_a_change_are_refused,
   ::test_revocation_cache_is_bounded (60 s). Resta: Firebase vero non esercitato; con più istanze un token revocato può
   valere fino a 60 s su un'altra istanza (oggi maxScale 1).
4. **Invito riconosciuto solo dall'email — coperto.** firebase_flows_test::test_invitation_migrates_only_with_a_verified_email;
   backend_isolation_test::test_invite_of_other_tenant_email_is_neutral; backend_platform_test::TestTenants::
   test_used_email_refused_and_name_not_consumed; repository_suite::test_atomic_claims; platform_test::
   test_unverified_email_gets_no_role. Resta: fiducia nel campo email_verified di Firebase.
5. **Cancellazione Firebase globale — coperto per la minima.** firebase_flows_test::
   test_delete_by_email_skips_accounts_with_claims. Resta (fuori dalla minima): con persone in più organizzazioni
   «rimuovere da una» non potrà voler dire «cancellare l'account».
6. **Log senza tenant agli admin — coperto.** backend_platform_test::TestWebhookLogs::
   test_unattributed_calls_only_for_the_platform; repository_suite::test_webhook_logs_per_tenant_newest_first (anche
   Firestore, 100 per organizzazione); backend_isolation_test::test_webhook_of_other_tenant_routes_and_logs_only_there.
   Resta: nulla di noto.
7. **Italianway duplicati o attribuiti male — coperto, atomico.** tenant_test::
   test_same_italianway_code_at_once_in_two_organisations, ::test_italianway_code_is_freed_by_a_change_or_a_deletion;
   repository_suite::test_external_id_claims; backend_isolation_test::test_other_tenant_ids_and_codes_are_not_reusable;
   webhook_test::test_ambiguous_code_is_refused (409). Resta: per appartamenti nati prima dell'indice il controllo è una
   lettura; il webhook rifiuta comunque l'ambiguità.
8. **URL e segreti verso risorse altrui — coperto.** instances_url_test::test_secret_name_always_derived_from_apartment_id,
   ::test_link_key; backend_phase3_test::TestInstanceUrl::test_secret_name_not_accepted_nor_returned; real_mode_test::
   test_admin_cannot_create, ::test_admin_cannot_relink_but_can_edit_with_the_same_link, ::test_admin_cannot_delete,
   ::test_same_engine_link_refused_for_two_apartments (409 link_in_use su ogni forma dello stesso collegamento, anche
   fra organizzazioni). Resta: un IP e un nome DNS dello stesso host non sono riconosciuti uguali (il collegamento lo
   imposta solo la piattaforma).
9. **Riuso di ID con dati precedenti — coperto.** backend_platform_test::TestApartments::test_delete_and_id_never_reused;
   repository_suite::test_atomic_claims; apartment_scope_test::test_deletion_stops_the_upstream_stream. Resta: nulla di
   noto.
10. **Stream, hub, notifiche dopo revoca — coperto, salvo sospensione.** apartment_scope_test::
    test_open_stream_closes_when_apartment_is_removed, ::test_open_stream_closes_when_user_is_deleted,
    ::test_open_stream_closes_after_sessions_are_revoked, ::test_dev_mode_streams_skip_the_revocation_check; push_test::
    test_push_only_to_users_who_see_the_apartment, ::test_push_never_crosses_tenants. Resta: chiusura entro 30 s;
    sospensione dell'organizzazione fuori dalla minima; dopo una revoca il dispositivo resta registrato per la stessa
    persona se il sito non ha tolto il token.
11. **Token push residui — coperto.** push_test::test_token_belongs_to_one_person_across_tenants; repository_suite::
    test_users_with_push_token (anche Firestore). Resta: nulla di noto lato server.
12. **Dati nel browser — lato sito (D-59); lato server coperto.** backend_test::test_app_answers_are_not_stored_by_browsers
    (no-store su /app/*, anche sugli errori). Resta: cache di React Query e archiviazione locale (frontend/).
13. **Accesso di assistenza — fuori dalla minima, non esiste.** routes_test::
    test_platform_module_has_no_way_into_organisation_data (ast: platform.py non usa proxy, utenti, prenotazioni,
    resolve_user, get_tenant_apartment); backend_platform_test::TestApartments::
    test_organisation_admin_uses_it_platform_does_not_see_inside. Resta: da progettare quando servirà.
14. **Richieste concorrenti — coperto per i punti noti.** Invito, nome, id, codice Italianway atomici;
    repository_suite::test_last_admin_concurrent_demotions, ::test_last_admin_concurrent_deletions,
    ::test_last_platform_manager_concurrent_removals (asyncio.gather, anche Firestore); tenant_test::
    test_two_admins_demoting_each_other_at_once_leave_one, ::test_two_admins_removing_each_other_at_once_leave_one.
    Meccanismo: transazione Firestore più lock per organizzazione nel processo (l'emulatore non risolve transazioni
    incrociate). Resta: con più istanze, affidato alle sole transazioni di Firestore vero, non provato; modifiche
    concorrenti dello stesso appartamento: vince l'ultima; una lista apartment_ids può tenere un id «morto», mai riusato.

Mutazioni già fatte: controllo del tenant tolto (25 rosse su 33), router di piattaforma senza require_platform (2 rosse),
ricontrollo dello stream disattivato (2 rosse), controllo dell'apartment_ids tolto (2 rosse).
