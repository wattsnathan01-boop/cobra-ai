// Cobra Queen palette (matches design/previews)
import QtQuick

QtObject {
    readonly property color bg: Qt.rgba(0.05, 0.07, 0.08, 0.96)
    readonly property color text: "#d9e4e1"
    readonly property color muted: "#7d8f8a"
    readonly property color mint: "#3bf0b6"
    readonly property color violet: "#8a7bff"
    readonly property color crimson: "#ff2d63"
    readonly property color amber: "#ffb547"
    readonly property string mono: "JetBrainsMono Nerd Font"

    function accent(mode) {
        return mode === "listening" ? mint
             : mode === "thinking" ? violet
             : mode === "speaking" ? crimson
             : muted
    }
}
