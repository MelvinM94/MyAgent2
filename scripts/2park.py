"""Integration with the 2park parking API."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict

import requests
from requests import Session


BASE_URL = "https://mijn.2park.nl"
HEADERS = {
    "Accept-Language": "nl-NL",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}

_session: Session | None = None


def login() -> Session:
    """Log in to 2park and return an authenticated session.

    The credentials are read from the ``2PARK_USER`` and ``2PARK_PASS``
    environment variables.  A pre-request is performed to establish the
    necessary cookies before the CSRF-protected login flow.
    """
    global _session
    if _session is not None:
        return _session

    username = os.environ.get("2PARK_USER")
    password = os.environ.get("2PARK_PASS")
    if not username or not password:
        raise RuntimeError("2PARK_USER and 2PARK_PASS must be set in the environment")

    sess = requests.Session()
    sess.headers.update(HEADERS)

    # Pre-request to obtain initial cookies
    sess.get(f"{BASE_URL}/parking-actions-form/create")

    # Fetch login page to grab CSRF token
    resp = sess.get(f"{BASE_URL}/login")
    match = re.search(r'name="_csrf" value="([^"]*)"', resp.text)
    if not match:
        raise RuntimeError("Could not find CSRF token on login page")
    csrf = match.group(1)

    data = {"username": username, "password": password, "_csrf": csrf}

    login_resp = sess.post(f"{BASE_URL}/login", data=data)
    if login_resp.status_code >= 400:
        login_resp = sess.post(f"{BASE_URL}/j_spring_security_check", data=data)

    if "JSESSIONID" not in sess.cookies:
        raise RuntimeError("Login failed: JSESSIONID cookie missing")

    _session = sess
    return sess


def _build_payload(params: list[dict[str, str]]) -> Dict[str, Any]:
    return {"action": {"atn_parameters": params}}


def start_parking() -> str:
    """Start a parking session for five hours."""
    sess = login()
    start = datetime.now()
    end = start + timedelta(hours=5)
    fmt = "%d-%m-%Y %H:%M:%S"
    start_str = start.strftime(fmt)
    end_str = end.strftime(fmt)

    params = [
        {"prr_label": "MBR_IDENT", "prr_value": "S325VG"},
        {"prr_label": "TIMESTART", "prr_value": start_str},
        {"prr_label": "TIMEEND", "prr_value": end_str},
        {"prr_label": "LOCATION", "prr_value": "BDA1305"},
    ]

    payload = json.dumps(_build_payload(params))
    resp = sess.post(
        f"{BASE_URL}/gsmpark-app-www/json/start_action.json",
        data={"action": payload},
    )
    if resp.ok:
        return f"Parkeren gestart van {start_str} tot {end_str}."
    return f"Fout {resp.status_code}: {resp.text}"


def stop_parking(action_id: str | None = None) -> str:
    """Stop a running parking session.

    Args:
        action_id: Optional action identifier. If provided, it will be used
            instead of the MBR_IDENT/TIMEEND/LOCATION combination.
    """
    sess = login()
    fmt = "%d-%m-%Y %H:%M:%S"
    now = datetime.now().strftime(fmt)
    params: list[dict[str, str]]
    if action_id:
        params = [{"prr_label": "ACTION_ID", "prr_value": action_id}]
    else:
        params = [
            {"prr_label": "MBR_IDENT", "prr_value": "S325VG"},
            {"prr_label": "TIMEEND", "prr_value": now},
            {"prr_label": "LOCATION", "prr_value": "BDA1305"},
        ]
    payload = json.dumps(_build_payload(params))
    resp = sess.post(
        f"{BASE_URL}/gsmpark-app-www/json/stop_action.json",
        data={"action": payload},
    )
    if resp.ok:
        return "Parkeren gestopt."
    return f"Fout {resp.status_code}: {resp.text}"


# Register as chat triggers for gptme
chattriggers = {
    "Start parkeren": start_parking,
    "Stop parkeren": stop_parking,
}
