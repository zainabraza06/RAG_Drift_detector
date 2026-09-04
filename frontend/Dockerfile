# Frontend image: Vite build served by nginx, which also fronts the API.
#
#   docker build -f frontend/Dockerfile -t drift-frontend .

FROM node:22-alpine AS build

WORKDIR /app

# Lockfile-only install first, so editing a component does not re-resolve the
# dependency tree.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Type errors fail the build here rather than shipping a broken bundle: the
# build script runs `tsc --noEmit` before vite.
RUN npm run build


FROM nginx:1.27-alpine AS runtime

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD wget --quiet --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
