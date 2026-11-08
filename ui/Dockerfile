# syntax=docker/dockerfile:1.7

# UI container — Next.js static export served by nginx.

ARG NODE_VERSION=20.18-alpine3.20
ARG NGINX_VERSION=1.27-alpine

# ---------- builder ----------
FROM node:${NODE_VERSION} AS builder

ENV NEXT_TELEMETRY_DISABLED=1 \
    npm_config_fund=false \
    npm_config_audit=false

WORKDIR /app

# Layer the lockfile-only install above the source copy so source-only
# edits don't bust the install cache.
COPY ui/litellm-dashboard/package.json ui/litellm-dashboard/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --prefer-offline

COPY ui/litellm-dashboard/ ./
RUN npm run build

# ---------- runtime ----------
FROM nginx:${NGINX_VERSION} AS runtime

# Drop the upstream default :80 server; we own the config.
RUN rm -f /etc/nginx/conf.d/default.conf

# Static export → web root.
COPY --from=builder /app/out /usr/share/nginx/html

# Make readiness fail closed if a later volume mount replaces the export with
# an empty or partial directory. The marker is created only after the build
# output has been copied into the runtime image.
RUN test -f /usr/share/nginx/html/index.html \
    && test -d /usr/share/nginx/html/_next \
    && find /usr/share/nginx/html/_next -type f -print -quit | grep -q . \
    && touch /usr/share/nginx/html/.litellm_ui_ready

# Routing rules — see ui/nginx.conf for the full description.
COPY ui/nginx.conf /etc/nginx/nginx.conf

EXPOSE 3000/tcp

# nginx as PID 1 in foreground; respects SIGTERM out of the box, so
# no tini/dumb-init wrapper needed.
CMD ["nginx", "-g", "daemon off;"]
