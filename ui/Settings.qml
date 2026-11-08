// Settings window: `cobractl settings [page]`, the HUD's gear button, or "Open Permissions".
// Every change is saved and applied straight away.
import QtQuick
import Quickshell
import "settings"

FloatingWindow {
    id: win

    required property Cobra cobra
    property Theme theme: Theme {}

    title: "Cobra settings"
    implicitWidth: 1400
    implicitHeight: 880
    minimumSize: Qt.size(1100, 640)
    color: "#0a0e10"
    visible: cobra.settingsOpen
    onVisibleChanged: if (!visible) cobra.settingsOpen = false

    readonly property var pages: [
        { key: "brains", label: "Brains", icon: 0xF09D1 },       // brain
        { key: "voice", label: "Voice", icon: 0xF147D },         // waveform
        { key: "wake", label: "Wake word", icon: 0xF0003 },      // access-point
        { key: "personality", label: "Personality", icon: 0xF0004 },  // account
        { key: "permissions", label: "Permissions", icon: 0xF0565 },  // shield-check
        { key: "shortcuts", label: "Shortcuts", icon: 0xF030C },      // keyboard
    ]

    // sidebar
    Rectangle {
        id: side
        width: 260
        height: parent.height
        color: "#0d1315"
        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Qt.alpha(win.theme.text, 0.06) }

        Row {
            x: 28
            y: 28
            spacing: 14
            Avatar { size: 42; ring: win.theme.mint }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 2
                Text {
                    text: "COBRA"
                    color: win.theme.mint
                    font { family: "Orbitron"; pixelSize: 18; weight: Font.Black; letterSpacing: 5 }
                }
                Text {
                    text: "settings"
                    color: win.theme.muted
                    font { family: win.theme.mono; pixelSize: 11 }
                }
            }
        }

        Column {
            x: 16
            y: 100
            width: parent.width - 32
            spacing: 6
            Repeater {
                model: win.pages
                Rectangle {
                    required property var modelData
                    readonly property bool on: win.cobra.settingsPage === modelData.key
                    width: parent.width
                    height: 40
                    radius: 10
                    color: on ? Qt.alpha(win.theme.mint, 0.1) : navMouse.containsMouse ? Qt.alpha(win.theme.text, 0.04) : "transparent"
                    border.color: on ? Qt.alpha(win.theme.mint, 0.4) : "transparent"
                    Row {
                        anchors { left: parent.left; leftMargin: 14; verticalCenter: parent.verticalCenter }
                        spacing: 14
                        Text {
                            text: String.fromCodePoint(modelData.icon)
                            color: parent.parent.on ? win.theme.mint : win.theme.muted
                            font { family: win.theme.mono; pixelSize: 16 }
                        }
                        Text {
                            text: modelData.label
                            color: parent.parent.on ? win.theme.text : win.theme.muted
                            font { family: win.theme.mono; pixelSize: 13; weight: parent.parent.on ? Font.Medium : Font.Normal }
                        }
                    }
                    MouseArea {
                        id: navMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: win.cobra.settingsPage = modelData.key
                    }
                }
            }
        }

        Text {
            anchors { left: parent.left; leftMargin: 28; bottom: parent.bottom; bottomMargin: 24 }
            text: win.cobra.online ? "●  cobrad connected" : "●  cobrad offline"
            color: win.cobra.online ? win.theme.mint : win.theme.crimson
            font { family: win.theme.mono; pixelSize: 10 }
        }
    }

    // the page
    Flickable {
        id: scroller
        anchors { left: side.right; right: parent.right; top: parent.top; bottom: parent.bottom }
        contentHeight: loader.height + 88
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Loader {
            id: loader
            x: 44
            y: 44
            width: scroller.width - 88
            sourceComponent: ({ brains: brainsPage, voice: voicePage, wake: wakePage,
                                personality: personalityPage, permissions: permissionsPage,
                                shortcuts: shortcutsPage })[win.cobra.settingsPage] || brainsPage
            onLoaded: scroller.contentY = 0
        }
    }

    Component { id: brainsPage; BrainsPage { cobra: win.cobra } }
    Component { id: voicePage; VoicePage { cobra: win.cobra } }
    Component { id: wakePage; WakePage { cobra: win.cobra } }
    Component { id: personalityPage; PersonalityPage { cobra: win.cobra } }
    Component { id: permissionsPage; PermissionsPage { cobra: win.cobra } }
    Component { id: shortcutsPage; ShortcutsPage { cobra: win.cobra } }

    // "voice changed to …" / an error, for a few seconds
    Rectangle {
        id: toast
        anchors { right: parent.right; rightMargin: 32; bottom: parent.bottom; bottomMargin: 28 }
        width: note.implicitWidth + 32
        height: 38
        radius: 10
        color: "#111a1c"
        border.color: Qt.alpha(win.cobra.settingsError ? win.theme.crimson : win.theme.mint, 0.6)
        opacity: shown ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
        property bool shown: false
        Text {
            id: note
            anchors.centerIn: parent
            text: win.cobra.settingsNote
            color: win.cobra.settingsError ? win.theme.crimson : win.theme.mint
            font { family: win.theme.mono; pixelSize: 12 }
        }
        Timer { id: hideToast; interval: 3500; onTriggered: toast.shown = false }
        Connections {
            target: win.cobra
            function onSettingsNoteChanged() { toast.shown = true; hideToast.restart() }
        }
    }
}
