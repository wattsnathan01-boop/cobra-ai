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

    function send(msg) {
        if (!sock.connected) return
        sock.write(JSON.stringify(msg) + "\n")
        sock.flush()
    }
    function hush() { send({ type: "hush" }) }
    function cancelListening() { send({ type: "listen", action: "cancel" }) }

    function handle(ev) {
        switch (ev.type) {
        case "hello":
            model = ev.model || ""; voice = ev.voice || ""; stt = ev.stt || ""
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
            if (confirmTool === "") { transcript = ev.text; reply = ""; error = "" }
            confirmTool = ""
            break
        case "delta":
            reply += ev.text
            break
        case "tool":
            tool = (ev.status === "done" || ev.status === "failed") ? "" : ev.name
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
