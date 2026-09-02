# syntax=docker/dockerfile:1.7-labs
FROM node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 AS deps
WORKDIR /repo

# workspace manifest 만 먼저 복사 — install 캐시 layer.
#
# 손으로 유지하는 목록을 두지 않는다. 종전에는 `apps/mobile/package.json`과
# `apps/mobile/vendor/vworld-map-rn-1.0.0.tgz`가 빠져 있었고, 그러면
# `npm install`이 lockfile 트리를 **조용히 버리고** 다시 푼다. 루트
# `package.json`의 `workspaces` glob과 이 목록이 갈라져도 아무도 알려주지
# 않는 이중 선언이었다. glob에서 직접 유도한다(`--parents`, 1.7-labs).
COPY package.json package-lock.json ./
COPY --parents apps/*/package.json packages/*/package.json ./
COPY --parents apps/*/vendor/ ./

# `npm install`이 아니라 `npm ci`다. manifest와 lockfile이 어긋나면 조용히
# 다른 트리를 만드는 대신 **실패한다**. 위 누락이 바로 그렇게 숨었다.
RUN npm ci --no-audit --no-fund

# ─────────────────────────────────────────────
FROM node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 AS build
WORKDIR /repo
# 루트 `node_modules`만이 아니라 deps 스테이지의 트리를 통째로 가져온다.
# npm은 버전이 충돌하면 hoist 대신 **중첩**한다 — 실제로 루트는
# `tailwindcss@3`(다른 workspace가 끌어온다)이고 `apps/web`이 쓰는
# `tailwindcss@4`는 `apps/web/node_modules`에 있다. 루트만 복사하면 webpack이
# v3를 집어 `@import "tailwindcss"`가 `Can't resolve 'tailwindcss'`로 죽는다
# (2026-09-02 pinned rebuild 실패의 직접 원인).
#
# 어느 workspace가 중첩되는지 열거하지 않는다. 그 목록은 lockfile 해석 결과라
# 의존성 하나만 바뀌어도 달라지고, 열거하면 같은 방식으로 조용히 드리프트한다.
COPY --from=deps /repo ./
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
FROM node:22-bookworm-slim@sha256:83f487e0a63425e5b4d146fb5e5be574bcbe1b7b843d3ebafdd95eaf7767a7e5 AS runtime
WORKDIR /app

ARG PINVI_BUILD_ENVIRONMENT=development
ARG PINVI_SOURCE_REVISION=development
ARG NEXT_PUBLIC_PINVI_API_URL=http://localhost:12801
ARG NEXT_PUBLIC_GRAFANA_URL=http://localhost:12205
ARG NEXT_PUBLIC_GRAFANA_DASHBOARD_PATH=/d/pinvi/overview?orgId=1&kiosk=tv
ARG NEXT_PUBLIC_PINVI_RESTORE_HOTSWAP_UI_ENABLED=0
ARG NEXT_PUBLIC_VWORLD_API_KEY=
COPY scripts/validate-image-provenance.sh /tmp/validate-image-provenance.sh
RUN /bin/sh /tmp/validate-image-provenance.sh "$PINVI_BUILD_ENVIRONMENT" "$PINVI_SOURCE_REVISION" \
    && rm /tmp/validate-image-provenance.sh
LABEL org.opencontainers.image.revision="${PINVI_SOURCE_REVISION}" \
      io.pinvi.build.environment="${PINVI_BUILD_ENVIRONMENT}"
ENV NODE_ENV=production
ENV PORT=3000
ENV PINVI_SOURCE_REVISION=${PINVI_SOURCE_REVISION}
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
# `/app`은 곧 `apps/web`이므로 그 workspace의 중첩 node_modules가 루트보다
# 우선해야 한다. 지금은 build 전용(tailwind)뿐이지만, 런타임 의존이 중첩되면
# 이 줄이 없을 때 컨테이너가 기동 후에야 죽는다.
COPY --from=build /repo/apps/web/node_modules ./node_modules

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "const ports=[process.env.PINVI_WEB_PORT,process.env.PORT,'12805','3000'].filter(Boolean);Promise.any(ports.map((p)=>fetch('http://127.0.0.1:'+p).then((r)=>{if(!r.ok)throw new Error(String(r.status));}))).then(()=>process.exit(0)).catch(()=>process.exit(1))"

CMD ["npx", "next", "start", "-p", "3000"]
