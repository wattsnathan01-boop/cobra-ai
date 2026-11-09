// A titled panel on the Today page.
import QtQuick
import ".."

Rectangle {
    id: panel
    property string title
    property string note: ""
    property Theme theme: Theme {}
    default property alias content: inner.data

    radius: 12
    color: "#11181b"
    border.color: "#22302f"
    clip: true
    Text {
        id: head
        x: 20; y: 18
        text: panel.title
        color: panel.theme.text
        font { family: panel.theme.mono; pixelSize: 14; weight: Font.DemiBold }
    }
    Text {
        anchors { right: parent.right; rightMargin: 20; verticalCenter: head.verticalCenter }
        text: panel.note
        color: panel.theme.muted
        font { family: panel.theme.mono; pixelSize: 10 }
    }
    Item {
        id: inner
        anchors { left: parent.left; right: parent.right; top: head.bottom; bottom: parent.bottom
                  leftMargin: 20; rightMargin: 20; topMargin: 14; bottomMargin: 16 }
    }
}
