import threading
import time
import base64
import cv2

PLUGIN = {
    "name": "live_camera_analysis",
    "description": "Starts or stops a background process to periodically capture webcam frames and analyze them visually.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "active": {
                "type": "BOOLEAN",
                "description": "Whether to enable (true) or disable (false) background camera analysis."
            },
            "interval_seconds": {
                "type": "INTEGER",
                "description": "Interval between captures in seconds. Defaults to 5."
            }
        },
        "required": ["active"]
    }
}

# Global dictionary to track active analysis threads
_active_analyses = {}
_analyses_lock = threading.Lock()

def _analysis_loop(interval, player, session_memory):
    """Background thread function for capturing and analyzing frames."""
    thread_id = threading.get_ident()
    cap = cv2.VideoCapture(0)
    
    if player:
        player.write_log(f"Live camera analysis started (Thread ID: {thread_id}).")

    try:
        if not cap.isOpened():
            if player:
                player.write_log("Error: Could not open webcam for live analysis.")
            return

        while True:
            with _analyses_lock:
                if thread_id not in _active_analyses or not _active_analyses[thread_id]:
                    break
            
            ret, frame = cap.read()
            if ret:
                # Basic processing: Convert to base64 for vision LLM API, mock analysis here
                _, buffer = cv2.imencode('.jpg', frame)
                # base64_image = base64.b64encode(buffer).decode('utf-8')
                
                # MOCK ANALYSIS: In production, send base64_image to visual LLM endpoint
                # results = send_to_vision_llm(base64_image)
                results = "Mock analysis: User appears focused on screen."

                if player:
                     player.write_log(f"Camera analysis update: {results}")

            time.sleep(interval)

    except Exception as e:
        if player:
            player.write_log(f"Critical error in camera analysis loop: {str(e)}")
    finally:
        cap.release()
        if player:
            player.write_log(f"Live camera analysis stopped (Thread ID: {thread_id}).")

def run(parameters: dict, player=None, session_memory=None) -> str:
    """Activates or deactivates the background visual analysis loop."""
    try:
        active = parameters.get("active", False)
        interval = parameters.get("interval_seconds", 5)

        if active:
            # Check if there is already an active thread
            with _analyses_lock:
                # Kill existing threads if requested to start new, simple management
                for tid in list(_active_analyses.keys()):
                    _active_analyses[tid] = False
                
                # Start new analysis thread
                t = threading.Thread(
                    target=_analysis_loop, 
                    args=(interval, player, session_memory), 
                    daemon=True
                )
                t.start()
                # Store the state, associating it with the new thread ID
                time.sleep(0.1) # Small delay to let thread ID populate
                _active_analyses[t.ident] = True
            
            return "Live camera analysis has commenced in the background."

        else:
            # Stop analysis
            with _analyses_lock:
                for tid in list(_active_analyses.keys()):
                    _active_analyses[tid] = False
            
            return "Stopping background camera analysis."

    except Exception as e:
        error_msg = f"Failed to modify camera analysis state: {str(e)}"
        if player:
            player.write_log(error_msg)
        return "I encountered an error trying to adjust the live camera analysis."