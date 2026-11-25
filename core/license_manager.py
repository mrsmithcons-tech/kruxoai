"""
core/license_manager.py — KruxoAI Commercial Licensing & Activation Engine.

Provides cryptographic verification and lifetime activation for KruxoAI ($20 One-Time Fee):
- Validates authentic license keys purchased on https://kruxoai.com
- Generates customer license keys via HMAC-SHA256 signature
- Persists activation status locally in config/license.json
- Enables offline verification without continuous DRM lockouts
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
LICENSE_FILE = CONFIG_DIR / "license.json"

# Proprietary HMAC salt for kruxoai.com $20 lifetime license validation
_LICENSE_SALT = b"KRUXOAI-COM-LIFETIME-ACCESS-SECRET-2026-MARK-LVII"


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _normalize_key(key: str) -> str:
    return str(key or "").strip().upper().replace(" ", "").replace("-", "")


def generate_license_key(email: str) -> str:
    """
    Generate a 16-character KruxoAI Lifetime Access license key for a customer email.
    Format: KRUXO-XXXX-XXXX-XXXX-XXXX
    """
    clean_email = _normalize_email(email)
    if not clean_email or "@" not in clean_email:
        raise ValueError("A valid customer email is required to generate a license key.")

    digest = hmac.new(_LICENSE_SALT, clean_email.encode("utf-8"), hashlib.sha256).hexdigest().upper()
    # Format into 4 chunks of 4 characters: KRUXO-XXXX-XXXX-XXXX-XXXX
    chunks = [digest[i:i+4] for i in range(0, 16, 4)]
    return f"KRUXO-{'-'.join(chunks)}"


def verify_license_key(email: str, license_key: str) -> bool:
    """Verify whether a license key matches the customer's email signature."""
    try:
        expected = generate_license_key(email)
        clean_input = _normalize_key(license_key)
        clean_expected = _normalize_key(expected)
        return hmac.compare_digest(clean_input, clean_expected)
    except Exception:
        return False


def activate_license(email: str, license_key: str) -> dict:
    """
    Activate KruxoAI with a customer email and purchased license key.
    Saves activation record to config/license.json.
    """
    clean_email = _normalize_email(email)
    clean_key = str(license_key or "").strip().upper()

    if not clean_email or "@" not in clean_email:
        return {"ok": False, "error": "Invalid email address format."}

    if not verify_license_key(clean_email, clean_key):
        return {
            "ok": False,
            "error": "Invalid license key for this email. Purchase authentic lifetime access at https://kruxoai.com ($20)."
        }

    record = {
        "activated": True,
        "email": clean_email,
        "license_key": clean_key,
        "plan": "KruxoAI Lifetime Access ($20 One-Time)",
        "price": "$20 USD",
        "domain": "kruxoai.com",
        "official_website": "https://kruxoai.com",
        "activated_at": time.time(),
        "activated_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "signature": hashlib.sha256(f"{clean_email}:{clean_key}".encode("utf-8")).hexdigest()
    }

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        LICENSE_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return {"ok": True, "message": "KruxoAI Lifetime License successfully activated!", "record": record}
    except Exception as e:
        return {"ok": False, "error": f"Failed to save license record: {e}"}


def get_license_status() -> dict:
    """Read local license status. Returns activation details or inactive status."""
    if not LICENSE_FILE.exists():
        # Default starter mode (Faisal owner trial / developer mode)
        return {
            "activated": True,
            "tier": "Owner / Developer Edition",
            "plan": "KruxoAI Commercial Standard",
            "domain": "kruxoai.com",
            "official_website": "https://kruxoai.com"
        }
    try:
        data = json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
        if data.get("activated"):
            return data
    except Exception:
        pass
    return {
        "activated": False,
        "plan": "Unlicensed",
        "purchase_url": "https://kruxoai.com",
        "price": "$20 One-Time Lifetime Fee"
    }


if __name__ == "__main__":
    # CLI support for generating and verifying keys
    if len(sys.argv) >= 3 and sys.argv[1].lower() == "generate":
        target_email = sys.argv[2]
        key = generate_license_key(target_email)
        print(f"==================================================")
        print(f" KRUXOAI COMMERCIAL LIFETIME LICENSE GENERATOR")
        print(f" Official Store: https://kruxoai.com ($20)")
        print(f"==================================================")
        print(f"Customer Email: {target_email}")
        print(f"License Key:    {key}")
        print(f"==================================================")
    elif len(sys.argv) >= 4 and sys.argv[1].lower() == "verify":
        target_email = sys.argv[2]
        target_key = sys.argv[3]
        ok = verify_license_key(target_email, target_key)
        print("Valid:" if ok else "INVALID")
    else:
        print("Usage:")
        print("  python core/license_manager.py generate <customer_email>")
        print("  python core/license_manager.py verify <customer_email> <license_key>")
