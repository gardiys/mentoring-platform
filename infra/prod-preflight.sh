#!/bin/sh

set -eu

env_file=${1:-.env.production}
errors=0

fail() {
    printf 'ERROR: %s\n' "$1" >&2
    errors=$((errors + 1))
}

value_of() {
    awk -v wanted="$1" '
        /^[A-Za-z_][A-Za-z0-9_]*=/ {
            separator = index($0, "=")
            key = substr($0, 1, separator - 1)
            if (key != wanted) {
                next
            }
            value = substr($0, separator + 1)
            sub(/^[[:space:]]+/, "", value)
            sub(/[[:space:]]+$/, "", value)
            if (length(value) >= 2) {
                first = substr(value, 1, 1)
                last = substr(value, length(value), 1)
                if ((first == "\"" && last == "\"") || (first == "\047" && last == "\047")) {
                    value = substr(value, 2, length(value) - 2)
                }
            }
            result = value
        }
        END { print result }
    ' "$env_file"
}

require_value() {
    key=$1
    value=$(value_of "$key")
    if [ -z "$value" ]; then
        fail "$key must be set in $env_file"
    fi
}

require_min_length() {
    key=$1
    minimum=$2
    value=$(value_of "$key")
    if [ "${#value}" -lt "$minimum" ]; then
        fail "$key must contain at least $minimum characters"
    fi
}

require_https_if_set() {
    key=$1
    value=$(value_of "$key")
    if [ -n "$value" ]; then
        case "$value" in
            https://*) ;;
            *) fail "$key must use https:// in production" ;;
        esac
    fi
}

if [ ! -f "$env_file" ]; then
    printf 'ERROR: production environment file %s does not exist\n' "$env_file" >&2
    exit 1
fi

# The file contains credentials for every production integration.
chmod 600 "$env_file"

duplicate_keys=$(
    awk -F= '
        /^[A-Za-z_][A-Za-z0-9_]*=/ { count[$1]++ }
        END { for (key in count) if (count[key] > 1) print key }
    ' "$env_file" | sort
)
if [ -n "$duplicate_keys" ]; then
    fail "duplicate keys in $env_file: $(printf '%s' "$duplicate_keys" | tr '\n' ' ')"
fi

placeholder_keys=$(
    awk '
        /^[A-Za-z_][A-Za-z0-9_]*=/ {
            separator = index($0, "=")
            key = substr($0, 1, separator - 1)
            value = toupper(substr($0, separator + 1))
            if (value ~ /REPLACE_/ || value ~ /CHANGE[_-]?ME/) print key
        }
    ' "$env_file" | sort -u
)
if [ -n "$placeholder_keys" ]; then
    fail "placeholder values remain in $env_file: $(printf '%s' "$placeholder_keys" | tr '\n' ' ')"
fi

for key in \
    DOMAIN CADDY_EMAIL POSTGRES_PASSWORD DATABASE_URL REDIS_PASSWORD \
    TELEGRAM_BOT_TOKEN TELEGRAM_BOT_URL BOT_INTEGRATION_TOKEN \
    TELEGRAM_WEB_CLIENT_ID TELEGRAM_WEB_CLIENT_SECRET WEB_SESSION_SECRET \
    S3_BUCKET S3_ACCESS_KEY_ID S3_SECRET_ACCESS_KEY \
    TRANSCRIPTION_PROVIDER NEXARA_API_KEY \
    INTERVIEW_AI_PROVIDER OPENAI_API_KEY OPENAI_ANALYSIS_MODEL OPENAI_EXTRACTION_MODEL
do
    require_value "$key"
done

require_min_length POSTGRES_PASSWORD 24
require_min_length REDIS_PASSWORD 32
require_min_length BOT_INTEGRATION_TOKEN 32
require_min_length WEB_SESSION_SECRET 32

redis_password=$(value_of REDIS_PASSWORD)
case "$redis_password" in
    *[!A-Za-z0-9._~-]*)
        fail "REDIS_PASSWORD must be URL-safe (A-Z, a-z, 0-9, dot, underscore, tilde or dash)"
        ;;
esac

postgres_password=$(value_of POSTGRES_PASSWORD)
case "$postgres_password" in
    mentoring|postgres|password|admin|qwerty)
        fail "POSTGRES_PASSWORD uses a known development/default value"
        ;;
esac

database_url=$(value_of DATABASE_URL)
case "$database_url" in
    postgresql+asyncpg://*@postgres:5432/*) ;;
    *) fail "DATABASE_URL must use asyncpg and the internal postgres:5432 service" ;;
esac
case "$database_url" in
    *://mentoring:mentoring@*) fail "DATABASE_URL contains the development password" ;;
esac

domain=$(value_of DOMAIN)
case "$domain" in
    *://*|*/*|localhost|*.localhost|example.com|*.example.com|127.*|0.0.0.0)
        fail "DOMAIN must be a real public hostname without scheme or path"
        ;;
esac
if ! printf '%s' "$domain" | grep -Eq '^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$'; then
    fail "DOMAIN contains unsupported characters"
fi

caddy_email=$(value_of CADDY_EMAIL)
case "$caddy_email" in
    *@*.*) ;;
    *) fail "CADDY_EMAIL must be a valid operational email address" ;;
esac
case "$caddy_email" in
    *@example.com) fail "CADDY_EMAIL must not use example.com" ;;
esac

telegram_bot_url=$(value_of TELEGRAM_BOT_URL)
case "$telegram_bot_url" in
    https://t.me/*) ;;
    *) fail "TELEGRAM_BOT_URL must use https://t.me/" ;;
esac

for key in \
    S3_ENDPOINT_URL S3_PUBLIC_ENDPOINT_URL NEXARA_BASE_URL TOCHKA_API_BASE_URL
do
    require_https_if_set "$key"
done

transcription_provider=$(value_of TRANSCRIPTION_PROVIDER)
if [ "$transcription_provider" != "nexara" ]; then
    fail "TRANSCRIPTION_PROVIDER must be nexara in production"
fi

ai_provider=$(value_of INTERVIEW_AI_PROVIDER)
if [ "$ai_provider" != "openai" ]; then
    fail "INTERVIEW_AI_PROVIDER must be openai in production"
fi

if [ "$(value_of BOT_INTEGRATION_TOKEN)" = "$(value_of WEB_SESSION_SECRET)" ]; then
    fail "BOT_INTEGRATION_TOKEN and WEB_SESSION_SECRET must be different"
fi

case "$(value_of DEV_AUTH_ENABLED)" in
    true|TRUE|1|yes|YES) fail "DEV_AUTH_ENABLED must not be enabled in production" ;;
esac
case "$(value_of APP_DEBUG)" in
    true|TRUE|1|yes|YES) fail "APP_DEBUG must not be enabled in production" ;;
esac
app_env=$(value_of APP_ENV)
if [ -n "$app_env" ] && [ "$app_env" != "production" ]; then
    fail "APP_ENV must be production when it is present in $env_file"
fi

if [ "$errors" -ne 0 ]; then
    printf 'Production preflight failed with %s error(s).\n' "$errors" >&2
    exit 1
fi

printf 'Production preflight passed; %s permissions are 0600.\n' "$env_file"
