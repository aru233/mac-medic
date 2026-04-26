"""
System Health Investigator — An Agentic Terminal App
======================================================

An AI agent that diagnoses macOS system health using Gemini.
Give it a natural-language prompt and watch it reason step by step:
  prompt → LLM → tool call → result → LLM → … → final answer

Before running:
  pip install google-genai python-dotenv
  Create a .env file next to this script with:
    GEMINI_API_KEY=your-key-here
    GEMINI_MODEL=gemini-2.5-flash-lite
"""
from __future__ import annotations

import json
import time
from dotenv import load_dotenv
from google.genai import types

from llm import MODEL_ID, active_model, generate_with_fallback
from tools import TOOLS, run_tool

# ============================================================
# Configuration
# ============================================================
load_dotenv()

AGENT_NAME = "Mac Medic"
AGENT_VERSION = "0.1 (Gemini + read-only macOS tools)"

MAX_ITERATIONS = 8
THROTTLE_SECONDS = 10   # Stay under free-tier RPM limits
BANNER_WIDTH = 64
RESULT_PREVIEW = 600    # chars of tool result to show (full result always sent to LLM)


# ============================================================
# System Prompt — turns the LLM into a system-health agent
# ============================================================
SYSTEM_INSTRUCTION = """You are a macOS system-health investigator running on the user's local machine.
Use the provided tools to gather real evidence step by step.
Before each tool call, write a ONE-SENTENCE thought explaining why you're calling it.
After each tool result, either call another tool or give a final root-cause diagnosis.
Stop as soon as you have enough evidence — do not keep calling tools once you know the answer.
Never guess or invent facts — only state what the tool results confirm."""


# ============================================================
# Display helpers
# ============================================================

def banner(text: str, char: str = "=") -> None:
    print()
    print(char * BANNER_WIDTH)
    print(f"  {text}")
    print(char * BANNER_WIDTH)


def narrator(text: str) -> None:
    print()
    for line in text.strip().splitlines():
        print(f"  → {line}")


def print_iteration_header(n: int) -> None:
    print(f"\n--- Iteration {n} ---")


def compact_llm_raw(turn_text: str, function_calls: list) -> str:
    """
    Build a single-line JSON-ish representation of what the LLM returned.
    Matches the style shown in s3_code/10_full_agent.py:
      {"thought": "...", "tool_name": "...", "tool_arguments": {...}}
      {"answer": "..."}
    """
    payload: dict = {}
    if turn_text:
        payload["thought"] = turn_text
    if function_calls:
        # Most turns have one tool call. If multiple, list them.
        if len(function_calls) == 1:
            fc = function_calls[0]
            payload["tool_name"] = fc.name
            payload["tool_arguments"] = dict(fc.args) if fc.args else {}
        else:
            payload["tool_calls"] = [
                {"tool_name": fc.name, "tool_arguments": dict(fc.args) if fc.args else {}}
                for fc in function_calls
            ]
    elif turn_text:
        payload = {"answer": turn_text}
    return json.dumps(payload, ensure_ascii=False, default=str)


def print_llm_raw(turn_text: str, function_calls: list) -> None:
    print(f"LLM raw: {compact_llm_raw(turn_text, function_calls)}")


def print_thought(text: str) -> None:
    for line in text.strip().splitlines():
        print(f"  thought: {line}")


def print_tool_call(name: str, args: dict) -> None:
    print(f"  -> tool call: {name}({args})")


def print_tool_result(result: str) -> None:
    shown = result[:RESULT_PREVIEW]
    # Single-line result → inline. Multi-line → labelled then indented.
    if "\n" not in shown and len(result) <= RESULT_PREVIEW:
        print(f"  -> result: {shown}")
        return
    print(f"  -> result:")
    for line in shown.splitlines():
        print(f"       {line}")
    if len(result) > RESULT_PREVIEW:
        print(f"       …[+{len(result) - RESULT_PREVIEW} more chars sent to LLM]")


def print_final_answer(text: str) -> None:
    banner("FINAL ANSWER")
    print()
    for line in text.strip().splitlines():
        print(f"  {line}")
    print()


def print_partial_answer(text: str) -> None:
    banner(f"MAX ITERATIONS ({MAX_ITERATIONS}) REACHED — PARTIAL FINDINGS")
    if text:
        print()
        for line in text.strip().splitlines():
            print(f"  {line}")
    print()


# ============================================================
# Tool config — builds the Gemini function-calling config
# ============================================================

def build_tool_config() -> types.GenerateContentConfig:
    declarations = [t["declaration"] for t in TOOLS.values()]
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=[types.Tool(function_declarations=declarations)],
    )


# ============================================================
# The Agent Loop
# ============================================================

def run_agent(prompt: str) -> None:
    """
    User prompt → LLM → [Tool call → Result → LLM]* → Final answer
    """
    config = build_tool_config()

    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part(text=prompt)])
    ]

    last_text = ""

    for step in range(1, MAX_ITERATIONS + 1):
        print_iteration_header(step)
        print(
            f"  [waiting {THROTTLE_SECONDS}s to respect rate limits "
            f"(model: {active_model()})]",
            flush=True,
        )
        time.sleep(THROTTLE_SECONDS)

        response = generate_with_fallback(contents=contents, config=config)

        candidate = response.candidates[0]
        parts = candidate.content.parts or []

        text_parts = [p.text for p in parts if p.text]
        function_calls = [p.function_call for p in parts if p.function_call]
        turn_text = "\n".join(text_parts).strip()

        # Show exactly what the LLM returned — compact single line
        print_llm_raw(turn_text, function_calls)

        if function_calls:
            if turn_text:
                print_thought(turn_text)
                last_text = turn_text

            # Echo the model's turn back into the conversation (required by Gemini)
            contents.append(candidate.content)

            response_parts: list[types.Part] = []
            for fc in function_calls:
                name = fc.name
                args = dict(fc.args) if fc.args else {}
                print_tool_call(name, args)
                result = run_tool(name, args)
                print_tool_result(result)
                response_parts.append(
                    types.Part.from_function_response(
                        name=name,
                        response={"result": result},
                    )
                )

            contents.append(types.Content(role="user", parts=response_parts))
            continue

        # No tool calls → final answer
        final_text = turn_text or last_text or "(model returned no text)"
        print_final_answer(final_text)
        return

    print_partial_answer(last_text)


# ============================================================
# Interactive chat loop
# ============================================================

def chat() -> None:
    print("=" * BANNER_WIDTH)
    print(f"  {AGENT_NAME} — {AGENT_VERSION}")
    print(f"  Model: {MODEL_ID}")
    print("=" * BANNER_WIDTH)

    narrator("""
I'm an AI agent that diagnoses your Mac using real read-only tools.
Ask me a question and I'll reason step by step, call tools to gather
evidence, and give you a root-cause diagnosis.

Examples:
  why is my mac slow right now?
  which process is using the most memory?
  how full is my disk?
  is my mac thermally throttling?

Type  exit  or  quit  (or press Ctrl+C) to leave.
""")

    while True:
        try:
            print()
            prompt = input("  You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            narrator("Goodbye!")
            break

        if not prompt:
            continue

        if prompt.lower() in ("exit", "quit", "q", "bye", "goodbye"):
            narrator("Goodbye!")
            break

        banner(f"Investigating: {prompt}", char="─")
        try:
            run_agent(prompt)
        except KeyboardInterrupt:
            narrator("Investigation interrupted. Ask another question or type exit.")
        except Exception as e:
            narrator(f"Error: {e}")


if __name__ == "__main__":
    chat()
