// Right panel: the tools she has just used, and a few things to try.
import QtQuick

Rectangle {
    id: panel

    required property Cobra cobra
    property Theme theme: Theme {}

    width: 340
    height: col.implicitHeight + 48
    radius: 14
    color: Qt.rgba(0.05, 0.07, 0.08, 0.75)
    border.color: Qt.alpha(theme.text, 0.08)

    MouseArea { anchors.fill: parent }  // clicks on the panel don't close the HUD

    component Action: Rectangle {
        id: row
        property string name
        property string detail
        property string status   // running | done | failed
        width: parent.width
        height: 56
        radius: 10
        color: Qt.alpha(panel.theme.text, 0.04)
        readonly property color tint: status === "done" ? panel.theme.mint
                                    : status === "failed" ? panel.theme.crimson
                                    : panel.theme.violet
        Text {
            id: mark
            anchors { left: parent.left; leftMargin: 14; verticalCenter: parent.verticalCenter }
            // check-circle / close-circle / loading
            text: String.fromCodePoint(row.status === "done" ? 0xF05E1
                                     : row.status === "failed" ? 0xF015A : 0xF0772)
            color: row.tint
            font { family: panel.theme.mono; pixelSize: 16 }
            RotationAnimator on rotation {
                from: 0; to: 360; duration: 1200; loops: Animation.Infinite
                running: row.status === "running"
            }
        }
        Column {
            anchors { left: mark.right; leftMargin: 12; right: parent.right; rightMargin: 12
                      verticalCenter: parent.verticalCenter }
            spacing: 4
            Text {
                text: row.name
                color: panel.theme.text
                font { family: panel.theme.mono; pixelSize: 12; weight: Font.Medium }
            }
            Text {
                width: parent.width
                text: row.detail
                color: panel.theme.muted
                font { family: panel.theme.mono; pixelSize: 10 }
                elide: Text.ElideRight
            }
        }
    }

    Column {
        id: col
        anchors { fill: parent; margins: 24 }
        spacing: 12

        Text {
            text: "ACTIONS"
            color: panel.theme.muted
            font { family: panel.theme.mono; pixelSize: 11; letterSpacing: 3 }
        }
        Action {
            visible: panel.cobra.mode === "speaking"
            name: "speak"
            detail: "piper · " + panel.cobra.voice + " · streaming"
            status: "running"
        }
        Repeater {
            model: panel.cobra.actions
            Action {
                required property var model
                width: col.width
                name: model.name
                detail: model.detail + (model.ms > 0 ? " · " + model.ms + "ms" : "")
                status: model.status
            }
        }
        Text {
            visible: panel.cobra.actions.count === 0 && panel.cobra.mode !== "speaking"
            text: "Nothing yet"
            color: panel.theme.muted
            font { family: panel.theme.mono; pixelSize: 12 }
        }

        Item { width: 1; height: 8 }
        Text {
            text: "TRY"
            color: panel.theme.muted
            font { family: panel.theme.mono; pixelSize: 11; letterSpacing: 3 }
        }
        Repeater {
            model: ["how hot is my GPU?", "what's playing?", "put the volume on thirty"]
            Text {
                required property string modelData
                text: "“" + modelData + "”"
                color: tryMouse.containsMouse ? panel.theme.text : panel.theme.violet
                font { family: panel.theme.mono; pixelSize: 12 }
                MouseArea {
                    id: tryMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: panel.cobra.ask(modelData)
                }
            }
        }
    }
}
