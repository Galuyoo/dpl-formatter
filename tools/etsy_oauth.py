from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import string
import urllib.parse
from typing import Any

import requests


AUTH_URL = "https://www.etsy.com/oauth/connect"
TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
DEFAULT_SCOPES = "transactions_r"


def generate_code_verifier(length: int = 64) -> str:
    alphabet = string.ascii_letters + string.digits + "-._~"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


def build_authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    scope: str = DEFAULT_SCOPES,
    state: str | None = None,
    code_verifier: str | None = None,
) -> dict[str, str]:
    if not client_id:
        raise ValueError("client_id is required")

    if not redirect_uri:
        raise ValueError("redirect_uri is required")

    state = state or secrets.token_urlsafe(24)
    code_verifier = code_verifier or generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)

    params = {
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "client_id": client_id,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    return {
        "authorization_url": AUTH_URL + "?" + urllib.parse.urlencode(params),
        "state": state,
        "code_verifier": code_verifier,
        "scope": scope,
        "redirect_uri": redirect_uri,
    }


def exchange_code_for_token(
    *,
    client_id: str,
    redirect_uri: str,
    code: str,
    code_verifier: str,
    timeout: int = 30,
) -> dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code": code,
        "code_verifier": code_verifier,
    }

    response = requests.post(TOKEN_URL, data=data, timeout=timeout)

    if response.status_code >= 400:
        raise RuntimeError(f"Etsy token exchange failed {response.status_code}: {response.text}")

    return response.json()


def refresh_access_token(
    *,
    client_id: str,
    refresh_token: str,
    timeout: int = 30,
) -> dict[str, Any]:
    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }

    response = requests.post(TOKEN_URL, data=data, timeout=timeout)

    if response.status_code >= 400:
        raise RuntimeError(f"Etsy token refresh failed {response.status_code}: {response.text}")

    return response.json()


def print_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Etsy OAuth helper for DPL Formatter.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_parser = subparsers.add_parser("auth-url", help="Generate Etsy authorization URL.")
    auth_parser.add_argument("--client-id", required=True, help="Etsy API keystring / client ID.")
    auth_parser.add_argument("--redirect-uri", required=True, help="Redirect URI configured in your Etsy app.")
    auth_parser.add_argument("--scope", default=DEFAULT_SCOPES, help="Space-separated Etsy OAuth scopes.")

    exchange_parser = subparsers.add_parser("exchange", help="Exchange authorization code for tokens.")
    exchange_parser.add_argument("--client-id", required=True, help="Etsy API keystring / client ID.")
    exchange_parser.add_argument("--redirect-uri", required=True, help="Same redirect URI used for auth-url.")
    exchange_parser.add_argument("--code", required=True, help="Authorization code from Etsy redirect URL.")
    exchange_parser.add_argument("--code-verifier", required=True, help="Code verifier printed by auth-url command.")

    refresh_parser = subparsers.add_parser("refresh", help="Refresh Etsy access token.")
    refresh_parser.add_argument("--client-id", required=True, help="Etsy API keystring / client ID.")
    refresh_parser.add_argument("--refresh-token", required=True, help="Etsy refresh token.")

    args = parser.parse_args()

    if args.command == "auth-url":
        result = build_authorization_url(
            client_id=args.client_id,
            redirect_uri=args.redirect_uri,
            scope=args.scope,
        )
        print_json(result)
        return

    if args.command == "exchange":
        result = exchange_code_for_token(
            client_id=args.client_id,
            redirect_uri=args.redirect_uri,
            code=args.code,
            code_verifier=args.code_verifier,
        )
        print_json(result)
        return

    if args.command == "refresh":
        result = refresh_access_token(
            client_id=args.client_id,
            refresh_token=args.refresh_token,
        )
        print_json(result)
        return


if __name__ == "__main__":
    main()
