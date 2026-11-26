"""
core/license_manager.py — KruxoAI Commercial Licensing, Buyer Registry & Anti-Tamper DRM.

Provides cryptographic verification, buyer management, ban/revocation, and anti-tamper alerts:
- Generates and registers customer license keys ($20 Lifetime Access)
- Maintains persistent buyer database in config/buyers_registry.json
- Immediate license ban/revocation (illegal resale, chargebacks, crack attempts)
- Real-time anti-tamper and code integrity monitoring with security alerts
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import sys
import time
import urllib.request
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
MEMORY_DIR = BASE_DIR / "memory"
LICENSE_FILE = CONFIG_DIR / "license.json"
REGISTRY_FILE = CONFIG_DIR / "buyers_registry.json"
ALERTS_FILE = MEMORY_DIR / "tamper_alerts.json"

# Proprietary HMAC salt for kruxoai.com $20 lifetime license validation
_LICENSE_SALT = b"KRUXOAI-COM-LIFETIME-ACCESS-SECRET-2026-MARK-LVII"


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _normalize_key(key: str) -> str:
    return str(key or "").strip().upper().replace(" ", "").replace("-", "")


# ── Registry & Database Management ────────────────────────────────────────────

def _load_registry() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_FILE.exists():
        # Default starter registry
        init_data = {
            "version": "2.0",
            "domain": "kruxoai.com",
            "buyers": {
                "faisal@kruxoai.com": {
                    "name": "Faisal (Founder)",
                    "email": "faisal@kruxoai.com",
                    "license_key": "KRUXO-B7D6-37B7-8593-D34E",
                    "status": "ACTIVE",
                    "plan": "Founder Master Lifetime License",
                    "created_at": "2026-11-25 19:42:14",
                    "notes": "System Owner & Creator"
                }
            },
            "banned_keys": [],
            "banned_emails": []
        }
        REGISTRY_FILE.write_text(json.dumps(init_data, indent=2), encoding="utf-8")
        return init_data
    try:
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"buyers": {}, "banned_keys": [], "banned_emails": []}


def _save_registry(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ── Key Generation & Registration ─────────────────────────────────────────────

def generate_license_key(email: str) -> str:
    """
    Generate a 16-character KruxoAI Lifetime Access license key for a customer email.
    Format: KRUXO-XXXX-XXXX-XXXX-XXXX
    """
    clean_email = _normalize_email(email)
    if not clean_email or "@" not in clean_email:
        raise ValueError("A valid customer email is required to generate a license key.")

    digest = hmac.new(_LICENSE_SALT, clean_email.encode("utf-8"), hashlib.sha256).hexdigest().upper()
    chunks = [digest[i:i+4] for i in range(0, 16, 4)]
    return f"KRUXO-{'-'.join(chunks)}"


def register_buyer(email: str, name: str = "", notes: str = "") -> dict:
    """
    Register a new buyer, generate their license key, and save to buyers_registry.json.
    """
    clean_email = _normalize_email(email)
    if not clean_email or "@" not in clean_email:
        return {"ok": False, "error": "Invalid email format."}

    registry = _load_registry()
    key = generate_license_key(clean_email)

    buyer_record = {
        "name": name.strip() or clean_email.split("@")[0].title(),
        "email": clean_email,
        "license_key": key,
        "status": "ACTIVE",
        "plan": "KruxoAI Lifetime Access ($20 One-Time)",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "notes": notes.strip() or "Purchased on kruxoai.com ($20)"
    }

    registry["buyers"][clean_email] = buyer_record
    # If previously banned, remove from banned lists
    if clean_email in registry.get("banned_emails", []):
        registry["banned_emails"].remove(clean_email)
    if key in registry.get("banned_keys", []):
        registry["banned_keys"].remove(key)

    _save_registry(registry)
    return {"ok": True, "buyer": buyer_record}


def list_buyers() -> list[dict]:
    """Retrieve all buyers from the registry."""
    registry = _load_registry()
    return list(registry.get("buyers", {}).values())


# ── Ban, Revocation & Blacklisting ────────────────────────────────────────────

def ban_buyer(identifier: str, reason: str = "Violation of commercial terms (illegal resale/tampering)") -> dict:
    """
    Ban a buyer by email or license key. Immediately revokes license validation.
    """
    target = str(identifier or "").strip()
    if not target:
        return {"ok": False, "error": "Missing email or license key to ban."}

    registry = _load_registry()
    banned_emails = set(registry.get("banned_emails", []))
    banned_keys = set(registry.get("banned_keys", []))

    matched_email = None
    clean_id = _normalize_key(target)

    # Check if target is in buyers
    for email, record in registry.get("buyers", {}).items():
        if email.lower() == target.lower() or _normalize_key(record.get("license_key", "")) == clean_id:
            record["status"] = "BANNED"
            record["ban_reason"] = reason
            record["banned_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            banned_emails.add(email.lower())
            banned_keys.add(record.get("license_key", ""))
            matched_email = email
            break

    if "@" in target:
        banned_emails.add(target.lower())
    else:
        banned_keys.add(target.upper())

    registry["banned_emails"] = list(banned_emails)
    registry["banned_keys"] = list(banned_keys)
    _save_registry(registry)

    # If the currently installed local license is this banned user, revoke it!
    try:
        if LICENSE_FILE.exists():
            local_lic = json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
            if (local_lic.get("email", "").lower() in banned_emails or
                local_lic.get("license_key", "") in banned_keys):
                local_lic["activated"] = False
                local_lic["status"] = "REVOKED"
                local_lic["revocation_reason"] = reason
                LICENSE_FILE.write_text(json.dumps(local_lic, indent=2), encoding="utf-8")
    except Exception:
        pass

    # Dispatch security alert
    dispatch_tamper_alert(
        alert_type="LICENSE_REVOCATION",
        details={"identifier": target, "reason": reason, "matched_email": matched_email}
    )

    return {
        "ok": True,
        "message": f"License for {target} has been permanently BANNED and REVOKED.",
        "reason": reason
    }


def unban_buyer(identifier: str) -> dict:
    """Unban a previously revoked customer."""
    target = str(identifier or "").strip()
    registry = _load_registry()
    clean_id = _normalize_key(target)

    banned_emails = set(registry.get("banned_emails", []))
    banned_keys = set(registry.get("banned_keys", []))

    for email, record in registry.get("buyers", {}).items():
        if email.lower() == target.lower() or _normalize_key(record.get("license_key", "")) == clean_id:
            record["status"] = "ACTIVE"
            record.pop("ban_reason", None)
            record.pop("banned_at", None)
            banned_emails.discard(email.lower())
            banned_keys.discard(record.get("license_key", ""))
            break

    banned_emails.discard(target.lower())
    banned_keys.discard(target.upper())

    registry["banned_emails"] = list(banned_emails)
    registry["banned_keys"] = list(banned_keys)
    _save_registry(registry)
    return {"ok": True, "message": f"{target} has been unbanned and restored to ACTIVE."}


def is_banned(identifier: str) -> tuple[bool, str]:
    """Check if an email or license key is banned."""
    target = str(identifier or "").strip()
    if not target:
        return False, ""

    registry = _load_registry()
    banned_emails = [e.lower() for e in registry.get("banned_emails", [])]
    banned_keys = [_normalize_key(k) for k in registry.get("banned_keys", [])]

    if "@" in target and target.lower() in banned_emails:
        return True, "Email is blacklisted for commercial violation."

    clean_key = _normalize_key(target)
    if clean_key in banned_keys:
        return True, "License key is revoked for terms of service violation."

    # Check buyers dict
    for email, record in registry.get("buyers", {}).items():
        if email.lower() == target.lower() or _normalize_key(record.get("license_key", "")) == clean_key:
            if record.get("status") == "BANNED":
                return True, record.get("ban_reason", "License revoked by kruxoai.com.")

    return False, ""


# ── Verification & Activation ─────────────────────────────────────────────────

def verify_license_key(email: str, license_key: str) -> bool:
    """Verify whether a license key matches the customer's email signature and is not banned."""
    clean_email = _normalize_email(email)
    clean_key = str(license_key or "").strip()

    # 1. Ban Check
    banned, reason = is_banned(clean_email)
    if banned:
        return False
    banned, reason = is_banned(clean_key)
    if banned:
        return False

    # 2. Cryptographic signature check
    try:
        expected = generate_license_key(clean_email)
        clean_input = _normalize_key(clean_key)
        clean_expected = _normalize_key(expected)
        return hmac.compare_digest(clean_input, clean_expected)
    except Exception:
        return False


