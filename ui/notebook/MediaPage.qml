// Every photo, video, voice memo and file in the notebook.
import QtQuick
import ".."

Item {
    id: page
    required property var nb
    property Theme theme: Theme {}
    property string kind: "all"
    readonly property var items: nb.overview ? nb.overview.media.filter(m => kind === "all" || m.type === kind) : []

    Item {
        id: head
        x: 40; y: 32
        width: parent.width - 80
        height: 60
        Column {
            spacing: 6
            Text { text: "Media"; color: page.theme.text; font { family: page.theme.mono; pixelSize: 28; weight: Font.Bold } }
            Text { text: "Click to open its note, double-click to open the file."; color: page.theme.muted; font { family: page.theme.mono; pixelSize: 12 } }
        }
        Row {
            anchors { right: parent.right; bottom: parent.bottom }
            spacing: 6
            Repeater {
                model: [["all", "All"], ["image", "Photos"], ["video", "Videos"], ["audio", "Voice"], ["file", "Files"]]
                Chip { required property var modelData; label: modelData[1]; filled: page.kind === modelData[0]; onClicked: page.kind = modelData[0] }
            }
        }
    }
    MediaGrid {
        anchors { left: parent.left; right: parent.right; top: head.bottom; bottom: parent.bottom
                  leftMargin: 36; rightMargin: 36; topMargin: 20; bottomMargin: 24 }
        nb: page.nb
        items: page.items
        columns: Math.max(3, Math.floor(width / 240))
        emptyText: "Nothing yet. Attach photos and videos to a note with the 🖼 button, or record a voice memo."
    }
}
