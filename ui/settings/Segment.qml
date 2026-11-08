// Always / Ask first / Never.
import QtQuick
import ".."

Rectangle {
    id: seg

    property string value: "ask"
    property var disabled: []          // levels that can't be picked here
    property bool locked: false        // shown but not changeable
    property Theme theme: Theme {}
    signal picked(string level)

    readonly property var levels: [{ key: "always", label: "Always", tint: theme.mint },
                                   { key: "ask", label: "Ask first", tint: theme.violet },
                                   { key: "never", label: "Never", tint: theme.crimson }]

    width: row.implicitWidth + 8
    height: 34
    radius: 9
    color: Qt.rgba(0, 0, 0, 0.25)
    border.color: Qt.alpha(theme.text, 0.1)

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 2
        Repeater {
            model: seg.levels
            Rectangle {
                required property var modelData
                readonly property bool on: seg.value === modelData.key
                readonly property bool off: seg.locked || seg.disabled.indexOf(modelData.key) >= 0
                width: label.implicitWidth + 26
                height: 26
                radius: 7
                color: on ? Qt.alpha(modelData.tint, 0.15) : "transparent"
                border.color: on ? Qt.alpha(modelData.tint, 0.6) : "transparent"
                opacity: off && !on ? 0.3 : 1
                Text {
                    id: label
                    anchors.centerIn: parent
                    text: modelData.label
                    color: parent.on ? modelData.tint : seg.theme.muted
                    font { family: seg.theme.mono; pixelSize: 11; weight: parent.on ? Font.Medium : Font.Normal }
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: parent.off || parent.on ? Qt.ArrowCursor : Qt.PointingHandCursor
                    onClicked: if (!parent.off && !parent.on) seg.picked(modelData.key)
                }
            }
        }
    }
}
