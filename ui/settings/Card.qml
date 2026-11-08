// A settings panel: icon, title, optional status pill, then whatever goes inside.
import QtQuick
import ".."

Rectangle {
    id: card

    property int icon: 0
    property string title
    property string status: ""
    property color tint: theme.mint
    property Theme theme: Theme {}
    default property alias content: inner.data

    implicitHeight: col.implicitHeight + 48
    radius: 16
    color: Qt.rgba(1, 1, 1, 0.025)
    border.color: Qt.alpha(tint, 0.35)

    Column {
        id: col
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 24 }
        spacing: 18

        Item {
            width: parent.width
            height: 36
            visible: card.title !== ""
            Rectangle {
                id: badge
                width: 36
                height: 36
                radius: 9
                color: Qt.alpha(card.tint, 0.12)
                visible: card.icon !== 0
                Text {
                    anchors.centerIn: parent
                    text: String.fromCodePoint(card.icon)
                    color: card.tint
                    font { family: card.theme.mono; pixelSize: 17 }
                }
            }
            Text {
                anchors { left: badge.visible ? badge.right : parent.left; leftMargin: badge.visible ? 14 : 0
                          verticalCenter: parent.verticalCenter }
                text: card.title
                color: card.theme.text
                font { family: card.theme.mono; pixelSize: 15; weight: Font.Medium }
            }
            Rectangle {
                visible: card.status !== ""
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                width: pill.implicitWidth + 24
                height: 24
                radius: 12
                color: Qt.alpha(card.tint, 0.1)
                Text {
                    id: pill
                    anchors.centerIn: parent
                    text: "●  " + card.status
                    color: card.tint
                    font { family: card.theme.mono; pixelSize: 10 }
                }
            }
        }

        Column {
            id: inner
            width: parent.width
            spacing: 14
        }
    }
}
