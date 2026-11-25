# Property Onboarding Platform

Django + DRF backend, React (Vite) frontend, PostgreSQL.

**Phase 1** covers:
- **Properties**: the listing nickname is generated (`A37331-TOR-SPA1507`), and each property gets a licence record and an activity log.
- **12-step onboarding checklist**:
  - A step stays locked until the steps it depends on are done.
  - Some tasks need proof (a link or a note) before they can be ticked.
  - Steps can be marked blocked or waiting.
  - Progress and the current step are worked out automatically.
- **Dashboard**: summary tiles, a "needs attention" list, the pipeline by stage, and licence expiry warnings.
- **Procurement**:
  - Master list import from CSV, with quantity rules (fixed, per bedroom, per bathroom, per bed).
  - Price and stock check that flags items when out of stock or more than 25% over the typical price.
  - Approved replacements for flagged items.
  - Cross-check by item type that catches missing items and duplicates.
  - Store carts staged for review.
  - Approval ticks steps 5 and 6 on the property's checklist.
  - CSV order document.

The price check is **simulated** (`PRICE_CHECKER=simulated`). Real store lookups come in a later phase (see `backend/procurement/pricing.py`).

**Phase 2** adds the AI agents:
- **Intake agent:**
  - Upload the signed agreement PDF. Claude reads it into fields, which you review.
  - Then the agent creates the property, the unit's Google Drive folder (with subfolders), and a portfolio tracker row.
  - It also drafts the registration email to building management, with the agreement attached.
- **Compliance agent:**
  - Creates the unit's unique email (Google Workspace).
  - Builds the licence packet checklist.
  - Drafts an email asking the owner for missing documents.
- **Daily checks** (`python manage.py run_agent_sweeps`):
  - Licence renewal reminders at 60/30/7 days; expired licences are marked.
  - A follow-up draft when building management hasn't replied within 5 days.
- **Approvals:** every agent email is a draft until someone approves it. Sending the building email ticks "Lease sent to building management".
- **Screens:**
  - Upload-and-review form for the agreement.
  - Live agent trace on each property, and the licence packet.
  - Approvals inbox, Licences page, Buildings page.

**Phase 3** adds listings and photos:
- **Photos:**
  - Upload the photographer's set, or import it from the Google Drive link.
  - Each photo gets a room and caption; you choose the cover and the order.
  - A re-shoot starts a new set, which replaces the old one in Guesty.
- **Property page:** a photo grid with a full-screen viewer, and tabs for Onboarding, Listing and Photos.
- **Listing preview:**
  - Title, highlights, amenities, sleeping arrangements and house rules (with the licence number).
  - Target rate, go-live readiness, and channel status.
- **Listing agent:**
  - Checks the photo set and ticks step 8.
  - Creates the Guesty listing with the nickname, hidden from marketplaces until go-live (`isListed: false`).
  - Uploads the photos cover-first and ticks step 9.
  - Drafts the "ready to optimize" email to Angel Host. Sending it ticks step 10's first task.
- **Guesty connection:** the Guesty token is cached for 24 hours, because Guesty allows only 5 token requests per day.

Guesty downloads photos from URLs, so in live mode the backend must be reachable from the internet. Set `PUBLIC_BASE_URL` to the deployed backend address; `localhost` won't work. Before switching on live mode, test the request bodies in `backend/listings/guesty.py` against a Guesty test account.

The demo data includes illustrated sample photos (not real units) for two properties: BAY617 and YON1802.

**Phase 4** completes the journey to live:
- **Guest experience tab** (step 11):
  - The guest guide: arrival, buzzer, lockbox, Wi-Fi, parking, garbage, house rules, local tips, emergency contact.
  - Lockbox codes and Wi-Fi passwords are hidden after saving. Showing them is logged in the activity feed.
  - The guide ticks step 11 as it fills in.
  - Enso Connect has no public API, so **Copy guidebook for Enso** produces the full text to paste into Enso. The guidebook link is then saved back here.
