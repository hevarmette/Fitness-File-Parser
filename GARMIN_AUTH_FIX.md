# Garmin Authentication Fix

## Background

As of March 2026, Garmin changed their authentication flow by adding Cloudflare TLS fingerprinting that blocks third-party clients. This broke:
- **garth** (deprecated by maintainer, see [garth#222 discussion](https://github.com/matin/garth/discussions/222))
- **garminexport** (which depended on garth)
- **python-garminconnect** (which depended on garth, see [issue #332](https://github.com/cyberjunky/python-garminconnect/issues/332))

The root cause is Garmin's Cloudflare setup blocking requests that don't have a real browser's TLS fingerprint. See the [Garmin forum post about TLS fingerprinting](https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-connect-web/433892/tls-fingerprinting-blocks-third-party-clients).

---

## Tier 1: Upgrade garminexport (simplest, try first)

The garminexport maintainer already merged fixes:
- [PR #105](https://github.com/petergardfjall/garminexport/pull/105) — adds `curl_cffi` for TLS browser fingerprint impersonation
- [PR #119](https://github.com/petergardfjall/garminexport/pull/119) — rewrites auth flow, removes garth dependency (released as v0.6.0)

This uses [`curl_cffi`](https://github.com/yifeikong/curl_cffi) to make HTTP requests that look like they come from a real browser at the TLS level, fooling Cloudflare.

### Clone at the right version

Since I use a custom naming convention, clone the repo directly at the latest fixed tag (`v0.7.1`, Jan 2026) to modify locally:

```bash
git clone --branch v0.7.1 https://github.com/petergardfjall/garminexport.git
cd garminexport
pip install -e ".[impersonate-browser]"
```

Available tags with the auth fix:
- `v0.7.1` (Jan 10, 2026) — latest, includes [PR #125](https://github.com/petergardfjall/garminexport/pull/125)
- `v0.7.0` (2025/2026) — includes PR #119 auth rewrite
- `v0.6.0` (Aug 2025) — first version with the new auth flow (PR #119)
- `v0.5.0` — has `curl_cffi` impersonation (PR #105) but uses old garth-based auth

Use `v0.7.1` unless you have a reason not to. All versions >= 0.6.0 have the new auth flow that doesn't depend on garth.

### Install (if not cloning)

```bash
pip install --upgrade garminexport[impersonate-browser]
```

### Run (same as before)

```bash
garmin-backup --backup-dir=activities --format fit --format json_summary your@email.com
```

This produces the same `{timestamp}_{activity_id}.fit` + `{timestamp}_{activity_id}_summary.json` file pairs that `parse_fit_garmin_connect.py` expects. **No code changes needed in the Fitness File Parser.**

---

## Tier 2: Swap auth layer with garmin-health-data's client

If Tier 1 fails (Garmin tightens fingerprinting beyond what garminexport's `curl_cffi` handles), **swap out only the auth layer** in garminexport with [garmin-health-data](https://github.com/diegoscarabelli/garmin-health-data)'s more robust auth client.

### Why this works

garminexport's architecture:

```
auth layer (garth/curl_cffi) → authenticated session → API calls → file naming/saving
```

Only the auth layer breaks. Everything downstream (API calls, `_summary.json`, file naming) still works — it just needs valid OAuth tokens. garmin-health-data's auth client (`garmin_health_data/garmin_client/`) has 5 fallback SSO strategies:

1. Portal web login via `curl_cffi` (TLS browser fingerprint impersonation, 30-45s pre-submit delay)
2. Portal web login via `requests` (30-45s pre-submit delay)
3. Mobile portal login via `curl_cffi` (mobile TLS impersonation, 30-45s pre-submit delay)
4. Mobile login via `requests` (30-45s pre-submit delay)
5. Widget login via `curl_cffi` (last resort)

See [garmin-health-data auth internals](https://github.com/diegoscarabelli/garmin-health-data#authentication-internals) for full documentation.

### Implementation

1. Clone garminexport at v0.7.1 (with your custom naming)
2. `pip install garmin-health-data` (for its auth client)
3. In garminexport's `garminclient.py`, replace the existing login/auth code with garmin-health-data's client to obtain OAuth tokens
4. Feed those tokens into garminexport's existing HTTP session
5. Everything else stays the same — API calls, `_summary.json` generation, `.fit` downloads, your custom file naming

### Reference: someone did this for another project

[@yeled replaced garth in their garminspo2 project](https://github.com/yeled/garminspo2/pull/3) using garmin-health-data's auth. Same concept — swap auth, keep the rest.

### No changes needed in Fitness File Parser

Since garminexport still produces the same `{timestamp}_{activity_id}.fit` + `{timestamp}_{activity_id}_summary.json` output, `parse_fit_garmin_connect.py` and `helpers.py` remain untouched.

---

## Tier 3: Playwright browser login (nuclear option — unblockable)

If both `curl_cffi` approaches fail (Garmin detects impersonated TLS fingerprints), use a **real browser** for authentication. A real Chromium browser is indistinguishable from a human user — Cloudflare cannot block it.

### How it works

1. Playwright launches a headless Chromium browser
2. Browser navigates to Garmin SSO login page
3. Fills in credentials, submits login form
4. Captures the CAS ticket or OAuth tokens from the redirect URL
5. Those tokens are fed into your existing HTTP session for API calls

The browser is only needed for the initial login (and token refresh if tokens expire). Once you have tokens, all subsequent API calls are normal HTTP requests.

### Trade-offs

| | curl_cffi (Tier 1/2) | Playwright (Tier 3) |
|---|---|---|
| **Dependencies** | ~5MB Python package | ~200MB+ Chromium binary |
| **Speed** | Fast (milliseconds) | Slow (seconds to launch browser) |
| **Detection risk** | Possible (impersonation isn't perfect) | Zero (it IS a real browser) |
| **Fragility** | TLS fingerprint may need updating | Login page HTML changes break selectors |
| **Headless/server** | Works anywhere | Needs display server or headless flag |

### Reference implementations

- **[@salanfe's Playwright login script](https://github.com/matin/garth/discussions/222#discussioncomment-16489035)** — Full working example: logs in via Playwright, extracts CAS ticket, exchanges for OAuth tokens via garth, saves tokens for reuse. Includes the complete `playwright_login.py` and shows how to use garth for subsequent API calls with the saved tokens.

- **[@etweisberg's garmin-connect-mcp](https://github.com/etweisberg/garmin-connect-mcp)** — Node.js MCP server that routes API calls through a headless Playwright browser. Captures auth cookies, exposes 27 tools for activities/health/FIT downloads. Overkill for batch pipelines but shows the pattern.

- **[@sturimcode's eufy-sync](https://github.com/sturimcode/eufy-sync)** — Playwright for initial browser login, captures OAuth2 tokens, then refreshes them automatically. The Garmin auth piece is reusable.

### Implementation in garminexport

Same approach as Tier 2, but use Playwright instead of garmin-health-data for the auth:

1. Clone garminexport at v0.7.1
2. `pip install playwright && playwright install chromium`
3. Write a `playwright_auth.py` module (based on @salanfe's script above) that:
   - Logs into Garmin SSO via Playwright
   - Extracts CAS ticket from redirect URL
   - Exchanges ticket for OAuth tokens
   - Saves tokens to disk for reuse
4. In garminexport's `garminclient.py`, call your Playwright auth to get tokens
5. Feed tokens into the existing HTTP session
6. Everything downstream stays the same

Tokens last ~18 hours (access) / 30 days (refresh), so the browser only launches occasionally.

---

## Fields from `_summary.json` that the Fitness File Parser needs

All solutions above preserve these fields because they only change the auth layer, not the API calls:

| JSON path | DB column |
|-----------|-----------|
| `activityName` | `activity_name` |
| `description` | `description` |
| `eventTypeDTO.typeKey` | `category` |
| `summaryDTO.distance` | `adjusted_distance` |
| `summaryDTO.duration` | `adjusted_duration` |
| `summaryDTO.directWorkoutFeel` | `workout_feel` |
| `summaryDTO.directWorkoutRpe` | `effort` |

---

## Quick workarounds from the community

These are lighter-weight fixes mentioned in the [garth#222 discussion](https://github.com/matin/garth/discussions/222). They may break at any time but are easy to try:

- **Override User-Agent** ([posted by @diegoscarabelli](https://github.com/matin/garth/discussions/222#discussioncomment-16418591)) — Set a Chrome User-Agent before login. Works as of April 2026, confirmed by multiple users. One user reported it stopped working by late April.

- **Pin garth to v0.6.3** ([posted by @BastiTee](https://github.com/matin/garth/discussions/222#discussioncomment-17409232)) — v0.6.3 uses the older web SSO flow (not the mobile API that Garmin blocked). Confirmed working as of June 2026.

- **User-Agent fix + MFA** ([posted by @m-zanichelli](https://github.com/matin/garth/discussions/222#discussioncomment-16567643)) — Shows how to combine the User-Agent override with MFA/2FA email code flow.

---

## Links

| Resource | URL |
|----------|-----|
| garth deprecation discussion | https://github.com/matin/garth/discussions/222 |
| garth issue #217 (original breakage) | https://github.com/matin/garth/issues/217 |
| garminexport repo | https://github.com/petergardfjall/garminexport |
| garminexport PR #105 (curl_cffi) | https://github.com/petergardfjall/garminexport/pull/105 |
| garminexport PR #119 (auth rewrite) | https://github.com/petergardfjall/garminexport/pull/119 |
| garmin-health-data | https://github.com/diegoscarabelli/garmin-health-data |
| garmin-health-data auth docs | https://github.com/diegoscarabelli/garmin-health-data#authentication-internals |
| garmin-connect-mcp (Playwright + MCP) | https://github.com/etweisberg/garmin-connect-mcp |
| eufy-sync (Playwright OAuth reusable) | https://github.com/sturimcode/eufy-sync |
| garminspo2 PR (garth replacement example) | https://github.com/yeled/garminspo2/pull/3 |
| curl_cffi library | https://github.com/yifeikong/curl_cffi |
| Garmin forum post (TLS fingerprinting) | https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-connect-web/433892/tls-fingerprinting-blocks-third-party-clients |
| python-garminconnect issue #332 | https://github.com/cyberjunky/python-garminconnect/issues/332 |
