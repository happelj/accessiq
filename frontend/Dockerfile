FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine

ARG ACCESSIQ_VERSION=0.1.0
ARG ACCESSIQ_GIT_SHA=unknown
ARG ACCESSIQ_GIT_TAG=
ARG ACCESSIQ_BUILD_TIMESTAMP=

LABEL org.opencontainers.image.title="AccessIQ Frontend"
LABEL org.opencontainers.image.version="${ACCESSIQ_VERSION}"
LABEL org.opencontainers.image.revision="${ACCESSIQ_GIT_SHA}"
LABEL org.opencontainers.image.ref.name="${ACCESSIQ_GIT_TAG}"
LABEL org.opencontainers.image.created="${ACCESSIQ_BUILD_TIMESTAMP}"

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
