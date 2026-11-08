// On/off switch.
import QtQuick
import ".."

Rectangle {
    id: toggle

    property bool checked: false
    property bool enabled: true
    property Theme theme: Theme {}
    signal toggled(bool on)

    width: 44
    height: 24
    radius: 12
    opacity: enabled ? 1 : 0.4
    color: checked ? theme.mint : Qt.alpha(theme.text, 0.15)
    Behavior on color { ColorAnimation { duration: 150 } }

    Rectangle {
        width: 18
        height: 18
        radius: 9
        y: 3
        x: toggle.checked ? toggle.width - width - 3 : 3
        color: toggle.checked ? "#0b1210" : toggle.theme.text
        Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
    }
    MouseArea {
        anchors.fill: parent
        cursorShape: toggle.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (toggle.enabled) toggle.toggled(!toggle.checked)
    }
}
