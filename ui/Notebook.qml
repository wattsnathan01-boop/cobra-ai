// The notebook window: notes, diary, reminders and media shared with Cobra and Claude.
// Open it with `cobractl notebook`, or "Cobra, open my notebook".
import QtQuick
import QtQuick.Dialogs
import Quickshell
import "notebook"

FloatingWindow {
    id: win

    required property Cobra cobra
    property Theme theme: Theme {}
    property Fmt fmt: Fmt {}

    property string page: "today"        // today | notes | diary | reminders | media | activity
    property var overview: null
    property var note: null              // the open note
    property string query: ""
    property string tagFilter: ""
    property bool focusReminder: false
    property var recording: ({ on: false })
    property int recordSeconds: 0
    property string toastText: ""
    property bool toastError: false
    property var reminderBanner: null    // a reminder that just went off
    property int reqSeq: 0
    property var callbacks: ({})

    title: "Cobra notebook"
    implicitWidth: 1440
    implicitHeight: 900
    minimumSize: Qt.size(1180, 700)
    color: "#0b1012"
    visible: cobra.notebookOpen
    onVisibleChanged: {
        if (!visible) cobra.notebookOpen = false
        else refresh()
    }

    // ── talking to cobrad ──
    function request(action, args, then) {
        const msg = Object.assign({ type: "notebook", action: action, req: ++reqSeq }, args || {})
        if (then) callbacks[reqSeq] = then
        cobra.send(msg)
    }
    function refresh() {
        request("overview")
        if (note) request("get", { id: note.id })
    }
    function showNote(data) {
        if (note && data.id === note.id && editor.busy) {   // don't pull text out from under you
            note.updated = data.updated
            return
        }
        note = data
        editor.reload()
    }
    function toast(text, error) { toastText = text; toastError = !!error; toastShow.restart() }

    function handle(ev) {
        if (ev.type === "notebook_changed") { refresh(); return }
        if (ev.type === "recording") { recording = ev; if (ev.on) recordSeconds = 0; return }
        if (ev.type === "reminder") { reminderBanner = ev; return }
        if (ev.type === "notebook_open") { if (ev.page) page = ev.page; if (ev.id) open(ev.id); return }
        if (ev.type !== "notebook") return
        const then = callbacks[ev.req]
        delete callbacks[ev.req]
        if (!ev.ok) { toast(ev.error, true); return }
        const d = ev.data
        switch (ev.action) {
        case "overview":
            overview = d
            recording = d.recording || { on: false }
            if (note && !d.notes.some(n => n.id === note.id)) { note = null; editor.reload() }
            break
        case "get": case "update": case "append":
            showNote(d)
            break
        case "create": case "diary_today": case "attach": case "record_stop":
            note = d; editor.reload()
            if (page !== "notes" && page !== "diary") page = d.kind === "diary" ? "diary" : "notes"
            if (ev.action === "attach") toast("added to " + d.title)
            break
        case "delete":
            note = null; editor.reload(); toast("moved to the notebook's trash")
            break
        case "undo":
            toast(d)
            break
        case "reminder_add":
            toast("reminder set for " + fmt.due(d.due))
            break
        }
        if (then) then(d)
    }
    Connections {
        target: win.cobra
        function onNotebookEvent(ev) { win.handle(ev) }
        function onOnlineChanged() { if (win.cobra.online && win.visible) win.refresh() }
    }

    // ── actions the pages use ──
    function open(id) {
        if (page !== "notes" && page !== "diary") page = "notes"
        request("get", { id: id }, d => { note = d; editor.reload() })
    }
    function newNote() {
        page = "notes"
        request("create", { title: "Untitled" })
    }
    function openDiary(day) { request("diary_today", { day: day || "" }) }
    function deleteNote(id) { request("delete", { id: id }) }
    function openPath(path) { request("open_path", { path: path }) }
    property string pickTarget: ""
    function pickFiles(noteId, media) {
        pickTarget = noteId
        picker.nameFilters = media ? ["Photos and videos (*.jpg *.jpeg *.png *.gif *.webp *.heic *.avif *.mp4 *.webm *.mkv *.mov *.m4v)", "All files (*)"]
                                   : ["All files (*)"]
        picker.open()
    }
    function captureToDiary(kind) {
        request("diary_today", {}, d => {
            if (kind === "media") pickFiles(d.id, true)
            else if (kind === "voice") request("record_start", { id: d.id })
        })
    }

    FileDialog {
        id: picker
        title: "Add to the note"
        fileMode: FileDialog.OpenFiles
        currentFolder: "file://" + Quickshell.env("HOME") + "/Pictures"
        onAccepted: {
            for (const url of selectedFiles)
                win.request("attach", { id: win.pickTarget, path: decodeURIComponent(url.toString().replace(/^file:\/\//, "")) })
        }
    }

    Timer { interval: 1000; repeat: true; running: win.recording.on; onTriggered: win.recordSeconds++ }

    // ── sidebar ──
    Rectangle {
        id: side
        width: 248
        height: parent.height
        color: "#11181b"
        Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: "#22302f" }

        Column {
            x: 20; y: 28
            width: parent.width - 40
            spacing: 26

            Column {
                spacing: 6
                Text { text: "COBRA"; color: win.theme.mint; font { family: "Orbitron"; pixelSize: 22; weight: Font.Black; letterSpacing: 6 } }
                Text { text: "N O T E B O O K"; color: win.theme.muted; font { family: win.theme.mono; pixelSize: 10 } }
            }

            Rectangle {
                width: parent.width
                height: 42
                radius: 10
                color: newMouse.containsMouse ? Qt.alpha(win.theme.mint, 0.16) : Qt.alpha(win.theme.mint, 0.1)
                border.color: Qt.alpha(win.theme.mint, 0.35)
                Row {
                    anchors { left: parent.left; leftMargin: 14; verticalCenter: parent.verticalCenter }
                    spacing: 10
                    Ico { name: "plus"; size: 16; color: win.theme.mint }
                    Text { text: "New entry"; color: win.theme.mint; font { family: win.theme.mono; pixelSize: 13; weight: Font.DemiBold } }
                }
                Text {
                    anchors { right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                    text: "Ctrl N"
                    color: win.theme.muted
                    font { family: win.theme.mono; pixelSize: 10 }
                }
                MouseArea { id: newMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: win.newNote() }
            }

            Column {
                width: parent.width
                spacing: 2
                Repeater {
                    model: [
                        ["today", "sun", "Today", ""],
                        ["notes", "notebook", "All notes", "notes"],
                        ["diary", "diary", "Diary", "diary"],
                        ["reminders", "bell", "Reminders", "reminders"],
                        ["media", "images", "Media", "media"],
                        ["activity", "sparkle", "AI activity", ""],
                    ]
                    Rectangle {
                        id: navItem
                        required property var modelData
                        readonly property bool on: win.page === modelData[0]
                        width: parent.width
                        height: 38
                        radius: 8
                        color: on ? "#172124" : navMouse.containsMouse ? Qt.alpha(win.theme.text, 0.03) : "transparent"
                        Row {
                            anchors { left: parent.left; leftMargin: 12; verticalCenter: parent.verticalCenter }
                            spacing: 12
                            Ico { name: navItem.modelData[1]; size: 16; color: navItem.on ? win.theme.mint : win.theme.muted }
                            Text { text: navItem.modelData[2]; color: navItem.on ? win.theme.text : "#a9b8b4"; font { family: win.theme.mono; pixelSize: 13 } }
                        }
                        Text {
                            anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                            text: navItem.modelData[3] && win.overview ? win.overview.counts[navItem.modelData[3]] : ""
                            color: win.theme.muted
                            font { family: win.theme.mono; pixelSize: 11 }
                        }
                        MouseArea {
                            id: navMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: { win.page = navItem.modelData[0]; win.tagFilter = "" }
                        }
                    }
                }
            }

            Column {
                width: parent.width
                spacing: 8
                visible: !!(win.overview && win.overview.tags.length > 0)
                Text { text: "T A G S"; color: win.theme.muted; font { family: win.theme.mono; pixelSize: 10 } }
                Repeater {
                    model: win.overview ? win.overview.tags.slice(0, 8) : []
                    Rectangle {
                        id: tagItem
                        required property var modelData
                        required property int index
                        width: parent.width
                        height: 26
                        radius: 6
                        color: win.tagFilter === modelData[0] ? "#172124" : "transparent"
                        Row {
                            anchors { left: parent.left; leftMargin: 12; verticalCenter: parent.verticalCenter }
                            spacing: 10
                            Rectangle { width: 7; height: 7; radius: 3.5; anchors.verticalCenter: parent.verticalCenter
                                        color: [win.theme.mint, win.theme.violet, win.theme.crimson, win.theme.amber][tagItem.index % 4] }
                            Text { text: "#" + tagItem.modelData[0]; color: "#a9b8b4"; font { family: win.theme.mono; pixelSize: 12 } }
                        }
                        Text {
                            anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                            text: tagItem.modelData[1]
                            color: win.theme.muted
                            font { family: win.theme.mono; pixelSize: 10 }
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: { win.tagFilter = win.tagFilter === tagItem.modelData[0] ? "" : tagItem.modelData[0]; win.page = "notes" }
                        }
                    }
                }
            }
        }

        Rectangle {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 20 }
            height: con.implicitHeight + 28
            radius: 10
            color: "#0b1012"
            border.color: "#22302f"
            Column {
                id: con
                x: 14; y: 14
                width: parent.width - 28
                spacing: 10
                Text { text: "C O N N E C T E D"; color: win.theme.muted; font { family: win.theme.mono; pixelSize: 10 } }
                Repeater {
                    model: {
                        const claude = win.overview ? win.overview.activity.find(a => a.who === "claude") : null
                        return [
                            ["Cobra", win.cobra.online ? "voice · local" : "offline", win.cobra.online ? win.theme.mint : win.theme.crimson],
                            ["Claude Code", claude && win.fmt.isToday(claude.ts) ? "mcp · " + win.fmt.hm(new Date(claude.ts)) : "mcp", win.theme.violet],
                        ]
                    }
                    Item {
                        required property var modelData
                        width: parent.width
                        height: 16
                        Row {
                            spacing: 10
                            anchors.verticalCenter: parent.verticalCenter
                            Rectangle { width: 8; height: 8; radius: 4; color: modelData[2]; anchors.verticalCenter: parent.verticalCenter }
                            Text { text: modelData[0]; color: win.theme.text; font { family: win.theme.mono; pixelSize: 12 } }
                        }
                        Text {
                            anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                            text: modelData[1]
                            color: win.theme.muted
                            font { family: win.theme.mono; pixelSize: 10 }
                        }
                    }
                }
            }
        }
    }

    // ── pages ──
    Item {
        id: main
        anchors { left: side.right; right: parent.right; top: parent.top; bottom: parent.bottom }

        TodayPage { anchors.fill: parent; nb: win; visible: win.page === "today" }

        Item {
            anchors.fill: parent
            visible: win.page === "notes" || win.page === "diary"
            NoteList { id: noteList; width: 360; height: parent.height; nb: win }
            Editor {
                id: editor
                anchors { left: noteList.right; right: parent.right; top: parent.top; bottom: parent.bottom }
                nb: win
            }
        }

        Loader { anchors.fill: parent; active: win.page === "reminders"; sourceComponent: RemindersPage { nb: win } }
        Loader { anchors.fill: parent; active: win.page === "media"; sourceComponent: MediaPage { nb: win } }
        Loader { anchors.fill: parent; active: win.page === "activity"; sourceComponent: ActivityPage { nb: win } }
    }

    Shortcut { sequence: "Ctrl+N"; onActivated: win.newNote() }
    Shortcut { sequence: "Ctrl+W"; onActivated: win.cobra.notebookOpen = false }

    // a reminder going off
    Rectangle {
        visible: win.reminderBanner !== null
        anchors { horizontalCenter: main.horizontalCenter; top: parent.top; topMargin: 20 }
        width: bannerRow.implicitWidth + 36
        height: 52
        radius: 12
        color: "#1a1712"
        border.color: Qt.alpha(win.theme.amber, 0.7)
        Row {
            id: bannerRow
            anchors.centerIn: parent
            spacing: 12
            Ico { name: "bellRing"; size: 20; color: win.theme.amber; anchors.verticalCenter: parent.verticalCenter }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: win.reminderBanner ? win.reminderBanner.text : ""
                color: win.theme.text
                font { family: win.theme.mono; pixelSize: 14; weight: Font.DemiBold }
            }
            Chip { label: "Done"; icon: "check"; tint: win.theme.amber; active: true
                   onClicked: { win.request("reminder_done", { rid: win.reminderBanner.id }); win.reminderBanner = null } }
            Chip { label: "10 min"; icon: "snooze"
                   onClicked: { win.request("reminder_snooze", { rid: win.reminderBanner.id, minutes: 10 }); win.reminderBanner = null } }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: "✕"
                color: win.theme.muted
                font { family: win.theme.mono; pixelSize: 12 }
                MouseArea { anchors { fill: parent; margins: -6 } cursorShape: Qt.PointingHandCursor; onClicked: win.reminderBanner = null }
            }
        }
    }

    // "added to …" / an error, for a few seconds
    Rectangle {
        anchors { right: parent.right; rightMargin: 28; bottom: parent.bottom; bottomMargin: 96 }
        width: toastLabel.implicitWidth + 32
        height: 38
        radius: 10
        color: "#111a1c"
        border.color: Qt.alpha(win.toastError ? win.theme.crimson : win.theme.mint, 0.6)
        opacity: toastShow.running ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 200 } }
        Text {
            id: toastLabel
            anchors.centerIn: parent
            text: win.toastText
            color: win.toastError ? win.theme.crimson : win.theme.mint
            font { family: win.theme.mono; pixelSize: 12 }
        }
        Timer { id: toastShow; interval: 3500 }
    }
}
