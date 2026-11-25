import subprocess
import json
import logging

PLUGIN = {
    "name": "audio_device_switcher",
    "description": "Inspects audio output devices, sets the default playback device, or adjusts audio volume using PowerShell/Windows audio APIs.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "The action to perform: 'list' (list audio devices), 'set_default' (change default playback device), or 'set_volume' (set master volume level 0-100)."
            },
            "device_name": {
                "type": "STRING",
                "description": "Target device name or partial name (used when action is 'set_default')."
            },
            "volume_level": {
                "type": "INTEGER",
                "description": "Volume percentage from 0 to 100 (used when action is 'set_volume')."
            }
        },
        "required": ["action"]
    }
}

def _run_powershell(script: str) -> tuple[int, str, str]:
    """Helper to execute PowerShell commands safely."""
    try:
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return -1, "", str(e)

def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        action = parameters.get("action", "list").lower()
        device_name = parameters.get("device_name", "")
        volume_level = parameters.get("volume_level", None)

        if player:
            player.write_log(f"[AudioDeviceSwitcher] Executing action: {action}")

        if action == "list":
            ps_script = """
            Get-CimInstance Win32_SoundDevice | Select-Object Name, Status, DeviceID | ConvertTo-Json
            """
            code, out, err = _run_powershell(ps_script)
            if code != 0 or not out:
                return "Failed to retrieve audio devices from the system."
            
            try:
                devices = json.loads(out)
                if isinstance(devices, dict):
                    devices = [devices]
                
                device_list_str = "\n".join([f"• {d.get('Name', 'Unknown Device')} ({d.get('Status', 'OK')})" for d in devices])
                display_text = f"Available Audio Devices:\n\n{device_list_str}"
                
                if player:
                    player.show_content("Audio Devices", display_text)
                
                return f"Found {len(devices)} audio device(s). Displaying them on screen."
            except Exception:
                return f"Audio devices found:\n{out}"

        elif action == "set_default":
            if not device_name:
                return "Please specify a device name to set as default."

            # Attempts to use AudioDeviceCmdlets or falls back to ncmdump/ncat/powershell audio device setting via standard WMI/COM where available
            ps_script = f"""
            if (Get-Module -ListAvailable -Name AudioDeviceCmdlets) {{
                Import-Module AudioDeviceCmdlets
                $dev = Get-AudioDevice -List | Where-Object {{ $_.Name -like "*{device_name}*" }} | Select-Object -First 1
                if ($dev) {{
                    Set-AudioDevice -Index $dev.Index | Out-Null
                    Write-Output "SUCCESS: $($dev.Name)"
                }} else {{
                    Write-Error "Device not found"
                }}
            }} else {{
                # Fallback: Check device presence via WMI
                $dev = Get-CimInstance Win32_SoundDevice | Where-Object {{ $_.Name -like "*{device_name}*" }} | Select-Object -First 1
                if ($dev) {{
                    Write-Output "FOUND: $($dev.Name). (Install AudioDeviceCmdlets PowerShell module for full seamless switching)."
                }} else {{
                    Write-Error "Device not found"
                }}
            }}
            """
            code, out, err = _run_powershell(ps_script)
            if "SUCCESS" in out:
                dev_matched = out.replace("SUCCESS:", "").strip()
                if player:
                    player.show_content("Audio Output Changed", f"Default playback device set to:\n{dev_matched}")
                return f"Switched default audio playback to {dev_matched}."
            elif "FOUND" in out:
                dev_matched = out.replace("FOUND:", "").strip()
                return f"Found device {dev_matched}, but AudioDeviceCmdlets module is required to change defaults automatically."
            else:
                return f"Could not find an audio device matching '{device_name}'."

        elif action == "set_volume":
            if volume_level is None or not (0 <= volume_level <= 100):
                return "Please provide a valid volume level between 0 and 100."

            # Uses SVolume / WScript COM Object via PowerShell to adjust master volume safely
            normalized_vol = volume_level / 100.0
            ps_script = f"""
            $wsh = New-Object -ComObject WScript.Shell
            # Adjust master volume via Windows CoreAudio API via inline C#
            $code = @'
            using System.Runtime.InteropServices;
            public class Audio {{
                [DllImport("user32.dll")]
                public static extern void keybd_event(byte bVk, byte bScan, uint dwFlags, uint dwExtraInfo);
            }}
'@
            Add-Type -TypeDefinition $code
            # Set volume via sound master endpoint if possible, or send volume keys
            [Math]::Min(100, [Math]::Max(0, {volume_level}))
            """
            # Alternative: WScript SendKeys loop or nircmd/endpoint volume
            ps_script_vol = f"""
            $obj = New-Object -ComObject WScript.Shell
            # Execute standard PowerShell audio volume adjustment script snippet
            Add-Type -TypeDefinition @"
            using System.Runtime.InteropServices;
            [Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
            interface IAudioEndpointVolume {{
                int f(); int g(); int h(); int i();
                int SetMasterVolumeLevelScalar(float fLevel, System.Guid pguidEventContext);
            }}
            [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
            interface IMMDevice {{
                int Activate(ref System.Guid id, int clsCtx, System.IntPtr activationParams, [MarshalAs(UnmanagedType.IUnknown)] out object interfacePointer);
            }}
            [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
            interface IMMDeviceEnumerator {{
                int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
            }}
            [ComImport, Guid("BCDE0385-4926-4AEB-B8B7-0A67011A638B")] class MMDeviceEnumeratorComObject {{ }}
            public class AudioControl {{
                public static void SetVolume(float level) {{
                    var enumerator = (IMMDeviceEnumerator)(new MMDeviceEnumeratorComObject());
                    IMMDevice dev;
                    enumerator.GetDefaultAudioEndpoint(0, 1, out dev);
                    var iid = typeof(IAudioEndpointVolume).GUID;
                    object obj;
                    dev.Activate(ref iid, 23, System.IntPtr.Zero, out obj);
                    var vol = (IAudioEndpointVolume)obj;
                    vol.SetMasterVolumeLevelScalar(level, System.Guid.Empty);
                }}
            }}
"@
            [AudioControl]::SetVolume({normalized_vol})
            """
            code, out, err = _run_powershell(ps_script_vol)
            if code == 0:
                if player:
                    player.write_log(f"[AudioDeviceSwitcher] Volume set to {volume_level}%")
                return f"Master volume set to {volume_level} percent."
            else:
                return f"Failed to set volume level. Error details: {err if err else 'Unknown error'}"

        else:
            return f"Unsupported action '{action}'. Supported actions are: list, set_default, set_volume."

    except Exception as e:
        logging.error(f"Error in audio_device_switcher plugin: {e}", exc_info=True)
        return "An error occurred while managing audio devices."