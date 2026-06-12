FROM node:22-alpine AS base

WORKDIR /app/frontend

RUN apk add --no-cache libc6-compat


FROM base AS deps

COPY frontend/package.json frontend/package-lock.json frontend/tsconfig.base.json ./
COPY frontend/apps/store-owner-assistant/package.json ./apps/store-owner-assistant/
COPY frontend/packages/ui/package.json ./packages/ui/
COPY frontend/packages/api-client/package.json ./packages/api-client/

RUN npm ci


FROM base AS builder

COPY --from=deps /app/frontend/node_modules ./node_modules
COPY frontend/package.json frontend/package-lock.json frontend/tsconfig.base.json ./
COPY frontend/apps ./apps
COPY frontend/packages ./packages

ARG APP_WORKSPACE

RUN npm run build --workspace "${APP_WORKSPACE}"


FROM base AS runner

ENV NODE_ENV=production
ENV HOSTNAME=0.0.0.0

COPY --from=builder /app/frontend/apps/store-owner-assistant/.next/standalone ./
COPY --from=builder /app/frontend/apps/store-owner-assistant/.next/static ./apps/store-owner-assistant/.next/static

EXPOSE 3000

CMD ["node", "apps/store-owner-assistant/server.js"]