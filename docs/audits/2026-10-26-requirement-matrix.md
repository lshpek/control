# BOTVEX Control Center — requirement matrix

**Baseline:** `main` @ `2506ae34b22057275bf02c2753640247dde5cc04`
**Scope:** locally prepared, unapplied patch. Status describes this working copy, not the live GitHub repository.

Legend: **Implemented** = code path + appropriate tests/evidence exist; **Partial** = useful working slice exists but acceptance criteria remain incomplete; **Not implemented** = no complete working implementation; **Blocked** = verification/publication requires unavailable dependency or permission.

| Requirement area | Status | Evidence and remaining work |
|---|---|---|
| Current-state audit | Implemented for this iteration | Repository metadata and base SHA verified; files, manifests, migrations, auth, CRUD, UI and tests inspected. Full browser inspection unavailable. |
| One-time owner bootstrap | Partial | CLI bootstrap defaults to username `lshpek`, reads temporary password only from environment, refuses when any user exists, hashes with Argon2id and forces change. Operator must privately supply the agreed temporary password; bootstrap does not auto-run. |
| Owner account recovery | Partial | CLI recovery only updates an existing owner, requires `--confirm`, revokes sessions and forces a password change. It requires trusted local OS/database access; no email-based recovery flow. |
| Password authentication/session | Implemented foundation | Generic errors, Argon2id, opaque hashed sessions, HttpOnly/Secure/SameSite cookie behavior, expiry, logout/revocation, first-login change. Backend tests pass; external browser E2E not run. |
| Brute-force controls | Implemented foundation | DB-backed identity/IP throttling, account lockout and sanitized generic errors. No external distributed rate-limit service. |
| Telegram authentication | Partial | Official SDK adapter and server-side raw `initData` HMAC/freshness validation; Telegram ID must be explicitly linked. Actual BotFather/HTTPS launch not verified. |
| Built-in roles / custom RBAC | Partial | Owner, Administrator, Manager, Developer, Client, Observer and custom permission grants; deny-by-default backend checks; owner-only sensitive delegation; roles can be managed in UI. Per-user overrides and every requested matrix/scope form are not fully implemented. |
| Record-level scopes | Partial | SQL-level all/assigned/own-customer scopes and project assignments exist; tests cover scoped records. Complete per-record grants across every future resource type remain incomplete. |
| Account management | Partial | Search/pagination, create user, one-time temp credential, role/client binding, activation, reset and session listing/revocation. Full audit/security event separation and all account lifecycle details remain. |
| Client portal | Partial | Linked client sees own published/non-archived orders, customer-visible events/messages; backend denies cross-client order IDs and internal messages. No files, payment actions, formal approval, change requests or full profile flow. |
| CRM / lead pipeline | Partial | Existing Client CRUD is retained; a distinct New → Contacted → Qualified → Proposal → Won/Lost lifecycle, contact interactions, follow-ups and conversion are not implemented. |
| Quotations and versions | Not implemented | No quote/line-item/version/approval model or document generation. |
| Orders | Partial | Order entity, draft and controlled transitions, status history, internal/public messages, pagination, archive/restore, commercial-field freeze after draft. No formal change request, accepted quotation version or delivery acceptance. |
| Projects / tasks | Partial | Existing CRUD, dates/statuses, scoped access and project assignment support. No complete kanban/timeline, reusable project templates, dependencies or full client-facing milestones. |
| Service catalog and pricing | Partial | Existing service records remain manual and honest; prices, currencies, estimates and historical commercial pricing are not implemented. |
| Financial tracking | Not implemented | No manual payment ledger, expense/margin calculations or provider verification. |
| Files / attachments | Not implemented | No upload/download storage, file type/size validation or per-record file authorization. |
| Notifications / reminders | Not implemented | No notification center or scheduled worker/dispatch. In-app activity is not external delivery proof. |
| Activity history | Partial | Existing business activity records plus security-related activity messages; no distinct tamper-evident audit store. |
| Application diagnostics/logs | Partial | Existing log-entry UI is manual data only. Structured request IDs, centralized production diagnostics, retention and safe trace correlation are incomplete. |
| Health monitoring / incidents | Not implemented | No scheduler, outbound probes, SSRF-safe monitor, incident deduplication or recovery lifecycle. Manual service status is not represented as automatic verification. |
| GitHub CI | Partial / blocked | `.github/workflows/quality.yml` exists in local patch and YAML parses; no workflow is published or run on GitHub. |
| Migration stability | Implemented foundation | Explicit historical schema plus additive reversible `0002`; upgrade → downgrade → upgrade passed on temporary SQLite. Column names match all 21 ORM tables. Type/index/FK parity is not exhaustively diff-tested. |
| Safe backup/recovery | Partial | README describes stopping backend, protected copy and restore verification; no automated backup or tested restore command exists. |
| Frontend authentication/admin/portal/orders | Partial | Login/password-change gate, role admin, session controls, order UI and client portal are connected to APIs in source. Responsive CSS was inspected, but no browser/E2E visual QA. |
| Design-system / `App.tsx` refactor | Partial | Shared format/Telegram modules and new focused screens exist. `App.tsx` remains large; no exhaustive accessibility audit or screen-by-screen visual inspection. |
| Frontend dependency reproducibility | Blocked | `package-lock.json` could not be generated because npm network install timed out and offline cache was incomplete (`ENOTCACHED`). |
| Full frontend lint/typecheck/tests/build | Blocked | `eslint` and `vitest` not installed; TypeScript/build missing React/Lucide/JSX packages. Syntax transpilation passed for 15 TS/TSX files, but that is not semantic typecheck. |
| Real responsive/mobile/Telegram E2E | Blocked | No running browser/Telegram WebView plus configured public HTTPS bot app in the available test environment. |
| GitHub branch/commit/PR | Blocked | Feature branch create returned 403. The patch remains unapplied; no commit/PR was created and `main` is unchanged. |
| Production readiness | Not achieved | Core security foundation is improved, but full frontend verification, production configuration review, penetration/security review and several critical requested modules are still missing. |
