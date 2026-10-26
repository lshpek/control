# BOTVEX Control Center

BOTVEX Control Center is a single-business workspace for managing client records, projects, tasks, services, manual operational records and development orders. It contains a Russian-language React interface and a FastAPI backend. Customer-facing access is provided through a separately rendered portal backed by server-side customer scoping.

## Current implementation

- React 18, TypeScript, Vite 6, and Lucide icons.
- FastAPI REST API under `/api/v1`, SQLAlchemy 2.x, SQLite, and Alembic migrations.
- Username/password authentication, Argon2id password hashes, opaque server-side sessions, `HttpOnly` session cookies, logout/revocation, temporary-password replacement, generic login errors, and database-backed login throttling.
- One-time owner bootstrap command. It does not run during app startup and refuses to run when any user already exists.
- Built-in roles, permission grants, custom roles, resource scope checks, project assignments, user activation controls, one-time account password reset, and activity records for security-sensitive account operations.
- Draft orders and controlled order-state transitions, order-event history, internal and customer-visible messages, archive/restore endpoints, and server-side order list pagination.
- A client portal for an explicitly linked client account. It lists only that client's non-draft, non-archived orders and exposes only customer-visible fields, events, and messages.
- Official Telegram Web Apps SDK integration. Telegram login is available only when raw, signed `initData` is valid and the Telegram user ID is explicitly linked to an existing local account. Opening the Mini App does not create an account or grant access automatically.
- Existing CRUD sections for clients, projects, tasks, services, log entries, manual test runs and manual deployment records. Manual records are not represented as automated verification.
- Bounded list query parameters, selected-resource scoping, date-only formatting helpers, a read-only settings GET endpoint, and a GitHub Actions quality workflow definition.

## Known limitations

This repository is **not production-ready** yet. Quotes and immutable quote revisions, payment ledger/provider verification, formal change requests and customer approvals, secure attachments/file exchange, external notification delivery, real service-monitoring checks and incidents, a notification center, full CRM lead conversion/follow-up workflow, and automated backup execution are not implemented. The customer portal currently supports orders and customer-visible messages/events, not attachments or payment actions. GitHub Actions has been configured in source, but a successful run must be observed after the workflow is published. Frontend dependencies do not currently have a committed `package-lock.json`, so installation is not yet fully reproducible.

## Requirements

- Python 3.11–3.13
- Node.js 22 LTS (Node.js 20+ may work, but CI uses Node.js 22)
- npm
- Windows PowerShell examples are used below; Linux/macOS commands may be adapted to the same environment variables and Python modules.

Docker, PostgreSQL, a Telegram bot token and a hosting provider are not required for local browser/password-login development.

## Local setup (Windows 11 / PowerShell)

Run the commands from the repository root. Create the Python virtual environment and install backend dependencies:

```powershell
py -m venv .venv
Copy-Item .env.example .env
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
python -m alembic -c backend\alembic.ini upgrade head
```

The defaults in `.env.example` are for local development on loopback (`127.0.0.1`). `LOCAL_DEV_MODE=true` affects local cookie/CORS-related configuration; it is **not an authentication bypass**. A user account and login session are still required. Do not expose the local development configuration to the public internet.

### Create the initial owner once

The default initial username is `lshpek`. The temporary password is supplied interactively to the one-time bootstrap process through `BOOTSTRAP_OWNER_PASSWORD`; it is not stored in tracked files and it is not included in examples. Do not place the temporary password in source code, command history, `.env.example`, logs, a ticket, or the frontend bundle.

```powershell
$secure = Read-Host "Enter the temporary owner password" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:BOOTSTRAP_OWNER_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $env:PYTHONPATH = "$PWD\backend"
    python -m app.bootstrap_owner
} finally {
    Remove-Item Env:BOOTSTRAP_OWNER_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    $secure.Dispose()
}
```

This command creates the owner only when the `users` table is empty. If a user already exists, bootstrap exits without changing any account. Do not run it as a password-reset command. The first successful sign-in is forced to replace the temporary password with a strong password of at least 12 characters before accessing the workspace.

### Recover an existing owner account

Recovery requires local operating-system/database access. Stop the backend first, verify that `.env` points at the intended database, and create a protected backup. The command only resets a record already marked as an owner; it never creates a missing owner. It revokes that user's active sessions and forces another password change at the next sign-in.

```powershell
$secure = Read-Host "Enter a temporary recovery password (12+ characters)" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:OWNER_RECOVERY_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $env:OWNER_RECOVERY_USERNAME = "lshpek"
    $env:PYTHONPATH = "$PWD\backend"
    python -m app.recover_owner --confirm
} finally {
    Remove-Item Env:OWNER_RECOVERY_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:OWNER_RECOVERY_USERNAME -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    $secure.Dispose()
}
```

Use this only as a deliberate local recovery operation; it is not an HTTP endpoint or a login bypass. It records a security activity event and changes no other user's credentials.

### Start the backend

```powershell
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```

- API: `http://127.0.0.1:8000`
- Interactive API docs: `http://127.0.0.1:8000/docs`
- Liveness/database check: `http://127.0.0.1:8000/health`

### Start the frontend

Open a second PowerShell window in the repository root:

