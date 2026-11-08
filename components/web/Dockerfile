# syntax=docker/dockerfile:1

# ---- Stage 1: build the Vite app ----
FROM node:24-alpine AS build
WORKDIR /app

# Install deps against the committed lockfile. Use a build-local .npmrc so the repo's
# engine-strict=true doesn't fight the base image, and legacy-peer-deps matches how the
# lockfile was resolved (openapi-typescript peer-depends on TS ^5; app is on TS 6).
COPY package.json package-lock.json ./
RUN printf 'legacy-peer-deps=true\nengine-strict=false\n' > .npmrc \
 && npm ci

# Build-time API wiring, baked into the static bundle (Vite inlines VITE_* at build).
ARG VITE_API_MODE=http
ARG VITE_API_BASE_URL=https://metron-api-846191018592.us-east4.run.app
ENV VITE_API_MODE=$VITE_API_MODE
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
# Demo login pre-filled on the live login page: the seeded "Agua Azul (demo,
# standard)" coordinator (whatsapp/api scripts/seed.py; password is the
# seed-demo-password secret). Public on purpose, for demos: anyone can sign in
# to that production org. Clear these before real resident data goes there.
ARG VITE_DEMO_EMAIL=ana@aguazul.org
ARG VITE_DEMO_PASSWORD=781a9c099ba72c79c242617ec17d7019656838219fe73333
ENV VITE_DEMO_EMAIL=$VITE_DEMO_EMAIL
ENV VITE_DEMO_PASSWORD=$VITE_DEMO_PASSWORD

COPY . .
RUN npm run build

# ---- Stage 2: serve dist/ with nginx ----
FROM nginx:1.27-alpine AS runtime

# Our server config (listens on $PORT, SPA fallback, gzip, caching, strict CSP).
COPY deploy/nginx.conf.template /etc/nginx/templates/default.conf.template

# Replace the stock nginx.conf so we fully control the http/events blocks and can
# run as the templated server on Cloud Run's $PORT.
COPY deploy/nginx.main.conf /etc/nginx/nginx.conf

COPY --from=build /app/dist /usr/share/nginx/html

# Cloud Run provides $PORT (default 8080). nginx's envsubst template entrypoint
# (built into the official image) renders ${PORT} from the environment. Restrict
# substitution to PORT so the CSP's and nginx's own $-vars are left intact.
ENV PORT=8080
ENV NGINX_ENVSUBST_FILTER=PORT
EXPOSE 8080

# The official nginx image's /docker-entrypoint.d/ scripts run envsubst over
# /etc/nginx/templates/*.template → /etc/nginx/conf.d/ before starting nginx.
CMD ["nginx", "-g", "daemon off;"]
