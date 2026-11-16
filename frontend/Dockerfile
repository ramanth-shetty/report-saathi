# ==============================================================================
# ReportSaathi Frontend Service (Vite + TypeScript Single-Page Application)
# Multi-stage build: Node.js 20 Alpine builder -> Nginx 1.27 Alpine runtime
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build the static web client assets
# ------------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Copy dependency manifests first to leverage Docker layer caching
COPY frontend/package.json frontend/package-lock.json ./frontend/

WORKDIR /app/frontend
RUN npm ci --prefer-offline --no-audit

# Copy shared contract definitions and frontend source code
WORKDIR /app
COPY shared/ ./shared/
COPY frontend/ ./frontend/

WORKDIR /app/frontend

# Optional build argument to bake API endpoint into static build
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL

# Build production bundle (runs "tsc && vite build" -> dist/)
RUN npm run build

# ------------------------------------------------------------------------------
# Stage 2: Ultralightweight Nginx Alpine web server (~25MB)
# ------------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runner

# Remove default nginx welcome page
RUN rm -rf /usr/share/nginx/html/*

# Copy custom SPA Nginx configuration with gzip and security headers
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# Copy compiled static assets from builder stage
COPY --from=builder /app/frontend/dist /usr/share/nginx/html

EXPOSE 80

# Health check probing Nginx /health endpoint
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -qO- http://localhost:80/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
