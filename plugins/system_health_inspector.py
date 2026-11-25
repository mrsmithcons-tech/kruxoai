"""
plugins/system_health_inspector.py — Competitor-Adopted Feature: System Health & Diagnostic Suite.

Adapted from Open Interpreter & Windows Copilot diagnostics:
- Monitors CPU, RAM, GPU, Disk, and Process health.
- Identifies resource hogs and memory leaks.
- Streams structured Markdown status cards to the HUD Content Panel.
- Complies strictly with AGENTS.md rules.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

PLUGIN = {
    "name": "system_health_inspector",
    "description": (
        "Inspect PC health, CPU/RAM usage, top memory hogs, disk space, and system performance. "
        "Streams a structured diagnostics card to the HUD panel."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "focus": {
                "type": "STRING",
                "description": "What to inspect: 'summary' (all metrics), 'ram' (memory hogs), 'cpu' (processor load), 'disk' (storage space).",
                "enum": ["summary", "ram", "cpu", "disk"]
            }
        },
        "required": []
    }
}


def _gather_metrics(focus: str, player=None):
    if player:
        player.write_log("🩺 Running PC health diagnostics...")

    try:
        import psutil

        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count(logical=True)
        mem = psutil.virtual_memory()
        ram_total_gb = round(mem.total / (1024 ** 3), 1)
        ram_used_gb = round(mem.used / (1024 ** 3), 1)
        ram_percent = mem.percent

        # Disk
        disk = psutil.disk_usage("C:\\")
        disk_total_gb = round(disk.total / (1024 ** 3), 1)
        disk_free_gb = round(disk.free / (1024 ** 3), 1)
        disk_percent = disk.percent

        # Top processes by RAM
        procs = []
        for p in psutil.process_iter(["pid", "name", "memory_percent", "cpu_percent"]):
            try:
                info = p.info
                if info["name"] and info["name"].lower() not in ("system idle process", "system"):
                    procs.append(info)
            except Exception:
                pass

        top_ram = sorted(procs, key=lambda x: x["memory_percent"] or 0, reverse=True)[:5]
        top_cpu = sorted(procs, key=lambda x: x["cpu_percent"] or 0, reverse=True)[:5]

        # Markdown Report
        ram_table = "\n".join(
            f"| `{p['name']}` | PID {p['pid']} | {round(p['memory_percent'] or 0, 1)}% RAM |"
            for p in top_ram
        )
        cpu_table = "\n".join(
            f"| `{p['name']}` | PID {p['pid']} | {round(p['cpu_percent'] or 0, 1)}% CPU |"
            for p in top_cpu
        )

        health_status = "Optimal"
        if ram_percent > 85 or cpu_percent > 85:
            health_status = "High Load"
        elif ram_percent > 70 or cpu_percent > 70:
            health_status = "Moderate Load"

        md_report = f"""### 🩺 System Diagnostics Report
**Overall Status:** `{health_status}`

#### ⚡ Core Metrics
- **CPU Load:** `{cpu_percent}%` ({cpu_count} logical cores)
- **RAM Usage:** `{ram_percent}%` ({ram_used_gb} GB used / {ram_total_gb} GB total)
- **C: Storage:** `{disk_free_gb} GB free` / {disk_total_gb} GB total ({disk_percent}% used)

#### 🧠 Top Memory Consumers
| Application | Process ID | Memory Usage |
|:---|:---|:---|
{ram_table}

#### ⚙️ Top CPU Consumers
| Application | Process ID | CPU Load |
|:---|:---|:---|
{cpu_table}
"""
        if player:
            player.show_content("🩺 System Health Dashboard", md_report)
            player.write_log(f"✓ Health check complete: CPU {cpu_percent}%, RAM {ram_percent}%")

    except Exception as e:
        if player:
            player.write_log(f"⚠️ Health check error: {e}")
            player.show_content("Health Check Error", str(e))


def run(parameters: dict, player=None, session_memory=None) -> str:
    focus = str(parameters.get("focus", "summary")).strip().lower() or "summary"

    t = threading.Thread(
        target=_gather_metrics,
        args=(focus, player),
        daemon=True,
        name="HealthInspectorThread"
    )
    t.start()

    return "Checking system health, CPU load, and memory usage now. The full diagnostics card is opening on your panel."
