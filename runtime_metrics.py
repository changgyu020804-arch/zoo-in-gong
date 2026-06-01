from pathlib import Path


def get_process_memory_mb():
    try:
        status = Path("/proc/self/status").read_text(encoding="utf-8")
    except OSError:
        return None

    for line in status.splitlines():
        if line.startswith("VmRSS:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) / 1024
    return None
