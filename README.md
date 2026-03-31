# Link Branch

`v0.1.1` release.

Link Branch is a self-hosted link-in-bio platform built with FastAPI, Jinja2, and SQLite.
It supports custom profile design, shareable redirect links, analytics, assets, and account management.

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
  - `GET /l/{link_id}`
- Share logging endpoint:
  - `POST /api/share`
- Click logging endpoint:
  - `POST /api/click`
- Analytics dashboard:
  - `GET /analytics`
  - KPIs (views, unique visitors, clicks, shares, CTR)
  - Trend charts
  - Top links/platforms/referrers
  - Device split
  - Country/city aggregation
  - Recent clicks
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

## Tech Stack
- FastAPI
- Uvicorn
- SQLAlchemy
- Jinja2 templates
- SQLite (default)
- bcrypt password hashing
- Session auth via Starlette `SessionMiddleware`

## Project Structure
- `main.py`: app bootstrap, router registration, migration helpers
- `models.py`: SQLAlchemy models
- `database.py`: DB engine/session setup
- `routes/`:
  - `auth.py`
  - `dashboard.py`
  - `public.py`
  - `settings.py`
  - `analytics.py`
  - `profile.py`
- `templates/`: Jinja templates (dashboard, profile, settings, analytics, auth, etc.)
- `static/uploads/`: uploaded assets

## Setup
1. Create and activate a virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Create `.env` with:
   - `SECRET_KEY=<your-secret>`
   - Optional: `DATABASE_URL=sqlite:///./branchtree.db`
4. Run:
   - `uvicorn main:app --reload`
5. Open:
   - `http://127.0.0.1:8000`

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
- `GET /profile/{username}`
- `GET /l/{link_id}`

### Analytics API/pages
- `POST /api/share`
- `POST /api/click`
- `GET /analytics`

## Known Issue (Planned Fix)
- Geo analytics (country/city) can be inconsistent in local development environments.
- This is expected and will be improved in a future update with stronger production-grade geo handling.

## Version
- Current release: `0.1.1`
