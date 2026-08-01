from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

AUTHORIZATION_ENDPOINT = "https://oauth.telegram.org/auth"
TOKEN_ENDPOINT = "https://oauth.telegram.org/token"
JWKS_ENDPOINT = "https://oauth.telegram.org/.well-known/jwks.json"
ISSUER = "https://oauth.telegram.org"
SUPPORTED_ALGORITHMS = {"RS256", "ES256"}
CONNECT_RETRIES = 2
CONNECT_TIMEOUT_SECONDS = 5.0
REQUEST_TIMEOUT_SECONDS = 15.0


class TelegramOidcError(RuntimeError):
    pass


@dataclass(frozen=True)
class TelegramIdentity:
    telegram_id: int
    first_name: str
    last_name: str | None
    telegram_username: str | None = None


def _telegram_http_client(proxy_url: str | None = None) -> httpx.AsyncClient:
    # Telegram publishes both A and AAAA records. Binding the direct transport to
    # the IPv4 wildcard avoids waiting on a broken IPv6 route inside Docker/VPS.
    transport = httpx.AsyncHTTPTransport(
        retries=CONNECT_RETRIES,
        local_address=None if proxy_url else "0.0.0.0",
        proxy=proxy_url,
    )
    timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS)
    return httpx.AsyncClient(transport=transport, timeout=timeout)


def authorization_url(*, client_id: str, redirect_uri: str, state: str, challenge: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid profile",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{AUTHORIZATION_ENDPOINT}?{query}"


async def exchange_code_for_identity(
    *,
    code: str,
    verifier: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    proxy_url: str | None = None,
) -> TelegramIdentity:
    try:
        async with _telegram_http_client(proxy_url) as client:
            token_response = await client.post(
                TOKEN_ENDPOINT,
                auth=(client_id, client_secret),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "client_id": client_id,
                    "code_verifier": verifier,
                },
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
            id_token = token_payload.get("id_token")
            if not isinstance(id_token, str):
                raise TelegramOidcError("Telegram did not return an ID token")

            jwks_response = await client.get(JWKS_ENDPOINT)
            jwks_response.raise_for_status()
            jwks = jwks_response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise TelegramOidcError("Telegram OIDC request failed") from exc

    claims = _decode_id_token(id_token, jwks, client_id)
    return _identity_from_claims(claims)


def _decode_id_token(id_token: str, jwks: dict[str, Any], client_id: str) -> dict[str, Any]:
    try:
        header = jwt.get_unverified_header(id_token)
        algorithm = header.get("alg")
        key_id = header.get("kid")
        if algorithm not in SUPPORTED_ALGORITHMS or not isinstance(key_id, str):
            raise TelegramOidcError("Telegram ID token uses an unsupported signing key")
        key_set = jwt.PyJWKSet.from_dict(jwks)
        signing_key = next((key for key in key_set.keys if key.key_id == key_id), None)
        if signing_key is None or signing_key.algorithm_name != algorithm:
            raise TelegramOidcError("Telegram ID token signing key was not found")
        claims = jwt.decode(
            id_token,
            key=signing_key.key,
            algorithms=[algorithm],
            audience=client_id,
            issuer=ISSUER,
            options={"require": ["sub", "iat", "exp"]},
        )
    except jwt.PyJWTError as exc:
        raise TelegramOidcError("Telegram ID token is invalid") from exc
    return claims


def _identity_from_claims(claims: dict[str, Any]) -> TelegramIdentity:
    raw_telegram_id = claims.get("id")
    if isinstance(raw_telegram_id, str) and raw_telegram_id.isascii() and raw_telegram_id.isdigit():
        telegram_id = int(raw_telegram_id)
    elif isinstance(raw_telegram_id, int) and not isinstance(raw_telegram_id, bool):
        telegram_id = raw_telegram_id
    else:
        telegram_id = 0
    if telegram_id <= 0:
        raise TelegramOidcError("Telegram profile does not contain a valid user id")

    given_name = claims.get("given_name")
    family_name = claims.get("family_name")
    display_name = claims.get("name")
    if not isinstance(given_name, str) or not given_name.strip():
        if not isinstance(display_name, str) or not display_name.strip():
            raise TelegramOidcError("Telegram profile does not contain a name")
        given_name = display_name.strip()
    last_name = (
        family_name.strip() if isinstance(family_name, str) and family_name.strip() else None
    )
    raw_username = claims.get("preferred_username", claims.get("username"))
    telegram_username = (
        raw_username.strip().lstrip("@")[:64]
        if isinstance(raw_username, str) and raw_username.strip().lstrip("@")
        else None
    )
    return TelegramIdentity(
        telegram_id=telegram_id,
        first_name=given_name.strip(),
        last_name=last_name,
        telegram_username=telegram_username,
    )
