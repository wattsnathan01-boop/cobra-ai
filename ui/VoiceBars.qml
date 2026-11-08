// The little meter under the text: follows your mic while listening, her voice while
// speaking, ripples while thinking and lies flat when idle.
import QtQuick

Row {
    id: bars

    property string mode: "idle"
    property real level: 0
    property color color: "white"
    property int count: 16
    property real maxHeight: 14

    property var heights: Array(count).fill(0)
    property int tick: 0

    spacing: 2
    height: maxHeight

    Timer {
        interval: 33
        repeat: true
        running: bars.visible && bars.mode !== "idle"
        onTriggered: {
            bars.tick++
            const h = bars.heights.slice(1)
            if (bars.mode === "thinking")
                h.push(0.15 + 0.25 * Math.max(0, Math.sin(bars.tick / 3)))
            else  // a little jitter so steady sound still looks alive
                h.push(Math.min(1, bars.level * (0.7 + Math.random() * 0.6)))
            bars.heights = h
        }
    }
    onModeChanged: if (mode === "idle") heights = Array(count).fill(0)

    Repeater {
        model: bars.count
        Rectangle {
            required property int index
            anchors.verticalCenter: parent.verticalCenter
            width: 2
            radius: 1
            height: Math.max(2, bars.maxHeight * bars.heights[index])
            color: bars.color
            opacity: bars.mode === "idle" ? 0.5 : 0.95
        }
    }
}
