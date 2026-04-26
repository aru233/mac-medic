import subprocess

_FORBIDDEN_CHARS = frozenset(";|&><`$()")
_MAX_OUTPUT_BYTES = 8_000
_PID_MAX = 10_000_000


def _check_argv(argv: list[str]) -> None:
    for elem in argv:
        if not isinstance(elem, str):
            raise ValueError(f"argv element is not a string: {elem!r}")
        for ch in elem:
            if ch in _FORBIDDEN_CHARS:
                raise ValueError(f"forbidden character {ch!r} in argv element {elem!r}")


def _run(argv: list[str], timeout: int = 5) -> str:
    _check_argv(argv)
    try:
        result = subprocess.run(
            argv,
            timeout=timeout,
            capture_output=True,
            text=True,
            shell=False,
        )
        output = result.stdout or result.stderr or ""
        if len(output) > _MAX_OUTPUT_BYTES:
            truncated = len(output) - _MAX_OUTPUT_BYTES
            output = output[:_MAX_OUTPUT_BYTES] + f"\n…[truncated {truncated} bytes]"
        return output.strip() or "[no output]"
    except subprocess.TimeoutExpired:
        return f"[timeout after {timeout}s]"
    except FileNotFoundError as e:
        return f"[command not found: {e}]"
    except Exception as e:
        return f"[error: {e}]"


# ── individual tool functions ──────────────────────────────────────────────────

def _list_top_processes(sort_by: str, limit: int) -> str:
    if sort_by not in ("cpu", "mem"):
        return "[invalid sort_by: must be 'cpu' or 'mem']"
    if not isinstance(limit, int) or not (1 <= limit <= 20):
        return "[invalid limit: must be integer 1–20]"
    raw = _run(["ps", "-Ao", "pid,pcpu,pmem,rss,comm"])
    if raw.startswith("["):
        return raw
    lines = raw.splitlines()
    if not lines:
        return "[no output from ps]"
    header, *data = lines
    col = 1 if sort_by == "cpu" else 2
    try:
        data.sort(key=lambda l: float(l.split()[col]), reverse=True)
    except (IndexError, ValueError):
        pass
    return "\n".join([header] + data[:limit])


def _process_details(pid: int) -> str:
    if not isinstance(pid, int) or not (1 <= pid < _PID_MAX):
        return "[invalid pid]"
    return _run([
        "ps", "-p", str(pid), "-o",
        "pid,ppid,user,pcpu,pmem,rss,vsz,etime,state,comm,args",
    ])


def _open_files_for_pid(pid: int) -> str:
    if not isinstance(pid, int) or not (1 <= pid < _PID_MAX):
        return "[invalid pid]"
    raw = _run(["lsof", "-p", str(pid), "-n", "-P"], timeout=10)
    if raw.startswith("["):
        return raw
    lines = raw.splitlines()
    if len(lines) > 100:
        lines = lines[:100] + [f"…[{len(lines) - 100} more lines truncated]"]
    return "\n".join(lines)


def _network_connections_for_pid(pid: int) -> str:
    if not isinstance(pid, int) or not (1 <= pid < _PID_MAX):
        return "[invalid pid]"
    return _run(["lsof", "-i", "-a", "-p", str(pid), "-n", "-P"], timeout=10)


def _disk_usage() -> str:
    return _run(["df", "-h"])


def _memory_stats() -> str:
    return _run(["vm_stat"])


def _swap_usage() -> str:
    return _run(["sysctl", "-n", "vm.swapusage"])


def _uptime_and_load() -> str:
    return _run(["uptime"])


def _top_snapshot(sort_by: str, limit: int) -> str:
    if sort_by not in ("cpu", "mem"):
        return "[invalid sort_by: must be 'cpu' or 'mem']"
    if not isinstance(limit, int) or not (1 <= limit <= 15):
        return "[invalid limit: must be integer 1–15]"
    sort_flag = "cpu" if sort_by == "cpu" else "mem"
    return _run([
        "top", "-l", "1", "-n", str(limit),
        "-o", sort_flag,
        "-stats", "pid,command,cpu,mem,state,threads",
    ], timeout=15)


