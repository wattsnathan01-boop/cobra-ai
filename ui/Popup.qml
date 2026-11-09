// Mini pop-up: top-right, under the bar. Appears when Cobra is listening, thinking or speaking,
// and lingers a few seconds after she finishes so you can read the answer.
import QtQuick
import QtQuick.Effects
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: win

    required property Cobra cobra
    property Theme theme: Theme {}

    readonly property int glow: 18  // room around the card for its glow
    readonly property bool active: cobra.mode !== "idle"
    readonly property bool watching: cobra.screenState === "watching" && !active && !linger.running
    readonly property bool shown: (active || linger.running || watching) && !cobra.hudOpen
    readonly property string mode: cobra.mode
    readonly property color accent: watching || (cobra.error !== "" && !active) ? theme.crimson
                                                                                : theme.accent(mode)

    anchors { top: true; right: true }
    margins { top: 10 - glow; right: 12 - glow }
    exclusionMode: ExclusionMode.Normal
    exclusiveZone: 0
    implicitWidth: 420 + 2 * glow
    implicitHeight: card.height + 2 * glow
    color: "transparent"
    visible: card.opacity > 0
    mask: Region { item: card }

    WlrLayershell.namespace: "cobra"
    WlrLayershell.layer: WlrLayer.Overlay

    Timer { id: linger; interval: 5000 }
    onActiveChanged: if (!active) linger.restart()

    readonly property string mainText: {
        if (mode === "listening")
            return cobra.transcript !== "" ? "“" + cobra.transcript + "”" : "Listening…"
        if (mode === "thinking")
            return cobra.confirmTool !== ""
                ? "Allow " + cobra.confirmTool.replace(/_/g, " ") + "? "
                  + (cobra.wakeOn ? "Say yes or no" : "Hold SUPER+C, say yes or no")
                : "Thinking · " + (cobra.answering === "claude"
                                   ? "Claude · " + cobra.answeringModel.replace("claude-", "")
                                   : "local · " + cobra.model)
        if (mode === "speaking")
            return tail(cobra.reply.trim(), 72)
        if (watching)
            return "I can see your screen" + (cobra.screenWindows.length
                                              ? " \u00b7 " + cobra.screenWindows.join(", ") : "")
        return cobra.error || cobra.reply.trim()
            || (cobra.wakeOn ? "Say \u201cCobra\u201d or hold SUPER+C" : "Hold SUPER+C to talk")
    }
    readonly property string caption: {
        if (mode === "listening") return cobra.stt.split("-")[0] === "large"
                                         ? "whisper · live transcript" : "live transcript"
        if (mode === "thinking") return cobra.tool !== "" ? "tool: " + cobra.tool
                                       : cobra.transcript !== "" ? "you: " + cobra.transcript : ""
        if (mode === "speaking") return "piper · " + cobra.voice.split("-")[0]
        if (watching) return "WATCHING \u00b7 local vision \u00b7 nothing leaves this laptop"
        return !cobra.online ? "cobrad offline"
             : cobra.wakeOn ? "wake word armed" : "push-to-talk ready"
    }
    // Nerd Font Material Design icons
    readonly property string icon: String.fromCodePoint(
        mode === "listening" ? 0xF036C      // microphone
      : mode === "thinking" ? 0xF0772       // loading
      : mode === "speaking" ? 0xF057E       // volume-high
      : watching ? 0xF0209                  // eye-off: stop watching
      : 0xF0594)                            // weather-night

    // while she talks, show the end of what she's saying rather than the start
    function tail(s, n) {
        if (s.length <= n) return s
        const cut = s.slice(-n)
        return "\u2026" + cut.slice(cut.indexOf(" ") + 1)
    }

    Rectangle {
        id: card
        x: win.glow
        y: win.glow
        width: 420
        height: 96
        radius: 14
        color: win.theme.bg
        border.width: 1
        border.color: Qt.alpha(win.accent, 0.55)
        opacity: win.shown ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
        Behavior on border.color { ColorAnimation { duration: 250 } }

        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Qt.alpha(win.accent, 0.45)
            shadowBlur: 1.0
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
        }

        Avatar {
            id: face
            anchors { left: parent.left; leftMargin: 16; verticalCenter: parent.verticalCenter }
            ring: win.accent
            mode: win.mode
            level: win.mode === "listening" ? win.cobra.micLevel : win.cobra.voiceLevel
        }

        Column {
            anchors {
                left: face.right; leftMargin: 16
                right: button.left; rightMargin: 12
                verticalCenter: parent.verticalCenter
            }
            spacing: 8

            Text {
                width: parent.width
                text: win.mainText
                color: win.mode === "idle" && win.cobra.reply === "" && win.cobra.error === ""
                       ? win.theme.muted : win.theme.text
                font { family: win.theme.mono; pixelSize: 13 }
                wrapMode: Text.Wrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }

            Row {
                spacing: 8
                VoiceBars {
                    mode: win.mode
                    level: win.mode === "listening" ? win.cobra.micLevel : win.cobra.voiceLevel
                    color: win.accent
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: win.caption
                    color: win.theme.muted
                    font { family: win.theme.mono; pixelSize: 10 }
                    elide: Text.ElideRight
                    width: Math.min(implicitWidth, 220)
                }
            }
        }

        // listening: cancel · thinking/speaking: stop her · idle: dismiss
        Rectangle {
            id: button
            anchors { right: parent.right; rightMargin: 16; verticalCenter: parent.verticalCenter }
            width: 32
            height: 32
            radius: 8
            color: Qt.alpha(win.accent, mouse.containsMouse ? 0.25 : 0.12)

            Text {
                anchors.centerIn: parent
                text: win.icon
                color: win.accent
                font { family: win.theme.mono; pixelSize: 17 }
                RotationAnimator on rotation {
                    from: 0; to: 360; duration: 1200; loops: Animation.Infinite
                    running: win.mode === "thinking"
                }
                onTextChanged: rotation = 0
            }

            MouseArea {
                id: mouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    if (win.watching) win.cobra.stopWatching()
                    else if (win.mode === "listening") win.cobra.cancelListening()
                    else if (win.active) win.cobra.hush()
                    else linger.stop()
                }
            }
        }
    }
}
