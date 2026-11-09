// Who wrote something: you, Cobra or Claude.
import QtQuick
import ".."

Rectangle {
    id: chip
    property string who: "you"
    property bool long: false   // "Cobra added" instead of "Cobra"
    property Theme theme: Theme {}
    readonly property color tint: who === "claude" ? theme.violet : who === "cobra" ? theme.mint : "#a9b8b4"

    width: row.implicitWidth + 12
    height: 18
    radius: 4
    color: Qt.alpha(tint, who === "you" ? 0.08 : 0.12)
    Row {
        id: row
        anchors.centerIn: parent
        spacing: 5
        Ico {
            anchors.verticalCenter: parent.verticalCenter
            name: chip.who === "you" ? "you" : chip.who === "cobra" ? "waveform" : "sparkle"
            size: 11
            color: chip.tint
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: {
                const name = chip.who === "you" ? "you" : chip.who === "cobra" ? "Cobra" : "Claude"
                return chip.long ? (chip.who === "you" ? "you wrote" : name + " added") : name
            }
            color: chip.tint
            font { family: chip.theme.mono; pixelSize: 10 }
        }
    }
}
