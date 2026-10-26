# BOTVEX Control Center — implementation and verification audit

**Date:** 2026-10-26

**Source-of-truth repository:** `https://github.com/lshpek/controlll`

**Verified base:** `main` @ `2506ae34b22057275bf02c2753640247dde5cc04`
**Publication state:** this working copy contains unapplied changes; GitHub branch creation returned HTTP 403. No source changes were pushed to GitHub, no pull request was created, and no deployment occurred.

## Executive summary

The current source has been extended locally with account authentication, session management, Argon2id password hashing, one-time owner bootstrap/recovery commands, role/permission administration, SQL-level record scoping, a limited client portal, and order lifecycle/message APIs. Regression tests were added around data integrity and authorization boundaries. This is an implementation slice, not the complete product in the full request. The repository is not production-ready because the full frontend toolchain and real browser/Telegram behavior remain unverified, and several requested commercial/operational modules have not been implemented.

## Source-backed changes in this working copy

- `backend/app/auth.py`, `backend/app/auth_routes.py`: username/password login, opaque server-side sessions, Argon2id hashes, first-login password replacement, logout/session revocation, login rate limiting, owner/staff account operations and custom role/permission endpoints.
- `backend/app/bootstrap_owner.py`, `backend/app/recover_owner.py`: explicit CLI-only bootstrap/recovery using environment variables; bootstrap refuses to run if any user already exists, and recovery only resets an existing owner while revoking sessions. Neither workflow is executed automatically on application startup.
- `backend/app/access_scopes.py`, `backend/app/crud.py`: SQL-level filters for all/assigned/own-customer scope, related-record checks, bounded lists and explicit archive/restore routes.
- `backend/app/orders.py`: order listing, state transitions, history, separate internal/client-visible messages, archive/restore and a restricted portal API.
- `backend/app/models.py`, `backend/app/schemas.py`, `backend/migrations/versions/0001_initial_schema.py`, `0002_accounts_rbac_orders.py`: account/session/RBAC/project-assignment/order models and an explicit reversible schema migration for the new tables.
- `backend/app/main.py`: read-only settings GET, protected API routes and production-mode Origin checks on mutations. `backend/tests/test_migrations.py` adds an automated temporary-database migration cycle and checks tables, columns, foreign keys, uniqueness and index columns.
- `backend/app/security.py`: raw Telegram `initData` HMAC/freshness validator; login is possible only for a Telegram identity explicitly linked to an existing local account.
- `frontend/src/AuthGate.tsx`, `LoginScreen.tsx`, `AdminAccessPage.tsx`, `OrdersPage.tsx`, `PortalApp.tsx`: login/password-change gate, localized user/role UI, session controls, orders, and a basic customer portal. `frontend/src/telegram.ts` adapts the official SDK. `frontend/src/formatting.ts` handles date-only values and overdue status.
- `.github/workflows/quality.yml`: prepared backend/frontend quality workflow. It is not yet present on GitHub because the feature branch could not be created.
- `README.md`, `.env.example`: setup, bootstrap/recovery, migration, account access and known limitation documentation.

## Confirmed verification evidence

