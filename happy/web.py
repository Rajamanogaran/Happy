"""Read-only public web tools. No local-network browsing or remote execution."""

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS


def validate_url(url):
    p = urlsplit(url)
    if (
        p.scheme not in ("http", "https")
        or not p.hostname
        or p.username
        or p.password
        or p.port not in (None, 80, 443)
    ):
        raise ValueError("Use a public HTTP or HTTPS URL on a standard port.")
    addresses = socket.getaddrinfo(
        p.hostname,
        p.port or (443 if p.scheme == "https" else 80),
        type=socket.SOCK_STREAM,
    )
    if not addresses or any(
        not ipaddress.ip_address(a[4][0]).is_global for a in addresses
    ):
        raise ValueError("Private and local network addresses are not allowed.")
    return addresses[0][4][0]


def browse(url):
    # Validate every redirect, disable environment proxies and cap downloaded data.
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
        for _ in range(5):
            address = validate_url(url)
            original = httpx.URL(url)
            # Pin the validated IP to prevent DNS rebinding between validation
            # and connection, while retaining the hostname for TLS and HTTP.
            pinned = original.copy_with(host=address)
            headers = {
                "User-Agent": "HappyResearch/1.0",
                "Host": original.netloc.decode(),
            }
            with client.stream(
                "GET",
                pinned,
                headers=headers,
                extensions={"sni_hostname": original.host},
            ) as response:
                if response.is_redirect:
                    url = str(original.join(response.headers["location"]))
                    continue
                response.raise_for_status()
                if not any(
                    t in response.headers.get("content-type", "")
                    for t in ("text/", "application/xhtml")
                ):
                    raise ValueError("Only text and HTML pages are supported.")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 2_000_000:
                        raise ValueError("Page exceeds the 2 MB reading limit.")
                soup = BeautifulSoup(bytes(raw), "html.parser")
                title = soup.title.get_text(" ", strip=True) if soup.title else url
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                return {
                    "title": title,
                    "url": url,
                    "content": soup.get_text(" ", strip=True)[:18000],
                }
        raise ValueError("Too many redirects.")


def search(query):
    results = DDGS(timeout=12).text(query, max_results=5)
    return [
        {"title": r["title"], "url": r["href"], "content": r.get("body", "")}
        for r in results
        if r.get("href", "").startswith(("https://", "http://"))
    ]
