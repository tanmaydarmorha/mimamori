# Build context is the repo root: docker build -f services/web-ui/Dockerfile .
FROM node:24-alpine AS build
WORKDIR /app/services/web-ui
COPY services/web-ui/package.json services/web-ui/package-lock.json ./
RUN npm ci
COPY services/web-ui/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/services/web-ui/dist /usr/share/nginx/html
COPY services/web-ui/nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY services/web-ui/nginx/mimamori-proxy.conf /etc/nginx/mimamori-proxy.conf
# Defaults for a local `docker run`; compose / Cloud Run override them. URLs without a trailing slash.
ENV PORT=8080 \
    MIMAMORI_ENV=local \
    MIMAMORI_SPEECH=typed \
    CORE_BANK_URL=http://core-bank-mock:8081 \
    SCORING_URL=http://scoring:8082 \
    CASE_SVC_URL=http://case-svc:8083 \
    CONVERSATION_SVC_URL=http://conversation-svc:8084
EXPOSE 8080
