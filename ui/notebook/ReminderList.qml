// Reminders with tick, snooze and remove. Who set each one, and whether she'll say it.
import QtQuick
import ".."

ListView {
    id: view
    required property var nb
    property var items: []
    property bool compact: false
    property Theme theme: Theme {}
    property Fmt fmt: Fmt {}

    clip: true
    spacing: 4
    boundsBehavior: Flickable.StopAtBounds
    model: items

    delegate: Rectangle {
        id: row
        required property var modelData
        readonly property bool overdue: !modelData.done && new Date(modelData.due) < new Date()
        readonly property bool soon: view.fmt.isToday(modelData.due) || overdue
        width: view.width
        height: 52
        radius: 8
        color: soon && !modelData.done ? "#172124" : hover.hovered ? Qt.alpha(view.theme.text, 0.03) : "transparent"
        HoverHandler { id: hover }

        Ico {
            id: tick
            x: 12; anchors.verticalCenter: parent.verticalCenter
            name: row.modelData.done ? "circleChecked" : "circle"
            size: 17
            color: row.modelData.done ? view.theme.mint : tickMouse.containsMouse ? view.theme.mint : view.theme.muted
            MouseArea { id: tickMouse; anchors { fill: parent; margins: -6 } hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                        onClicked: view.nb.request("reminder_done", { rid: row.modelData.id, done: !row.modelData.done }) }
        }
        Column {
            anchors { left: tick.right; leftMargin: 12; right: side.left; rightMargin: 10; verticalCenter: parent.verticalCenter }
            spacing: 4
            Text {
                width: parent.width
                text: row.modelData.text
                elide: Text.ElideRight
                color: row.modelData.done ? view.theme.muted : view.theme.text
                font { family: view.theme.mono; pixelSize: 12; strikeout: row.modelData.done }
            }
            Row {
                spacing: 5
                Ico {
                    anchors.verticalCenter: parent.verticalCenter
                    name: row.modelData.author === "claude" ? "sparkle" : row.modelData.author === "cobra" ? "waveform" : "you"
                    size: 10
                    color: row.modelData.author === "claude" ? view.theme.violet : row.modelData.author === "cobra" ? view.theme.mint : view.theme.muted
                }
                Text {
                    text: (row.modelData.author === "you" ? "you" : row.modelData.author === "cobra" ? "set by Cobra" : "set by Claude")
                          + (row.modelData.speak ? " · Cobra will say it" : "")
                    color: view.theme.muted
                    font { family: view.theme.mono; pixelSize: 10 }
                }
                Text {
                    visible: !!row.modelData.note_id
                    text: "· open note"
                    color: view.theme.violet
                    font { family: view.theme.mono; pixelSize: 10 }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: view.nb.open(row.modelData.note_id) }
                }
            }
        }
        Item {
            id: side
            anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
            width: hover.hovered && !row.modelData.done ? btns.width : when.width
            height: 30
            Column {
                id: when
                visible: !(hover.hovered && !row.modelData.done)
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                spacing: 2
                Text {
                    anchors.right: parent.right
                    text: row.overdue ? "overdue" : view.fmt.due(row.modelData.due).split(" ").pop()
                    color: row.overdue ? view.theme.crimson : row.soon ? view.theme.amber : view.theme.muted
                    font { family: view.theme.mono; pixelSize: 12 }
                }
                Text {
                    anchors.right: parent.right
                    text: row.modelData.done ? "done" : row.soon ? (row.overdue ? view.fmt.due(row.modelData.due) : "today")
                          : view.fmt.due(row.modelData.due).split(" ").slice(0, -1).join(" ")
                    color: view.theme.muted
                    font { family: view.theme.mono; pixelSize: 9 }
                }
            }
            Row {
                id: btns
                visible: hover.hovered && !row.modelData.done
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                spacing: 4
                Chip { icon: "snooze"; label: "10m"; height: 26; fontSize: 10
                       onClicked: view.nb.request("reminder_snooze", { rid: row.modelData.id, minutes: 10 }) }
                Chip { icon: "trash"; label: ""; height: 26; fontSize: 10; tint: view.theme.crimson
                       onClicked: view.nb.request("reminder_delete", { rid: row.modelData.id }) }
            }
        }
    }

    Text {
        visible: view.count === 0
        y: 10
        width: view.width
        wrapMode: Text.Wrap
        text: "No reminders. Try “Cobra, remind me to take the bins out at 7”."
        color: view.theme.muted
        font { family: view.theme.mono; pixelSize: 12 }
    }
}
