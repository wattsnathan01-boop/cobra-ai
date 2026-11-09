"""Choosing a brain per question: local (free, on the GPU) or Claude (cloud, paid).

Modes: "local" and "claude" always use that brain; "auto" decides per question, rules first
(PLAN.md):
  1. "ask Claude" / "use local" in the question wins.
  2. Claude not set up or unreachable: local.
  3. Quick things (media, volume, system info, windows, apps, memory, small talk): local.
  4. Coding, files, explanations, writing, the web (search, news, weather, prices), longer
     questions: Claude, which has web search.
Screenshots are read by the local vision model either way, so the screen never leaves the
laptop.
"""
from __future__ import annotations

import logging
import re
from typing import AsyncIterator, Awaitable, Callable

from .ollama import BrainError

log = logging.getLogger(__name__)

MODES = ("local", "claude", "auto")

_ASK_CLAUDE = re.compile(r"\b(ask|use|with) claude\b|\bclaude,", re.IGNORECASE)
_USE_LOCAL = re.compile(r"\b(use|ask) (the )?local\b|\blocally\b", re.IGNORECASE)
_HEAVY = re.compile(
    r"\b(code|coding|script|program|function|class|bug|debug|error|traceback|exception|"
    r"compile|regex|refactor|explain|why|how (do|does|can|would|should)|what('s| is) the "
    r"difference|compare|plan|write|draft|essay|email|letter|summar\w*|translate|file|files|"
    r"config|configure|folder|edit|fix|terminal|command|shell|research|recommend|ideas?|"
    r"design|mock-?up|wireframe|layout|canvas|pencil|landing page|ui|"
    r"remind\w*|diary|jot|note (that|this|it|down)|"
    r"search|look up|look it up|google|news|latest|weather|forecast|price|prices|cost|"
    r"web|website|online|internet|open(ing)? (hours|times)|score|results?|"
    r"site|web ?page|tab|your browser|fill in|form|sign up|log ?in|"
    r"skills?|remotion|animat\w*|render\w*|(make|create|build) (me )?(a|an) (video|clip))\b",
    re.IGNORECASE)
_QUICK = re.compile(
    r"\b(volume|mute|unmute|louder|quieter|play|pause|resume|skip|next|previous|song|music|"
    r"playing|brightness|battery|charging|gpu|cpu|ram|memory|temperature|temp|hot|disk|space|"
    r"window|windows|workspace|fullscreen|float|open|launch|close|time|date|day|today|"
    r"remember|forget|hello|hi|hey|thanks|thank you|morning|night|how are you|screen|"
    r"watch|install|package)\b", re.IGNORECASE)
LONG_QUESTION_WORDS = 14
# a short answer to a question she just asked ("today at 6") stays with the brain that asked
FOLLOW_UP_WORDS = 8
# "ask Claude: …" / "use local, …" at the start is for the router, not the model
_LEADING_CHOICE = re.compile(r"^\s*(?:(?:please|hey|ok|okay)\W+)?(?:(?:ask|use|with) "
                             r"(?:claude|the local( brain| model)?|local)|locally)\b(?:\s+to\b)?"
                             r"[\s,:;.!-]*", re.IGNORECASE)


def strip_choice(text: str) -> str:
    """The question without a leading "ask Claude:" / "use local," (if anything is left)."""
    rest, n = _LEADING_CHOICE.subn("", text, count=1)
    rest = rest.strip()
    if not n or not rest:
        return text
    return rest[:1].upper() + rest[1:]


def choose(text: str, mode: str, claude_ready: bool) -> str:
    if mode == "local" or not claude_ready:
        return "local"
    if mode == "claude":
        return "claude"
    if _ASK_CLAUDE.search(text):
        return "claude"
    if _USE_LOCAL.search(text):
        return "local"
    if _HEAVY.search(text):
        return "claude"
    if _QUICK.search(text):
        return "local"
    return "claude" if len(text.split()) >= LONG_QUESTION_WORDS else "local"


class Router:
    """Looks like one brain to the agent; picks local or Claude at the start of each question
    and sticks with it for that question's tool steps."""

    def __init__(self, local, claude=None, mode: str = "local"):
        self.local = local
        self.claude = claude
        self.mode = mode if mode in MODES else "local"
        self.current = local
        self.background = local  # summaries etc. always run locally (free)

    @property
    def name(self) -> str:
        return self.current.name

    @property
    def model(self) -> str:
        return self.current.model

    async def select(self, text: str,
                     emit: Callable[[dict], Awaitable[None]] | None = None,
                     previous: str = "") -> str:
        """Pick the brain for this question; returns the question as the model should see it.
        previous: her last reply. If it asked something and this is a short answer, the same
        brain carries on (the other one wouldn't know what "today at 6" is about)."""
        follow_up = (self.mode == "auto" and previous.rstrip().endswith("?")
                     and len(text.split()) <= FOLLOW_UP_WORDS
                     and not _ASK_CLAUDE.search(text) and not _USE_LOCAL.search(text))
        if not follow_up:
            which = choose(text, self.mode, self.claude is not None)
            self.current = self.claude if which == "claude" else self.local
        if emit:
            await emit({"type": "brain", "name": self.current.name, "model": self.current.model})
        return strip_choice(text)

    async def chat(self, messages: list[dict], tools: list[dict],
                   context: str = "") -> AsyncIterator[dict]:
        if self.current is self.local:
            async for ev in self.local.chat(messages, tools, context):
                yield ev
            return
        produced = False
        try:
            async for ev in self.claude.chat(messages, tools, context):
                produced = True
                yield ev
        except BrainError as e:
            if produced:
                raise
            # Claude unreachable / out of credit before saying anything: answer locally
            log.warning("Claude failed (%s); answering locally", e)
            self.current = self.local
            async for ev in self.local.chat(messages, tools, context):
                yield ev

    def assistant_message(self, text: str, calls: list[dict]) -> dict:
        return self.current.assistant_message(text, calls)

    def tool_message(self, name: str, result: str, call_id: str | None = None) -> dict:
        return self.current.tool_message(name, result, call_id)

    async def ping(self) -> bool:
        return await self.local.ping()
