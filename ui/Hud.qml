// Full HUD: opens over the focused monitor with `cobractl hud` (bound to SUPER+SHIFT+C).
// ESC closes it, TAB types a question instead of speaking.
import QtQuick
import QtQuick.Shapes
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland

PanelWindow {
    id: hud

    required property Cobra cobra
    property Theme theme: Theme {}
    property bool typing: false

    readonly property string mode: cobra.mode
    readonly property color accent: theme.accent(mode)

    anchors { top: true; bottom: true; left: true; right: true }
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"
    visible: content.opacity > 0

    WlrLayershell.namespace: "cobra-hud"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: cobra.hudOpen ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    Connections {
        target: hud.cobra
        function onHudOpenChanged() {
            if (!hud.cobra.hudOpen) return
            // open on whichever monitor you're using
            const name = Hyprland.focusedMonitor ? Hyprland.focusedMonitor.name : ""
            hud.screen = Quickshell.screens.find(s => s.name === name) || Quickshell.screens[0]
            hud.typing = false
            content.forceActiveFocus()
        }
    }

    Timer {
        interval: 2000
        repeat: true
        triggeredOnStart: true
        running: hud.cobra.hudOpen
        onTriggered: hud.cobra.requestStats()
    }

    function tail(s, n) {
        if (s.length <= n) return s
        const cut = s.slice(-n)
        return "…" + cut.slice(cut.indexOf(" ") + 1)
    }

    component IconButton: Rectangle {
        id: btn
        property int icon
        property bool enabled: true
        property color tint: hud.theme.text
        signal clicked
        width: 40
        height: 40
        radius: 10
        color: Qt.alpha(tint, btnMouse.containsMouse && enabled ? 0.14 : 0.05)
        border.color: Qt.alpha(tint, 0.25)
        opacity: enabled ? 1 : 0.35
        Text {
            anchors.centerIn: parent
            text: String.fromCodePoint(btn.icon)
            color: btn.tint
            font { family: hud.theme.mono; pixelSize: 18 }
        }
        MouseArea {
            id: btnMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: btn.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: if (btn.enabled) btn.clicked()
        }
    }

    component Brain: Rectangle {
        id: brain
        property int icon
        property string title
        property string detail
        property bool active
        width: 172
        height: 44
        radius: 9
        color: active ? Qt.alpha(hud.theme.mint, 0.12) : "transparent"
        border.color: active ? Qt.alpha(hud.theme.mint, 0.5) : "transparent"
        opacity: active ? 1 : 0.45
        Row {
            anchors { left: parent.left; leftMargin: 12; verticalCenter: parent.verticalCenter }
            spacing: 10
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: String.fromCodePoint(brain.icon)
                color: brain.active ? hud.theme.mint : hud.theme.muted
                font { family: hud.theme.mono; pixelSize: 16 }
            }
            Column {
                Text {
                    text: brain.title
                    color: hud.theme.text
                    font { family: hud.theme.mono; pixelSize: 12 }
                }
                Text {
                    text: brain.detail
                    color: hud.theme.muted
                    font { family: hud.theme.mono; pixelSize: 9 }
                }
            }
        }
    }

    component Key: Row {
        id: key
        property string keys
        property string label
        spacing: 10
        Rectangle {
            width: keyText.implicitWidth + 16
            height: 24
            radius: 5
            color: Qt.alpha(hud.theme.text, 0.06)
            border.color: Qt.alpha(hud.theme.text, 0.15)
            Text {
                id: keyText
                anchors.centerIn: parent
                text: key.keys
                color: hud.theme.text
                font { family: hud.theme.mono; pixelSize: 11 }
            }
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: key.label
            color: hud.theme.muted
            font { family: hud.theme.mono; pixelSize: 11 }
        }
    }

    Item {
        id: content
        anchors.fill: parent
        opacity: hud.cobra.hudOpen ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
        focus: true

        Keys.onPressed: event => {
            if (event.key === Qt.Key_Escape) {
                if (hud.typing) hud.typing = false
                else hud.cobra.hudOpen = false
                event.accepted = true
            } else if (event.key === Qt.Key_Tab) {
                hud.typing = true
                input.forceActiveFocus()
                event.accepted = true
            }
        }

        // dark glass, with soft colour glows in the corners
        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0.02, 0.03, 0.04, 0.94)
            MouseArea {  // click anywhere empty to close
                anchors.fill: parent
                onClicked: hud.cobra.hudOpen = false
            }
        }
        Repeater {
            model: [{ x: 0.08, y: 0.85, color: "mint" }, { x: 0.75, y: 0.25, color: "crimson" },
                    { x: 0.5, y: 0.5, color: "violet" }]
            Shape {
                required property var modelData
                anchors.fill: parent
                ShapePath {
                    strokeColor: "transparent"
                    fillGradient: RadialGradient {
                        centerX: content.width * modelData.x; centerY: content.height * modelData.y
                        focalX: centerX; focalY: centerY
                        centerRadius: content.height * 0.5; focalRadius: 0
                        GradientStop { position: 0; color: Qt.alpha(hud.theme[modelData.color], 0.07) }
                        GradientStop { position: 1; color: "transparent" }
                    }
                    PathRectangle { width: content.width; height: content.height }
                }
            }
        }

        // ── header ─────────────────────────────────────────────────────────
        Row {
            anchors { left: parent.left; leftMargin: 56; top: parent.top; topMargin: 50 }
            spacing: 24
            Text {
                text: "COBRA"
                color: hud.theme.mint
                font { family: "Orbitron"; pixelSize: 34; weight: Font.Black; letterSpacing: 10 }
            }
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: online.implicitWidth + 28
                height: 26
                radius: 13
                readonly property color tint: hud.cobra.online ? hud.theme.mint : hud.theme.crimson
                color: Qt.alpha(tint, 0.1)
                border.color: Qt.alpha(tint, 0.4)
                Text {
                    id: online
                    anchors.centerIn: parent
                    text: "●  " + (hud.cobra.online ? "ONLINE" : "OFFLINE")
                    color: parent.tint
                    font { family: hud.theme.mono; pixelSize: 10; letterSpacing: 2 }
                }
            }
        }

        Rectangle {
            anchors { horizontalCenter: parent.horizontalCenter; top: parent.top; topMargin: 44 }
            width: brains.implicitWidth + 12
            height: 54
            radius: 12
            color: Qt.rgba(0.05, 0.07, 0.08, 0.8)
            border.color: Qt.alpha(hud.theme.text, 0.1)
            MouseArea { anchors.fill: parent }
            Row {
                id: brains
                anchors.centerIn: parent
                spacing: 4
                Brain { icon: 0xF015F; title: "Claude"; detail: "opus-5.5 · no key yet" }
                Brain {
                    icon: 0xF061A; title: "Local"; active: true
                    detail: hud.cobra.model + " · RTX 5060"
                }
                Brain { icon: 0xF062C; title: "Auto"; detail: "needs Claude" }
            }
        }

        Row {
            anchors { right: parent.right; rightMargin: 56; top: parent.top; topMargin: 50 }
            spacing: 10
            IconButton {
                icon: 0xF036C  // microphone
                tint: hud.mode === "listening" ? hud.theme.mint : hud.theme.text
                onClicked: hud.cobra.toggleListening()
            }
            IconButton {
                icon: 0xF057E  // volume-high: stop her talking
                tint: hud.mode === "speaking" ? hud.theme.crimson : hud.theme.text
                onClicked: hud.cobra.hush()
            }
            IconButton { icon: 0xF0493; enabled: false }  // settings arrive in milestone 7
            IconButton { icon: 0xF0156; onClicked: hud.cobra.hudOpen = false }
        }

        // ── panels ─────────────────────────────────────────────────────────
        ContextPanel {
            cobra: hud.cobra
            anchors { left: parent.left; leftMargin: 56; top: parent.top; topMargin: 200 }
        }
        ActionsPanel {
            cobra: hud.cobra
            anchors { right: parent.right; rightMargin: 56; top: parent.top; topMargin: 200 }
        }

        // ── her ───────────────────────────────────────────────────────────
        Character {
            id: character
            mode: hud.mode
            level: hud.mode === "listening" ? hud.cobra.micLevel : hud.cobra.voiceLevel
            readonly property real room: bottom.y - 140
            scale: Math.min(1, room / implicitHeight)
            transformOrigin: Item.Top
            width: implicitWidth
            height: implicitHeight
            anchors { horizontalCenter: parent.horizontalCenter; top: parent.top; topMargin: 140 }
        }

        // ── what's being said ─────────────────────────────────────────────
        Column {
            id: bottom
            anchors { horizontalCenter: parent.horizontalCenter; bottom: footer.top; bottomMargin: 90 }
            width: Math.min(1100, parent.width - 200)
            spacing: 14

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: hud.mode.toUpperCase()
                color: hud.accent
                font { family: "Orbitron"; pixelSize: 16; weight: Font.Bold; letterSpacing: 8 }
            }
            VoiceBars {
                anchors.horizontalCenter: parent.horizontalCenter
                mode: hud.mode
                level: hud.mode === "listening" ? hud.cobra.micLevel : hud.cobra.voiceLevel
                color: hud.accent
                count: 48
                maxHeight: 22
            }
            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                visible: hud.cobra.transcript !== ""
                text: "<font color='" + hud.theme.muted + "' size='1'>YOU</font>&nbsp;&nbsp;“"
                      + hud.cobra.transcript.replace(/</g, "&lt;") + "”"
                textFormat: Text.StyledText
                color: Qt.alpha(hud.theme.text, 0.7)
                font { family: hud.theme.mono; pixelSize: 15 }
                elide: Text.ElideRight
            }
            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: hud.cobra.error !== "" && hud.mode === "idle" ? hud.cobra.error
                    : hud.mode === "speaking" ? hud.tail(hud.cobra.reply.trim(), 180)
                    : hud.mode === "idle" && hud.cobra.reply === ""
                      ? (hud.cobra.wakeOn ? "Say \u201cCobra\u201d, hold SUPER+C, or press TAB to type"
                                          : "Hold SUPER+C to talk, or press TAB to type")
                    : hud.mode === "idle" ? hud.cobra.reply.trim() : ""
                color: hud.cobra.error !== "" && hud.mode === "idle" ? hud.theme.crimson
                     : hud.cobra.reply === "" ? hud.theme.muted : hud.theme.text
                font { family: hud.theme.mono; pixelSize: 22 }
                lineHeight: 1.25
                wrapMode: Text.Wrap
                maximumLineCount: 3
                elide: Text.ElideRight
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                readonly property double latency: (hud.cobra.firstWordAt - hud.cobra.askedAt) / 1000
                readonly property double rate: hud.cobra.words
                    / Math.max(0.001, (hud.cobra.lastWordAt - hud.cobra.firstWordAt) / 1000)
                visible: hud.cobra.words > 1
                text: "<font color='" + hud.accent + "'>—</font>  " + hud.mode
                      + " · first word " + latency.toFixed(1) + "s · "
                      + Math.round(rate) + " tok/s · local"
                textFormat: Text.StyledText
                color: hud.theme.muted
                font { family: hud.theme.mono; pixelSize: 11 }
            }
        }

        // ── typing box (TAB) ───────────────────────────────────────────────
        Rectangle {
            visible: hud.typing
            anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 32 }
            width: 640
            height: 44
            radius: 10
            color: Qt.rgba(0.05, 0.07, 0.08, 0.95)
            border.color: Qt.alpha(hud.theme.violet, 0.6)
            MouseArea { anchors.fill: parent }
            TextInput {
                id: input
                anchors { fill: parent; leftMargin: 16; rightMargin: 16 }
                verticalAlignment: TextInput.AlignVCenter
                color: hud.theme.text
                selectionColor: Qt.alpha(hud.theme.violet, 0.5)
                font { family: hud.theme.mono; pixelSize: 14 }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: input.text === ""
                    text: "Ask Cobra…  (Enter to send, Esc to cancel)"
                    color: hud.theme.muted
                    font: input.font
                }
                Keys.onReturnPressed: {
                    if (text.trim() !== "") hud.cobra.ask(text.trim())
                    text = ""
                    hud.typing = false
                    content.forceActiveFocus()
                }
                Keys.onEscapePressed: {
                    text = ""
                    hud.typing = false
                    content.forceActiveFocus()
                }
            }
        }

        Row {
            id: footer
            visible: !hud.typing
            anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 40 }
            spacing: 36
            Key { keys: "SUPER + C"; label: "push to talk" }
            Key { visible: hud.cobra.wakeOn; keys: "\u201cCobra\u201d"; label: "wake word" }
            Key { keys: "TAB"; label: "type instead" }
            Key { keys: "ESC"; label: "dismiss" }
        }
    }
}
