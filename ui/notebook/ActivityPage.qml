// The full log of what Cobra and Claude did in the notebook.
import QtQuick
import ".."

Item {
    id: page
    required property var nb
    property Theme theme: Theme {}

    Column {
        id: head
        x: 40; y: 32
        spacing: 6
        Text { text: "AI activity"; color: page.theme.text; font { family: page.theme.mono; pixelSize: 28; weight: Font.Bold } }
        Text {
            text: "Everything Cobra and Claude added or changed. Undo takes back just that change."
            color: page.theme.muted
            font { family: page.theme.mono; pixelSize: 12 }
        }
    }
    Rectangle {
        anchors { left: parent.left; right: parent.right; top: head.bottom; bottom: parent.bottom
                  leftMargin: 40; rightMargin: 40; topMargin: 22; bottomMargin: 32 }
        radius: 12
        color: "#11181b"
        border.color: "#22302f"
        ActivityList {
            anchors { fill: parent; margins: 16 }
            nb: page.nb
            items: page.nb.overview ? page.nb.overview.activity : []
        }
    }
}
