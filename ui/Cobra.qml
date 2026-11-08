// Connection to cobrad: subscribes to its events and keeps the latest state for the UI.
import QtQuick
import Quickshell
import Quickshell.Io

Item {
    id: root

    property bool online: false
    property string mode: "idle"        // idle | listening | thinking | speaking
    property string transcript: ""      // what you said (live while listening)
    property string reply: ""           // what she's saying
    property string tool: ""            // tool being used right now
    property string confirmTool: ""     // waiting for yes/no on this tool
    property string error: ""
    property string model: ""
    property string voice: ""
    property string stt: ""
    property real micLevel: 0
    property real voiceLevel: 0

    property bool hudOpen: false
    property bool wakeOn: false          // listening for "Cobra"
    property var stats: ({})            // system_stats + playing, polled while the HUD is open
    // recent tool calls, newest first: {name, detail, status: running|done|failed, ms}
    property ListModel actions: ListModel {}

    // reply timing for the HUD: when you finished asking, her first word, words since
    property double askedAt: 0
    property double firstWordAt: 0
    property double lastWordAt: 0
    property int words: 0

    function send(msg) {
        if (!sock.connected) return
        sock.write(JSON.stringify(msg) + "\n")
        sock.flush()
    }
    function hush() { send({ type: "hush" }) }
    function ask(text) { send({ type: "ask", text: text, speak: true }) }
    function toggleListening() { send({ type: "listen", action: "toggle" }) }
    function requestStats() { send({ type: "stats" }) }

    function summarise(args) {
        const parts = Object.keys(args || {}).map(k => String(args[k]))
        return parts.length ? parts.join(" \u00b7 ") : "no arguments"
    }
    function cancelListening() { send({ type: "listen", action: "cancel" }) }

    function handle(ev) {
        switch (ev.type) {
        case "hello":
            model = ev.model || ""; voice = ev.voice || ""; stt = ev.stt || ""
            wakeOn = !!ev.wake
            break
        case "state":
            if (ev.state === "listening" && mode !== "listening") {
                transcript = ""; reply = ""; tool = ""; error = ""
            }
            if (ev.state !== "thinking") tool = ""
            mode = ev.state
            break
        case "partial":
            transcript = ev.text
            break
        case "heard":
            if (confirmTool === "") {
                transcript = ev.text; reply = ""; error = ""
                askedAt = Date.now(); firstWordAt = 0; lastWordAt = 0; words = 0
            }
            confirmTool = ""
            break
        case "delta":
            reply += ev.text
            if (firstWordAt === 0) firstWordAt = Date.now()
            lastWordAt = Date.now()
            words++
            break
        case "tool":
            tool = (ev.status === "done" || ev.status === "failed") ? "" : ev.name
            if (ev.status === "checking") {
                actions.insert(0, { name: ev.name, detail: summarise(ev.args),
                                    status: "running", ms: 0 })
                while (actions.count > 4) actions.remove(actions.count - 1)
            } else if ((ev.status === "done" || ev.status === "failed") && actions.count > 0
                       && actions.get(0).name === ev.name) {
                actions.setProperty(0, "status", ev.status)
                actions.setProperty(0, "ms", ev.ms || 0)
            }
            break
        case "hud":
            hudOpen = ev.action === "toggle" ? !hudOpen : ev.action === "show"
            break
        case "wake":
            wakeOn = !!ev.on
            break
        case "stats":
            stats = ev
            break
        case "confirm":
            confirmTool = ev.tool
            break
        case "error":
            error = ev.message
            break
        case "level":
            if (ev.source === "mic") micLevel = ev.value
            else voiceLevel = ev.value
            break
        }
    }

    Socket {
        id: sock
        path: (Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/cobra.sock"
        connected: true
        onConnectedChanged: {
            root.online = connected
            if (connected) root.send({ type: "subscribe" })
            else root.mode = "idle"
        }
        parser: SplitParser {
            onRead: line => {
                try { root.handle(JSON.parse(line)) } catch (e) { console.warn("cobra: bad event", line) }
            }
        }
    }

    // cobrad not running yet, or restarted: keep trying
    Timer {
        interval: 2000
        repeat: true
        running: !sock.connected
        onTriggered: sock.connected = true
    }
}
