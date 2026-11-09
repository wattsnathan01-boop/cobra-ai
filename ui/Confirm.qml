// Confirm pop-ups, centre-screen: "Cobra wants to run a command / edit a file" (Y / A / N, or
// say yes / no; auto-denied when the time runs out), and "Blocked" when a Never tool was tried.
import QtQuick
import QtQuick.Effects
import Quickshell
import Quickshell.Hyprland
import Quickshell.Wayland

PanelWindow {
    id: win

    required property Cobra cobra
    property Theme theme: Theme {}

    readonly property var card: cobra.card
    readonly property var blocked: card ? null : cobra.blocked
    readonly property var preview: (card ? card.preview : blocked ? blocked.preview : null) || ({})
    readonly property string kind: blocked ? "blocked" : (preview.kind || "other")
    readonly property bool showing: card !== null || blocked !== null
    readonly property color accent: kind === "blocked" ? theme.crimson
                                  : kind === "edit" || kind === "create" ? theme.mint
                                  : theme.violet

    implicitWidth: 640 + 2 * glow
    implicitHeight: box.height + 2 * glow
    readonly property int glow: 24
    color: "transparent"
    visible: showing
    exclusionMode: ExclusionMode.Ignore
    mask: Region { item: box }

    WlrLayershell.namespace: "cobra-confirm"
    WlrLayershell.layer: WlrLayer.Overlay
    // a question takes the keyboard (Y / A / N); a "blocked" notice doesn't hold you up
    WlrLayershell.keyboardFocus: card ? WlrKeyboardFocus.Exclusive
                               : blocked ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None

    onShowingChanged: {
        if (!showing) return
        const name = Hyprland.focusedMonitor ? Hyprland.focusedMonitor.name : ""
        screen = Quickshell.screens.find(s => s.name === name) || Quickshell.screens[0]
        keys.forceActiveFocus()
    }

    // a Never card goes away by itself after a while
    Timer {
        interval: 10000
        running: win.blocked !== null
        onTriggered: win.cobra.blocked = null
    }


    function allow(remember) { cobra.answer(true, remember) }
    function deny() { cobra.answer(false, false) }
    function dismiss() { cobra.blocked = null }

    readonly property string title: {
        if (kind === "blocked") return "Blocked: " + (blocked.tool === "files_delete" ? "delete files"
                                                      : blocked.tool.replace(/_/g, " "))
        if (kind === "command") return preview.root ? "Cobra wants to run a command as root"
                                                    : "Cobra wants to run a command"
        if (kind === "edit") return "Cobra wants to edit a file"
        if (kind === "packages") return "Cobra wants to install software"
        if (kind === "create") return "Cobra wants to create a file"
        if (kind === "delete") return "Cobra wants to move a file to the trash"
        return "Cobra wants to use " + (card ? card.tool.replace(/_/g, " ") : "")
    }
    readonly property string subtitle: {
        if (kind === "blocked") return preview.path ? "Cobra tried to remove " + preview.path
                                                    : "Cobra tried to use " + blocked.tool
        if (kind === "edit" || kind === "create" || kind === "delete") return preview.path
        return card && card.reason ? "because you said “" + card.reason + "”" : ""
    }

    component Button: Rectangle {
        id: button
        property string label
        property string key
        property color tint
        property bool filled: false
        signal clicked
        height: 40
        radius: 9
        color: filled ? tint : Qt.alpha(tint, mouse.containsMouse ? 0.14 : 0.05)
        border.color: filled ? "transparent" : Qt.alpha(tint, 0.5)
        Row {
            anchors.centerIn: parent
            spacing: 10
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: button.label
                color: button.filled ? "#0b1210" : button.tint
                font { family: win.theme.mono; pixelSize: 12; weight: Font.Medium }
            }
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: keyLabel.implicitWidth + 10
                height: 18
                radius: 4
                color: Qt.alpha(button.filled ? "#0b1210" : button.tint, 0.15)
                Text {
                    id: keyLabel
                    anchors.centerIn: parent
                    text: button.key
                    color: button.filled ? "#0b1210" : button.tint
                    font { family: win.theme.mono; pixelSize: 10 }
                }
            }
        }
        MouseArea {
            id: mouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: button.clicked()
        }
    }

    Item {
        id: keys
        focus: true
        Keys.onPressed: event => {
            const k = event.key
            if (win.blocked) {
                if (k === Qt.Key_Escape || k === Qt.Key_Return || k === Qt.Key_Enter) win.dismiss()
            } else if (win.card) {
                if (k === Qt.Key_Y || k === Qt.Key_Return || k === Qt.Key_Enter) win.allow(false)
                else if (k === Qt.Key_A && win.card.always && win.kind !== "edit") win.allow(true)
                else if (k === Qt.Key_N || k === Qt.Key_Escape) win.deny()
            }
            event.accepted = true
        }
    }

    Rectangle {
        id: box
        x: win.glow
        y: win.glow
        width: 640
        height: body.implicitHeight + 48
        radius: 16
        color: Qt.rgba(0.05, 0.07, 0.08, 0.97)
        border.width: 1
        border.color: Qt.alpha(win.accent, 0.6)
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: Qt.alpha(win.accent, 0.4)
            shadowBlur: 1.0
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
        }

        Column {
            id: body
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 24 }
            spacing: 18

            // header: her face, what she wants, why
            Row {
                spacing: 14
                Avatar { size: 46; ring: win.accent }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 5
                    Text {
                        text: win.title
                        color: win.theme.text
                        font { family: win.theme.mono; pixelSize: 15; weight: Font.Medium }
                    }
                    Text {
                        width: 520
                        visible: text !== ""
                        text: win.subtitle
                        color: win.theme.muted
                        font { family: win.theme.mono; pixelSize: 11 }
                        elide: Text.ElideRight
                    }
                }
            }

            // a command
            Rectangle {
                visible: win.kind === "command"
                width: parent.width
                height: cmd.implicitHeight + 28
                radius: 10
                color: Qt.rgba(0, 0, 0, 0.35)
                border.color: Qt.alpha(win.theme.text, 0.1)
                Text {
                    id: cmd
                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter
                              margins: 16 }
                    text: "<font color='" + win.theme.muted + "'>" + (win.preview.root ? "#" : "$")
                          + "</font>&nbsp;&nbsp;" + (win.preview.command || "").replace(/&/g, "&amp;")
                                                     .replace(/</g, "&lt;")
                    textFormat: Text.StyledText
                    color: win.theme.text
                    wrapMode: Text.WrapAnywhere
                    maximumLineCount: 8
                    elide: Text.ElideRight
                    font { family: win.theme.mono; pixelSize: 13 }
                }
            }

            // a diff
            Rectangle {
                visible: win.kind === "edit" || win.kind === "create"
                width: parent.width
                height: Math.min(diff.implicitHeight, 330)
                radius: 10
                clip: true
                color: Qt.rgba(0, 0, 0, 0.35)
                border.color: Qt.alpha(win.theme.text, 0.1)
                Column {
                    id: diff
                    width: parent.width
                    topPadding: 4
                    bottomPadding: 4
                    Repeater {
                        model: win.preview.diff || []
                        Rectangle {
                            required property var modelData
                            width: diff.width
                            height: 26
                            color: modelData.op === "+" ? Qt.alpha(win.theme.mint, 0.1)
                                 : modelData.op === "-" ? Qt.alpha(win.theme.crimson, 0.12)
                                 : "transparent"
                            Text {
                                anchors { left: parent.left; leftMargin: 14; right: parent.right
                                          rightMargin: 14; verticalCenter: parent.verticalCenter }
                                text: (modelData.op === "+" || modelData.op === "-" ? modelData.op : " ")
                                      + "   " + modelData.text
                                color: modelData.op === "+" ? win.theme.mint
                                     : modelData.op === "-" ? win.theme.crimson
                                     : modelData.op === "@" ? win.theme.muted : win.theme.text
                                font { family: win.theme.mono; pixelSize: 12 }
                                elide: Text.ElideRight
                            }
                        }
                    }
                }
            }

            // software to install
            Rectangle {
                visible: win.kind === "packages"
                width: parent.width
                height: pkgs.implicitHeight + 8
                radius: 10
                color: Qt.rgba(0, 0, 0, 0.35)
                border.color: Qt.alpha(win.theme.text, 0.1)
                Column {
                    id: pkgs
                    width: parent.width
                    topPadding: 4
                    Repeater {
                        model: win.kind === "packages" ? win.preview.packages : []
                        Item {
                            required property var modelData
                            width: pkgs.width
                            height: 32
                            opacity: modelData.installed ? 0.45 : 1
                            Text {
                                anchors { left: parent.left; leftMargin: 16; verticalCenter: parent.verticalCenter }
                                text: modelData.name + "  <font color='" + win.theme.muted + "'>"
                                      + modelData.version + "</font>"
                                textFormat: Text.StyledText
                                color: win.theme.text
                                font { family: win.theme.mono; pixelSize: 13 }
                            }
                            Text {
                                anchors { right: parent.right; rightMargin: 16; verticalCenter: parent.verticalCenter }
                                text: modelData.installed ? "already installed"
                                      : (modelData.source === "aur" ? "AUR" : modelData.source)
                                        + (modelData.size ? "  \u00b7  " + modelData.size : "")
                                color: modelData.source === "aur" && !modelData.installed
                                       ? win.theme.crimson : win.theme.muted
                                font { family: win.theme.mono; pixelSize: 11 }
                            }
                        }
                    }
                }
            }
            Rectangle {
                visible: win.kind === "packages" && !!win.preview.warning
                width: parent.width
                height: warn.implicitHeight + 24
                radius: 10
                color: Qt.alpha(win.theme.crimson, 0.07)
                border.color: Qt.alpha(win.theme.crimson, 0.3)
                Text {
                    id: warn
                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter
                              margins: 14 }
                    text: win.preview.warning || ""
                    color: win.theme.text
                    wrapMode: Text.Wrap
                    font { family: win.theme.mono; pixelSize: 11 }
                }
            }

            // anything else: just the arguments
            Text {
                visible: win.kind === "other" || win.kind === "delete"
                width: parent.width
                text: win.card ? JSON.stringify(win.card.args) : ""
                color: win.theme.text
                wrapMode: Text.WrapAnywhere
                font { family: win.theme.mono; pixelSize: 12 }
            }

            // blocked: what happened
            Rectangle {
                visible: win.kind === "blocked"
                width: parent.width
                height: why.implicitHeight + 32
                radius: 10
                color: Qt.alpha(win.theme.crimson, 0.06)
                border.color: Qt.alpha(win.theme.crimson, 0.25)
                Text {
                    id: why
                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter
                              margins: 18 }
                    text: (win.blocked && win.blocked.tool === "files_delete" ? "Deleting files"
                           : "That") + " is set to Never, so nothing was touched. You can do it "
                          + "yourself, or change the rule in Permissions."
                    color: win.theme.text
                    wrapMode: Text.Wrap
                    font { family: win.theme.mono; pixelSize: 12 }
                    lineHeight: 1.3
                }
            }

            Row {
                visible: (win.preview.tags || []).length > 0
                spacing: 8
                Repeater {
                    model: win.preview.tags || []
                    Rectangle {
                        required property string modelData
                        width: tag.implicitWidth + 18
                        height: 22
                        radius: 11
                        readonly property color tint: modelData === "sudo" ? win.theme.crimson
                                                                           : win.theme.violet
                        color: Qt.alpha(tint, 0.14)
                        Text {
                            id: tag
                            anchors.centerIn: parent
                            text: modelData
                            color: parent.tint
                            font { family: win.theme.mono; pixelSize: 10 }
                        }
                    }
                }
            }

            Text {
                visible: win.kind === "edit" || win.kind === "create"
                text: win.preview.summary || ""
                color: win.theme.muted
                font { family: win.theme.mono; pixelSize: 11 }
            }

            // buttons
            Row {
                width: parent.width
                spacing: 10
                visible: win.card !== null
                readonly property bool always: win.card !== null && win.card.always
                                               && win.kind !== "edit" && win.kind !== "create"
                Button {
                    width: parent.width - 10 * (parent.always ? 2 : 1) - deny.width
                           - (parent.always ? alwaysButton.width : 0)
                    label: win.kind === "edit" || win.kind === "create" ? "Apply"
                         : win.kind === "packages" ? "Install" : "Allow once"
                    key: "Y"
                    tint: win.theme.mint
                    filled: true
                    onClicked: win.allow(false)
                }
                Button {
                    id: alwaysButton
                    visible: parent.always
                    width: 120
                    label: "Always"
                    key: "A"
                    tint: win.theme.violet
                    onClicked: win.allow(true)
                }
                Button {
                    id: deny
                    width: 110
                    label: "Deny"
                    key: "N"
                    tint: win.theme.crimson
                    onClicked: win.deny()
                }
            }
            Row {
                width: parent.width
                spacing: 10
                visible: win.kind === "blocked"
                Button {
                    width: parent.width - 10 - ok.width
                    label: "Open Permissions"
                    key: "↗"
                    tint: win.theme.crimson
                    filled: true
                    onClicked: { win.cobra.openSettings("permissions"); win.dismiss() }
                }
                Button {
                    id: ok
                    width: 110
                    label: "OK"
                    key: "Esc"
                    tint: win.theme.text
                    onClicked: win.dismiss()
                }
            }

            // time left before it's denied for you
            Column {
                visible: win.card !== null
                width: parent.width
                spacing: 8
                property real remaining: 1
                Timer {
                    interval: 100
                    repeat: true
                    running: win.card !== null
                    onTriggered: parent.remaining = Math.max(0, 1 - (Date.now() - win.card.shownAt)
                                                           / (1000 * win.card.timeout))
                }
                Rectangle {
                    width: parent.width
                    height: 3
                    radius: 1.5
                    color: Qt.alpha(win.theme.text, 0.08)
                    Rectangle {
                        width: parent.width * parent.parent.remaining
                        height: parent.height
                        radius: parent.radius
                        color: win.theme.violet
                    }
                }
                Text {
                    text: "auto-deny in " + Math.ceil(parent.remaining * (win.card ? win.card.timeout : 0))
                          + "s · or say yes / no"
                    color: win.theme.muted
                    font { family: win.theme.mono; pixelSize: 10 }
                }
            }
        }
    }
}
