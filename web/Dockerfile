FROM node:24-slim AS deps

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

FROM deps AS dev

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

FROM deps AS build

COPY . .
# Set by the Release workflow and shown in the app footer.
ARG APP_VERSION=dev
ARG APP_COMMIT=unknown
RUN VITE_APP_VERSION=$APP_VERSION VITE_APP_COMMIT=$APP_COMMIT npm run build

FROM nginxinc/nginx-unprivileged:1.31-alpine AS prod

# Backend base URL that /api requests are proxied to; override at deploy time.
# nginx's resolver ignores DNS search domains, so use a fully qualified name in
# Kubernetes (for example http://api.<namespace>.svc.cluster.local:8000).
# THEME_TOGGLE (true/false) shows the light/dark mode toggle in the header.
ENV API_UPSTREAM=http://backend:8000 \
    THEME_TOGGLE=true \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
