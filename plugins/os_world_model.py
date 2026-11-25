import psutil
import os
import shutil
import platform
import json

PLUGIN = {
    "name": "os_world_model",
    "description": "Allows perception and manipulation of the operating system file structure, active processes, and system information.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["get_system_overview", "list_files", "get_process_info", "read_file_tail"],
                "description": "The specific integration action to perform."
            },
            "path": {
                "type": "STRING",
                "description": "Path required for 'list_files' or 'read_file_tail'."
            },
            "pid": {
                "type": "INTEGER",
                "description": "Process ID required for 'get_process_info'."
            }
        },
        "required": ["action"]
    }
}

def get_size(bytes, suffix="B"):
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor

def get_system_overview():
    uname = platform.uname()
    cpufreq = psutil.cpu_freq()
    svmem = psutil.virtual_memory()
    partitions = psutil.disk_partitions()
    
    disk_info = []
    for partition in partitions:
        try:
            partition_usage = psutil.disk_usage(partition.mountpoint)
            disk_info.append({
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "total": get_size(partition_usage.total),
                "used": get_size(partition_usage.used),
                "free": get_size(partition_usage.free),
                "percent": partition_usage.percent
            })
        except PermissionError:
            continue

    return {
        "system": uname.system,
        "node": uname.node,
        "release": uname.release,
        "machine": uname.machine,
        "cpu_cores": psutil.cpu_count(logical=True),
        "cpu_max_freq": f"{cpufreq.max:.2f}Mhz",
        "memory_total": get_size(svmem.total),
        "memory_used": get_size(svmem.used),
        "disks": disk_info
    }

def list_files(path):
    if not path or not os.path.exists(path):
        return {"error": "Invalid path provided."}
    
    items = []
    try:
        with os.scandir(path) as it:
            for entry in it:
                info = {
                    "name": entry.name,
                    "is_file": entry.is_file(),
                    "size": get_size(entry.stat().st_size) if entry.is_file() else None
                }
                items.append(info)
        return {"path": path, "items": items}
    except PermissionError:
        return {"error": f"Permission denied for entry: {path}"}

def get_process_info(pid):
    try:
        p = psutil.Process(pid)
        return {
            "pid": p.pid,
            "name": p.name(),
            "status": p.status(),
            "cpu_percent": p.cpu_percent(),
            "memory_info": p.memory_info()._asdict()
        }
    except psutil.NoSuchProcess:
        return {"error": f"No process found with PID: {pid}"}

def read_file_tail(path, lines=20):
    if not path or not os.path.isfile(path):
        return {"error": "Invalid file path provided."}
    
    try:
        with open(path, 'rb') as f:
            f.seek(0, os.SEEK_END)
            buffer = bytearray()
            pointer = f.tell()
            count = 0
            
            while pointer >= 0 and count <= lines:
                f.seek(pointer)
                char = f.read(1)
                if char == b'\n':
                    count += 1
                buffer.extend(char)
                pointer -= 1
                
        return {"path": path, "content": buffer[::-1].decode('utf-8', errors='replace')}
    except Exception as e:
        return {"error": str(e)}

def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        action = parameters.get("action")
        result_data = {}
        summary = ""

        if player:
            player.write_log(f"OS World Model accessing: {action}")

        if action == "get_system_overview":
            result_data = get_system_overview()
            summary = "System overview retrieved successfully."
        elif action == "list_files":
            path = parameters.get("path", ".")
            result_data = list_files(path)
            summary = f"File list for '{path}' retrieved."
        elif action == "get_process_info":
            pid = parameters.get("pid")
            if pid is None:
                return "Error: Missing parameter 'pid'."
            result_data = get_process_info(pid)
            summary = f"Information for PID {pid} retrieved."
        elif action == "read_file_tail":
            path = parameters.get("path")
            result_data = read_file_tail(path)
            summary = f"Tail of file '{path}' retrieved."
        else:
            return "Error: Unknown action."

        formatted_json = json.dumps(result_data, indent=2)
        
        if player:
            player.show_content(f"OS Reality Layer - {action}", formatted_json)
        
        return summary

    except Exception as e:
        if player:
            player.write_log(f"Error in os_world_model: {str(e)}")
        return f"I encountered an internal error accessing the operating system structure: {str(e)}"