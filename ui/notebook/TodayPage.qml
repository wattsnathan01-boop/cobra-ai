// Today: quick capture, the diary calendar, reminders, what Cobra and Claude did, recent media.
import QtQuick
import ".."

Item {
    id: page

    required property var nb
    property Theme theme: Theme {}
    property Fmt fmt: Fmt {}
    readonly property var ov: nb.overview
    property date month: new Date()
    readonly property var upcoming: ov ? ov.reminders.filter(r => !r.done) : []
    readonly property int todayLeft: upcoming.filter(r => fmt.isToday(r.due) || new Date(r.due) < new Date()).length

    // ── header ──
    Item {
        id: header
        x: 40; y: 32
        width: parent.width - 80
        height: 62
        Column {
            width: parent.width - capture.width - 24
            spacing: 6
            Text {
                text: Qt.formatDate(new Date(), "dddd  ·  d MMMM").toUpperCase().split("").join(" ")
                color: page.theme.muted
                font { family: page.theme.mono; pixelSize: 10 }
            }
            Text {
                text: {
                    const h = new Date().getHours()
                    const hi = h < 12 ? "Morning." : h < 18 ? "Afternoon." : "Evening."
                    const n = page.todayLeft
                    return hi + " " + (n === 0 ? "Nothing left to do today." : n + (n === 1 ? " reminder" : " reminders") + " left today.")
                }
                width: parent.width
                elide: Text.ElideRight
                color: page.theme.text
                font { family: page.theme.mono; pixelSize: 26; weight: Font.Bold }
            }
        }
        Row {
            id: capture
            anchors { right: parent.right; bottom: parent.bottom }
            spacing: 8
            Chip { label: "Diary entry"; icon: "pencilPlus"; active: true; onClicked: page.nb.openDiary() }
            Chip { label: "Note"; icon: "plus"; onClicked: page.nb.newNote() }
            Chip { label: "Photo / video"; icon: "imagePlus"; onClicked: page.nb.captureToDiary("media") }
            Chip { label: "Voice"; icon: "mic"; onClicked: page.nb.captureToDiary("voice") }
            Chip { label: "Reminder"; icon: "bellPlus"; onClicked: { page.nb.page = "reminders"; page.nb.focusReminder = true } }
        }
    }

    // ── calendar + reminders ──
    Item {
        id: topRow
        anchors { left: parent.left; right: parent.right; top: header.bottom; leftMargin: 40; rightMargin: 40; topMargin: 24 }
        height: Math.max(360, (page.height - 160) * 0.56)

        Panel {
            id: cal
            anchors { left: parent.left; top: parent.top; bottom: parent.bottom; right: rem.left; rightMargin: 20 }
            title: "Diary · " + Qt.formatDate(page.month, "MMMM yyyy")

            Row {
                anchors { right: parent.right; top: parent.top; topMargin: -34 }
                spacing: 14
                Repeater {
                    model: [["good", page.theme.mint], ["meh", page.theme.amber], ["rough", page.theme.crimson]]
                    Row {
                        required property var modelData
                        spacing: 5
                        Rectangle { width: 6; height: 6; radius: 3; color: modelData[1]; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: modelData[0]; color: page.theme.muted; font { family: page.theme.mono; pixelSize: 10 } }
                    }
                }
                Text {
                    text: "‹"
                    color: page.theme.muted
                    font { family: page.theme.mono; pixelSize: 14 }
                    MouseArea { anchors { fill: parent; margins: -6 } cursorShape: Qt.PointingHandCursor
                                onClicked: page.month = new Date(page.month.getFullYear(), page.month.getMonth() - 1, 1) }
                }
                Text {
                    text: "›"
                    color: page.theme.muted
                    font { family: page.theme.mono; pixelSize: 14 }
                    MouseArea { anchors { fill: parent; margins: -6 } cursorShape: Qt.PointingHandCursor
                                onClicked: page.month = new Date(page.month.getFullYear(), page.month.getMonth() + 1, 1) }
                }
            }

            Column {
                anchors.fill: parent
                spacing: 6
                readonly property int lead: (new Date(page.month.getFullYear(), page.month.getMonth(), 1).getDay() + 6) % 7
                readonly property int days: new Date(page.month.getFullYear(), page.month.getMonth() + 1, 0).getDate()
                readonly property int weeks: Math.ceil((lead + days) / 7)
                readonly property real cellH: (height - 20 - weeks * 6) / weeks
                id: grid
                Row {
                    width: parent.width
                    Repeater {
                        model: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                        Text {
                            required property string modelData
                            width: grid.width / 7
                            horizontalAlignment: Text.AlignHCenter
                            text: modelData
                            color: page.theme.muted
                            font { family: page.theme.mono; pixelSize: 10 }
                        }
                    }
                }
                Repeater {
                    model: grid.weeks
                    Row {
                        id: week
                        required property int index
                        spacing: 6
                        Repeater {
                            model: 7
                            Rectangle {
                                id: cell
                                required property int index
                                readonly property int day: week.index * 7 + index - grid.lead + 1
                                readonly property bool valid: day >= 1 && day <= grid.days
                                readonly property date date: new Date(page.month.getFullYear(), page.month.getMonth(), day)
                                readonly property var info: valid && page.ov ? (page.ov.calendar[page.fmt.dayKey(date)] || null) : null
                                readonly property bool today: valid && page.fmt.sameDay(date, new Date())
                                readonly property bool future: date > new Date()
                                width: (grid.width - 36) / 7
                                height: grid.cellH
                                radius: 8
                                color: !valid ? "transparent" : today ? Qt.alpha(page.theme.mint, 0.1)
                                       : cellMouse.containsMouse ? "#1d292c" : "#172124"
                                border.color: today ? page.theme.mint : "transparent"
                                Text {
                                    visible: cell.valid
                                    x: 8; y: 6
                                    text: cell.day
                                    color: cell.today ? page.theme.mint : cell.future ? "#4e5e5a" : page.theme.text
                                    font { family: page.theme.mono; pixelSize: 11; weight: cell.today ? Font.Bold : Font.Normal }
                                }
                                Row {
                                    visible: cell.valid && cell.info !== null
                                    x: 8
                                    anchors { bottom: parent.bottom; bottomMargin: 7 }
                                    spacing: 5
                                    Rectangle {
                                        visible: !!(cell.info && cell.info.mood)
                                        anchors.verticalCenter: parent.verticalCenter
                                        width: 6; height: 6; radius: 3
                                        color: cell.info ? ({ good: page.theme.mint, meh: page.theme.amber, rough: page.theme.crimson })[cell.info.mood] || "transparent" : "transparent"
                                    }
                                    Ico { visible: !!(cell.info && cell.info.diary && !cell.info.mood); name: "diary"; size: 10; color: page.theme.muted }
                                    Ico { visible: !!(cell.info && cell.info.media); name: cell.info && cell.info.media === "video" ? "video" : cell.info && cell.info.media === "audio" ? "mic" : "image"; size: 10; color: page.theme.muted }
                                    Ico { visible: !!(cell.info && cell.info.reminder); name: "bell"; size: 10; color: page.theme.amber }
                                }
                                MouseArea {
                                    id: cellMouse
                                    anchors.fill: parent
                                    enabled: cell.valid
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: page.nb.openDiary(page.fmt.dayKey(cell.date))
                                }
                            }
                        }
                    }
                }
            }
        }

        Panel {
            id: rem
            anchors { right: parent.right; top: parent.top; bottom: parent.bottom }
            width: 400
            title: "Reminders"
            note: page.upcoming.length ? page.upcoming.length + " to go" : ""
            ReminderList {
                anchors.fill: parent
                nb: page.nb
                items: page.upcoming
                compact: true
            }
        }
    }

    // ── activity + media ──
    Item {
        anchors { left: parent.left; right: parent.right; top: topRow.bottom; bottom: parent.bottom
                  leftMargin: 40; rightMargin: 40; topMargin: 20; bottomMargin: 32 }

        Panel {
            id: act
            anchors { left: parent.left; top: parent.top; bottom: parent.bottom; right: med.left; rightMargin: 20 }
            title: "What Cobra & Claude did"
            note: "every change can be undone"
            ActivityList { anchors.fill: parent; nb: page.nb; items: page.ov ? page.ov.activity : [] }
        }

        Panel {
            id: med
            anchors { right: parent.right; top: parent.top; bottom: parent.bottom }
            width: 400
            title: "Recent media"
            note: page.ov ? page.ov.counts.media + " in the notebook" : ""
            MediaGrid {
                anchors.fill: parent
                nb: page.nb
                items: page.ov ? page.ov.media.slice(0, 3) : []
                columns: 3
                emptyText: "Photos, videos and voice memos you add show up here."
            }
        }
    }
}
