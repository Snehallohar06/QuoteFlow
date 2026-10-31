# QuoteFlow frontend — production image.
#
# Builds the static bundle, then serves it from nginx. The API is reached
# through nginx's /api proxy, so the browser stays same-origin and the bundle
# needs no absolute API URL baked in.

# ---- build stage ----------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /build

# Copy the manifests first so the dependency layer caches independently of
# source changes.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Left blank so the bundle uses relative /api URLs and nginx proxies them.
# Override at build time only if the API lives on another origin.
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ---- runtime stage --------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
