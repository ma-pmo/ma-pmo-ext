# MA-PMO dashboard image (Next.js) — standalone multi-stage
FROM node:20-slim AS build
WORKDIR /app
# NEXT_PUBLIC_* is inlined at build time -> pass the browser-reachable API URL as a build-arg
ARG NEXT_PUBLIC_API_BASE=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM node:20-slim AS run
WORKDIR /app
ENV NODE_ENV=production PORT=3000
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
