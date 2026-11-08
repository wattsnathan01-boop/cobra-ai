// What she remembers about you, and the conversation she keeps across restarts.
import QtQuick
import ".."

Column {
    id: page

    required property Cobra cobra
    property Theme theme: Theme {}
    readonly property var m: cobra.settings ? cobra.settings.memory : null
    property bool confirmDelete: false

    spacing: 28

    PageHeader {
        width: parent.width
        title: "Memory"
        subtitle: "Say “Cobra, remember that …” and she keeps it for every future "
                  + "conversation; “forget that …” removes it. Everything stays on this "
                  + "laptop."
    }

    Card {
        width: parent.width
        icon: 0xF0BA1  // brain-ish: head-lightbulb
        title: "Remembered"
        status: page.m ? page.m.facts.length + (page.m.facts.length === 1 ? " thing" : " things") : ""

        Text {
            visible: page.m && page.m.facts.length === 0
            width: parent.width
            text: "Nothing yet. Try “Cobra, remember that I take my coffee black.”"
            color: page.theme.muted
            font { family: page.theme.mono; pixelSize: 12 }
        }
        Repeater {
            model: page.m ? page.m.facts : []
            Rectangle {
                required property string modelData
                width: parent.width
                height: fact.implicitHeight + 22
                radius: 8
                color: Qt.alpha(page.theme.text, 0.035)
                Text {
                    id: fact
                    anchors { left: parent.left; leftMargin: 14; right: forget.left; rightMargin: 14
                              verticalCenter: parent.verticalCenter }
                    text: modelData
                    color: page.theme.text
                    wrapMode: Text.Wrap
                    font { family: page.theme.mono; pixelSize: 12 }
                }
                Text {
                    id: forget
                    anchors { right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                    text: "✕"
                    color: forgetMouse.containsMouse ? page.theme.crimson : page.theme.muted
                    font { family: page.theme.mono; pixelSize: 12 }
                    MouseArea {
                        id: forgetMouse
                        anchors { fill: parent; margins: -8 }
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: page.cobra.set("memory.remove", modelData)
                    }
                }
            }
        }
        Rectangle {
            width: parent.width
            height: 40
            radius: 8
            color: Qt.rgba(0, 0, 0, 0.3)
            border.color: add.activeFocus ? Qt.alpha(page.theme.mint, 0.5) : Qt.alpha(page.theme.text, 0.1)
            TextInput {
                id: add
                anchors { fill: parent; leftMargin: 14; rightMargin: 14 }
                verticalAlignment: TextInput.AlignVCenter
                color: page.theme.text
                font { family: page.theme.mono; pixelSize: 12 }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: add.text === ""
                    text: "+  Add something for her to remember (Enter)"
                    color: page.theme.mint
                    font: add.font
                }
                Keys.onReturnPressed: {
                    if (text.trim()) page.cobra.set("memory.add", text.trim())
                    text = ""
                }
            }
        }
        Text {
            width: parent.width
            text: "Kept in " + (page.m ? page.m.file : "") + ", which you can also edit by hand."
            color: page.theme.muted
            font { family: page.theme.mono; pixelSize: 10 }
        }
    }

    Card {
        width: parent.width
        icon: 0xF0B79  // chat-processing
        title: "Conversation"
        tint: page.theme.violet
        status: page.m ? page.m.messages + " messages now · " + page.m.all_messages + " saved" : ""

        Column {
            width: parent.width
            spacing: 6
            visible: page.m && page.m.summary !== ""
            Text {
                text: "What she remembers of this conversation so far"
                color: page.theme.muted
                font { family: page.theme.mono; pixelSize: 10 }
            }
            Text {
                width: parent.width
                text: page.m ? page.m.summary : ""
                color: page.theme.text
                wrapMode: Text.Wrap
                lineHeight: 1.3
                font { family: page.theme.mono; pixelSize: 12 }
            }
        }

        Column {
            width: parent.width
            spacing: 12
            Item {
                width: parent.width
                height: 18
                Text {
                    text: "After a restart, carry on the conversation from up to"
                    color: page.theme.text
                    font { family: page.theme.mono; pixelSize: 13 }
                }
                Text {
                    anchors.right: parent.right
                    text: page.m ? (page.m.resume_hours > 0 ? page.m.resume_hours + " h ago" : "never") : ""
                    color: page.theme.muted
                    font { family: page.theme.mono; pixelSize: 11 }
                }
            }
            Slider {
                width: parent.width
                from: 0
                to: 24
                stepSize: 1
                value: page.m ? page.m.resume_hours : 6
                onMoved: v => page.cobra.set("memory.resume_hours", Math.round(v))
            }
        }

        Row {
            spacing: 10
            Button {
                label: "Start a fresh conversation"
                tint: page.theme.violet
                onClicked: page.cobra.set("memory.clear_conversation", true)
            }
            Button {
                label: page.confirmDelete ? "Click again to delete everything" : "Delete all saved conversations"
                tint: page.theme.crimson
                filled: page.confirmDelete
                onClicked: {
                    if (page.confirmDelete) {
                        page.cobra.set("memory.clear_history", true)
                        page.confirmDelete = false
                    } else {
                        page.confirmDelete = true
                        disarm.restart()
                    }
                }
                Timer { id: disarm; interval: 4000; onTriggered: page.confirmDelete = false }
            }
        }
        Text {
            width: parent.width
            text: "Remembered things above are kept either way."
            color: page.theme.muted
            font { family: page.theme.mono; pixelSize: 10 }
        }
    }
}
