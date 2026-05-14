# Link Branch

`v0.1.1` — **[🌐 Try it live at linkbranch.duckdns.org](http://linkbranch.duckdns.org)**  &nbsp;|&nbsp; **[📂 GitHub Repository](https://github.com/MDnoob/Link-Branch)**

Link Branch is a self-hosted link-in-bio platform built with FastAPI, Jinja2, and SQLite.
It supports custom profile design, shareable redirect links, deep analytics (including per-link insights), asset management, and full account management.

---

## Live Demo

You can try the full application right now — no setup required:

**[http://linkbranch.duckdns.org](http://linkbranch.duckdns.org)**

Register a free account, build your page, and start sharing your links in minutes.

---

## What Ships in v0.1.1

### Phase 1 + 2 (UI and profile system)
- Custom public profile page with Linktree-style island layout
- 404 page for missing profiles
- Auto `display_name` on registration
- Section/divider links (`is_section`)
- Per-link 3-dot menu share/copy options
- Profile share sheet modal
- Dashboard "share my page" flow

### Phase 3 (analytics)
- Analytics models:
  - `ProfileView`
  - `LinkClick`
  - `ShareEvent`
- Redirect route with logging:
  - `GET /l/{link_id}` — trackable public redirect (appears on your profile)
  - `GET /r/{redirect_id}` — **stealth redirect link** (does NOT appear on your public profile page, but works in the background and is fully tracked in your analytics dashboard)
- Share logging endpoint:
  - `POST /api/share`
- Click logging endpoint:
  - `POST /api/click`
- Analytics dashboard:
  - `GET /analytics`
  - Two tabs: **Overview** (profile-button clicks) and **Redirects** (redirect-link clicks) — switch between them seamlessly
  - KPIs: views, unique visitors, clicks, shares, CTR
  - Trend charts (daily breakdown)
  - Top links / platforms / referrers
  - Device split (desktop / mobile / tablet / bot)
  - Country & city aggregation (powered by queued ip-api.com lookups or Cloudflare/Vercel proxy headers as fallback)
  - Recent clicks table (paginated)
- **Per-link analytics drilldown** (`GET /analytics/link/{link_id}`):
  - Scoped KPIs: total clicks, unique clickers, CTR vs. profile views
  - Daily click trend chart
  - Device split for that specific link
  - Top countries & cities for that link
  - Top referrers for that link
  - Recent click log (paginated)
- Date-range memory:
  - Last selected analytics range is remembered in session

### Phase 4 (auth and account management)
- Login/register with lowercase username enforcement
- Phone number support at registration
- Password policy validation (frontend checklist + backend enforcement)
- Forgot password flow (`/forgot-password`)
- My Profile page (`/my-profile`)
  - Update profile details (name/email/phone)
  - Change password (new password cannot equal old password)
  - Permanent account delete flow

### Design and customization
- Background customization:
  - Solid color
  - Gradient
  - Image + overlay
- Island card customization:
  - Frosted glass
  - Solid color
  - Gradient
  - Image + overlay
- Avatar customization:
  - URL source
  - Shape
  - Fit (`cover`/`contain`)
  - Scale (70% to 140%)
- Button customization:
  - Shape
  - Fill style
  - Button/text colors
  - Hover effects
- Typography customization:
  - Font family
  - Font size
  - Name/bio colors
- Branding toggle for public page footer

### Dashboard tools
- Add/edit/delete links
- Add sections/dividers
- Enable/disable links
- Drag-and-drop reorder
- Icon picker (brand + custom uploaded icons)
- Upload/manage assets
- Copy trackable redirect link per dashboard link

---

## Redirect Links — Public vs. Stealth

Link Branch supports two types of redirect links:

| Type | Route | Visible on profile page? | Tracked in analytics? |
|---|---|---|---|
| **Profile link** | `/l/{link_id}` | ✅ Yes | ✅ Yes |
| **Stealth redirect** | `/r/{redirect_id}` | ❌ No | ✅ Yes |

**Stealth redirect links** (`/r/...`) are shareable URLs you can give out on other platforms (email campaigns, DMs, paid ads, etc.) without cluttering your public profile page. They log every click — including device, country, city, referrer — exactly like profile links do, but they never appear in your public link list. You manage them from the dashboard under the Redirects section.

---

## Per-Link Analytics

From your analytics dashboard, click any link in the **Top Links** table to open its dedicated analytics page (`/analytics/link/{link_id}`). You'll see:

- **Total clicks** and **unique clickers** for that link
- **CTR** calculated against total profile views in the same period
- **Daily click trend** chart
- **Device breakdown** specific to that link
- **Top countries and cities** that clicked that link
- **Top referrers** driving traffic to that link
- **Full paginated click log** with timestamps, device, location, and referrer

---

## Asset Storage — Dual Mode (OCI + Local Disk)

Link Branch ships a `storage.py` module that automatically routes all file uploads to the right backend depending on your configuration. **No code changes are needed to switch between modes.**

### How it works

| Condition | Upload destination | URL stored in DB |
|---|---|---|
| OCI env vars **present** | Oracle Cloud Object Storage bucket | `https://objectstorage.…/o/<filename>` |
| OCI env vars **absent** | `static/uploads/` on local disk | `/static/uploads/<filename>` |

The same logic applies to deletes — `storage.py` checks the stored URL at delete time so mixed-mode deployments (e.g. some old files on disk, new files in OCI) work correctly during migrations.

### Option 1 — Local disk (default, zero config)

No extra steps. Uploaded assets are saved to `static/uploads/` and served directly by the FastAPI `StaticFiles` mount. This is the default when no OCI variables are set.

### Option 2 — Oracle Cloud Object Storage

#### Prerequisites
1. Create an **OCI account** at [cloud.oracle.com](https://cloud.oracle.com) (Always Free tier is sufficient).
2. Create a **bucket** in Object Storage and set its **visibility to Public**.
3. Generate an **API key** for your user under Identity → Users → API Keys. Download the `.pem` private key file.
4. Note the **fingerprint**, **user OCID**, **tenancy OCID**, **region**, and **namespace** shown in the configuration preview.

#### Upload the private key to your server

```bash
scp -i "<your-ssh-key>" "<path-to-downloaded.pem>" user@<server-ip>:/path/to/link-branch/oci_private_key.pem
```

Lock down permissions:

```bash
chmod 600 /path/to/link-branch/oci_private_key.pem
```

#### Add OCI variables to `.env`

```env
OCI_USER_OCID=ocid1.user.oc1..<your-user-ocid>
OCI_TENANCY_OCID=ocid1.tenancy.oc1..<your-tenancy-ocid>
OCI_FINGERPRINT=xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx
OCI_REGION=<region-identifier>        # e.g. eu-amsterdam-1
OCI_NAMESPACE=<your-object-storage-namespace>
OCI_BUCKET_NAME=<your-bucket-name>
OCI_PRIVATE_KEY_PATH=/absolute/path/to/oci_private_key.pem
```

#### Install the OCI Python SDK

```bash
source venv/bin/activate
pip install oci
```

#### Test the connection

```bash
python3 -c "
import oci, os
from dotenv import load_dotenv
load_dotenv()
config = {
    'user': os.getenv('OCI_USER_OCID'),
    'fingerprint': os.getenv('OCI_FINGERPRINT'),
    'tenancy': os.getenv('OCI_TENANCY_OCID'),
    'region': os.getenv('OCI_REGION'),
    'key_file': os.getenv('OCI_PRIVATE_KEY_PATH'),
}
client = oci.object_storage.ObjectStorageClient(config)
print('Connected! Namespace:', client.get_namespace().data)
"
```

If this prints your namespace, restart the app and new uploads will go directly to your bucket.

#### Migrating existing local files (optional)

Existing files in `static/uploads/` are **not automatically moved**. Their `/static/uploads/...` URLs will continue to work as long as the directory exists on disk. To migrate them, upload each file to the bucket manually (or write a one-time migration script) and update the `url` column in the `assets` table to the OCI URL.

---

## Tech Stack
- FastAPI
- Uvicorn
- SQLAlchemy
- Jinja2 templates
- SQLite (default)
- bcrypt password hashing
- Session auth via Starlette `SessionMiddleware`
- ip-api.com for server-side geo analytics; bounded queue + cache included, falls back to Cloudflare/Vercel proxy headers
- Oracle Cloud Object Storage via `oci` Python SDK (optional; falls back to local disk)

---

## Project Structure
- `main.py`: app bootstrap, router registration, migration helpers, sitemap + robots.txt
- `models.py`: SQLAlchemy models (`User`, `Link`, `Asset`, `RedirectLink`, `ProfileView`, `LinkClick`, `ShareEvent`)
- `database.py`: DB engine/session setup
- `geo.py`: IP geolocation helper (ip-api.com + bounded queue/cache + proxy header fallback)
- `security.py`: rate limiting, input sanitisation, client IP resolution
- `storage.py`: dual-mode asset storage — routes uploads/deletes to OCI or local disk automatically
- `routes/`:
  - `auth.py`
  - `dashboard.py`
  - `public.py` — public profile rendering, `/l/{link_id}`, `/r/{redirect_id}`
  - `settings.py`
  - `analytics.py` — main analytics page + per-link drilldown
  - `profile.py`
  - `home.py`
  - `admin.py`
- `templates/`: Jinja2 templates (dashboard, profile, settings, analytics, link_analytics, auth, home, etc.)
- `static/uploads/`: uploaded user assets (used when OCI is not configured)

---

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/MDnoob/Link-Branch.git
   cd Link-Branch
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. *(Optional)* Install the OCI SDK if you want cloud asset storage:
   ```bash
   pip install oci
   ```
5. Create a `.env` file:
   ```env
   SECRET_KEY=<your-secret-key>

   # Optional: restrict CORS origins
   CORS_ALLOW_ORIGINS=https://yourdomain.com

   # Optional: set the public base URL (used in sitemap + share links)
   PUBLIC_BASE_URL=https://yourdomain.com

   # Optional: grant super-admin access
   SUPERADMIN_USERNAME=<your-username>

   # Optional: enforce secure cookies in production
   SESSION_HTTPS_ONLY=true
   ENV=production
   ENABLE_DOCS=false

   # Optional: custom database path
   DATABASE_URL=sqlite:///./branchtree.db

   # Optional: backend external-service queue limits
   GEO_LOOKUP_CONCURRENCY=4
   GEO_LOOKUP_QUEUE_TIMEOUT_SECONDS=2
   GEO_LOOKUP_TIMEOUT_SECONDS=3
   GEO_CACHE_TTL_SECONDS=86400
   OCI_STORAGE_CONCURRENCY=4
   OCI_STORAGE_QUEUE_TIMEOUT_SECONDS=15

   # Optional: Oracle Cloud Object Storage (leave blank to use local disk)
   OCI_USER_OCID=
   OCI_TENANCY_OCID=
   OCI_FINGERPRINT=
   OCI_REGION=
   OCI_NAMESPACE=
   OCI_BUCKET_NAME=
   OCI_PRIVATE_KEY_PATH=
   ```
6. Run the development server:
   ```bash
   uvicorn main:app --reload
   ```
7. Open in your browser:
   ```
   http://127.0.0.1:8000
   ```

For production, do not use `--reload`. Set `ENV=production`, configure a real `SECRET_KEY`, and run under your process manager with a command like:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
```

---

## Core Routes

### Auth
- `GET /login`
- `POST /login`
- `GET /register`
- `POST /register`
- `GET /forgot-password`
- `POST /forgot-password`
- `GET /logout`

### Dashboard and assets
- `GET /dashboard`
- `POST /dashboard/links/add`
- `POST /dashboard/links/add-section`
- `POST /dashboard/links/{link_id}/edit`
- `POST /dashboard/links/{link_id}/toggle`
- `POST /dashboard/links/{link_id}/delete`
- `POST /dashboard/links/reorder`
- `GET /assets`
- `POST /dashboard/assets/upload`
- `POST /dashboard/assets/{asset_id}/delete`

### Profile and public
- `GET /settings`
- `POST /settings`
- `GET /my-profile`
- `POST /my-profile`
- `POST /my-profile/password`
- `POST /my-profile/delete`
- `GET /profile/{username}` — public profile page
- `GET /l/{link_id}` — tracked profile-link redirect
- `GET /r/{redirect_id}` — stealth redirect (hidden from public profile)

### Analytics
- `POST /api/share`
- `POST /api/click`
- `POST /api/frontend-error`
- `GET /analytics` — main analytics dashboard (Overview + Redirects tabs)
- `GET /analytics/link/{link_id}` — per-link analytics drilldown

### Utility
- `GET /health`
- `GET /robots.txt`
- `GET /sitemap.xml`

### Super admin
- `GET /admin` (accessible only to usernames listed in `SUPERADMIN_USERNAME` or `SUPERADMIN_USERNAMES`)

---

## Known Issues (Planned Fix)
- Geo analytics (country/city) can be inconsistent in local development environments. This is expected because local/private IPs are skipped and proxy headers are only present on deployments behind Cloudflare or Vercel.

---

## Version
- Current release: `0.1.1`
- Live demo: [linkbranch.duckdns.org](http://linkbranch.duckdns.org)
- Repository: [github.com/MDnoob/Link-Branch](https://github.com/MDnoob/Link-Branch)
