// Attachments as tiles: photos show, videos and voice memos get a badge. Click opens the note.
import QtQuick
import ".."

GridView {
    id: grid
    required property var nb
    property var items: []
    property int columns: 4
    property string emptyText: "Nothing here yet."
    property Theme theme: Theme {}

    clip: true
    boundsBehavior: Flickable.StopAtBounds
    cellWidth: width / columns
    cellHeight: Math.min(cellWidth, Math.max(80, columns <= 3 ? height : cellWidth))
    model: items

    delegate: Item {
        id: tile
        required property var modelData
        width: grid.cellWidth
        height: grid.cellHeight
        Rectangle {
            anchors { fill: parent; margins: 4 }
            radius: 8
            color: "#172124"
            clip: true
            Image {
                visible: tile.modelData.type === "image"
                anchors.fill: parent
                source: visible ? "file://" + tile.modelData.path : ""
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                sourceSize.width: 500
            }
            Ico {
                visible: tile.modelData.type !== "image"
                anchors.centerIn: parent
                name: tile.modelData.type === "video" ? "video" : tile.modelData.type === "audio" ? "waveform" : "doc"
                size: 30
                color: tile.modelData.type === "audio" ? grid.theme.crimson : Qt.alpha(grid.theme.text, 0.6)
            }
            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: 26
                color: Qt.rgba(0.04, 0.06, 0.07, 0.78)
                Text {
                    anchors { left: parent.left; right: parent.right; leftMargin: 8; rightMargin: 8; verticalCenter: parent.verticalCenter }
                    text: tile.modelData.caption || tile.modelData.title
                    elide: Text.ElideRight
                    color: grid.theme.text
                    font { family: grid.theme.mono; pixelSize: 10 }
                }
            }
            MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                        onClicked: grid.nb.open(tile.modelData.note_id)
                        onDoubleClicked: grid.nb.openPath(tile.modelData.path) }
        }
    }

    Text {
        visible: grid.count === 0
        y: 10
        width: grid.width
        wrapMode: Text.Wrap
        text: grid.emptyText
        color: grid.theme.muted
        font { family: grid.theme.mono; pixelSize: 12 }
    }
}