| Check | Result | Evidence / limitation |
|---|---|---|
| Full backend suite | PASS | `python -m pytest backend/tests -q` — **41 passed**. |
| Python compilation | PASS | `python -m compileall -q backend/app backend/tests`. |
| Alembic upgrade/downgrade/upgrade | PASS | On an isolated temporary SQLite DB: `upgrade head`, `downgrade -1`, `upgrade head`. The real project DB was not used. |
| Migrated-schema table/column names | PASS | All **21** ORM tables exist; column names, foreign-key relationships, unique constraints and index column sets are compared in the migration regression test. SQL type nuances and every runtime query plan are not exhaustively checked. |
| Workflow YAML parsing | PASS | Local PyYAML parse confirmed `backend` and `frontend` jobs. This does not constitute a GitHub Actions run. |
| Frontend TS/TSX syntax transpilation | PASS | `typescript.transpileModule` processed **15** `.ts`/`.tsx` files; this is a syntax/transpilation check, not a semantic typecheck. |
| Frontend ESLint | BLOCKED | `npm run lint`: exit 127, `eslint: not found`. |
| Frontend Vitest | BLOCKED | `npm run test`: exit 127, `vitest: not found`. |
| Frontend TypeScript typecheck / build | BLOCKED | `npm run typecheck` and `npm run build` exit 2 because frontend packages and React/JSX type declarations are not installed. Two missing icon imports found during this check were fixed; complete semantic validation remains blocked. |
| Lockfile / dependency install | BLOCKED | No `package-lock.json` exists. Online `npm install` timed out in the execution environment; an offline lockfile-generation attempt returned `ENOTCACHED`. No lockfile has been fabricated. |
| Browser/mobile visual QA and real Telegram launch | NOT RUN | No usable browser/Telegram WebView, configured bot token or public HTTPS launch environment was available for this pass. |
| GitHub Actions run | NOT RUN | GitHub Actions API returned no runs for the current baseline. The proposed workflow is only in this unapplied working copy. |
| GitHub branch/PR | BLOCKED | `mcp__GitHub__create_branch` for `codex/botvex-control-center-upgrade` returned HTTP 403 `Resource not accessible by integration`. No further identical write retries were made. |

## Regression-driven security/data-integrity findings

- `GET /api/v1/settings` previously wrote default settings to SQLite. Defaults are now virtual until saved, and a regression test verifies no rows are created by a read.
- Production state-changing requests now require an `Origin` in the exact configured origin allowlist. Local development still supports origin-less CLI/test requests, while explicitly untrusted origins are rejected. The new production-mode test failed before the fix and passed after it.
- PATCH updates now validate only explicitly supplied relationships rather than treating an omitted existing `project_id` as a missing relationship.
- Archive state has explicit archive/restore routes instead of an order being silently archived through general PATCH.
- Commercial scope, amount/type/currency and delivery-date fields cannot be silently rewritten after an order leaves its draft/approval-preparation stage.
- Users cannot combine the `Client` role with staff roles through account administration; the backend also denies non-portal permissions to any user with an active Client role if role data is misconfigured.
- Administrative permission delegation, owner account modifications, temporary-password/session handling and client order/message scope have API-level regression coverage.

## Product requirement boundary

Implemented foundations do not equal the complete product requested. Missing or incomplete capabilities include: a full lead pipeline and follow-up history; quote versions and client approvals; formal change requests; payment/expense ledger; secure file upload/download; delivery acceptance; actual notification dispatch; global search; a dedicated notification center; separate structured application diagnostics/security-audit persistence; real health-check scheduling and incident lifecycle; automated backups and restore validation; per-user permission overrides; complete client profile workflows; a full multi-page refactor of the large `frontend/src/App.tsx`; and real responsive/browser/Telegram E2E tests.

The service status and deployment/test sections remain manual records unless a real integration supplies verified results. No fake monitoring history, deployment success, uptime or CI result was introduced.

## Security / setup notes

- The initial username defaults to `lshpek`; the temporary owner password is supplied privately through `BOOTSTRAP_OWNER_PASSWORD` only when running the one-time CLI bootstrap. It is not stored in tracked source or examples. First login must change it.
- Production must disable local development mode, configure HTTPS/origins/cookies, and review hosting and database access. This code has not received independent penetration testing.
- `.env.example` contains placeholders only. No actual password/token values should be committed.
- The owner recovery tool requires local database/OS access and `--confirm`; stop the backend and back up the target DB first.
- `npm install` currently uses exact top-level versions in `package.json`, but without a committed lockfile its transitive dependency tree is not fully reproducible.

## Final status

The prepared patch is a source-level, locally tested feature slice. It is **not applied to GitHub**, **not merged**, and **not deployed**. Product completion is partial and awaits frontend dependency installation, full frontend tests/build, browser/Telegram E2E, and implementation of remaining product requirements.
