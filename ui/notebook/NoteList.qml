// The middle column: search, filters and the notes as cards.
import QtQuick
import ".."

Rectangle {
    id: list

    required property var nb          // the Notebook window
    property Theme theme: Theme {}
    property Fmt fmt: Fmt {}
    property string filter: "all"      // all | text | image | video | audio
    readonly property var notes: {
        const all = nb.overview ? nb.overview.notes : []
        const words = nb.query.toLowerCase().split(/\s+/).filter(w => w)
        return all.filter(n => {
            if (nb.page === "diary" && n.kind !== "diary") return false
            if (nb.tagFilter && n.tags.indexOf(nb.tagFilter) < 0) return false
            if (filter === "text" && n.media.length) return false
            if (filter !== "all" && filter !== "text" && n.media.indexOf(filter) < 0) return false
            const hay = (n.title + " " + n.preview + " " + n.tags.join(" ")).toLowerCase()
            return words.every(w => hay.indexOf(w) >= 0)
        })
    }

    color: "transparent"
    Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: "#22302f" }

    Column {
        id: top
        x: 20; y: 28
        width: parent.width - 40
        spacing: 16

        Item {
            width: parent.width
            height: 26
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: list.nb.tagFilter ? "#" + list.nb.tagFilter
                      : list.nb.page === "diary" ? "Diary" : "All notes"
                color: list.theme.text
                font { family: list.theme.mono; pixelSize: 18; weight: Font.DemiBold }
            }
            Text {
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                text: list.nb.tagFilter ? "clear ✕" : list.notes.length + (list.notes.length === 1 ? " note" : " notes")
                color: list.theme.muted
                font { family: list.theme.mono; pixelSize: 11 }
                MouseArea {
                    anchors { fill: parent; margins: -6 }
                    enabled: list.nb.tagFilter !== ""
                    cursorShape: Qt.PointingHandCursor
                    onClicked: list.nb.tagFilter = ""
                }
            }
        }

        Rectangle {
            width: parent.width
            height: 38
            radius: 8
            color: "#11181b"
            border.color: search.activeFocus ? Qt.alpha(list.theme.mint, 0.5) : "#22302f"
            Ico { x: 12; anchors.verticalCenter: parent.verticalCenter; name: "search"; size: 15; color: list.theme.muted }
            TextInput {
                id: search
                anchors { fill: parent; leftMargin: 36; rightMargin: 12 }
                verticalAlignment: TextInput.AlignVCenter
                color: list.theme.text
                selectionColor: Qt.alpha(list.theme.mint, 0.35)
                font { family: list.theme.mono; pixelSize: 12 }
                clip: true
                text: list.nb.query
                onTextEdited: list.nb.query = text
                Keys.onEscapePressed: { text = ""; list.nb.query = "" }
                Text {
                    visible: !search.text && !search.activeFocus
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Search notes…"
                    color: list.theme.muted
                    font: search.font
                }
            }
        }

        Row {
            spacing: 6
            Repeater {
                model: [["all", "All"], ["text", "Text"], ["image", "Photos"], ["video", "Video"], ["audio", "Voice"]]
                Chip {
                    required property var modelData
                    label: modelData[1]
                    height: 26
                    fontSize: 11
                    filled: list.filter === modelData[0]
                    onClicked: list.filter = modelData[0]
                }
            }
        }
    }

    ListView {
        id: view
        anchors { left: parent.left; right: parent.right; top: top.bottom; bottom: parent.bottom
                  leftMargin: 14; rightMargin: 14; topMargin: 14; bottomMargin: 14 }
        clip: true
        spacing: 4
        boundsBehavior: Flickable.StopAtBounds
        model: list.notes

        delegate: Rectangle {
            id: card
            required property var modelData
            readonly property bool open: list.nb.note && list.nb.note.id === modelData.id
            width: view.width
            height: col.implicitHeight + 28
            radius: 10
            color: open ? "#172124" : cardMouse.containsMouse ? Qt.alpha(list.theme.text, 0.03) : "transparent"
            border.color: open ? Qt.alpha(list.theme.mint, 0.25) : "transparent"

            MouseArea {
                id: cardMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: list.nb.open(card.modelData.id)
            }

            Column {
                id: col
                x: 14; y: 14
                width: parent.width - 28
                spacing: 8

                Item {
                    width: parent.width
                    height: title.implicitHeight
                    Row {
                        spacing: 6
                        width: parent.width - time.implicitWidth - 10
                        Ico { visible: card.modelData.pinned; name: "pin"; size: 12; color: list.theme.amber; anchors.verticalCenter: parent.verticalCenter }
                        Ico { visible: card.modelData.kind === "diary"; name: "diary"; size: 12; color: list.theme.mint; anchors.verticalCenter: parent.verticalCenter }
                        Text {
                            id: title
                            width: parent.width - 40
                            text: card.modelData.title
                            elide: Text.ElideRight
                            color: list.theme.text
                            font { family: list.theme.mono; pixelSize: 13; weight: Font.DemiBold }
                        }
                    }
                    Text {
                        id: time
                        anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                        text: list.fmt.when(card.modelData.updated)
                        color: list.theme.muted
                        font { family: list.theme.mono; pixelSize: 10 }
                    }
                }
                Text {
                    visible: text !== ""
                    width: parent.width
                    text: card.modelData.preview
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                    lineHeight: 1.3
                    color: "#94a5a1"
                    font { family: list.theme.mono; pixelSize: 11 }
                }
                Item {
                    width: parent.width
                    height: 18
                    Row {
                        spacing: 6
                        Repeater {
                            model: card.modelData.authors
                            Author { required property string modelData; who: modelData }
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: card.modelData.tags.map(t => "#" + t).join(" ")
                            color: list.theme.muted
                            font { family: list.theme.mono; pixelSize: 10 }
                        }
                    }
                    Row {
                        anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                        spacing: 6
                        Repeater {
                            model: card.modelData.media
                            Ico {
                                required property string modelData
                                name: ({ image: "image", video: "video", audio: "mic", file: "paperclip", checklist: "boxChecked" })[modelData] || "file"
                                size: 13
                                color: list.theme.muted
                            }
                        }
                    }
                }
            }
        }

        Text {
            visible: view.count === 0
            anchors.horizontalCenter: parent.horizontalCenter
            y: 40
            width: parent.width - 40
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.Wrap
            text: list.nb.overview === null ? "Loading…"
                  : list.nb.query ? "Nothing matches “" + list.nb.query + "”."
                  : "No notes yet. Press New entry, or say “Cobra, note that …”."
            color: list.theme.muted
            font { family: list.theme.mono; pixelSize: 12 }
        }
    }
}
