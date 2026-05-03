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
  - Country & city aggregation (powered by IPstack or Cloudflare/Vercel proxy headers as fallback)
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

## Tech Stack
- FastAPI
- Uvicorn
- SQLAlchemy
- Jinja2 templates
- SQLite (default)
- bcrypt password hashing
- Session auth via Starlette `SessionMiddleware`
- IPstack API (optional) for geo analytics; falls back to Cloudflare/Vercel proxy headers

---

## Project Structure
- `main.py`: app bootstrap, router registration, migration helpers, sitemap + robots.txt
- `models.py`: SQLAlchemy models (`User`, `Link`, `Asset`, `RedirectLink`, `ProfileView`, `LinkClick`, `ShareEvent`)
- `database.py`: DB engine/session setup
- `geo.py`: IP geolocation helper (IPstack + proxy header fallback)
- `security.py`: rate limiting, input sanitisation, client IP resolution
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
- `static/uploads/`: uploaded user assets

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
4. Create a `.env` file:
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

   # Optional: custom database path
   DATABASE_URL=sqlite:///./branchtree.db

   # Optional: IPstack API key for geo analytics
   IPSTACK_KEY=<your-ipstack-key>
   ```
5. Run the server:
   ```bash
   uvicorn main:app --reload
   ```
6. Open in your browser:
   ```
   http://127.0.0.1:8000
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
- Geo analytics (country/city) can be inconsistent in local development environments without an `IPSTACK_KEY`. This is expected — the app falls back to proxy headers, which are only present on deployments behind Cloudflare or Vercel. Configure `IPSTACK_KEY` in `.env` for accurate local geo data.

---

## Version
- Current release: `0.1.1`
- Live demo: [linkbranch.duckdns.org](http://linkbranch.duckdns.org)
- Repository: [github.com/MDnoob/Link-Branch](https://github.com/MDnoob/Link-Branch)
