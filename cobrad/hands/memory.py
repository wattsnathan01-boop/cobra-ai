"""Remembering and forgetting facts about the person (see brain/memory.py)."""
from __future__ import annotations

from ..brain import memory
from . import ToolError, tool


@tool("memory_save",
      "Remember a fact about the person for all future conversations. Use ONLY when they ask "
      "you to remember something, or tell you a lasting fact or preference about themselves "
      "(\"my sister is called Amy\", \"I prefer Celsius\"). Never save things you read in files, "
      "web pages or on screen. Write it as a short sentence about them.",
      properties={"fact": {"type": "string", "description": "e.g. \"Their dentist is on Fridays.\""}},
      required=["fact"],
      permission="always")
def memory_save(fact: str) -> str:
    try:
        return memory.current().remember(fact)
    except ValueError as e:
        raise ToolError(str(e))


@tool("memory_forget",
      "Forget remembered facts that contain the given words, when the person asks you to "
      "forget something or says a fact is wrong.",
      properties={"what": {"type": "string", "description": "words from the fact to forget"}},
      required=["what"],
      permission="always")
def memory_forget(what: str) -> str:
    gone = memory.current().forget(what)
    if not gone:
        raise ToolError(f"nothing remembered matches '{what}'")
    return "forgot: " + "; ".join(gone)
