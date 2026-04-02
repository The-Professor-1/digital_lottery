#!/usr/bin/env python3
"""
Probe https://transactioninfo.ethiotelecom.et/receipt/<id> from the server (e.g. EC2).

On success (HTTP 200), the **full HTML body** is written to stdout so you can redirect
to a file or pipe — that is proof the page was fetched end-to-end. Diagnostics (URL,
DNS, status, timing) go to stderr so they do not mix with the HTML.

Uses only the Python standard library (no pip install required).

Examples:
  python ethiotelecom_receipt_probe.py > receipt.html
  python ethiotelecom_receipt_probe.py -o receipt.html
  python ethiotelecom_receipt_probe.py DCQ18KZIKF 2>probe.log > receipt.html

Exit codes:
  0  HTTP 200 and non-empty body (HTML emitted unless --no-html)
  1  Network / DNS / TLS / timeout
  2  HTTP non-200
  3  HTTP 200 but empty body
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional, Tuple

DEFAULT_RECEIPT = "DCQ18KZIKF"
BASE = "https://transactioninfo.ethiotelecom.et/receipt/"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def build_url(receipt_or_url: str) -> str:
    s = receipt_or_url.strip()
    if s.startswith("http://") or s.startswith("https://"):
        return s
    return f"{BASE}{s}"


def fetch(url: str, timeout: float) -> Tuple[Optional[int], dict, bytes, Optional[BaseException]]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        method="GET",
    )
    meta: dict = {}
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            meta["final_url"] = resp.geturl()
            meta["status"] = resp.getcode()
            meta["content_type"] = resp.headers.get("Content-Type", "")
            body = resp.read()
        meta["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        return meta.get("status"), meta, body, None
    except urllib.error.HTTPError as e:
        meta["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        try:
            body = e.read()
        except Exception:
            body = b""
        meta["final_url"] = getattr(e, "url", url) or url
        meta["status"] = e.code
        meta["content_type"] = e.headers.get("Content-Type", "") if e.headers else ""
        return e.code, meta, body, None
    except Exception as e:
        meta["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        return None, meta, b"", e


def main() -> int:
    p = argparse.ArgumentParser(
        description="Fetch Ethio Telecom receipt HTML; full page on stdout, diagnostics on stderr."
    )
    p.add_argument(
        "receipt_or_url",
        nargs="?",
        default=DEFAULT_RECEIPT,
        help=f"Receipt id or full URL (default: {DEFAULT_RECEIPT})",
    )
    p.add_argument("--timeout", type=float, default=20.0, help="Socket timeout in seconds (default: 20)")
    p.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="Also write the HTML body to this file (in addition to stdout unless --no-html)",
    )
    p.add_argument(
        "--no-html",
        action="store_true",
        help="Do not write HTML to stdout (still use -o to save to a file on success)",
    )
    args = p.parse_args()
    url = build_url(args.receipt_or_url)

    log(f"URL: {url}")
    log(f"Timeout: {args.timeout}s")
    try:
        host = urllib.parse.urlparse(url).hostname
    except Exception:
        host = None
    if not host:
        log("ERROR: could not parse host from URL")
        return 1

    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addrs = sorted({x[4][0] for x in infos})
        log(f"DNS: {host} -> {addrs[:5]}{' ...' if len(addrs) > 5 else ''}")
    except socket.gaierror as e:
        log(f"DNS FAILED: {e}")
        return 1

    status, meta, body, err = fetch(url, args.timeout)
    elapsed = meta.get("elapsed_ms", "?")
    final_u = meta.get("final_url", url)
    ctype = meta.get("content_type", "")

    if err is not None:
        log(f"REQUEST FAILED after {elapsed} ms: {type(err).__name__}: {err}")
        return 1

    log(f"HTTP: {status}")
    log(f"Final URL: {final_u}")
    log(f"Content-Type: {ctype}")
    log(f"Body bytes: {len(body)}")
    log(f"Time: {elapsed} ms")

    if status is None:
        return 1

    if status != 200:
        log("--- response body (first 2000 chars, stderr) ---")
        log(body[:2000].decode("utf-8", errors="replace"))
        return 2

    if len(body) == 0:
        log("ERROR: HTTP 200 but empty body")
        return 3

    html = body.decode("utf-8", errors="replace")

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8", newline="") as f:
                f.write(html)
            log(f"Wrote HTML to: {args.output}")
        except OSError as e:
            log(f"ERROR writing --output file: {e}")
            return 1

    if not args.no_html:
        sys.stdout.write(html)
        if not html.endswith("\n"):
            sys.stdout.write("\n")

    log("OK: full HTML received (reachable). stdout = page unless --no-html.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
