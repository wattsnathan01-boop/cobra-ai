// Her face in a ring that takes the colour of the current state.
import QtQuick
import Quickshell.Widgets

Item {
    id: avatar

    property int size: 62
    property color ring: "white"

    width: size
    height: size

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: "transparent"
        border.color: avatar.ring
        border.width: 2
        Behavior on border.color { ColorAnimation { duration: 250 } }
    }

    ClippingRectangle {
        anchors.fill: parent
        anchors.margins: 4
        radius: width / 2
        color: "transparent"
        Image {
            anchors.fill: parent
            source: Qt.resolvedUrl("assets/cobra-avatar.png")
            sourceSize: Qt.size(128, 128)
            fillMode: Image.PreserveAspectCrop
            smooth: true
        }
    }
}
