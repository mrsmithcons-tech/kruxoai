"""
network_speed_tester.py — JARVIS Plugin

Measures network latency (ping to 8.8.8.8 via socket connection timing) 
and network adapter throughput (sent/received MB/s) over a sample duration 
using psutil.net_io_counters().
"""

import time
import socket
import psutil

PLUGIN = {
    "name": "network_speed_tester",
    "description": "Measures network latency (ping to 8.8.8.8) and current network adapter throughput (sent and received MB/s).",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "duration": {
                "type": "INTEGER",
                "description": "Duration in seconds to sample network throughput (default 2 seconds)."
            },
            "ping_host": {
                "type": "STRING",
                "description": "Target IP or hostname to measure ping latency (default 8.8.8.8)."
            }
        },
        "required": []
    }
}


def measure_latency(host: str = "8.8.8.8", port: int = 53, timeout: float = 3.0) -> float:
    """
    Measures TCP connection handshake latency to specified host and port.
    Returns latency in milliseconds, or -1.0 on failure.
    """
    start_time = time.perf_counter()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()
        end_time = time.perf_counter()
        return round((end_time - start_time) * 1000, 2)
    except Exception:
        return -1.0


def run(parameters: dict = None, player=None, session_memory=None) -> str:
    """
    Main plugin entry point.
    Runs ping measurement and calculates net IO throughput over duration.
    """
    try:
        if parameters is None:
            parameters = {}

        duration = parameters.get("duration", 2)
        if not isinstance(duration, (int, float)) or duration <= 0:
            duration = 2

        ping_host = parameters.get("ping_host", "8.8.8.8")

        if player:
            player.write_log(f"[network_speed_tester] Measuring latency to {ping_host} and bandwidth over {duration}s...")

        # 1. Measure Latency (3 samples for average)
        latencies = []
        for _ in range(3):
            lat = measure_latency(host=ping_host)
            if lat >= 0:
                latencies.append(lat)
            time.sleep(0.1)

        avg_latency = round(sum(latencies) / len(latencies), 2) if latencies else None

        # 2. Measure IO Throughput over specified duration
        io_start = psutil.net_io_counters()
        time.sleep(duration)
        io_end = psutil.net_io_counters()

        bytes_sent = io_end.bytes_sent - io_start.bytes_sent
        bytes_recv = io_end.bytes_recv - io_start.bytes_recv

        mb_sent_per_sec = round((bytes_sent / (1024 * 1024)) / duration, 2)
        mb_recv_per_sec = round((bytes_recv / (1024 * 1024)) / duration, 2)

        # 3. Format Output
        latency_str = f"{avg_latency} ms" if avg_latency is not None else "Unreachable"

        display_text = (
            f"Target Ping ({ping_host}): {latency_str}\n"
            f"Sample Duration: {duration} sec\n\n"
            f"Download Speed: {mb_recv_per_sec} MB/s\n"
            f"Upload Speed:   {mb_sent_per_sec} MB/s"
        )

        if player:
            player.show_content("Network Diagnostics", display_text)
            player.write_log("[network_speed_tester] Completed network assessment successfully.")

        if avg_latency is not None:
            return f"Network test complete. Latency to {ping_host} is {avg_latency} milliseconds. Download speed is {mb_recv_per_sec} MB/s and upload speed is {mb_sent_per_sec} MB/s."
        else:
            return f"Network test complete. Could not reach {ping_host}. Download speed is {mb_recv_per_sec} MB/s and upload speed is {mb_sent_per_sec} MB/s."

    except Exception as e:
        error_msg = f"Failed to measure network speed: {str(e)}"
        if player:
            player.write_log(f"[network_speed_tester] Error: {error_msg}")
        return f"An error occurred while testing network speed: {str(e)}"