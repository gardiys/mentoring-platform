FROM postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777

# PGDATA ownership is prepared by the tightly scoped postgres-permissions
# service. The main container never starts as root, so the upstream gosu
# helper is both unnecessary and removed from the runtime filesystem.
RUN rm -f /usr/local/bin/gosu

USER postgres

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
    CMD pg_isready -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-postgres}" || exit 1
