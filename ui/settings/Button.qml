// A small text button.
import QtQuick
import ".."

Rectangle {
    id: button

    property string label
    property color tint: theme.mint
    property bool filled: false
    property bool enabled: true
    property bool busy: false
    property Theme theme: Theme {}
    signal clicked

    width: text.implicitWidth + 28
    height: 32
    radius: 8
    opacity: enabled ? 1 : 0.4
    color: filled ? tint : Qt.alpha(tint, mouse.containsMouse && enabled ? 0.16 : 0.07)
    border.color: filled ? "transparent" : Qt.alpha(tint, 0.45)

    Text {
        id: text
        anchors.centerIn: parent
        text: button.busy ? "…" : button.label
        color: button.filled ? "#0b1210" : button.tint
        font { family: button.theme.mono; pixelSize: 11; weight: Font.Medium }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: button.enabled && !button.busy ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (button.enabled && !button.busy) button.clicked()
    }
}
