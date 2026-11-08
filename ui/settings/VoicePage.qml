// Her voice: preview any of them, then switch. New voices download on first use.
import QtQuick
import ".."

Column {
    id: page

    required property Cobra cobra
    property Theme theme: Theme {}
    readonly property var voices: cobra.settings ? cobra.settings.voice.voices : []

    spacing: 28

    PageHeader {
        width: parent.width
        title: "Voice"
        subtitle: "How Cobra sounds. Preview first; voices you haven't used download once "
                  + "(about 60–115 MB). There's no Australian voice in Piper yet."
    }

    Card {
        width: parent.width
        icon: 0xF057E  // volume-high
        title: "Voices"
        status: page.cobra.settings ? page.cobra.settings.voice.current : ""

        Repeater {
            model: page.voices
            Rectangle {
                required property var modelData
                readonly property bool on: modelData.current
                width: parent.width
                height: 58
                radius: 10
                color: on ? Qt.alpha(page.theme.mint, 0.08) : Qt.alpha(page.theme.text, 0.03)
                border.color: on ? Qt.alpha(page.theme.mint, 0.5) : Qt.alpha(page.theme.text, 0.07)

                Column {
                    anchors { left: parent.left; leftMargin: 18; verticalCenter: parent.verticalCenter }
                    spacing: 5
                    Text {
                        text: modelData.label.charAt(0).toUpperCase() + modelData.label.slice(1)
                              + (modelData.quality ? "  ·  " + modelData.quality : "")
                        color: page.theme.text
                        font { family: page.theme.mono; pixelSize: 13; weight: Font.Medium }
                    }
                    Text {
                        text: [modelData.gender, modelData.accent,
                               modelData.installed ? "downloaded" : modelData.size_mb + " MB download"]
                              .filter(x => x).join("  ·  ")
                        color: page.theme.muted
                        font { family: page.theme.mono; pixelSize: 10 }
                    }
                }
                Row {
                    anchors { right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                    spacing: 8
                    Button {
                        label: "Preview"
                        tint: page.theme.violet
                        busy: page.cobra.busyKey === "preview:" + modelData.name
                        enabled: page.cobra.busyKey === "" || busy
                        onClicked: page.cobra.previewVoice(modelData.name)
                    }
                    Button {
                        label: parent.parent.on ? "In use" : "Use"
                        filled: !parent.parent.on
                        enabled: !parent.parent.on && page.cobra.busyKey === ""
                        busy: page.cobra.busyKey === "voice.piper_voice" && !parent.parent.on
                              && page.pending === modelData.name
                        onClicked: { page.pending = modelData.name; page.cobra.set("voice.piper_voice", modelData.name) }
                    }
                }
            }
        }
    }
    property string pending: ""
}
