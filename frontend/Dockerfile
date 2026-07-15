# Build the SPA, then serve the static output from nginx.
#
# The built assets are plain files - no Node runtime in production, which keeps
# the image tiny and removes a whole class of server-side attack surface.

FROM node:20-alpine AS builder

WORKDIR /build

# Copy manifests first so `npm ci` is cached and only re-runs when deps change.
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
RUN npm run build


FROM nginx:1.27-alpine AS runtime

RUN rm -rf /usr/share/nginx/html/*
COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1

CMD ["nginx", "-g", "daemon off;"]
