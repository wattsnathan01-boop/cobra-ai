// The keys and words that drive Cobra.
import QtQuick
import ".."

Column {
    id: page

    required property Cobra cobra
    property Theme theme: Theme {}

    spacing: 28

    PageHeader {
        width: parent.width
        title: "Shortcuts"
        subtitle: "Keybinds live in ~/.config/hypr/hyprland.lua; the rest are built in."
    }

    Card {
        width: parent.width
        icon: 0xF030C  // keyboard
        title: "Keys and words"
        Repeater {
            model: [
                ["“Cobra, …”", "ask anything, hands-free"],
                ["SUPER + C", "hold to talk; press while she talks to interrupt"],
                ["SUPER + SHIFT + C", "open or close the full HUD"],
                ["TAB", "type a question (in the HUD)"],
                ["ESC", "close the HUD, or say no to a pop-up"],
                ["Y  /  A  /  N", "allow once / always / deny, in a confirm pop-up"],
                ["“yes”  /  “no”", "answer a confirm pop-up by voice"],
                ["cobractl settings", "open this window from a terminal"],
            ]
            Item {
                required property var modelData
                required property int index
                width: parent.width
                height: 44
                Rectangle {
                    visible: index > 0
                    width: parent.width
                    height: 1
                    color: Qt.alpha(page.theme.text, 0.07)
                }
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: keys.implicitWidth + 20
                    height: 26
                    radius: 6
                    color: Qt.alpha(page.theme.text, 0.06)
                    border.color: Qt.alpha(page.theme.text, 0.15)
                    Text {
                        id: keys
                        anchors.centerIn: parent
                        text: modelData[0]
                        color: page.theme.text
                        font { family: page.theme.mono; pixelSize: 11 }
                    }
                }
                Text {
                    anchors { left: parent.left; leftMargin: 220; verticalCenter: parent.verticalCenter }
                    text: modelData[1]
                    color: page.theme.muted
                    font { family: page.theme.mono; pixelSize: 12 }
                }
            }
        }
    }
}
