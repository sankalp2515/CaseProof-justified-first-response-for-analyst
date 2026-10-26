# Frontend service: builds the React application and serves it with nginx.
#   FRONTEND_PROFILE=local (default): Compose; API paths are proxied to the `api` service.
#   FRONTEND_PROFILE=cloud: Cloud Run behind the HTTPS load balancer, which routes
#     /v1/* and /health to the API. STAFF_ACCESS=google signs staff in with Google
#     (VITE_GOOGLE_CLIENT_ID); STAFF_ACCESS=practice uses labelled demo personas that
#     the server confines to each visitor's own practice session.
ARG FRONTEND_PROFILE=local

FROM node:24-alpine@sha256:44fce696f38ba8c987c4db89954051000bbd05ffd8d8659ba15ed4a8602e937f AS build
ARG FRONTEND_PROFILE
ARG STAFF_ACCESS=google
ARG VITE_GOOGLE_CLIENT_ID=
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . ./
RUN test "$FRONTEND_PROFILE" = local || test "$STAFF_ACCESS" = practice \
    || test -n "$VITE_GOOGLE_CLIENT_ID" \
    || { echo "cloud Google sign-in requires VITE_GOOGLE_CLIENT_ID" >&2; exit 1; }
ENV VITE_AUTH_PROFILE=${FRONTEND_PROFILE} VITE_STAFF_ACCESS=${STAFF_ACCESS} \
    VITE_GOOGLE_CLIENT_ID=${VITE_GOOGLE_CLIENT_ID}
RUN npm run build

FROM nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236
ARG FRONTEND_PROFILE
# The image entrypoint renders templates with envsubst (only defined variables).
ENV CASEPROOF_API_UPSTREAM=api:8000
RUN rm /etc/nginx/conf.d/default.conf
COPY docker/${FRONTEND_PROFILE}.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /web/dist /usr/share/nginx/html/app
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=4s --retries=6 \
    CMD wget -qO- http://127.0.0.1:8080/app/ >/dev/null || exit 1
