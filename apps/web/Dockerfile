# syntax=docker/dockerfile:1.7-labs
FROM node:22-bookworm-slim AS deps
WORKDIR /repo

# workspace package.json 만 먼저 복사 — install 캐시 layer
COPY package.json package-lock.json* ./
COPY apps/web/package.json apps/web/
COPY packages/schemas/package.json packages/schemas/
COPY packages/api-client/package.json packages/api-client/
COPY packages/state/package.json packages/state/
COPY packages/design-tokens/package.json packages/design-tokens/
COPY packages/domain/package.json packages/domain/
COPY packages/hooks/package.json packages/hooks/
COPY packages/i18n/package.json packages/i18n/
COPY apps/mobile/vendor/vworld-map-core-1.0.0.tgz apps/mobile/vendor/
COPY apps/web/vendor/vworld-map-web-1.0.0.tgz apps/web/vendor/

RUN npm install --no-audit --no-fund

# ─────────────────────────────────────────────
FROM node:22-bookworm-slim AS build
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_PINVI_API_URL=http://localhost:12801
ARG NEXT_PUBLIC_GRAFANA_URL=http://localhost:12205
ARG NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH=/d/pinvi/overview?orgId=1&kiosk=tv
ARG NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=0
ARG NEXT_PUBLIC_VWORLD_API_KEY=
ENV NEXT_PUBLIC_PINVI_API_URL=${NEXT_PUBLIC_PINVI_API_URL}
ENV NEXT_PUBLIC_GRAFANA_URL=${NEXT_PUBLIC_GRAFANA_URL}
ENV NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH=${NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH}
ENV NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=${NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED}
ENV NEXT_PUBLIC_VWORLD_API_KEY=${NEXT_PUBLIC_VWORLD_API_KEY}
RUN npm --workspace apps/web run build

# ─────────────────────────────────────────────
FROM node:22-bookworm-slim AS runtime
WORKDIR /app

ARG NEXT_PUBLIC_PINVI_API_URL=http://localhost:12801
ARG NEXT_PUBLIC_GRAFANA_URL=http://localhost:12205
ARG NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH=/d/pinvi/overview?orgId=1&kiosk=tv
ARG NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=0
ARG NEXT_PUBLIC_VWORLD_API_KEY=
ENV NODE_ENV=production
ENV PORT=3000
ENV NEXT_PUBLIC_PINVI_API_URL=${NEXT_PUBLIC_PINVI_API_URL}
ENV NEXT_PUBLIC_GRAFANA_URL=${NEXT_PUBLIC_GRAFANA_URL}
ENV NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH=${NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH}
ENV NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=${NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED}
ENV NEXT_PUBLIC_VWORLD_API_KEY=${NEXT_PUBLIC_VWORLD_API_KEY}

COPY --from=build /repo/apps/web/.next ./.next
COPY --from=build /repo/apps/web/public ./public
COPY --from=build /repo/apps/web/package.json ./package.json
COPY --from=build /repo/apps/web/next.config.mjs ./next.config.mjs
COPY --from=build /repo/node_modules ./node_modules

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "const ports=[process.env.PINVI_WEB_PORT,process.env.PORT,'12805','3000'].filter(Boolean);Promise.any(ports.map((p)=>fetch('http://127.0.0.1:'+p).then((r)=>{if(!r.ok)throw new Error(String(r.status));}))).then(()=>process.exit(0)).catch(()=>process.exit(1))"

CMD ["npx", "next", "start", "-p", "3000"]
