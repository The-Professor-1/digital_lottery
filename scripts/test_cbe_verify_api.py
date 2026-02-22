#!/usr/bin/env python3
"""
Standalone script to test CBE verify API from EC2 (or any server).
Run: python test_cbe_verify_api.py
  or: python test_cbe_verify_api.py --reference FT26045VN81B --suffix 24627387

Flow:
  1. Try request WITHOUT fallback (normal).
  2. If that fails, try WITH skipPrimaryVerification=True (fallback proxy).
Logs every step and error type in detail so you can share output.
"""
import argparse
import json
import logging
import sys

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)

# Defaults from your verifier test
DEFAULT_API_KEY = "Y21qZHZ4am9jMDAwcWxiMHZrd3NvM3podi0xNzY2MjEwMjU0NTk5LXd0cjVsZjl2OTNk"
DEFAULT_REFERENCE = "FT26045VN81B"
DEFAULT_SUFFIX = "24627387"
URL = "https://verifyapi.leulzenebe.pro/verify-cbe"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return "***"
    return key[:4] + "..." + key[-4:]


def call_cbe_api(api_key: str, reference: str, account_suffix: str, use_fallback: bool) -> dict:
    """Returns dict with: success, status_code, reason, body, error_type, error_message."""
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
    }
    payload = {"reference": reference, "accountSuffix": account_suffix}
    if use_fallback:
        payload["skipPrimaryVerification"] = True

    result = {
        "success": False,
        "status_code": None,
        "reason": None,
        "body": None,
        "body_raw": None,
        "error_type": None,
        "error_message": None,
    }

    log.info("  Request URL: %s", URL)
    log.info("  Request payload: %s", json.dumps(payload, indent=2))
    log.info("  x-api-key: %s", mask_key(api_key))

    try:
        resp = requests.post(URL, json=payload, headers=headers, timeout=20)
    except requests.exceptions.ConnectTimeout as e:
        result["error_type"] = "TIMEOUT"
        result["error_message"] = str(e)
        log.error("[ERROR_TYPE] TIMEOUT - Connection timed out: %s", e)
        return result
    except requests.exceptions.ConnectionError as e:
        result["error_type"] = "CONNECTION_ERROR"
        result["error_message"] = str(e)
        log.error("[ERROR_TYPE] CONNECTION_ERROR - Could not reach server: %s", e)
        return result
    except requests.RequestException as e:
        result["error_type"] = "REQUEST_EXCEPTION"
        result["error_message"] = str(e)
        log.error("[ERROR_TYPE] REQUEST_EXCEPTION: %s", e)
        return result

    result["status_code"] = resp.status_code
    result["reason"] = resp.reason
    result["body_raw"] = resp.text

    log.info("  Response status: %s %s", resp.status_code, resp.reason)
    log.info("  Response Content-Type: %s", resp.headers.get("Content-Type", ""))

    try:
        if resp.headers.get("Content-Type", "").startswith("application/json"):
            result["body"] = resp.json()
            log.info("  Response body (JSON): %s", json.dumps(result["body"], indent=2, default=str))
        else:
            log.warning("  Response body (non-JSON): %s", resp.text[:500])
    except Exception as e:
        log.warning("  Response body parse error: %s. Raw: %s", e, resp.text[:300])

    err_msg_from_body = None
    if isinstance(result["body"], dict):
        err_msg_from_body = result["body"].get("error") or result["body"].get("message")

    if not resp.ok:
        result["error_message"] = err_msg_from_body or resp.reason
        if 500 <= resp.status_code < 600:
            result["error_type"] = "HTTP_5XX"
            log.error("[ERROR_TYPE] HTTP_5XX - Server error. message=%s", result["error_message"])
        else:
            result["error_type"] = "HTTP_4XX"
            log.error("[ERROR_TYPE] HTTP_4XX - Client/API error. message=%s", result["error_message"])
        return result

    if isinstance(result["body"], dict) and result["body"].get("success") is True:
        result["success"] = True
        result["error_type"] = "SUCCESS"
        log.info("[ERROR_TYPE] SUCCESS - Verification passed.")
        return result

    result["error_type"] = "SUCCESS_FALSE"
    result["error_message"] = err_msg_from_body if err_msg_from_body else "Verification failed"
    log.warning("[ERROR_TYPE] SUCCESS_FALSE - API returned success=false. message=%s", result["error_message"])
    return result


def main():
    parser = argparse.ArgumentParser(description="Test CBE verify API (normal then fallback)")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help="Verify API key")
    parser.add_argument("--reference", default=DEFAULT_REFERENCE, help="CBE reference (e.g. FT26045VN81B)")
    parser.add_argument("--suffix", default=DEFAULT_SUFFIX, help="CBE account suffix 8 digits (e.g. 24627387)")
    args = parser.parse_args()

    api_key = (args.api_key or "").strip()
    reference = (args.reference or "").strip()
    suffix = (args.suffix or "").strip()
    if not api_key or not reference or not suffix:
        log.error("Missing api_key, reference or suffix")
        sys.exit(1)

    log.info("========== CBE Verify API Test ==========")
    log.info("Reference: %s", reference)
    log.info("Suffix: %s", suffix)
    log.info("API key: %s", mask_key(api_key))
    log.info("")

    # Attempt 1: normal (no fallback)
    log.info("---------- Attempt 1: NORMAL (no fallback proxy) ----------")
    r1 = call_cbe_api(api_key, reference, suffix, use_fallback=False)
    log.info("")

    if r1["success"]:
        log.info("Result: SUCCESS on first attempt (normal). No need to try fallback.")
        sys.exit(0)

    # Attempt 2: with fallback
    log.info("---------- Attempt 2: WITH FALLBACK (skipPrimaryVerification=true) ----------")
    r2 = call_cbe_api(api_key, reference, suffix, use_fallback=True)
    log.info("")

    if r2["success"]:
        log.info("Result: SUCCESS only with fallback proxy. Use fallback when server is outside Ethiopia.")
        sys.exit(0)

    log.info("Result: BOTH attempts failed.")
    log.info("  Attempt 1 error_type: %s  message: %s", r1.get("error_type"), r1.get("error_message"))
    log.info("  Attempt 2 error_type: %s  message: %s", r2.get("error_type"), r2.get("error_message"))
    sys.exit(1)


if __name__ == "__main__":
    main()
