# PRD — Domotica appartamenti (PWA + BFF)

## Original problem statement
Build the manager-facing web app of a smart-home system for short-term rental apartments (PWA React 18 + TS + Vite, shadcn/Tailwind, Recharts; BFF FastAPI stateless without domain logic; Firestore via repository interface with InMemory/Firestore implementations; Firebase Auth with dev mode; API types generated from contract/openapi.yaml v1.0.4; SSE relay; built-in stateful mock instance; FCM push behind flag; Italian UI via it.json; deploy artefacts for Cloud Run + Firebase Hosting; tests). Full text: see the first user message of the job (sections 1–11). Delivery in 4 phases, user reviews each phase in preview.

User choice: mock /ask = deterministic Italian keyword replies (spegni / gradi|temperatura / "alle HH" → schedule / caldaia while occupied → needs_approval / fallback), async ~1 s, every action references a real mock command/schedule.

## Architecture
- `contract/openapi.yaml` (source of truth) → `frontend/src/api/schema.ts` via `yarn gen:api` (openapi-typescript)
- `bff/` FastAPI: config, logs (JSON), auth (dev X-Dev-User / Firebase ID token + claims), repository (base, memory, seed; firestore = Phase 4), features (x-features map), instances (base URL, API key from Secret Manager/env, /version 60 s cache, summary), sse_hub (1 upstream per instance, ring buffer 1 h, Last-Event-ID), routes/apartments (me, dev/users, apartments, summary, transparent proxy, stream), mock_instance (state.py engine + app.py contract routes, standalone `python -m bff.mock_instance --port 8100`)
- `backend/server.py`: preview adapter of the original development tool, mounting BFF under `/api` (ingress only routes /api)
- `frontend/` Vite PWA (vite-plugin-pwa), zustand store + pure stream reducer, TanStack Query, sonner

## User personas
Property manager admin (all + admin area), operator (commands/mode/hold/approvals/rules/assistant), viewer (read-only).

## Implemented (2026-10-14) — Phase 1
- Dev login (4 seeded users incl. owner m.cracchiolo@hqe.it), apartments list cards, overview with mode/hold, health strip, devices by room, capability renderers (switch, climate, heating, power_meter, temperature, humidity, contact, motion, unknown → "non supportata"), async command chips via SSE, rename/move device, feature gating (config ∩ instance + runtime 501), contract major check, Italian i18n, PWA manifest + SW
- Complete mock instance (all 23 operations incl. energy, schedule, rules, approvals, decisions, ask, bookings, _test/state, stream)
- Testing agent iteration 1: backend 18/18, frontend flows 100 %

## Implemented (2026-10-15) — Phase 2
- Stream auth hardened: fetch-based SSE (@microsoft/fetch-event-source), X-Dev-User/Authorization + Last-Event-ID only as headers; BFF no longer accepts dev_user/access_token/last_event_id query params
- Mock window rule honours `minutes` × MOCK_TIME_SCALE (real seconds per simulated minute, default 1; 60 = real time)
- aria-disabled on mode buttons (viewer); CopyableId next to every error (toast, ErrorNotice, CommandChip, approvals/decisions/assistant)
- Screens: Programmazione (list, add/move/cancel dialog in apartment tz), Regole (draft + inline limit validation, save bar, locked rules), Approvazioni (pending/all, countdown, approve/reject with note, live via SSE), Decisioni (actor/device filters, client search, infinite cursor), Consumi (today/7d/30d Recharts, by device), Assistente (POST /ask + polling, session persistence, suggestions)
- react-query: no retry on 4xx; Card/Badge forwardRef
- Testing agent iteration 2: backend 42/42, frontend 100 %

## Implemented (2026-10-15) — Phase 3
- Consumi: period "Soggiorno in corso" (GET /apartment `current_checkin` → now; only when occupied; hour <48h else day). Contract addition: optional `Apartment.current_checkin` (openapi.yaml + mock + schema.ts)
- Simulator page `/a/:id/simulatore` (admin + APP_ENV dev/staging): windows, device online/offline, trigger approval, booking event via SimulatorTranslator → `POST /app/apartments/{id}/simulator/booking`
- Admin area `/admin`: users (invite by email, role, delete; self-demotion/self-delete guarded), apartments CRUD + "Verifica connessione" (`POST /app/admin/apartments/{id}/verify` → /health + /version), features per tenant (`PATCH /app/admin/tenant`) and per apartment (`enabled_features` / `clear_features`)
- Webhook `POST /webhooks/italianway`: HMAC-SHA256 on raw body (ITALIANWAY_WEBHOOK_SECRET / ITALIANWAY_SIGNATURE_HEADER), BookingTranslator protocol, ItalianwayTranslator = explicit STUB, SimulatorTranslator; idempotent forward to POST /bookings with 3 retries (bff/bookings/)
- Push (bff/push.py): hub hooks on approval.pending, device offline beyond offline_alert rule, instance.health down; FCM behind FCM_ENABLED (background hubs started when on); `/app/push/subscribe`, `/app/me/notification-prefs`, `/app/push/status`; frontend dev toasts + Settings notification prefs + FCM token flow (lib/push.ts, public/firebase-messaging-sw.js)
- Testing agent iteration 3: backend 38/38, frontend 100 %

## Implemented (2026-10-15) — Phase 4 + contract fix
- Contract restored to the original v1.0.4 (sha256 8b297c97535bd11144b61687db744933244ab7940c9e2ff1d451fb7e450b3967, same as first commit) — `current_checkin` removed from contract, mock, schema.ts and tests. RULE: never modify contract/openapi.yaml
- Booking archive in the BFF (`BookingRecord`, `apply_booking_event`, `GET /app/apartments/{id}/bookings[?booking_id]`), filled by the forwarder; "Soggiorno in corso" = checkin_at of `current_booking_id` when occupied, hidden when the BFF has no record; comparison with previous archived stay via GET /energy on both ranges (hidden when missing)
- FirestoreRepository (bff/repository/firestore.py) behind REPOSITORY=firestore; shared suite tests/repository_suite_test.py (memory always, firestore with FIRESTORE_EMULATOR_HOST)
- Firebase Auth: claims tenant_id/role are source of truth; invited `inv-*` users recognised by email and migrated to real uid; scripts/set_claims.py (--email/--tenant/--role [--create --send-reset-link] | --from-repo)
- Deploy artefacts: bff/Dockerfile, bff/cloudrun.yaml, scripts/deploy.sh, frontend/firebase.json, frontend/.firebaserc, .gcloudignore, README.md (placeholders only)

## Implemented (2026-10-15) — Webhook log (pilot freeze)
- `WebhookLog` persisted in memory and Firestore (`webhook_logs`, last 100), filled by POST /webhooks/italianway: timestamp, HMAC outcome, event_id, booking_id, correlation_id, forward status + attempts, raw body (≤16 KB); `GET /app/admin/webhook-logs` (admin only, tenant-scoped + unresolved calls); Admin tab "Webhook"; shared repo suite extended
- `.gitignore` now excludes `.env` files (examples stay tracked); no real secrets/project ids in code (placeholders only)
- NO NEW FEATURES after this: user will evaluate simulator reset, CSV export, daily digest after the pilot. User verifies Firestore live, Firebase Auth, FCM on the real project.

## Backlog (post-pilot, not to be built now)
- Simulator reset, CSV export of stay energy, daily digest; replace ItalianwayTranslator stub; split mock state.py

## Next tasks
None — repository ready for GitHub export. React only to defects reported from the real environment.