def _thermal_state() -> str:
    return _run(["pmset", "-g", "therm"])


def _load_averages() -> str:
    return _run(["sysctl", "-n", "vm.loadavg"])


# ── registry ───────────────────────────────────────────────────────────────────

TOOLS: dict[str, dict] = {
    "list_top_processes": {
        "fn": _list_top_processes,
        "declaration": {
            "name": "list_top_processes",
            "description": (
                "List the top processes on this Mac sorted by CPU or memory usage. "
                "Use this as the first step when diagnosing slowness."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sort_by": {
                        "type": "string",
                        "enum": ["cpu", "mem"],
                        "description": "Sort by 'cpu' or 'mem'.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "description": "Number of processes to return (1–20).",
                    },
                },
                "required": ["sort_by", "limit"],
            },
        },
    },
    "process_details": {
        "fn": _process_details,
        "declaration": {
            "name": "process_details",
            "description": "Get detailed info (CPU, memory, state, command) for a specific PID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {
                        "type": "integer",
                        "description": "The process ID to inspect.",
                    },
                },
                "required": ["pid"],
            },
        },
    },
    "open_files_for_pid": {
        "fn": _open_files_for_pid,
        "declaration": {
            "name": "open_files_for_pid",
            "description": "List files opened by a process. Useful for spotting runaway log writers or file leaks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {"type": "integer", "description": "The process ID."},
                },
                "required": ["pid"],
            },
        },
    },
    "network_connections_for_pid": {
        "fn": _network_connections_for_pid,
        "declaration": {
            "name": "network_connections_for_pid",
            "description": "Show network connections for a specific PID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pid": {"type": "integer", "description": "The process ID."},
                },
                "required": ["pid"],
            },
        },
    },
    "disk_usage": {
        "fn": lambda: _disk_usage(),
        "declaration": {
            "name": "disk_usage",
            "description": "Show disk usage for all mounted filesystems (df -h).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    "memory_stats": {
        "fn": lambda: _memory_stats(),
        "declaration": {
            "name": "memory_stats",
            "description": "Show macOS virtual memory stats (vm_stat): free pages, wired, compressed, page-ins/outs.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    "swap_usage": {
        "fn": lambda: _swap_usage(),
        "declaration": {
            "name": "swap_usage",
            "description": "Show swap (virtual memory) usage. High swap use indicates memory pressure.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    "uptime_and_load": {
        "fn": lambda: _uptime_and_load(),
        "declaration": {
            "name": "uptime_and_load",
            "description": "Show system uptime and 1/5/15-minute load averages.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    "top_snapshot": {
        "fn": _top_snapshot,
        "declaration": {
            "name": "top_snapshot",
            "description": (
                "Take a one-shot snapshot of top processes using the `top` command. "
                "Slower than list_top_processes but shows thread counts and process state."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sort_by": {
                        "type": "string",
                        "enum": ["cpu", "mem"],
                        "description": "Sort by 'cpu' or 'mem'.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 15,
                        "description": "Number of processes to return (1–15).",
                    },
                },
                "required": ["sort_by", "limit"],
            },
        },
    },
    "thermal_state": {
        "fn": lambda: _thermal_state(),
        "declaration": {
            "name": "thermal_state",
            "description": "Check macOS thermal state and CPU speed limits. Use when suspecting thermal throttling.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    "load_averages": {
        "fn": lambda: _load_averages(),
        "declaration": {
            "name": "load_averages",
            "description": "Return numeric 1/5/15-minute load averages via sysctl.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
}


def run_tool(name: str, args: dict) -> str:
    if name not in TOOLS:
        return f"[unknown tool: {name!r}]"
    tool = TOOLS[name]
    try:
        fn = tool["fn"]
        params = tool["declaration"]["parameters"].get("properties", {})
        if params:
            return fn(**args)
        else:
            return fn()
    except TypeError as e:
        return f"[bad args for {name}: {e}]"
    except Exception as e:
        return f"[tool error: {e}]"
