"""The notebook: notes, diary, reminders and media that you, Cobra and Claude share.

Everything is plain files under one folder (~/notes/notebook by default), so it's readable
without Cobra and easy to back up:

    notes/<id>.md          one note per file: a few "key: value" lines, then Markdown
    media/<id>/<file>      photos, videos, voice memos and files attached to a note
    reminders.json         every reminder
    .cobra/activity.jsonl  what Cobra and Claude changed, with a copy of the file before,
    .cobra/undo/           so each change can be undone
    .cobra/trash/          deleted notes (never really deleted)

Inside a note, `<!-- by: cobra -->` marks who wrote the blocks that follow (you, cobra or
claude). Cobra writes through her tools (hands/notebook.py), Claude Code through the MCP
server (notebook/mcp_server.py), the window through the socket (notebook/service.py).
"""
from .store import AUTHORS, Notebook, NotebookError, current, parse_when  # noqa: F401
