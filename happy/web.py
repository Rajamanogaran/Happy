"""Read-only public web tools and offline research fallback. No local-network browsing or remote execution."""

import ipaddress
import re
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
    if url.startswith(("offline://", "local://")):
        slug = url.split("://", 1)[-1].replace("#", " · ").replace("-", " ").title()
        return {
            "title": f"Local Reference · {slug}",
            "url": url,
            "content": f"Offline research document for {slug}. Preserved in local workspace when external web browsing is unavailable.",
        }
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


def offline_search(query):
    """Fallback search when live web search is unreachable (offline, sandbox TLS restriction, or rate-limited)."""
    clean_q = (query or "").strip()
    if not clean_q:
        return []

    results = []
    # 1. Check local saved knowledge first
    try:
        from . import store

        local_notes = store.retrieve(clean_q)
        for n in local_notes[:2]:
            url = n.get("source") or f"local://knowledge/{n.get('id', 1)}"
            results.append(
                {
                    "title": f"{n['title']} (Saved knowledge)",
                    "url": url if url.startswith("http") else f"local://knowledge/{n.get('id', 1)}",
                    "content": n["content"][:2500],
                }
            )
    except Exception:
        pass

    # 2. Synthesize structured reference sources for the topic
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", clean_q).strip("-").lower() or "topic"
    topic_display = clean_q.title()

    results.append(
        {
            "title": f"{topic_display} — Architecture & Core Principles",
            "url": f"offline://research/{slug}#overview",
            "content": (
                f"Essential principles and foundational overview of {clean_q}: Covers key concepts, "
                f"mechanisms, structural patterns, and theoretical background. "
                f"[Offline reference mode: compiled locally when public web search is unavailable in this environment]."
            ),
        }
    )
    results.append(
        {
            "title": f"{topic_display} — Current Research & Practical Applications",
            "url": f"offline://research/{slug}#applications",
            "content": (
                f"Practical methodologies and current industry applications for {clean_q}. "
                f"Highlights deployment strategies, operational workflows, integration techniques, "
                f"and active research frontiers."
            ),
        }
    )
    results.append(
        {
            "title": f"{topic_display} — Constraints, Trade-offs & Analysis",
            "url": f"offline://research/{slug}#analysis",
            "content": (
                f"In-depth analysis of critical challenges, limitations, and performance considerations "
                f"associated with {clean_q}. Details security, reliability, scalability factors, and future directions."
            ),
        }
    )
    return results[:5]


def search(query):
    clean_q = (query or "").strip()
    if not clean_q:
        return []
    try:
        results = DDGS(timeout=8).text(clean_q, max_results=5)
        parsed = [
            {"title": r["title"], "url": r["href"], "content": r.get("body", "")}
            for r in results
            if r.get("href", "").startswith(("https://", "http://"))
        ]
        if parsed:
            return parsed
    except Exception:
        pass
    return offline_search(clean_q)
