"""Read-only capability inventory; no automatic performance claims."""
import os
import platform
import shutil
import subprocess


def hardware_inventory():
    devices = []
    executable = shutil.which("nvidia-smi")
    if executable:
        try:
            result = subprocess.run([executable, "--query-gpu=name,memory.total,memory.free",
                                     "--format=csv,noheader,nounits"], capture_output=True,
                                    text=True, timeout=3, check=True)
            for line in result.stdout.splitlines():
                name, total, free = [part.strip() for part in line.split(",")]
                devices.append({"name": name, "total_mib": int(total), "free_mib": int(free)})
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return {"os": platform.system(), "architecture": platform.machine(),
            "logical_cpus": os.cpu_count(), "nvidia_devices": devices,
            "gpu_detection": "available" if devices else "unavailable",
            "note": "GPU visibility does not prove model offload; verify the inference runtime separately"}
