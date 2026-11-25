"""Kleine HTTP-Helfer auf Basis der Standardbibliothek."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from today_cli import __version__

USER_AGENT = f"today-cli/{__version__}"
DEFAULT_TIMEOUT = 6
MAX_BYTES = 10_000_000  # Schutz vor riesigen Antworten (z. B. falscher iCal-Link)


class FetchError(Exception):
    """Netzwerk- oder HTTP-Fehler mit lesbarer Meldung."""


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Folgt Weiterleitungen, schickt den Authorization-Header aber nie an einen anderen Host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_request = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_request is not None:
            old_host = urllib.parse.urlparse(req.full_url).hostname
            new_host = urllib.parse.urlparse(newurl).hostname
            if old_host != new_host:
                new_request.remove_header("Authorization")
        return new_request


_OPENER = urllib.request.build_opener(_SafeRedirectHandler)


def safe_host(url: str) -> str:
    # Nur den Hostnamen zeigen: keine Zugangsdaten, keine Pfade, keine Tokens
    return urllib.parse.urlparse(url).hostname or "?"


def get_text(url: str, headers: dict[str, str] | None = None, timeout: float = DEFAULT_TIMEOUT) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with _OPENER.open(request, timeout=timeout) as response:
            body = response.read(MAX_BYTES + 1)
            charset = response.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as err:
        raise FetchError(f"HTTP {err.code} von {safe_host(url)}") from err
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        reason = getattr(err, "reason", None) or type(err).__name__
        raise FetchError(f"{safe_host(url)} nicht erreichbar ({reason})") from err
    if len(body) > MAX_BYTES:
        raise FetchError(f"Antwort von {safe_host(url)} ist zu groß")
    return body.decode(charset, errors="replace")


def get_json(url: str, headers: dict[str, str] | None = None, timeout: float = DEFAULT_TIMEOUT):
    text = get_text(url, headers=headers, timeout=timeout)
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise FetchError(f"Ungültige Antwort von {safe_host(url)}") from err
