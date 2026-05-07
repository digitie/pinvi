FROM node:22-bookworm-slim AS deps

WORKDIR /app

COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json

RUN npm ci

FROM deps AS builder

ARG NEXT_PUBLIC_TRIPMATE_API_URL=http://127.0.0.1:18082
ENV NEXT_PUBLIC_TRIPMATE_API_URL=${NEXT_PUBLIC_TRIPMATE_API_URL}

COPY apps/web ./apps/web

WORKDIR /app/apps/web

RUN npm run build

FROM node:22-bookworm-slim AS runtime

ENV NODE_ENV=production

WORKDIR /app

COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json

RUN npm ci --omit=dev \
    && npm cache clean --force

COPY --from=builder /app/apps/web/.next ./apps/web/.next
COPY --from=builder /app/apps/web/next.config.ts ./apps/web/next.config.ts

WORKDIR /app/apps/web

EXPOSE 3000

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
