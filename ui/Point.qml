// "Line 13": a highlight round the spot she means, a line to a callout with her note.
// Goes away after a while, or when you click "Got it". Positions are roughly right, not exact.
import QtQuick
import QtQuick.Effects
import QtQuick.Shapes
import Quickshell
import Quickshell.Wayland

PanelWindow {
    id: win

    required property Cobra cobra
    property Theme theme: Theme {}
    readonly property var p: cobra.point
    readonly property var target: Quickshell.screens.find(s => p && s.name === p.monitor) || null

    screen: target || Quickshell.screens[0]
    anchors { top: true; bottom: true; left: true; right: true }
    exclusionMode: ExclusionMode.Ignore
    color: "transparent"
    visible: p !== null && target !== null
    mask: Region { item: callout }

    WlrLayershell.namespace: "cobra-point"
    WlrLayershell.layer: WlrLayer.Overlay

    Timer {
        interval: 25000
        running: win.p !== null
        onTriggered: win.cobra.point = null
    }

    // the spot, in this monitor's coordinates (with some breathing room)
    readonly property real bx: p && target ? p.x - target.x - 6 : 0
    readonly property real by: p && target ? p.y - target.y - 4 : 0
    readonly property real bw: p ? p.w + 12 : 0
    readonly property real bh: p ? p.h + 8 : 0
    // the callout sits beside the spot, on whichever side has room
    readonly property bool right: bx + bw / 2 < width / 2

    Rectangle {
        id: box
        x: win.bx
        y: win.by
        width: win.bw
        height: win.bh
        radius: 8
        color: Qt.alpha(win.theme.crimson, 0.06)
        border.width: 2
        border.color: win.theme.crimson
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: win.theme.crimson
            shadowBlur: 0.8
            shadowHorizontalOffset: 0
            shadowVerticalOffset: 0
        }
    }

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: win.theme.crimson
            strokeWidth: 1.5
            fillColor: "transparent"
            startX: win.right ? box.x + box.width : box.x
            startY: box.y + box.height / 2
            PathCubic {
                x: win.right ? callout.x : callout.x + callout.width
                y: callout.y + 30
                control1X: (win.right ? box.x + box.width : box.x) + (win.right ? 80 : -80)
                control1Y: box.y + box.height / 2
                control2X: (win.right ? callout.x : callout.x + callout.width) + (win.right ? -80 : 80)
                control2Y: callout.y + 30
            }
        }
    }

    Rectangle {
        id: callout
        width: 400
        height: col.implicitHeight + 36
        x: win.right ? Math.min(win.width - width - 24, box.x + box.width + 120)
                     : Math.max(24, box.x - width - 120)
        y: Math.max(24, Math.min(win.height - height - 24, box.y + box.height / 2 - 30))
        radius: 14
        color: Qt.rgba(0.05, 0.07, 0.08, 0.96)
        border.color: Qt.alpha(win.theme.crimson, 0.55)

        Column {
            id: col
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: 18 }
            spacing: 12
            Row {
                spacing: 10
                Avatar { size: 28; ring: win.theme.crimson }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Here"
                    color: win.theme.crimson
                    font { family: win.theme.mono; pixelSize: 13; weight: Font.Medium }
                }
            }
            Text {
                width: parent.width
                text: win.p ? win.p.note : ""
                color: win.theme.text
                wrapMode: Text.Wrap
                maximumLineCount: 8
                elide: Text.ElideRight
                lineHeight: 1.3
                font { family: win.theme.mono; pixelSize: 12 }
            }
            Rectangle {
                width: got.implicitWidth + 28
                height: 30
                radius: 8
                color: gotMouse.containsMouse ? Qt.alpha(win.theme.text, 0.14) : Qt.alpha(win.theme.text, 0.06)
                border.color: Qt.alpha(win.theme.text, 0.2)
                Text {
                    id: got
                    anchors.centerIn: parent
                    text: "Got it"
                    color: win.theme.text
                    font { family: win.theme.mono; pixelSize: 11 }
                }
                MouseArea {
                    id: gotMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: win.cobra.point = null
                }
            }
        }
    }
}
