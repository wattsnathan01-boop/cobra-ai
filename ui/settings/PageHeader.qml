import QtQuick
import ".."

Column {
    property string title
    property string subtitle
    property Theme theme: Theme {}
    spacing: 10
    Text {
        text: parent.title
        color: parent.theme.text
        font { family: "Orbitron"; pixelSize: 28; weight: Font.Bold }
    }
    Text {
        width: parent.width
        text: parent.subtitle
        color: parent.theme.muted
        wrapMode: Text.Wrap
        font { family: parent.theme.mono; pixelSize: 12 }
    }
}
