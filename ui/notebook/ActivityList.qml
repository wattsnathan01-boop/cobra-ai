// What Cobra and Claude changed in the notebook, newest first, each with undo.
import QtQuick
import ".."

ListView {
    id: view
    required property var nb
    property var items: []
    property Theme theme: Theme {}
    property Fmt fmt: Fmt {}

    clip: true
    spacing: 2
    boundsBehavior: Flickable.StopAtBounds
    model: items

    delegate: Item {
        id: row
        required property var modelData
        readonly property color tint: modelData.who === "claude" ? view.theme.violet : view.theme.mint
        width: view.width
        height: 42
        opacity: modelData.undone ? 0.45 : 1

        Rectangle {
            id: av
            x: 4; anchors.verticalCenter: parent.verticalCenter
            width: 26; height: 26; radius: 13
            color: Qt.alpha(row.tint, 0.13)
            Ico { anchors.centerIn: parent; name: row.modelData.who === "claude" ? "sparkle" : "waveform"; size: 13; color: row.tint }
        }
        Row {
            anchors { left: av.right; leftMargin: 12; right: right.left; rightMargin: 10; verticalCenter: parent.verticalCenter }
            spacing: 6
            clip: true
            Text { text: row.modelData.who === "claude" ? "Claude" : "Cobra"; color: row.tint; font { family: view.theme.mono; pixelSize: 12; weight: Font.DemiBold } }
            Text { text: row.modelData.summary; color: view.theme.muted; font { family: view.theme.mono; pixelSize: 12 } }
            Text {
                text: row.modelData.title
                color: view.theme.text
                font { family: view.theme.mono; pixelSize: 12; strikeout: row.modelData.undone }
                MouseArea {
                    anchors.fill: parent
                    enabled: !!row.modelData.note_id && !row.modelData.undone && row.modelData.action !== "deleted"
                    cursorShape: Qt.PointingHandCursor
                    onClicked: view.nb.open(row.modelData.note_id)
                }
            }
        }
        Row {
            id: right
            anchors { right: parent.right; rightMargin: 4; verticalCenter: parent.verticalCenter }
            spacing: 10
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: view.fmt.when(row.modelData.ts)
                color: view.theme.muted
                font { family: view.theme.mono; pixelSize: 10 }
            }
            Chip {
                visible: row.modelData.can_undo
                icon: "undo"; label: "undo"; height: 24; fontSize: 10
                onClicked: view.nb.request("undo", { entry: row.modelData.id })
            }
            Text {
                visible: row.modelData.undone
                anchors.verticalCenter: parent.verticalCenter
                text: "undone"
                color: view.theme.muted
                font { family: view.theme.mono; pixelSize: 10 }
            }
        }
    }

    Text {
        visible: view.count === 0
        y: 10
        width: view.width
        wrapMode: Text.Wrap
        text: "Nothing yet. When Cobra or Claude add notes, diary entries or reminders, they show up here."
        color: view.theme.muted
        font { family: view.theme.mono; pixelSize: 12 }
    }
}
