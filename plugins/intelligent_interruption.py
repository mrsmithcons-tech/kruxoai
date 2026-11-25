import os
import time
import psutil
import threading
from typing import Optional, Dict, Any

# Top-level plugin definition for routing and auto-discovery
PLUGIN = {
    "name": "intelligent_interruption",
    "description": "Monitors ambient audio/system health during silent mode (e.g. user on a call), intelligently interrupting silence only for critical system alerts or high-priority reminders until 'Hello Jarvis' is spoken.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "mode": {
                "type": "STRING",
                "description": "Operation mode: 'enable', 'disable', or 'status'."
            },
            "cpu_threshold": {
                "type": "NUMBER",
                "description": "CPU usage percentage threshold for critical overheat/load alerts (default: 90.0)."
            },
            "ram_threshold": {
                "type": "NUMBER",
                "description": "RAM usage percentage threshold for low memory alerts (default: 90.0)."
            }
        },
        "required": ["mode"]
    }
}

# Module-level state for background thread management
_MONITOR_THREAD: Optional[threading.Thread] = None
_STOP_EVENT = threading.Event()
_SILENT_MODE_ACTIVE = False

class IntelligentInterruptionMonitor(threading.Thread):
    """
    Background worker that continuously monitors system health and speech context.
    If silent mode is active, it suppresses general speech input but breaks silence
    for high-priority system alerts or explicit resume commands ('Hello Jarvis').
    """
    def __init__(self, player=None, session_memory=None, cpu_thresh=90.0, ram_thresh=90.0):
        super().__init__(daemon=True)
        self.player = player
        self.session_memory = session_memory
        self.cpu_thresh = cpu_thresh
        self.ram_thresh = ram_thresh
        self.last_alert_time = 0.0
        self.alert_cooldown = 60.0  # Avoid spamming alerts within 60 seconds

    def run(self):
        if self.player:
            self.player.write_log("[IntelligentInterruption] Silent mode monitoring thread started.")

        while not _STOP_EVENT.is_set():
            try:
                self.check_system_health()
                self.check_priority_reminders()
                self.check_speech_inputs()
            except Exception as e:
                if self.player:
                    self.player.write_log(f"[IntelligentInterruption] Loop error: {str(e)}")
            
            # Poll every 2 seconds
            time.sleep(2.0)

        if self.player:
            self.player.write_log("[IntelligentInterruption] Silent mode monitoring thread stopped.")

    def check_system_health(self):
        """Checks hardware metrics for critical load or low memory."""
        current_time = time.time()
        if current_time - self.last_alert_time < self.alert_cooldown:
            return

        cpu_usage = psutil.cpu_percent(interval=None)
        ram_usage = psutil.virtual_memory().percent

        alert_msg = None
        if cpu_usage >= self.cpu_thresh:
            alert_msg = f"CRITICAL ALERT: CPU usage is at {cpu_usage:.1f}%."
        elif ram_usage >= self.ram_thresh:
            alert_msg = f"CRITICAL ALERT: System memory usage is at {ram_usage:.1f}%."

        if alert_msg:
            self.last_alert_time = current_time
            self.trigger_interruption("System Health Warning", alert_msg)

    def check_priority_reminders(self):
        """Inspects session memory for pending high-priority reminders."""
        if not self.session_memory or not isinstance(self.session_memory, dict):
            return

        reminders = self.session_memory.get("pending_reminders", [])
        current_time = time.time()

        for reminder in list(reminders):
            if not isinstance(reminder, dict):
                continue
            
            is_priority = reminder.get("priority", False)
            trigger_time = reminder.get("trigger_time", 0)

            if is_priority and trigger_time <= current_time:
                text = reminder.get("text", "Urgent reminder due.")
                self.trigger_interruption("Priority Reminder", text)
                # Remove triggered reminder from memory
                try:
                    reminders.remove(reminder)
                except ValueError:
                    pass

    def check_speech_inputs(self):
        """
        Parses recently captured speech transcriptions from session memory.
        Ignores general input while on call unless explicit wake trigger 'hello jarvis' is detected.
        """
        if not self.session_memory or not isinstance(self.session_memory, dict):
            return

        transcript_buffer = self.session_memory.get("recent_transcripts", [])
        if not transcript_buffer:
            return

        # Process and clear buffer
        while transcript_buffer:
            phrase = transcript_buffer.pop(0).strip().lower()
            if "hello jarvis" in phrase:
                global _SILENT_MODE_ACTIVE
                _SILENT_MODE_ACTIVE = False
                if self.player:
                    self.player.write_log("[IntelligentInterruption] Resuming normal mode via 'Hello Jarvis'.")
                    self.player.show_content(
                        "JARVIS Active",
                        "Silent mode disabled. How may I assist you?"
                    )
                # Break silence and notify user
                self.trigger_interruption("Status Update", "Silent mode deactivated. I am listening.", break_only=True)
                break
            else:
                if self.player:
                    self.player.write_log(f"[IntelligentInterruption] Ignored phrase in silent mode: '{phrase}'")

    def trigger_interruption(self, title: str, message: str, break_only: bool = False):
        """Briefly interrupts silence to announce urgent issue, then returns to silence."""
        if self.player:
            self.player.write_log(f"[IntelligentInterruption] Breaking silence: {title} - {message}")
            self.player.show_content(f"URGENT: {title}", message)

        # Update session memory log for tracking
        if self.session_memory and isinstance(self.session_memory, dict):
            alerts = self.session_memory.setdefault("interruption_alerts", [])
            alerts.append({"timestamp": time.time(), "title": title, "message": message})


