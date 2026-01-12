# =============================================================================
# Frontend Dockerfile for Next.js Legal Lease RAG Dashboard
# =============================================================================
# Multi-stage build optimized for Next.js production:
#   Stage 1: Install dependencies
#   Stage 2: Build the Next.js app
#   Stage 3: Minimal runtime with only production files
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Dependencies - Install node_modules
# -----------------------------------------------------------------------------
FROM node:20-alpine AS deps

# Alpine Linux is tiny (~5MB) - great for keeping images small
WORKDIR /app

# Copy package files for dependency installation
COPY package.json package-lock.json* ./

# Install dependencies
# --frozen-lockfile: Fail if lockfile is outdated (reproducible builds)
RUN npm ci --frozen-lockfile

# -----------------------------------------------------------------------------
# Stage 2: Builder - Compile Next.js
# -----------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules

# Copy source code
COPY . .

# Set environment for build
# NEXT_TELEMETRY_DISABLED: Opt out of Next.js telemetry
ENV NEXT_TELEMETRY_DISABLED=1

# Build the production app
# This creates the optimized .next folder
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 3: Runner - Production runtime
# -----------------------------------------------------------------------------
FROM node:20-alpine AS runner

WORKDIR /app

# Set to production mode
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

# Create non-root user for security
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy only what's needed to run (not source code)
# This keeps the final image small
COPY --from=builder /app/public ./public

# Next.js 13+ outputs to .next/standalone when configured
# But we'll use the standard approach for compatibility
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

# Switch to non-root user
USER nextjs

# Expose port 3000 (Next.js default)
EXPOSE 3000

# Set the port via environment variable
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Start Next.js in production mode
CMD ["npm", "run", "start"]
