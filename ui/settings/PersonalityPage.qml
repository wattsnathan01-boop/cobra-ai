// Her personality: the instructions she gets before every conversation.
import QtQuick
import QtQuick.Controls.Basic as C
import ".."

Column {
    id: page

    required property Cobra cobra
    property Theme theme: Theme {}
    readonly property var s: cobra.settings ? cobra.settings.persona : null
    property bool edited: false

    spacing: 28

    // pick up the saved text, unless you're in the middle of changing it
    Connections {
        target: page.cobra
        function onSettingsChanged() {
            if (!page.edited && page.s) editor.text = page.s.text
        }
    }
    Component.onCompleted: if (s) editor.text = s.text

    PageHeader {
        width: parent.width
        title: "Personality"
        subtitle: "Who Cobra is and how she talks. She reads this before every answer, so "
                  + "changes apply from her next reply."
    }

    Card {
        width: parent.width
        icon: 0xF0004  // account
        title: "Persona"
        status: page.edited ? "unsaved" : page.s && page.s.is_default ? "default" : "yours"
        tint: page.edited ? page.theme.violet : page.theme.mint

        Rectangle {
            width: parent.width
            height: 380
            radius: 10
            color: Qt.rgba(0, 0, 0, 0.3)
            border.color: editor.activeFocus ? Qt.alpha(page.theme.mint, 0.5) : Qt.alpha(page.theme.text, 0.1)
            C.ScrollView {
                anchors { fill: parent; margins: 4 }
                C.TextArea {
                    id: editor
                    wrapMode: TextEdit.Wrap
                    color: page.theme.text
                    selectionColor: Qt.alpha(page.theme.violet, 0.5)
                    font { family: page.theme.mono; pixelSize: 12 }
                    background: null
                    padding: 14
                    onTextChanged: if (activeFocus) page.edited = true
                }
            }
        }

        Row {
            spacing: 10
            Button {
                label: "Save"
                filled: true
                enabled: page.edited
                busy: page.cobra.busyKey === "persona"
                onClicked: { page.cobra.set("persona", editor.text); page.edited = false }
            }
            Button {
                label: "Undo changes"
                tint: page.theme.text
                enabled: page.edited
                onClicked: { editor.text = page.s.text; page.edited = false }
            }
            Button {
                label: "Reset to default"
                tint: page.theme.crimson
                enabled: page.s && !page.s.is_default
                onClicked: { page.edited = false; page.cobra.set("persona.reset", true) }
            }
        }
    }
}
