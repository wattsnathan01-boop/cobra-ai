// Left panel: what the machine is doing right now.
import QtQuick

Rectangle {
    id: panel

    required property Cobra cobra
    property Theme theme: Theme {}
    readonly property var s: cobra.stats

    width: 340
    height: col.implicitHeight + 48
    radius: 14
    color: Qt.rgba(0.05, 0.07, 0.08, 0.75)
    border.color: Qt.alpha(theme.text, 0.08)

    MouseArea { anchors.fill: parent }  // clicks on the panel don't close the HUD

    component Meter: Column {
        id: meter
        property int icon
        property string label
        property string value
        property real fraction
        property color color
        width: parent.width
        spacing: 8
        Item {
            width: parent.width
            height: 18
            Text {
                text: String.fromCodePoint(meter.icon) + "  " + meter.label
                color: panel.theme.text
                opacity: 0.85
                font { family: panel.theme.mono; pixelSize: 12 }
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                text: meter.value
                color: panel.theme.text
                font { family: panel.theme.mono; pixelSize: 13 }
            }
        }
        Rectangle {
            width: parent.width
            height: 3
            radius: 1.5
            color: Qt.alpha(panel.theme.text, 0.08)
            Rectangle {
                width: parent.width * Math.max(0, Math.min(1, meter.fraction))
                height: parent.height
                radius: parent.radius
                color: meter.color
                Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
            }
        }
    }

    Column {
        id: col
        anchors { fill: parent; margins: 24 }
        spacing: 18

        Text {
            text: "CONTEXT"
            color: panel.theme.muted
            font { family: panel.theme.mono; pixelSize: 11; letterSpacing: 3 }
        }
        Meter {
            icon: 0xF050F  // thermometer
            label: "GPU"
            value: panel.s.gpu ? panel.s.gpu.temp_c + "°C" : "–"
            fraction: panel.s.gpu ? panel.s.gpu.temp_c / 100 : 0
            color: panel.theme.mint
        }
        Meter {
            icon: 0xF061A  // chip
            label: "CPU"
            value: panel.s.cpu_percent !== undefined ? Math.round(panel.s.cpu_percent) + "%" : "–"
            fraction: (panel.s.cpu_percent || 0) / 100
            color: panel.theme.violet
        }
        Meter {
            icon: 0xF035B  // memory
            label: "RAM"
            value: panel.s.memory_total_gb ? panel.s.memory_used_gb + " / "
                                             + Math.round(panel.s.memory_total_gb) + " GB" : "–"
            fraction: panel.s.memory_total_gb ? panel.s.memory_used_gb / panel.s.memory_total_gb : 0
            color: panel.theme.violet
        }
        Meter {
            visible: panel.s.battery_percent !== undefined
            icon: panel.s.charging ? 0xF0084 : 0xF0079  // battery-charging / battery
            label: "Battery"
            value: panel.s.battery_percent + "%"
            fraction: (panel.s.battery_percent || 0) / 100
            color: panel.s.battery_percent < 20 && !panel.s.charging ? panel.theme.crimson
                                                                      : panel.theme.mint
        }
        Text {
            width: parent.width
            text: String.fromCodePoint(0xF075A) + "  "  // music note
                  + (panel.s.playing ? panel.s.playing.replace(/^Playing: /, "")
                                                    .replace(/^Paused: /, "paused · ")
                                     : "nothing playing")
            color: panel.s.playing ? panel.theme.text : panel.theme.muted
            font { family: panel.theme.mono; pixelSize: 12 }
            elide: Text.ElideRight
        }
    }
}
