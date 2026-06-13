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
COPY packages/hooks/package.json packages/hooks/
COPY packages/i18n/package.json packages/i18n/

RUN npm install --no-audit --no-fund

# ─────────────────────────────────────────────
FROM node:22-bookworm-slim AS build
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_PINVI_API_URL=http://localhost:12801
ENV NEXT_PUBLIC_PINVI_API_URL=${NEXT_PUBLIC_PINVI_API_URL}
RUN npm --workspace apps/web run build

# ─────────────────────────────────────────────
FROM node:22-bookworm-slim AS runtime
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

COPY --from=build /repo/apps/web/.next ./.next
COPY --from=build /repo/apps/web/public ./public
COPY --from=build /repo/apps/web/package.json ./package.json
COPY --from=build /repo/apps/web/next.config.mjs ./next.config.mjs
COPY --from=build /repo/node_modules ./node_modules

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD node -e "fetch('http://localhost:3000').then((r)=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["npx", "next", "start", "-p", "3000"]
