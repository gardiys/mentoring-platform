FROM node:22-alpine@sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32

ENV COREPACK_HOME=/opt/corepack
WORKDIR /app
RUN corepack enable \
    && corepack prepare pnpm@11.21.0 --activate \
    && pnpm --version \
    && rm -rf /usr/local/lib/node_modules/npm \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx \
    && chown node:node /app
COPY --chown=node:node package.json pnpm-lock.yaml* pnpm-workspace.yaml ./
USER node
RUN pnpm install --frozen-lockfile=false
COPY --chown=node:node . .
EXPOSE 5173
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD wget -q -O /dev/null http://127.0.0.1:5173/ || exit 1
CMD ["pnpm", "dev"]
