// A small clickable pill or button.
import QtQuick
import ".."

Rectangle {
    id: chip
    property string label
    property string icon: ""
    property bool active: false
    property color tint: theme.mint
    property bool filled: false
    property int fontSize: 11
    property Theme theme: Theme {}
    signal clicked

    width: row.implicitWidth + 22
    height: 30
    radius: 8
    color: filled ? tint : active ? Qt.alpha(tint, 0.12) : mouse.containsMouse ? Qt.alpha(theme.text, 0.06) : "#11181b"
    border.color: filled ? "transparent" : active ? Qt.alpha(tint, 0.45) : "#22302f"
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 7
        Ico {
            visible: chip.icon !== ""
            anchors.verticalCenter: parent.verticalCenter
            name: chip.icon
            size: chip.fontSize + 3
            color: chip.filled ? "#0b1012" : chip.active ? chip.tint : "#a9b8b4"
        }
        Text {
            visible: chip.label !== ""
            anchors.verticalCenter: parent.verticalCenter
            text: chip.label
            color: chip.filled ? "#0b1012" : chip.active ? chip.tint : chip.theme.text
            font { family: chip.theme.mono; pixelSize: chip.fontSize; weight: chip.filled ? Font.DemiBold : Font.Normal }
        }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: chip.clicked()
    }
}
