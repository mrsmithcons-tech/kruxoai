"""
plugins/license_activator.py — Master Admin Commercial License & DRM Command Center for KruxoAI.

Empowers Faisal (Founder & Admin) to manage commercial buyers, issue $20 lifetime licenses,
review revenue, ban violators, and inspect real-time activation requests directly from the HUD.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from core.license_manager import (
    activate_license,
    get_license_status,
    register_buyer,
    list_buyers,
    ban_buyer,
    unban_buyer
)

BASE_DIR = Path(__file__).resolve().parent.parent
REQUESTS_FILE = BASE_DIR / "memory" / "license_requests.json"

PLUGIN = {
    "name": "manage_license",
    "description": (
        "Master Admin Commercial License Manager for KruxoAI. Allows Faisal (Admin) to generate lifetime licenses, "
        "view registered buyers, check revenue, ban/revoke licenses, view incoming activation requests, or activate."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": [
                    "status",
                    "activate",
                    "list_buyers",
                    "generate_key",
                    "ban_buyer",
                    "unban_buyer",
                    "view_requests"
                ],
                "description": "Admin action: 'list_buyers', 'generate_key', 'ban_buyer', 'unban_buyer', 'view_requests', 'status', 'activate'."
            },
            "email": {
                "type": "STRING",
                "description": "Customer email to generate license for, activate, or ban."
            },
            "name": {
                "type": "STRING",
                "description": "Customer full name (optional, for registration)."
            },
            "license_key": {
                "type": "STRING",
                "description": "License key in format KRUXO-XXXX-XXXX-XXXX-XXXX."
            },
            "notes": {
                "type": "STRING",
                "description": "Payment notes (e.g. 'Paid $20 via Stripe', 'PayPal #102')."
            },
            "reason": {
                "type": "STRING",
                "description": "Reason for banning or revoking the license."
            }
        },
        "required": ["action"]
    }
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = parameters.get("action", "status").strip().lower()

    # ── 1. Local Status ───────────────────────────────────────────────────────
    if action == "status":
        info = get_license_status()
        active = info.get("activated", False)
        plan = info.get("plan", "Standard")
        domain = info.get("domain", "kruxoai.com")
        email = info.get("email", "faisal@kruxoai.com")
        key = info.get("license_key", "KRUXO-B7D6-37B7-8593-D34E")

        text = (
            f"### 🛡️ KruxoAI Commercial License Status\n\n"
            f"- **Status:** {'✅ Verified Lifetime Access' if active else '⚠️ Activation Required'}\n"
            f"- **Licensed To:** `{email}`\n"
            f"- **License Key:** `{key}`\n"
            f"- **Plan:** `{plan}`\n"
            f"- **Store:** [https://kruxoai.com](https://kruxoai.com) ($20 Lifetime Access)\n\n"
            f"Master Admin installation is permanently authorized."
        )
        if player:
            player.show_content("🛡️ License Certificate", text)
            player.write_log(f"Displayed license certificate for {email}.")
        return f"KruxoAI license is {'fully active with lifetime access' if active else 'pending activation'} under {domain}."

    # ── 2. List Registered Buyers & Revenue ────────────────────────────────────
    if action == "list_buyers":
        buyers = list_buyers()
        active_count = sum(1 for b in buyers if b.get("status") == "ACTIVE")
        banned_count = sum(1 for b in buyers if b.get("status") == "BANNED")
        revenue = active_count * 20

        lines = [
            f"# 👥 KruxoAI Commercial Buyers Registry",
            f"**Total Revenue:** `${revenue} USD`  |  **Active Licenses:** `{active_count}`  |  **Revoked/Banned:** `{banned_count}`",
            f"**Official Platform:** [https://kruxoai.com](https://kruxoai.com) ($20 Lifetime Access)",
            f"",
            f"---",
            f"",
            f"| # | Name | Email | Status | License Key | Date |",
            f"|---|---|---|---|---|---|",
        ]
        for i, b in enumerate(buyers, 1):
            st = "✅ Active" if b.get("status") == "ACTIVE" else "🚫 Banned"
            lines.append(f"| {i} | {b.get('name', 'Buyer')} | `{b.get('email')}` | {st} | `{b.get('license_key')}` | {b.get('created_at', '')[:10]} |")

        lines.append("")
        lines.append("---")
        lines.append(f"*All licenses are mathematically signed and enforceable globally.*")

        content_md = "\n".join(lines)
        if player:
            player.show_content("👥 Commercial Buyers & Revenue", content_md)
            player.write_log(f"Listed {len(buyers)} commercial buyers (${revenue} revenue).")

        return f"Faisal, you have {len(buyers)} registered buyers with total revenue of ${revenue} USD. Complete buyer records are displayed on your HUD."

    # ── 3. Generate License Key for Buyer ─────────────────────────────────────
    if action == "generate_key":
        email = parameters.get("email", "").strip()
        name = parameters.get("name", "").strip()
        notes = parameters.get("notes", "").strip() or "Registered via KruxoAI Admin"

        if not email:
            return "Please specify the customer's email address to generate a lifetime license."

        res = register_buyer(email, name=name, notes=notes)
        if not res.get("ok"):
            return f"Failed to register buyer: {res.get('error')}"

        b = res["buyer"]
        key = b["license_key"]
        buyer_name = b["name"]

        card_md = (
            f"### ⚡ Commercial Lifetime License Generated!\n\n"
            f"- **Customer Name:** `{buyer_name}`\n"
            f"- **Customer Email:** `{email}`\n"
            f"- **Lifetime License Key:** `{key}`\n"
            f"- **Plan:** `KruxoAI Lifetime Access ($20 One-Time)`\n"
            f"- **Store:** [https://kruxoai.com](https://kruxoai.com)\n"
            f"- **Status:** `✅ ACTIVE`\n"
            f"- **Notes:** `{notes}`\n\n"
            f"The buyer has been registered in your commercial database. Send this key to the customer."
        )
        if player:
            player.show_content("⚡ License Key Generated", card_md)
            player.write_log(f"Generated license key {key} for {email}.")

        return f"Sir, I have registered {buyer_name} and generated lifetime license key {key}. Details are displayed on your HUD."

    # ── 4. Ban / Revoke Buyer ─────────────────────────────────────────────────
    if action == "ban_buyer":
        target = parameters.get("email", "") or parameters.get("license_key", "")
        reason = parameters.get("reason", "").strip() or "Violation of commercial terms (illegal resale/tampering)"

        if not target:
            return "Please provide the email or license key of the user you want to ban."

        res = ban_buyer(target, reason=reason)
        if player:
            ban_md = (
                f"### 🚫 License Revoked & Blacklisted\n\n"
                f"- **Target:** `{target}`\n"
                f"- **Status:** `🚫 BANNED`\n"
                f"- **Reason:** `{reason}`\n"
                f"- **Enforcement:** `Immediate Global Lockdown`\n\n"
                f"This license has been added to the blacklist. Any instance attempting to use this key is locked."
            )
            player.show_content("🚫 License Revoked", ban_md)
            player.write_log(f"BANNED license for {target}. Reason: {reason}")

        return f"License for {target} has been permanently banned and revoked. Their KruxoAI will be locked out."

    # ── 5. Unban Buyer ────────────────────────────────────────────────────────
    if action == "unban_buyer":
        target = parameters.get("email", "") or parameters.get("license_key", "")
        if not target:
            return "Please provide the email or license key to unban."

        unban_buyer(target)
        if player:
            player.write_log(f"Restored license for {target}.")
        return f"User {target} has been unbanned and restored to ACTIVE status."

    # ── 6. View Activation Requests ───────────────────────────────────────────
    if action == "view_requests":
        requests_list = []
        if REQUESTS_FILE.exists():
            try:
                requests_list = json.loads(REQUESTS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass

        if not requests_list:
            if player:
                player.show_content("🔔 Activation Requests", "### 🔔 No Pending Activation Requests\n\nAll clear. Incoming requests from kruxoai.com will appear here.")
            return "There are no incoming license activation requests at the moment."

        lines = [
            f"# 🔔 KruxoAI Incoming License Requests ({len(requests_list)} Total)",
            f"Real-time requests received via kruxoai.com and permanent tunnel.",
            f"",
            f"| Time | Name | Email | Status | Key |",
            f"|---|---|---|---|---|",
        ]
        for r in requests_list[-15:]:
            lines.append(f"| {r.get('time_str', '')} | {r.get('name')} | `{r.get('email')}` | `{r.get('status')}` | `{r.get('license_key', '-')}` |")

        if player:
            player.show_content("🔔 Incoming License Requests", "\n".join(lines))
            player.write_log(f"Reviewed {len(requests_list)} incoming license requests.")

        return f"Faisal, here are the recent incoming license requests. Full details are displayed on your HUD."

    # ── 7. Client Activation ──────────────────────────────────────────────────
    if action == "activate":
        email = parameters.get("email", "").strip()
        key = parameters.get("license_key", "").strip()
        if not email or not key:
            return "Please provide both the purchase email and license key to activate KruxoAI."

        res = activate_license(email, key)
        if res.get("ok"):
            text = (
                f"### 🎉 KruxoAI Activated Successfully!\n\n"
                f"- **Licensed to:** `{email}`\n"
                f"- **Key:** `{key}`\n"
                f"- **Tier:** `Lifetime Access ($20 One-Time)`\n"
                f"- **Domain:** `kruxoai.com`\n\n"
                f"Welcome to KruxoAI Lifetime Access."
            )
            if player:
                player.show_content("🎉 KruxoAI Activated", text)
                player.write_log(f"Activated lifetime license for {email}")
            return f"License successfully verified and activated for {email}."
        else:
            return f"Activation failed: {res.get('error', 'Invalid license key')}."

    return "Unknown license action requested."