```powershell
cd frontend
npm install --no-audit --no-fund
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` and `/health` to the local backend. The first owner login uses the username configured in `.env` (defaults to `lshpek`) and the temporary password entered during bootstrap; it then requires a password change.

## Authentication, roles and data scope

- The server stores only Argon2id password hashes. The session cookie is `HttpOnly`, uses `SameSite=Lax`, and is `Secure` outside local-development mode. Session tokens are random opaque values; only their SHA-256 digests are stored in the database.
- Login errors do not reveal whether a username exists. Failed attempts are rate limited by normalized identity and client IP; accounts can be temporarily locked after repeated failures.
- There is no public self-registration. An authorized administrator creates an account and receives a generated temporary password once. The user must change it after first sign-in. Password reset revokes active sessions.
- The backend checks permissions on each protected API request. Built-in roles are Owner, Administrator, Manager, Developer, Client and Observer. Custom roles are owner-defined; sensitive account/role administration and settings can only be delegated by the owner. The Administrator role can manage regular accounts, but does not receive owner-only password reset, session revocation, suspension or role-editing powers.
- Client accounts cannot combine the Client role with staff roles. The backend rejects internal API permissions for any account with an active Client role, even if a database or configuration error adds an extra role. It is not sufficient for the frontend merely to hide internal screens.
- Authorized owner/staff users with `admin:users:sessions` can list session metadata and revoke another account's active session. Session identifiers are shown for administration, but raw session tokens and stored token hashes are never returned. The current session cannot be revoked from the same window; use logout instead.
- Effective grants from multiple roles are additive. For each permission, the broadest grant among active roles wins: `own_customer`, `assigned`, then `all`. This scope order is intentional and means role combinations must be reviewed carefully.
- Developer/observer record scopes use explicit project assignments. Client portal access requires a local user with the Client role and a linked `customer_id`. Telegram login additionally requires the Telegram user ID to be explicitly linked by an authorized account administrator.
- Client order APIs do not expose internal notes, internal messages or other customers' orders. Changing an order ID in a request must not grant access to another customer's data.

## Telegram Mini App setup

`frontend/index.html` loads the official Telegram Web Apps SDK. The adapter handles `ready()`, `expand()`, theme parameters, viewport/safe-area events and listener cleanup. For Telegram login, the backend verifies raw `initData` HMAC and freshness, then maps the signed Telegram user ID to an already-existing local account. It never automatically creates a new account or promotes the Telegram user to owner.

A real Mini App launch requires a public HTTPS frontend URL and BotFather configuration. If the frontend is hosted on a different origin, set that exact origin in `CORS_ORIGINS` and verify the cookie, Origin and reverse-proxy/TLS configuration for the chosen hosting setup. This repository's local tests do not prove that an actual Telegram launch works.

## Migrations and backup guidance

Apply migrations from the repository root:

```powershell
python -m alembic -c backend\alembic.ini upgrade head
```

The first migration now describes the original schema explicitly, rather than using the application's current SQLAlchemy metadata for historical create/drop operations. Migration `0002_accounts_rbac_orders.py` adds account, access, session, assignment and order-related tables. Test migrations against a disposable database before applying changes to any valuable data. Do not downgrade a production database without a separate backup and migration review.

The default SQLite file is `backend\botvex.db`. The safest simple local backup procedure is to stop the backend first, then copy the database to a protected directory outside the project/web root. Restore only while the backend is stopped, preserve a copy of the current file, put the chosen backup back in place, run `alembic upgrade head`, restart the app and verify login plus key records. Keep backups access-restricted; no scheduled backup or restore automation is implemented by this application.

## Quality checks

From the repository root:

```powershell
python -m pytest backend\tests -q
cd frontend
npm run lint
npm run typecheck
npm run test
npm run build
```

The backend test suite covers account bootstrap, login/logout, temporary-password replacement, session revocation, privilege escalation attempts, role/record scopes, cross-customer order isolation, internal-message privacy, order lifecycle, archival/restoration, the Telegram signature validator, settings GET side effects, CRUD validation and migrations as configured by the environment. Run the commands and inspect their exit codes before treating them as passed.

The workflow `.github/workflows/quality.yml` checks backend tests on Python 3.11 and 3.13, a clean Alembic upgrade against a temporary SQLite database, and frontend lint/type-check/test/build. It uses read-only workflow permissions and pinned action SHAs. There is no successful CI run to report until GitHub Actions actually executes the committed workflow. Once npm registry access is available, generate and review `frontend/package-lock.json`, commit it, and switch CI installs from `npm install` to `npm ci` for reproducibility.

## Integrations and release status

- Telegram SDK code exists; Telegram login requires a configured server-side bot token and a pre-linked account.
- GitHub Actions workflow code exists; run status is unknown until observed in GitHub.
- Test runs and deployment records entered through existing sections are manual records, not automated CI/deployment proof.
- No real health-check monitor, incident worker, notification delivery, payment-provider connection, file storage integration, AI API connection or production deploy is included.
- Before any public release, complete a separate security review, set production HTTPS/origin/cookie configuration, verify account recovery and backups, run frontend checks and actual responsive/browser/Telegram E2E tests, and review the hosting/storage model.
#   c o n t r o l  
 