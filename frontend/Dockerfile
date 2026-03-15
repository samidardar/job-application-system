# ── Stage 1: Build ───────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps separately so layer is cached when only source changes
COPY package.json package-lock.json* ./
RUN npm ci --frozen-lockfile

COPY . .

# Build production bundle (optimized, no hot-reload, no webpack watchers)
RUN npm run build

# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production

# Only copy what Next.js needs to run in production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

# Run the production server (not `npm run dev`)
CMD ["node", "server.js"]
