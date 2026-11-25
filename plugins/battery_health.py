import psutil

PLUGIN = {
    "name": "battery_health",
    "description": "Checks the laptop battery status, including charge percentage and power plug status.",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": []
    }
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        battery = psutil.sensors_battery()
        
        if battery is None:
            message = "I am unable to detect a battery on this device."
            if player:
                player.show_content("Battery Status", message)
            return message

        percent = round(battery.percent, 2)
        plugged = battery.power_plugged
        
        status_text = f"Battery level: {percent}%\nStatus: {'Plugged in' if plugged else 'Discharging'}"
        
        if player:
            player.show_content("Battery Status", status_text)
            player.write_log(f"Battery check: {percent}%, Plugged: {plugged}")

        summary = f"The battery is at {percent} percent and is currently {'plugged in' if plugged else 'discharging'}."
        return summary

    except Exception as e:
        error_msg = f"Error checking battery health: {str(e)}"
        if player:
            player.write_log(error_msg)
        return "I encountered an error trying to check the battery status."