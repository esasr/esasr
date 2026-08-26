FROM node:24-alpine AS builder

WORKDIR /app

COPY esasr-web/package.json esasr-web/package-lock.json ./
RUN npm ci

COPY esasr-web ./

ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

FROM nginx:1.27-alpine

COPY esasr-web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --retries=10 \
  CMD wget -q -O /dev/null http://127.0.0.1/health || exit 1
