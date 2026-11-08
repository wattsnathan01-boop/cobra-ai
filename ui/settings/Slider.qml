// A slider that reports its value when you let go (so each drag saves once).
import QtQuick
import ".."

Item {
    id: slider

    property real from: 0
    property real to: 1
    property real stepSize: 0.05
    property real value: 0
    property Theme theme: Theme {}
    signal moved(real value)

    property real shown: value
    onValueChanged: if (!area.pressed) shown = value

    implicitWidth: 320
    height: 24

    function valueAt(x) {
        const f = Math.max(0, Math.min(1, x / width))
        const v = from + f * (to - from)
        return Math.round(v / stepSize) * stepSize
    }

    Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width
        height: 4
        radius: 2
        color: Qt.alpha(slider.theme.text, 0.12)
        Rectangle {
            width: parent.width * (slider.shown - slider.from) / (slider.to - slider.from)
            height: parent.height
            radius: 2
            color: slider.theme.mint
        }
    }
    Rectangle {
        width: 18
        height: 18
        radius: 9
        anchors.verticalCenter: parent.verticalCenter
        x: (slider.width - width) * (slider.shown - slider.from) / (slider.to - slider.from)
        color: slider.theme.text
        border.color: slider.theme.mint
        border.width: 2
    }
    MouseArea {
        id: area
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onPressed: mouse => slider.shown = slider.valueAt(mouse.x)
        onPositionChanged: mouse => slider.shown = slider.valueAt(mouse.x)
        onReleased: slider.moved(slider.shown)
    }
}
