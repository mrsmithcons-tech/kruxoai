import json
import urllib.request

PLUGIN = {
    "name": "location_estimation",
    "description": "Estimates the user's general geographic location (City, Region, Country) based on their public IP address.",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": []
    }
}

def run(parameters: dict, player=None, session_memory=None) -> str:
    """
    Executes the location estimation plugin.
    Connects to an external API to resolve the public IP to geographic data.
    """
    url = "http://ip-api.com/json/"
    
    try:
        if player:
            player.write_log("Attempting to estimate location via IP...")

        with urllib.request.urlopen(url, timeout=10) as response:
            if response.status != 200:
                raise Exception(f"API returned status code {response.status}")
                
            data = json.loads(response.read().decode())

        if data.get("status") == "success":
            city = data.get("city", "Unknown City")
            region = data.get("regionName", "Unknown Region")
            country = data.get("country", "Unknown Country")
            
            location_string = f"{city}, {region}, {country}"
            display_text = (
                f"Estimated Location:\n"
                f"City: {city}\n"
                f"Region: {region}\n"
                f"Country: {country}\n"
                f"(Based on IP: {data.get('query', 'N/A')})"
            )

            if player:
                player.show_content("Geographic Location Estimate", display_text)
                player.write_log(f"Location estimated as: {location_string}")

            return f"Based on your network connection, your estimated location is {location_string}."
        
        else:
            message = data.get("message", "Unknown API error")
            raise Exception(f"API failed: {message}")

    except Exception as e:
        error_msg = f"Failed to estimate location: {str(e)}"
        if player:
            player.write_log(error_msg)
        return "I was unable to determine your location based on the network connection at this time."