def activate_license(email: str, license_key: str) -> dict:
    """
    Activate KruxoAI with a customer email and purchased license key.
    """
    clean_email = _normalize_email(email)
    clean_key = str(license_key or "").strip().upper()

    if not clean_email or "@" not in clean_email:
        return {"ok": False, "error": "Invalid email address format."}

    banned, reason = is_banned(clean_email)
    if banned:
        return {"ok": False, "error": f"LICENSE BANNED: {reason}"}
    banned, reason = is_banned(clean_key)
    if banned:
        return {"ok": False, "error": f"LICENSE BANNED: {reason}"}

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
        "machine_name": platform.node(),
        "os_info": f"{platform.system()} {platform.release()}",
        "signature": hashlib.sha256(f"{clean_email}:{clean_key}".encode("utf-8")).hexdigest()
    }

    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        LICENSE_FILE.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return {"ok": True, "message": "KruxoAI Lifetime License successfully activated!", "record": record}
    except Exception as e:
        return {"ok": False, "error": f"Failed to save license record: {e}"}


def check_remote_ban(email: str, key: str) -> tuple[bool, str]:
    """Check online ban status against kruxoai.com and permanent endpoint with short timeout."""
    endpoints = [
        f"https://kruxoai.com/api/license/check?email={email}&key={key}",
        f"https://stabilize-gladly-possibly.ngrok-free.dev/license_check?email={email}&key={key}"
    ]
    for url in endpoints:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "KruxoAI-Client/2.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode())
                if data.get("banned"):
                    return True, data.get("reason", "License revoked by kruxoai.com administration.")
        except Exception:
            continue
    return False, ""


