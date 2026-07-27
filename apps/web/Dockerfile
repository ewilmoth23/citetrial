FROM node:22-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:stable-alpine@sha256:97d490c12ba55b4946b01546d1c3ed324e8d41ab1c9fcb2a616aa470620e5b46
RUN addgroup -g 10001 -S citetrail && adduser -S -D -H -u 10001 -h /var/cache/nginx -s /sbin/nologin -G citetrail citetrail
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx-main.conf /etc/nginx/nginx.conf
RUN chown -R citetrail:citetrail /var/cache/nginx /var/run /usr/share/nginx/html && touch /var/run/nginx.pid && chown citetrail:citetrail /var/run/nginx.pid
USER citetrail
ENV NGINX_ENTRYPOINT_QUIET_LOGS=1
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
CMD ["nginx", "-g", "daemon off;"]
