# Mac Medic — System Health Investigator

![license](https://img.shields.io/badge/license-MIT-blue)
![python](https://img.shields.io/badge/python-3.9%2B-blue)
![platform](https://img.shields.io/badge/platform-macOS-lightgrey)
![model](https://img.shields.io/badge/LLM-Gemini%202.5-orange)

An agentic terminal app that diagnoses macOS system health using Gemini.
Ask it a natural-language question and watch it reason step by step:

```
prompt → LLM → tool call → result → LLM → … → final answer
```

Every iteration prints the raw LLM response, the thought, the tool call,
and the tool result — so you can see exactly what the agent is doing.

## Example

```
  You: why is my mac slow right now?

──────────────────────────────────────────────────────────
  Investigating: why is my mac slow right now?
──────────────────────────────────────────────────────────

--- Iteration 1 ---
  [waiting 10s to respect rate limits (model: gemini-2.5-flash-lite)]
LLM raw: {"thought": "Check which processes use the most CPU first.", "tool_name": "list_top_processes", "tool_arguments": {"sort_by": "cpu", "limit": 10}}
  thought: Check which processes use the most CPU first.
  -> tool call: list_top_processes({'sort_by': 'cpu', 'limit': 10})
  -> result:
       PID   %CPU %MEM  RSS   COMMAND
       8823  92.4  4.1  680M  node
       ...

--- Iteration 2 ---
  ...

============================================================
  FINAL ANSWER
============================================================

  A runaway node process (pid 8823) is pinning the CPU…
```

## Setup

**1. Get a free Gemini API key** at https://aistudio.google.com/apikey

**2. Create `.env`** (or copy `.env.example`) next to `agent.py`:

```
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.5-flash-lite
```

**3. Run it:**

```bash
./run.sh
```

`run.sh` creates a virtualenv and installs deps on first run, then drops
you into the interactive chat loop. Type questions and press Enter. Type
`exit` (or Ctrl+C) to leave.

### Manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python agent.py
```

## What it can ask about

The agent has **read-only** access to standard macOS diagnostic commands:

| Tool | Uses |
|---|---|
| `list_top_processes` | `ps -Ao pid,pcpu,pmem,rss,comm` — top CPU/mem processes |
| `process_details` | `ps -p <pid> -o …` — full detail for one pid |
| `open_files_for_pid` | `lsof -p <pid>` — files a process has open |
| `network_connections_for_pid` | `lsof -i -a -p <pid>` — network activity per pid |
| `disk_usage` | `df -h` — free space on all mounts |
| `memory_stats` | `vm_stat` — page-ins, free, wired, compressed |
| `swap_usage` | `sysctl vm.swapusage` — swap pressure |
| `uptime_and_load` | `uptime` — load averages |
| `top_snapshot` | `top -l 1` — one-shot top with threads |
| `thermal_state` | `pmset -g therm` — thermal throttling |
| `load_averages` | `sysctl vm.loadavg` — numeric load avg |

Try asking:

- *why is my mac slow right now?*
- *which process is using the most memory?*
- *how full is my disk?*
- *is my mac thermally throttling?*
- *what's pid 8823 doing?*

## Configuration

All via `.env`:

| Variable | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | — | Required. |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` | Primary model. Flash-Lite is the cheapest / most generous free tier. |
| `GEMINI_FALLBACK_MODEL` | `gemini-2.5-flash` | Used automatically when the primary model hits a 429. Once switched, stays on the fallback for the rest of the session. |

## Safety

The agent is built to be **foolproof** — it cannot modify your system.

- **Read-only tools.** No `rm`, `kill`, `renice`, or anything destructive.
- **No sudo.** Nothing requires elevated privileges.
- **No `shell=True`.** Each tool is a hard-coded `argv` list. The LLM only
  picks a tool name and supplies validated enum/integer args — it never
  sees or constructs a shell command.
- **Argument validation.** `pid` and `limit` are type- and range-checked;
  `sort_by` is an enum. Defense-in-depth: any argv element containing shell
  metacharacters is rejected before execution:

  ```
  ;   |   &   >   <   $(   backtick
  ```

- **Subprocess timeouts.** Every command is killed after 5–10 seconds.
- **Output capped.** Tool output is truncated at 8KB so nothing floods
  memory or the LLM's context.
- **Iteration cap.** Hard stop at 8 agent steps — it always terminates.

## Rate limits

Gemini free tier limits: https://aistudio.google.com/rate-limit

The agent sleeps 10s before each LLM call to stay under free-tier RPM,
and falls back to a second model automatically if the primary hits a
429.

## Project layout

```
sys-health-agent/
├── agent.py          # agent loop + display formatting + chat()
├── llm.py            # Gemini client + primary/fallback model logic
├── tools.py          # tool registry + validated subprocess wrappers
├── run.sh            # venv bootstrap + launch
├── requirements.txt
├── .env              # your config (gitignored)
├── .env.example      # template
├── .gitignore
├── LICENSE
└── README.md
```

## Why it's "agentic"

The LLM alone can't answer "why is my Mac slow?" — it has no access to
your machine. This tool gives it a fixed menu of diagnostic commands
and lets it loop: pick a tool, read the result, decide what to check
next, repeat until it has enough evidence. That loop is the agent.

## License

[MIT](LICENSE).