def get_license_status() -> dict:
    """Read local license status. Checks for bans, signatures, and returns activation details."""
    if not LICENSE_FILE.exists():
        return {
            "activated": False,
            "status": "UNLICENSED",
            "plan": "Unlicensed",
            "error": "Activation required. Purchase lifetime access at https://kruxoai.com ($20).",
            "purchase_url": "https://kruxoai.com",
            "price": "$20 USD"
        }
    try:
        data = json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
        email = data.get("email", "")
        key = data.get("license_key", "")

        # 1. Cryptographic signature and authenticity verification
        if not email or not key or not verify_license_key(email, key):
            return {
                "activated": False,
                "status": "INVALID_SIGNATURE",
                "plan": "Unlicensed",
                "error": "Tampered or invalid license key signature.",
                "purchase_url": "https://kruxoai.com"
            }

        # 2. Check local and remote ban status
        banned, reason = is_banned(email)
        if not banned:
            banned, reason = is_banned(key)
        if not banned and email and key:
            banned, reason = check_remote_ban(email, key)

        if banned:
            data["activated"] = False
            data["status"] = "BANNED / REVOKED"
            data["ban_reason"] = reason
            return data

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


# ── Anti-Tamper & Security Alert System ───────────────────────────────────────

def dispatch_tamper_alert(alert_type: str, details: dict) -> None:
    """Record and dispatch anti-tamper / piracy alert."""
    try:
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        alerts = []
        if ALERTS_FILE.exists():
            try:
                alerts = json.loads(ALERTS_FILE.read_text(encoding="utf-8"))
            except Exception:
                alerts = []

        event = {
            "timestamp": time.time(),
            "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
            "alert_type": alert_type,
            "machine": platform.node(),
            "os": f"{platform.system()} {platform.release()}",
            "details": details
        }
        alerts.append(event)
        # Keep last 100 alerts
        alerts = alerts[-100:]
        ALERTS_FILE.write_text(json.dumps(alerts, indent=2), encoding="utf-8")

        # Try to dispatch to local bridge so HUD logs it
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:9876/panel",
                data=json.dumps({
                    "title": f"🚨 SECURITY ALERT: {alert_type}",
                    "text": f"Warning: {alert_type}\nDetails: {json.dumps(details, indent=2)}",
                    "speak": "Security alert. Unauthorized license violation or tampering detected."
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=1)
        except Exception:
            pass

        # Try to dispatch to remote admin endpoints
        for remote_url in [
            "https://kruxoai.com/api/security-alert",
            "https://stabilize-gladly-possibly.ngrok-free.dev/security_alert"
        ]:
            try:
                remote_req = urllib.request.Request(
                    remote_url,
                    data=json.dumps(event).encode("utf-8"),
                    headers={"Content-Type": "application/json", "User-Agent": "KruxoAI-Client/2.0"}
                )
                urllib.request.urlopen(remote_req, timeout=1.5)
            except Exception:
                continue

    except Exception as e:
        print(f"[AntiTamper] Alert logging error: {e}")


def check_anti_tamper() -> dict:
    """
    Check codebase and branding integrity against unauthorized resale / white-label tampering.
    """
    violations = []
    # 1. Check if official domain kruxoai.com is intact in theme.py
    try:
        theme_path = BASE_DIR / "gui" / "theme.py"
        if theme_path.exists():
            content = theme_path.read_text(encoding="utf-8")
            if "kruxoai.com" not in content:
                violations.append("Core domain 'kruxoai.com' stripped from gui/theme.py (unauthorized white-labeling).")
    except Exception as e:
        violations.append(f"Unable to read gui/theme.py: {e}")

    # 2. Check if prompt.txt retains KruxoAI persona
    try:
        prompt_path = BASE_DIR / "core" / "prompt.txt"
        if prompt_path.exists():
            content = prompt_path.read_text(encoding="utf-8")
            if "kruxoai.com" not in content:
                violations.append("System persona modified: kruxoai.com reference removed.")
    except Exception as e:
        violations.append(f"Unable to read core/prompt.txt: {e}")

    if violations:
        dispatch_tamper_alert("UNAUTHORIZED_CODE_TAMPERING", {"violations": violations})
        return {"intact": False, "violations": violations}

    return {"intact": True, "message": "All integrity checks passed."}


# ── Interactive CLI ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("Usage:")
        print("  python core/license_manager.py generate <email> [name] [notes]")
        print("  python core/license_manager.py list")
        print("  python core/license_manager.py ban <email_or_key> [reason]")
        print("  python core/license_manager.py unban <email_or_key>")
        print("  python core/license_manager.py verify <email> <key>")
        print("  python core/license_manager.py check-tamper")
        sys.exit(0)

    cmd = args[0].lower()

    if cmd == "generate" and len(args) >= 2:
        email = args[1]
        name = args[2] if len(args) > 2 else ""
        notes = args[3] if len(args) > 3 else "Issued via CLI"
        res = register_buyer(email, name, notes)
        if res.get("ok"):
            b = res["buyer"]
            print(f"==================================================")
            print(f" ✅ KRUXOAI BUYER REGISTERED & LICENSE GENERATED")
            print(f" Official Store: https://kruxoai.com ($20)")
            print(f"==================================================")
            print(f"Buyer Name:   {b['name']}")
            print(f"Buyer Email:  {b['email']}")
            print(f"License Key:  {b['license_key']}")
            print(f"Status:       {b['status']}")
            print(f"Registered:   {b['created_at']}")
            print(f"Notes:        {b['notes']}")
            print(f"==================================================")
        else:
            print(f"Error: {res.get('error')}")

    elif cmd == "list":
        buyers = list_buyers()
        print(f"================================================================================")
        print(f" KRUXOAI REGISTERED BUYERS DATABASE ({len(buyers)} TOTAL)")
        print(f"================================================================================")
        for i, b in enumerate(buyers, 1):
            status_icon = "✅" if b.get("status") == "ACTIVE" else "🚫"
            print(f"{i}. {status_icon} [{b.get('status')}] {b.get('name')} <{b.get('email')}>")
            print(f"   Key: {b.get('license_key')} | Date: {b.get('created_at')}")
            if b.get("ban_reason"):
                print(f"   Ban Reason: {b.get('ban_reason')}")
            if b.get("notes"):
                print(f"   Notes: {b.get('notes')}")
            print("-" * 80)

    elif cmd == "ban" and len(args) >= 2:
        target = args[1]
        reason = " ".join(args[2:]) if len(args) > 2 else "Violation of commercial terms (illegal resale/tampering)"
        res = ban_buyer(target, reason)
        print(f"==================================================")
        print(f" 🚫 LICENSE BAN EXECUTED")
        print(f"==================================================")
        print(res.get("message"))
        print(f"Reason: {reason}")
        print(f"==================================================")

    elif cmd == "unban" and len(args) >= 2:
        target = args[1]
        res = unban_buyer(target)
        print(f"==================================================")
        print(f" ✅ LICENSE RESTORED")
        print(f"==================================================")
        print(res.get("message"))
        print(f"==================================================")

    elif cmd == "verify" and len(args) >= 3:
        email = args[1]
        key = args[2]
        banned, reason = is_banned(email)
        if banned:
            print(f"BANNED: {reason}")
        else:
            ok = verify_license_key(email, key)
            print("VALID (Active Lifetime)" if ok else "INVALID")

    elif cmd == "check-tamper":
        res = check_anti_tamper()
        print("Tamper check result:", res)
