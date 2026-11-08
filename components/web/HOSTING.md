# Firebase Hosting

The public site is Firebase Hosting in GCP project `csl-metron-webhook`, on the
hosting **target** `site`. `.firebaserc` maps that target to the site ID
`metron-reporter` (served at `https://metron-reporter.web.app`). The project's
default site `csl-metron-webhook.web.app` is deliberately not used: its name ties
CSL to the bot in public.

## Why the config lives in `components/web`

The React app in this folder will be deployed to the same site later, so the
config sits next to it. Moving the app in is then a change to `public` and a few
rewrites, not a new site. Until then `public` points at `static-site/`: two plain
HTML pages (home and `/privacidad`) and one stylesheet, with no scripts.

```bash
cd components/web
firebase deploy --only hosting --project csl-metron-webhook
```

`npm run deploy:web` at the repo root runs the same command after checking that
`static-site/` holds only `.html`/`.css` files.

Run the deploy from `components/web` only after checking `static-site/` holds just
the pages: everything in it is published. (`*.log` and dotfiles are ignored, because a
stray `firebase-debug.log` was published once and had to be removed.)

If the CLI's login is stale (`firebase login --reauth` from a shell where
`firebase` is on PATH), the first deploy on 2026-11-07 used the Hosting REST API
directly with `gcloud auth print-access-token` (create version with the same
headers/redirects, populateFiles, upload, finalize, release). Firebase was added
to the project with `projects/csl-metron-webhook:addFirebase`, which also created
the unused default site `csl-metron-webhook.web.app` (it serves nothing; a default
site cannot be deleted).

Meta app settings: Privacy Policy URL `https://metron-reporter.web.app/privacidad`,
App domain `metron-reporter.web.app`. Data deletion instructions are at
`/privacidad#borrar`. `/privacy` redirects to `/privacidad`.

## Headers (WEB-063)

Every response gets a strict CSP (`default-src 'self'`, no inline script or
style, `frame-ancestors 'none'`, `base-uri 'none'`), `Referrer-Policy:
no-referrer`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, HSTS,
`Cross-Origin-Opener-Policy: same-origin`, and a `Permissions-Policy` that turns
off camera, microphone, geolocation and payment. Everything is `Cache-Control: no-cache`
(the site is three small files), so text edits to the privacy page show up at once.
When the Vite build moves in, give hashed `/assets/**` a long `max-age` and keep HTML `no-cache`;
note that Hosting header globs match the request path, so with `cleanUrls` an `*.html` glob does not match `/privacidad`.

## Planned: React app and same-site `/v1`

The API's session cookie (`__Host-sid`, SameSite=Lax) needs the web app and the
API on the same site. The plan is to serve both from this Hosting site, with
`/v1/**` rewritten to the Cloud Run service. It is **not enabled yet**: the web app
has no sign-in screen, and the cookie blocker below is unresolved. When it is turned on, `hosting`
becomes:

```jsonc
"public": "dist",                       // npm run build output
"rewrites": [
  { "source": "/v1/**", "run": { "serviceId": "whatsapp-webhook", "region": "us-east4" } },
  { "source": "**", "destination": "/index.html" }   // SPA fallback, after /v1
]
```

Also at that point:

- Move `static-site/privacidad.html` to `public/privacidad.html` (Vite copies
  `public/` into `dist/`) so the Meta URL keeps working. The home page text moves
  into the app or a static `/acerca`.
- The CSP needs no API origin: with the rewrite, `connect-src 'self'` covers `/v1`. Keep `style-src 'self'` (Vite emits CSS files, no inline styles).
- Set the API's `WEB_ORIGIN` to the Hosting origin exactly.
- Do **not** route `/docs`, `/openapi.json` or the staff-only API through this
  site until they are meant to be public. Only `/v1/**` is rewritten, and the
  webhook path `/webhooks/whatsapp` stays on its `run.app` URL.

### Blocker to resolve first: Firebase strips cookies

Firebase Hosting forwards **only a cookie named `__session`** to Cloud Run
rewrites; all other request cookies are removed at the CDN. A `__Host-sid`
cookie would be set in the browser but never reach the API, so every request
would be 401. Options:

1. Name the session cookie `__session` when served behind Hosting. Keep
   `Secure; HttpOnly; Path=/; SameSite=Lax` and no `Domain`. This gives up the
   browser-enforced `__Host-` prefix guarantees (the attributes stay, the
   enforcement goes).
2. Use a custom domain and put the API on a sibling host (`app.example.org` on
   Hosting, `api.example.org` on Cloud Run). That is same-site, so SameSite=Lax
   works and `__Host-sid` can stay, but it needs CORS with credentials and a
   custom domain the team is willing to publish. (`*.web.app` and `*.run.app`
   are public suffixes, so those two hosts are never same-site.)
3. An external HTTPS load balancer in front of both (≈ USD 18/month base).

Also: Hosting's CDN caches responses that say `Cache-Control: public`. The API
must send `Cache-Control: private, no-store` on every `/v1` response.

Also confirm that Hosting supports Cloud Run rewrites in `us-east4` before
relying on it (the supported-region list is in the Firebase docs).
