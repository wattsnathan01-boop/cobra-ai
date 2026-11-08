// While Cobra can see a screen: a crimson edge round it and a pill at the bottom. Always shown,
// so she can never look without you knowing. Click the pill to stop watching.
import QtQuick
import QtQuick.Effects
import Quickshell
import Quickshell.Wayland

// one per monitor: watching lights them all (she looks at whichever you're on); a single look
// lights only the monitor she captured
Variants {
    id: variants
    required property Cobra cobra
    model: Quickshell.screens

    PanelWindow {
        id: edge

        required property var modelData
        readonly property Cobra cobra: variants.cobra
        property Theme theme: Theme {}
        readonly property bool watching: cobra.screenState === "watching"
        readonly property bool on: watching
            || (cobra.screenState === "looking" && cobra.screenMonitor === modelData.name)

        screen: modelData
        anchors { top: true; bottom: true; left: true; right: true }
        exclusionMode: ExclusionMode.Ignore
        color: "transparent"
        visible: frame.opacity > 0
        mask: Region { item: pill }  // clicks go straight through everything but the pill

        WlrLayershell.namespace: "cobra-edge"
        WlrLayershell.layer: WlrLayer.Overlay

        Rectangle {
            id: frame
            anchors.fill: parent
            color: "transparent"
            border.width: 3
            border.color: Qt.alpha(edge.theme.crimson, 0.9)
            opacity: edge.on ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 250 } }
            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: edge.theme.crimson
                shadowBlur: 1.0
                shadowHorizontalOffset: 0
                shadowVerticalOffset: 0
            }

            // breathing, so it's noticed
            SequentialAnimation on border.width {
                running: edge.on
                loops: Animation.Infinite
                NumberAnimation { to: 4; duration: 900; easing.type: Easing.InOutSine }
                NumberAnimation { to: 2; duration: 900; easing.type: Easing.InOutSine }
            }
        }

        Rectangle {
            id: pill
            anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 26 }
            width: pillRow.implicitWidth + 36
            height: 36
            radius: 18
            color: Qt.rgba(0.05, 0.07, 0.08, 0.92)
            border.color: Qt.alpha(edge.theme.crimson, 0.6)
            opacity: frame.opacity
            Row {
                id: pillRow
                anchors.centerIn: parent
                spacing: 10
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: 8
                    height: 8
                    radius: 4
                    color: edge.theme.crimson
                    SequentialAnimation on opacity {
                        running: edge.on
                        loops: Animation.Infinite
                        NumberAnimation { to: 0.3; duration: 700 }
                        NumberAnimation { to: 1; duration: 700 }
                    }
                }
                Text {
                    text: edge.watching ? "Cobra can see your screen" : "Cobra is looking at your screen"
                    color: edge.theme.text
                    font { family: edge.theme.mono; pixelSize: 12 }
                }
                Text {
                    visible: edge.watching
                    text: "click to stop"
                    color: edge.theme.muted
                    font { family: edge.theme.mono; pixelSize: 10 }
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            MouseArea {
                anchors.fill: parent
                cursorShape: edge.watching ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: if (edge.watching) edge.cobra.stopWatching()
            }
        }
    }
}