- **Go live tab** (step 12):
  - Final checks: steps 1–11, licence approved with a number, listing and photos in Guesty, guest guide and Enso link. Licence expiry under 30 days shows as an advisory.
  - **Approve go-live** sets `isListed: true` in Guesty and ticks "Final check passed".
  - The team then confirms each channel (Airbnb, Booking.com, direct site) after checking the live listing.
  - **Unlist** hides it again, for example for licence renewal or repairs.
- **Expired licence while listed:** the daily check drafts an urgent email to operations.
- **Real price and stock checks** (`PRICE_CHECKER=web`):
  - Reads each master-list item's product page (schema.org data or price meta tags).
  - Stores that block automated requests, or items without a link, are marked "Check by hand" and priced at the typical price. They don't block the order.
  - Keep `PRICE_CHECKER=simulated` for demos with the sample list, which has no product links.

### Dry-run mode
Without credentials, nothing leaves the system. The agents record what they *would* have done, and the app marks those steps "Dry run".
- **No `ANTHROPIC_API_KEY`:** agreements are read with a basic PDF text reader. Every field is highlighted for checking.
- **No Google settings:** Drive, Sheets, Gmail and the Admin SDK all dry-run. Each service goes live when its own settings are filled in. See `.env.example` and `backend/agents/integrations/google_workspace.py` for the scopes the service account needs (domain-wide delegation).

A fictional sample agreement for testing is at `backend/agents/data/sample_agreement.pdf`.

## Run it locally (Windows)

You need Python 3.11+, Node 20+, and PostgreSQL 16 (installed locally, or through Docker Desktop).

### 1. Database
With Docker:
```
docker compose up -d
```
Or with a local PostgreSQL install, create a database called `onboarding` (user `postgres`, password `postgres`).

### 2. Backend (terminal 1)
```
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```
`seed_demo` loads the five sample properties and the 59-item master list, and creates a login: **ops / onboarding2026**. The Django admin is at http://127.0.0.1:8000/admin/.

### 3. Frontend (terminal 2)
```
cd frontend
npm install
npm run dev
```
Open http://localhost:5173. The dev server forwards `/api` to Django on port 8000.

### Daily checks
Schedule this once a day (Windows Task Scheduler, cron, or a Render cron job):
```
python manage.py run_agent_sweeps
```
You can also run it from the Licences page with **Run daily checks now**.

### Tests
```
cd backend
python manage.py test tests
```

## Useful commands
| Command | What it does |
|---|---|
| `python manage.py import_master_list path\to\list.csv` | Import the client's master list (exported from their Google Sheet). |
| `python manage.py sync_steps` | Apply changes from `onboarding/definitions.py` to all properties. |
| `python manage.py seed_demo --reset` | Delete all properties and reload the demo data. |

## Where things live
```
backend/
  properties/    Property, Licence, ActivityLog, nickname rules (services.py)
  onboarding/    12-step definitions, checklist engine, dashboard and property API
  procurement/   Stores, master list, importer, pricing (simulated), order services and API
  agents/        Intake + Compliance agents, email drafts, buildings, Claude/Google integrations
  listings/      Photos, listing profile, Guesty client, Listing agent, readiness, guest guide, go-live
  tests/         Engine, procurement and API tests
frontend/src/
  pages/         Dashboard, Properties, PropertyDetail (+ property/ tabs), Procurement, MasterList, Approvals, Licences, Buildings, Login
  components/    Layout, NewPropertyDialog, ui (icons, pills, toast)
```

## Assumptions to confirm with the client
- **Nickname format:** A + sequence, city code, first 3 letters of the street + unit number.
- **Glasses:** wine and drinking glasses are counted 2 per bed (may need to be per guest instead).
- **Sofa beds:** not counted as beds.
- **Typical price:** a fixed reference price, not the last price paid.
- **Over-price threshold:** 25%. Change it with `OVER_PRICE_THRESHOLD`.

