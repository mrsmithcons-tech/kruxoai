"""
plugins/license_activator.py — Voice & HUD License Activator for KruxoAI.

Allows the user to check license status or activate their $20 lifetime license key
purchased from https://kruxoai.com.
"""
from __future__ import annotations

from core.license_manager import activate_license, get_license_status

PLUGIN = {
    "name": "manage_license",
    "description": (
        "Check KruxoAI commercial license status or activate a lifetime access key "
        "purchased on https://kruxoai.com for $20."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["status", "activate"],
                "description": "'status' to check current license, 'activate' to enter key."
            },
            "email": {
                "type": "STRING",
                "description": "Customer email used when purchasing on kruxoai.com (required for activation)."
            },
            "license_key": {
                "type": "STRING",
                "description": "Purchased license key in format KRUXO-XXXX-XXXX-XXXX-XXXX."
            }
        },
        "required": ["action"]
    }
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    action = parameters.get("action", "status").strip().lower()

    if action == "status":
        info = get_license_status()
        active = info.get("activated", False)
        plan = info.get("plan", "Standard")
        domain = info.get("domain", "kruxoai.com")

        text = (
            f"### 🛡️ KruxoAI Commercial License Status\n\n"
            f"- **Activation Status:** {'✅ Active (Lifetime Access)' if active else '⚠️ Unlicensed'}\n"
            f"- **Plan:** `{plan}`\n"
            f"- **Platform Domain:** `{domain}`\n"
            f"- **Official Store:** [https://kruxoai.com](https://kruxoai.com)\n"
            f"- **Price:** `$20 One-Time Lifetime Access`\n"
        )
        if player:
            player.show_content("🛡️ License & Activation", text)
            player.write_log("Checked KruxoAI commercial license status.")
        return f"KruxoAI license is {'fully active with lifetime access' if active else 'pending activation'} under {domain}."

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
                f"Thank you for supporting KruxoAI! All features and future updates are unlocked forever."
            )
            if player:
                player.show_content("🎉 KruxoAI Activated", text)
                player.write_log(f"Activated lifetime license for {email}")
            return f"License successfully verified and activated for {email}. Welcome to KruxoAI Lifetime Access."
        else:
            return f"Activation failed: {res.get('error', 'Invalid license key')}. Visit https://kruxoai.com to acquire a valid key."

    return "Unknown license action requested."
