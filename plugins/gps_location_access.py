import asyncio
import threading
import time

PLUGIN = {
    "name": "gps_location_access",
    "description": "Accesses the host machine's high-precision GPS or internal location sensor data via Windows Geolocation API.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "timeout": {
                "type": "INTEGER",
                "description": "Timeout in seconds to wait for location fix (default 10)"
            }
        },
        "required": []
    }
}

# WinRT imports only allowed inside the execution context to prevent installation issues on non-Windows
async def _get_winrt_location(timeout_sec):
    try:
        import winrt.windows.devices.geolocation as wdg
        
        locator = wdg.Geolocator()
        
        # Request high accuracy
        locator.desired_accuracy = wdg.PositionAccuracy.HIGH
        desired_accuracy_in_meters = 10 
        locator.desired_accuracy_in_meters = desired_accuracy_in_meters

        # Perform the async operation
        pos = await asyncio.wait_for(locator.get_geoposition_async(), timeout=timeout_sec)
        
        return {
            "latitude": pos.coordinate.point.position.latitude,
            "longitude": pos.coordinate.point.position.longitude,
            "accuracy": pos.coordinate.accuracy,
            "altitude": pos.coordinate.point.position.altitude,
            "source": str(pos.coordinate.position_source)
        }
    except Exception as e:
        return {"error": str(e)}

def _run_async_loop(timeout_sec):
    # Setup loop specifically for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_get_winrt_location(timeout_sec))
        return result
    finally:
        loop.close()

def run(parameters: dict, player=None, session_memory=None) -> str:
    timeout_sec = parameters.get("timeout", 10)
    
    if player:
        player.write_log("Requesting Windows Geolocation fix...")

    try:
        # Check platform
        import sys
        if sys.platform != "win32":
            return "This capability requires the Windows operating system."

        # Execute async operation in a dedicated thread to avoid COM apartment issues
        # and not block the main process. WinRT requires specific threading models.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(_run_async_loop, timeout_sec)
            location_data = future.result()

        if "error" in location_data:
            error_msg = location_data["error"]
            if player:
                player.write_log(f"Location access failed: {error_msg}")
            return f"Failed to access location data: {error_msg}"

        lat = location_data['latitude']
        lon = location_data['longitude']
        acc = location_data['accuracy']

        # Format output
        display_text = (
            f"Latitude: {lat:.6f}\n"
            f"Longitude: {lon:.6f}\n"
            f"Accuracy: {acc:.2f} meters\n"
            f"Altitude: {location_data.get('altitude', 0.0):.2f} meters\n"
            f"Source: {location_data.get('source', 'Unknown')}"
        )

        if player:
            player.show_content("Current Real-Time Location", display_text)
            player.write_log("Successfully parsed GPS/Location data.")

        return f"Location acquired: {lat:.4f}, {lon:.4f} with {acc:.1f} meters accuracy."

    except Exception as e:
        error_str = f"Critical error in location plugin: {str(e)}"
        if player:
            player.write_log(error_str)
        return "An unexpected error occurred while accessing high-precision location."