- **Licence packet:** the default packet list is a placeholder. The City of Toronto's exact requirements need confirming (`AGENTS["LICENCE_PACKET"]` in settings).
- **Unit email format:** `{street}{unit}@<domain>`, e.g. que1204@…

## Deploy to Render

`render.yaml` is a Render Blueprint. It creates two services from this repo:

| Resource | Type | What it is |
|---|---|---|
| `property-onboarding-api` | Web service (Python) | Django API, from `backend/`, started by `backend/start.sh` |
| `property-onboarding-web` | Static site | React app, from `frontend/`, built with Vite |

The database is external, because Render allows only one free Postgres per workspace. Use a free [Neon](https://neon.tech) database:
1. Create a project (e.g. `property-onboarding`, region close to the Render region, e.g. AWS US West / Oregon).
2. Copy the connection string. It looks like `postgresql://…@ep-….neon.tech/neondb?sslmode=require`.
3. Paste it into the API's `DATABASE_URL`.

### Steps

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, connect the GitHub repo, then **Apply**.
3. Render asks for the values marked `sync: false`. For now, enter:
   - **`DATABASE_URL`** (on the API): the Neon connection string
   - **`CORS_ALLOWED_ORIGINS`** (on the API): `https://property-onboarding-web.onrender.com`
   - **`VITE_API_URL`** (on the static site): `https://property-onboarding-api.onrender.com/api`
   - Leave the API keys blank. The agents run in dry-run mode until you add them.
4. Wait for both services to build. The first deploy takes a few minutes.
5. If Render gave a service a different address (it adds a suffix when a name is taken), update those two values in each service's **Environment** tab. Then redeploy: **Manual Deploy → Deploy latest commit** for the API, and **Clear build cache & deploy** for the static site, because `VITE_API_URL` is baked in at build time.
6. Open the static site's URL and sign in as **ops**. The password is the `DEMO_PASSWORD` value in the API's **Environment** tab, which Render generated.

The Django admin is at `https://<api-address>/admin/`, with the same login.

To change the password (no Shell needed): edit `DEMO_PASSWORD` in the API's **Environment** tab and save. Render redeploys, and `start.sh` runs `ensure_admin`, which sets the new password.

### Free plan limits

These are fine for a client demo:
- The API sleeps after 15 minutes without traffic. The first request afterwards takes about a minute.
- **No persistent disk.** Uploaded agreements and photos disappear on every deploy or restart. The demo photos are restored on each start (`SEED_DEMO=true`).
- A free Neon database sleeps when idle and wakes up in a second or two. It doesn't expire.
- Cron jobs are paid, so the daily checks don't run on their own. Use **Run daily checks now** on the Licences page.

### For real client data
- Switch the API to `plan: starter`, add the persistent disk (commented out in `render.yaml`) with `MEDIA_ROOT=/var/data/media`, and use a paid database plan (Neon or Render).
- Set `SEED_DEMO=false`, and create real users with `python manage.py createsuperuser` in the service's **Shell**.
- Uncomment the daily-checks cron job.
- Add the credentials in **Environment**: `ANTHROPIC_API_KEY`, the Google settings, `GUESTY_CLIENT_ID` / `GUESTY_CLIENT_SECRET`, `ANGEL_HOST_EMAIL`, `OPS_EMAIL`. `PUBLIC_BASE_URL` is filled in automatically from Render's address.

## What's left before production
- **Client credentials:**
  - Anthropic API key.
  - Google service account with domain-wide delegation, plus the Drive folder, tracker sheet and sender mailbox.
  - Guesty Open API client ID and secret.
  - Angel Host email.
- **Client data:** the real master list with product links, building contacts, and the City of Toronto licence packet requirements.
- **Deployment:** move from the free-plan staging setup to paid plans with a disk and the daily cron (see *Deploy to Render*).
- **Guesty testing:** test the Guesty request bodies against a Guesty test account before switching off dry-run.
