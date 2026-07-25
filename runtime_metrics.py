import platform
from pathlib import Path


def get_process_memory_mb():
    """Return RSS memory usage in MB for the current process.

    Supports Linux (/proc/self/status) and Windows (via ctypes).
    Returns None if memory info is unavailable.
    """
    if platform.system() == "Windows":
        return _get_memory_windows()
    return _get_memory_linux()


def _get_memory_linux():
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


def _get_memory_windows():
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        psapi = ctypes.windll.psapi
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetCurrentProcess()
        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return counters.WorkingSetSize / (1024 * 1024)
    except (OSError, AttributeError, ValueError):
        pass
    return None