def run(parameters: dict, player=None, session_memory=None) -> str:
    """
    Plugin execution entry point. Controls silent mode intelligent interruption state.
    """
    global _MONITOR_THREAD, _STOP_EVENT, _SILENT_MODE_ACTIVE

    try:
        mode = parameters.get("mode", "").lower()
        cpu_thresh = float(parameters.get("cpu_threshold", 90.0))
        ram_thresh = float(parameters.get("ram_threshold", 90.0))

        if mode == "enable":
            if _SILENT_MODE_ACTIVE and _MONITOR_THREAD and _MONITOR_THREAD.is_alive():
                return "Intelligent interruption is already active in silent mode."

            _STOP_EVENT.clear()
            _SILENT_MODE_ACTIVE = True
            
            _MONITOR_THREAD = IntelligentInterruptionMonitor(
                player=player,
                session_memory=session_memory,
                cpu_thresh=cpu_thresh,
                ram_thresh=ram_thresh
            )
            _MONITOR_THREAD.start()

            if player:
                player.write_log("[IntelligentInterruption] Entered silent mode with intelligent interruption enabled.")
                player.show_content(
                    "Silent Mode Active",
                    "Monitoring calls. General audio ignored. Urgent alerts and 'Hello Jarvis' will interrupt."
                )

            return "Silent mode enabled with intelligent interruption active."

        elif mode == "disable":
            if not _SILENT_MODE_ACTIVE:
                return "Silent mode is not currently active."

            _SILENT_MODE_ACTIVE = False
            _STOP_EVENT.set()
            if _MONITOR_THREAD:
                _MONITOR_THREAD.join(timeout=3.0)
                _MONITOR_THREAD = None

            if player:
                player.write_log("[IntelligentInterruption] Disabled silent mode monitoring.")
                player.show_content("Normal Mode", "Silent mode deactivated. Fully operational.")

            return "Intelligent interruption silent mode disabled."

        elif mode == "status":
            status_str = "active" if _SILENT_MODE_ACTIVE else "inactive"
            thread_alive = _MONITOR_THREAD.is_alive() if _MONITOR_THREAD else False
            
            if player:
                player.show_content(
                    "Interruption System Status",
                    f"Silent Mode: {status_str.upper()}\nMonitor Thread: {'Running' if thread_alive else 'Stopped'}"
                )
            
            return f"Silent mode is currently {status_str}."

        else:
            return f"Invalid mode '{mode}'. Supported modes are: 'enable', 'disable', 'status'."

    except Exception as e:
        error_msg = f"Error in intelligent_interruption plugin: {str(e)}"
        if player:
            try:
                player.write_log(f"[IntelligentInterruption] Exception caught: {error_msg}")
            except Exception:
                pass
        return f"Failed to execute intelligent interruption logic: {str(e)}"