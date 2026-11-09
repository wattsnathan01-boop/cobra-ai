// All reminders, with a form to add one.
import QtQuick
import ".."

Item {
    id: page
    required property var nb
    property Theme theme: Theme {}
    readonly property var all: nb.overview ? nb.overview.reminders : []
    property bool speak: true

    function add() {
        if (!what.text.trim() || !when.text.trim()) return
        nb.request("reminder_add", { text: what.text, when: when.text, speak: speak })
        what.text = ""; when.text = ""
        what.forceActiveFocus()
    }
    Connections {
        target: page.nb
        function onFocusReminderChanged() { if (page.nb.focusReminder) { what.forceActiveFocus(); page.nb.focusReminder = false } }
    }
    Component.onCompleted: if (nb.focusReminder) { what.forceActiveFocus(); nb.focusReminder = false }

    Column {
        x: 40; y: 32
        width: Math.min(900, parent.width - 80)
        height: parent.height - 64
        spacing: 22

        Column {
            spacing: 6
            Text { text: "Reminders"; color: page.theme.text; font { family: page.theme.mono; pixelSize: 28; weight: Font.Bold } }
            Text {
                text: "Cobra says them out loud when they're due, and a notification pops up. Tell her, or Claude, or add one here."
                color: page.theme.muted
                font { family: page.theme.mono; pixelSize: 12 }
            }
        }

        Rectangle {
            id: form
            width: parent.width
            height: 56
            radius: 12
            color: "#11181b"
            border.color: what.activeFocus || when.activeFocus ? Qt.alpha(page.theme.amber, 0.6) : "#22302f"
            Ico { id: bell; x: 16; anchors.verticalCenter: parent.verticalCenter; name: "bellPlus"; size: 18; color: page.theme.amber }
            TextInput {
                id: what
                anchors { left: bell.right; leftMargin: 12; right: whenBox.left; rightMargin: 12; verticalCenter: parent.verticalCenter }
                color: page.theme.text
                selectByMouse: true
                clip: true
                font { family: page.theme.mono; pixelSize: 13 }
                KeyNavigation.tab: when
                onAccepted: when.text ? page.add() : when.forceActiveFocus()
                Text { visible: !parent.text; text: "Remind me to…"; color: page.theme.muted; font: parent.font }
            }
            Rectangle {
                id: whenBox
                anchors { right: speakChip.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
                width: 260; height: 34; radius: 8
                color: "#0b1012"
                border.color: "#22302f"
                TextInput {
                    id: when
                    anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                    verticalAlignment: TextInput.AlignVCenter
                    color: page.theme.amber
                    selectByMouse: true
                    clip: true
                    font { family: page.theme.mono; pixelSize: 12 }
                    onAccepted: page.add()
                    Text { visible: !parent.text; anchors.verticalCenter: parent.verticalCenter
                           text: "18:30 · in 20 min · 2026-11-14 10:00"; color: page.theme.muted; font { family: page.theme.mono; pixelSize: 10 } }
                }
            }
            Chip {
                id: speakChip
                anchors { right: addBtn.left; rightMargin: 8; verticalCenter: parent.verticalCenter }
                icon: "speaker"; label: page.speak ? "say it" : "silent"; active: page.speak
                onClicked: page.speak = !page.speak
            }
            Chip {
                id: addBtn
                anchors { right: parent.right; rightMargin: 11; verticalCenter: parent.verticalCenter }
                label: "Add"; filled: true; tint: page.theme.amber
                onClicked: page.add()
            }
        }

        Rectangle {
            width: parent.width
            height: parent.height - y
            radius: 12
            color: "#11181b"
            border.color: "#22302f"
            ReminderList {
                anchors { fill: parent; margins: 14 }
                nb: page.nb
                items: page.all
            }
        }
    }
}
