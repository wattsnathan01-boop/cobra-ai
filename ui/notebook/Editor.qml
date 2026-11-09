// The open note: title, tags and mood, then its blocks (text, checklists, photos, videos, voice
// memos, files), each labelled with who added it. Text is edited in place and saved as you type.
import QtQuick
import QtMultimedia
import ".."

Item {
    id: ed

    required property var nb
    property Theme theme: Theme {}
    property Fmt fmt: Fmt {}
    readonly property var note: nb.note
    property var blocks: []
    property int textFocus: 0                 // text fields with focus (don't reload under them)
    readonly property bool busy: saveTimer.running || textFocus > 0
    property var focusItem: null               // {b, i}: a checklist item to focus once built
    property bool confirmDelete: false
    property bool asked: false                 // the composer asked Cobra something

    // the note from the daemon → blocks to show (plus an empty one to keep writing in)
    function reload() {
        confirmDelete = false
        if (!note) { blocks = []; return }
        const b = JSON.parse(JSON.stringify(note.blocks))
        const last = b.length ? b[b.length - 1] : null
        if (!last || last.type !== "text" || last.author !== "you")
            b.push({ type: "text", author: "you", text: "", ghost: true })
        blocks = b
    }
    function payload() {
        return blocks.filter(b => !(b.type === "text" && !b.text.trim()))
                     .map(b => { const c = Object.assign({}, b); delete c.path; delete c.ghost; return c })
    }
    function save() {
        saveTimer.stop()
        if (note) nb.request("update", { id: note.id, blocks: payload() })
    }
    function restructure(fn) {               // change the blocks' shape: rebuild and save now
        const b = JSON.parse(JSON.stringify(blocks))
        fn(b)
        blocks = b
        save()
    }
    function setField(key, value) {
        if (!note) return
        const msg = { id: note.id }
        msg[key] = value
        if (saveTimer.running) { msg.blocks = payload(); saveTimer.stop() }
        nb.request("update", msg)
    }

    Timer { id: saveTimer; interval: 700; onTriggered: ed.save() }

    // ── nothing open ──
    Column {
        visible: !ed.note
        anchors.centerIn: parent
        spacing: 14
        Ico { anchors.horizontalCenter: parent.horizontalCenter; name: "notebookOutline"; size: 40; color: Qt.alpha(ed.theme.mint, 0.5) }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Pick a note, or start a new one."
            color: ed.theme.muted
            font { family: ed.theme.mono; pixelSize: 13 }
        }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 8
            Chip { label: "New note"; icon: "plus"; active: true; onClicked: ed.nb.newNote() }
            Chip { label: "Today's diary"; icon: "diary"; onClicked: ed.nb.openDiary() }
        }
    }

    // ── toolbar ──
    Item {
        id: bar
        visible: !!ed.note
        x: 56; y: 22
        width: parent.width - 112
        height: 34
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: ed.note ? (ed.note.kind === "diary" ? "Diary  /  " + Qt.formatDate(new Date(ed.note.date), "MMMM") + "  /  " + Qt.formatDate(new Date(ed.note.date), "ddd d")
                                                       : "Notes  /  " + ed.note.title) : ""
            width: parent.width - tools.width - 20
            elide: Text.ElideRight
            color: ed.theme.muted
            font { family: ed.theme.mono; pixelSize: 11 }
        }
        Row {
            id: tools
            anchors.right: parent.right
            spacing: 8
            Chip { icon: "boxChecked"; label: ""; height: 32
                   onClicked: { const n = ed.blocks.length; ed.focusItem = { b: n, i: 0 }
                                ed.restructure(b => b.push({ type: "checklist", author: "you", items: [{ text: "", done: false }] })) } }
            Chip { icon: ed.note && ed.note.pinned ? "pin" : "pinOutline"; label: ""; height: 32
                   active: !!(ed.note && ed.note.pinned); tint: ed.theme.amber
                   onClicked: ed.setField("pinned", !ed.note.pinned) }
            Chip { icon: "trash"; label: ed.confirmDelete ? "Delete?" : ""; height: 32
                   active: ed.confirmDelete; tint: ed.theme.crimson
                   onClicked: { if (ed.confirmDelete) ed.nb.deleteNote(ed.note.id); else ed.confirmDelete = true } }
        }
    }

    // ── the note ──
    Flickable {
        id: flick
        visible: !!ed.note
        anchors { left: parent.left; right: parent.right; top: bar.bottom; bottom: composer.top
                  topMargin: 18; bottomMargin: 16 }
        contentHeight: body.implicitHeight + 40
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: body
            x: 56
            width: flick.width - 112
            spacing: 18

            // title, date, mood, tags
            Column {
                width: parent.width
                spacing: 10
                TextInput {
                    id: titleInput
                    width: parent.width
                    text: ed.note ? ed.note.title : ""
                    color: ed.theme.text
                    selectionColor: Qt.alpha(ed.theme.mint, 0.35)
                    selectByMouse: true
                    wrapMode: TextInput.Wrap
                    font { family: ed.theme.mono; pixelSize: 28; weight: Font.Bold }
                    onEditingFinished: if (ed.note && text.trim() && text !== ed.note.title) ed.setField("title", text.trim())
                    onActiveFocusChanged: ed.textFocus += activeFocus ? 1 : -1
                    Keys.onReturnPressed: focus = false
                }
                Row {
                    spacing: 14
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: ed.note ? Qt.formatDateTime(new Date(ed.note.created), "ddd d MMM yyyy · HH:mm") : ""
                        color: ed.theme.muted
                        font { family: ed.theme.mono; pixelSize: 11 }
                    }
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 4
                        Repeater {
                            model: [["good", "happy", ed.theme.mint], ["meh", "neutral", ed.theme.amber], ["rough", "sad", ed.theme.crimson]]
                            Rectangle {
                                required property var modelData
                                readonly property bool on: !!(ed.note && ed.note.mood === modelData[0])
                                width: moodRow.implicitWidth + 12
                                height: 22
                                radius: 4
                                color: on ? Qt.alpha(modelData[2], 0.14) : "transparent"
                                Row {
                                    id: moodRow
                                    anchors.centerIn: parent
                                    spacing: 4
                                    Ico { name: modelData[1]; size: 13; color: parent.parent.on ? modelData[2] : ed.theme.muted }
                                    Text {
                                        visible: parent.parent.on
                                        text: modelData[0] + " day"
                                        color: modelData[2]
                                        font { family: ed.theme.mono; pixelSize: 10 }
                                    }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: ed.setField("mood", parent.on ? "" : modelData[0])
                                }
                            }
                        }
                    }
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6
                        Ico { name: "tag"; size: 12; color: ed.theme.amber; anchors.verticalCenter: parent.verticalCenter }
                        TextInput {
                            id: tagsInput
                            anchors.verticalCenter: parent.verticalCenter
                            width: Math.max(140, contentWidth + 10)
                            text: ed.note ? ed.note.tags.map(t => "#" + t).join(" ") : ""
                            color: ed.theme.amber
                            selectByMouse: true
                            font { family: ed.theme.mono; pixelSize: 11 }
                            onActiveFocusChanged: ed.textFocus += activeFocus ? 1 : -1
                            onEditingFinished: {
                                const tags = text.split(/[\s,]+/).map(t => t.replace(/^#/, "")).filter(t => t)
                                if (ed.note && tags.join(" ") !== ed.note.tags.join(" ")) ed.setField("tags", tags)
                            }
                            Keys.onReturnPressed: focus = false
                            Text {
                                visible: !parent.text && !parent.activeFocus
                                text: "add tags"
                                color: ed.theme.muted
                                font: parent.font
                            }
                        }
                    }
                }
            }

            Repeater {
                model: ed.blocks
                delegate: Loader {
                    id: blockLoader
                    required property var modelData
                    required property int index
                    width: body.width
                    HoverHandler { id: blockHover }
                    Rectangle {
                        visible: blockHover.hovered && !blockLoader.modelData.ghost
                        anchors { right: parent.right; top: parent.top; topMargin: -4 }
                        z: 5
                        width: rm.implicitWidth + 14; height: 22; radius: 6
                        color: "#0b1012"
                        border.color: rmMouse.containsMouse ? ed.theme.crimson : "#22302f"
                        Text {
                            id: rm
                            anchors.centerIn: parent
                            text: "remove ✕"
                            color: rmMouse.containsMouse ? ed.theme.crimson : ed.theme.muted
                            font { family: ed.theme.mono; pixelSize: 10 }
                        }
                        MouseArea {
                            id: rmMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: ed.restructure(b => b.splice(blockLoader.index, 1))
                        }
                    }
                    sourceComponent: modelData.type === "text" ? textBlock
                                   : modelData.type === "checklist" ? checkBlock
                                   : modelData.type === "image" ? imageBlock
                                   : modelData.type === "video" ? videoBlock
                                   : modelData.type === "audio" ? audioBlock : fileBlock
                }
            }
        }
    }

    // ── block kinds ──

    // who added a block, shown when it changes from the block before
    component BlockHead: Item {
        id: head
        property var block
        property int index
        readonly property bool shown: !block.ghost && (index === 0 || !ed.blocks[index - 1] || ed.blocks[index - 1].author !== block.author)
        width: parent ? parent.width : 0
        height: shown ? 20 : 0
        visible: shown
        Author { who: head.block.author; long: true; anchors.verticalCenter: parent.verticalCenter }
    }

    Component {
        id: textBlock
        Column {
            id: tb
            readonly property var block: parent.modelData
            readonly property int index: parent.index
            spacing: 6
            BlockHead { block: tb.block; index: tb.index }
            TextEdit {
                id: te
                width: parent.width
                text: tb.block.text
                wrapMode: TextEdit.Wrap
                selectByMouse: true
                color: "#c9d6d2"
                selectionColor: Qt.alpha(ed.theme.mint, 0.35)
                font { family: ed.theme.mono; pixelSize: 14 }
                textFormat: TextEdit.PlainText
                onTextChanged: if (text !== ed.blocks[tb.index].text) { ed.blocks[tb.index].text = text; saveTimer.restart() }
                onActiveFocusChanged: ed.textFocus += activeFocus ? 1 : -1
                Text {
                    visible: !te.text && !!tb.block.ghost
                    text: ed.blocks.length > 1 ? "Keep writing…" : "Start writing…"
                    color: ed.theme.muted
                    font: te.font
                }
            }
        }
    }

    Component {
        id: checkBlock
        Rectangle {
            id: cb
            readonly property var block: parent.modelData
            readonly property int index: parent.index
            readonly property color tint: block.author === "claude" ? ed.theme.violet : block.author === "cobra" ? ed.theme.mint : ed.theme.muted
            height: col.implicitHeight + 28
            radius: 10
            color: Qt.alpha(tint, 0.04)
            Rectangle { width: 2; height: parent.height; color: cb.tint; radius: 1 }
            Column {
                id: col
                x: 16; y: 14
                width: parent.width - 32
                spacing: 8
                BlockHead { block: cb.block; index: cb.index }
                Repeater {
                    model: cb.block.items
                    Row {
                        id: itemRow
                        required property var modelData
                        required property int index
                        spacing: 10
                        width: col.width
                        Ico {
                            anchors.verticalCenter: parent.verticalCenter
                            name: itemRow.modelData.done ? "boxChecked" : "box"
                            size: 16
                            color: itemRow.modelData.done ? ed.theme.mint : ed.theme.muted
                            MouseArea {
                                anchors { fill: parent; margins: -4 }
                                cursorShape: Qt.PointingHandCursor
                                onClicked: ed.restructure(b => { const it = b[cb.index].items[itemRow.index]; it.done = !it.done })
                            }
                        }
                        TextInput {
                            id: itemInput
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 30
                            text: itemRow.modelData.text
                            color: itemRow.modelData.done ? ed.theme.muted : ed.theme.text
                            font { family: ed.theme.mono; pixelSize: 13; strikeout: itemRow.modelData.done }
                            selectByMouse: true
                            onActiveFocusChanged: ed.textFocus += activeFocus ? 1 : -1
                            onTextEdited: { ed.blocks[cb.index].items[itemRow.index].text = text; saveTimer.restart() }
                            Keys.onReturnPressed: {
                                ed.focusItem = { b: cb.index, i: itemRow.index + 1 }
                                ed.restructure(b => b[cb.index].items.splice(itemRow.index + 1, 0, { text: "", done: false }))
                            }
                            Keys.onPressed: e => {
                                if (e.key === Qt.Key_Backspace && text === "") {
                                    e.accepted = true
                                    ed.focusItem = itemRow.index > 0 ? { b: cb.index, i: itemRow.index - 1 } : null
                                    ed.restructure(b => { b[cb.index].items.splice(itemRow.index, 1)
                                                          if (!b[cb.index].items.length) b.splice(cb.index, 1) })
                                }
                            }
                            Component.onCompleted: if (ed.focusItem && ed.focusItem.b === cb.index && ed.focusItem.i === itemRow.index) {
                                ed.focusItem = null; forceActiveFocus(); cursorPosition = text.length
                            }
                            Text {
                                visible: !parent.text
                                text: "List item"
                                color: ed.theme.muted
                                font { family: ed.theme.mono; pixelSize: 13 }
                            }
                        }
                    }
                }
            }
        }
    }

    Component {
        id: imageBlock
        Column {
            id: ib
            readonly property var block: parent.modelData
            readonly property int index: parent.index
            spacing: 8
            BlockHead { block: ib.block; index: ib.index }
            Rectangle {
                width: parent.width
                height: Math.min(320, img.status === Image.Ready ? width * img.implicitHeight / Math.max(1, img.implicitWidth) : 220)
                radius: 10
                color: "#172124"
                clip: true
                Image {
                    id: img
                    anchors.fill: parent
                    source: "file://" + ib.block.path
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    sourceSize.width: 1400
                }
                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: ed.nb.openPath(ib.block.path) }
            }
            Text {
                visible: ib.block.caption !== ""
                text: ib.block.caption
                color: ed.theme.muted
                font { family: ed.theme.mono; pixelSize: 11 }
            }
        }
    }

    Component {
        id: videoBlock
        Column {
            id: vb
            readonly property var block: parent.modelData
            readonly property int index: parent.index
            spacing: 8
            BlockHead { block: vb.block; index: vb.index }
            Rectangle {
                width: parent.width
                height: Math.min(320, width * 9 / 16)
                radius: 10
                color: "#000000"
                clip: true
                MediaPlayer {
                    id: player
                    source: "file://" + vb.block.path
                    videoOutput: out
                    audioOutput: AudioOutput {}
                }
                VideoOutput { id: out; anchors.fill: parent; fillMode: VideoOutput.PreserveAspectFit }
                Component.onCompleted: { player.play(); player.pause() }   // shows the first frame
                Rectangle {
                    anchors.centerIn: parent
                    visible: player.playbackState !== MediaPlayer.PlayingState
                    width: 52; height: 52; radius: 26
                    color: Qt.rgba(0.04, 0.06, 0.07, 0.7)
                    border.color: Qt.alpha(ed.theme.mint, 0.5)
                    Ico { anchors.centerIn: parent; name: "play"; size: 24; color: ed.theme.mint }
                }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: player.playbackState === MediaPlayer.PlayingState ? player.pause() : player.play()
                    onDoubleClicked: ed.nb.openPath(vb.block.path)
                }
                Rectangle {
                    anchors { left: parent.left; bottom: parent.bottom; margins: 10 }
                    width: vcap.implicitWidth + 14; height: 20; radius: 4
                    color: Qt.rgba(0.04, 0.06, 0.07, 0.8)
                    Text {
                        id: vcap
                        anchors.centerIn: parent
                        text: (vb.block.caption || vb.block.src.split("/").pop())
                              + (player.duration > 0 ? "  ·  " + Math.floor(player.duration / 60000) + ":" + String(Math.floor(player.duration / 1000) % 60).padStart(2, "0") : "")
                        color: ed.theme.text
                        font { family: ed.theme.mono; pixelSize: 10 }
                    }
                }
            }
        }
    }

    Component {
        id: audioBlock
        Column {
            id: ab
            readonly property var block: parent.modelData
            readonly property int index: parent.index
            spacing: 8
            BlockHead { block: ab.block; index: ab.index }
            Rectangle {
                width: parent.width
                height: 56
                radius: 10
                color: "#11181b"
                border.color: "#22302f"
                MediaPlayer { id: aplayer; source: "file://" + ab.block.path; audioOutput: AudioOutput {} }
                Rectangle {
                    id: aplay
                    x: 14; anchors.verticalCenter: parent.verticalCenter
                    width: 32; height: 32; radius: 16
                    color: Qt.alpha(ed.theme.crimson, 0.14)
                    Ico { anchors.centerIn: parent; name: aplayer.playbackState === MediaPlayer.PlayingState ? "pause" : "play"; size: 16; color: ed.theme.crimson }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                onClicked: aplayer.playbackState === MediaPlayer.PlayingState ? aplayer.pause() : aplayer.play() }
                }
                Item {
                  anchors { left: aplay.right; leftMargin: 14; right: alabel.left; rightMargin: 14; top: parent.top; bottom: parent.bottom }
                  Row {
                    id: wave
                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter }
                    spacing: 3
                    readonly property int bars: Math.max(1, Math.floor(width / 6))
                    readonly property real progress: aplayer.duration > 0 ? aplayer.position / aplayer.duration : 0
                    Repeater {
                        model: wave.bars
                        Rectangle {
                            required property int index
                            anchors.verticalCenter: parent.verticalCenter
                            width: 3
                            radius: 1.5
                            // a steady made-up waveform (the real one would need decoding the file)
                            height: 6 + 20 * Math.abs(Math.sin(index * 1.7) * Math.cos(index * 0.37))
                            color: index / wave.bars <= wave.progress ? ed.theme.crimson : Qt.alpha(ed.theme.crimson, 0.25)
                        }
                    }
                  }
                  MouseArea {
                      anchors.fill: parent
                      cursorShape: Qt.PointingHandCursor
                      onClicked: m => { if (aplayer.duration > 0) { aplayer.position = aplayer.duration * m.x / width; aplayer.play() } }
                  }
                }
                Text {
                    id: alabel
                    anchors { right: parent.right; rightMargin: 16; verticalCenter: parent.verticalCenter }
                    text: ab.block.caption || ab.block.src.split("/").pop()
                    color: ed.theme.muted
                    font { family: ed.theme.mono; pixelSize: 10 }
                }
            }
        }
    }

    Component {
        id: fileBlock
        Column {
            id: fb
            readonly property var block: parent.modelData
            readonly property int index: parent.index
            spacing: 8
            BlockHead { block: fb.block; index: fb.index }
            Rectangle {
                width: Math.min(parent.width, frow.implicitWidth + 32)
                height: 44
                radius: 10
                color: fileMouse.containsMouse ? "#172124" : "#11181b"
                border.color: "#22302f"
                Row {
                    id: frow
                    anchors { left: parent.left; leftMargin: 16; verticalCenter: parent.verticalCenter }
                    spacing: 10
                    Ico { name: "doc"; size: 16; color: ed.theme.text }
                    Text {
                        text: fb.block.caption || fb.block.src.split("/").pop()
                        color: ed.theme.text
                        font { family: ed.theme.mono; pixelSize: 12 }
                    }
                    Ico { name: "open"; size: 13; color: ed.theme.muted }
                }
                MouseArea { id: fileMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                            onClicked: ed.nb.openPath(fb.block.path) }
            }
        }
    }

    // ── composer: ask Cobra about this note, attach things, record a voice memo ──
    Column {
        id: composer
        visible: !!ed.note
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: 56; rightMargin: 56; bottomMargin: 22 }
        spacing: 10

        Rectangle {
            visible: ed.asked && (ed.nb.cobra.reply !== "" || ed.nb.cobra.mode === "thinking")
            width: parent.width
            height: Math.min(140, replyText.implicitHeight + 24)
            radius: 10
            color: Qt.alpha(ed.theme.mint, 0.05)
            border.color: Qt.alpha(ed.theme.mint, 0.25)
            clip: true
            Text {
                id: replyText
                x: 14; y: 12
                width: parent.width - 50
                wrapMode: Text.Wrap
                text: ed.nb.cobra.mode === "thinking" && !ed.nb.cobra.reply
                      ? "Cobra is thinking" + (ed.nb.cobra.tool ? " · " + ed.nb.cobra.tool : "…")
                      : ed.nb.cobra.reply
                color: ed.theme.text
                font { family: ed.theme.mono; pixelSize: 12 }
            }
            Text {
                anchors { right: parent.right; top: parent.top; margins: 10 }
                text: "✕"
                color: ed.theme.muted
                font { family: ed.theme.mono; pixelSize: 11 }
                MouseArea { anchors { fill: parent; margins: -6 } cursorShape: Qt.PointingHandCursor; onClicked: ed.asked = false }
            }
        }

        Rectangle {
            width: parent.width
            height: 54
            radius: 12
            color: "#11181b"
            border.color: ed.nb.recording.on ? Qt.alpha(ed.theme.crimson, 0.6) : ask.activeFocus ? Qt.alpha(ed.theme.violet, 0.7) : Qt.alpha(ed.theme.violet, 0.33)

            Ico { id: spark; x: 16; anchors.verticalCenter: parent.verticalCenter; name: "sparkle"; size: 17; color: ed.theme.violet }
            TextInput {
                id: ask
                anchors { left: spark.right; leftMargin: 12; right: actions.left; rightMargin: 12; verticalCenter: parent.verticalCenter }
                color: ed.theme.text
                selectByMouse: true
                clip: true
                font { family: ed.theme.mono; pixelSize: 12 }
                onAccepted: {
                    if (!text.trim()) return
                    ed.nb.request("ask", { id: ed.note.id, text: text })
                    ed.asked = true
                    text = ""
                }
                Text {
                    visible: !ask.text
                    anchors.verticalCenter: parent.verticalCenter
                    text: ed.nb.recording.on ? "Recording a voice memo… press ■ to stop"
                                             : "Ask Cobra — “turn this into a checklist”, “remind me about this on Friday”"
                    color: ed.nb.recording.on ? ed.theme.crimson : ed.theme.muted
                    font: ask.font
                    width: ask.width
                    elide: Text.ElideRight
                }
            }
            Row {
                id: actions
                anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                spacing: 6
                Repeater {
                    model: [["imagePlus", "Photos and videos"], ["paperclip", "A file"]]
                    Rectangle {
                        required property var modelData
                        width: 32; height: 32; radius: 8
                        color: attMouse.containsMouse ? Qt.alpha(ed.theme.text, 0.07) : "transparent"
                        Ico { anchors.centerIn: parent; name: modelData[0]; size: 17; color: "#a9b8b4" }
                        MouseArea { id: attMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                    onClicked: ed.nb.pickFiles(ed.note.id, modelData[0] === "imagePlus") }
                    }
                }
                Rectangle {
                    width: ed.nb.recording.on ? recLabel.implicitWidth + 44 : 32
                    height: 32; radius: 8
                    color: ed.nb.recording.on ? Qt.alpha(ed.theme.crimson, 0.15) : micMouse.containsMouse ? Qt.alpha(ed.theme.text, 0.07) : "transparent"
                    Row {
                        anchors.centerIn: parent
                        spacing: 6
                        Ico { name: ed.nb.recording.on ? "stop" : "mic"; size: 17; color: ed.nb.recording.on ? ed.theme.crimson : "#a9b8b4" }
                        Text {
                            id: recLabel
                            visible: ed.nb.recording.on
                            anchors.verticalCenter: parent.verticalCenter
                            text: Math.floor(ed.nb.recordSeconds / 60) + ":" + String(ed.nb.recordSeconds % 60).padStart(2, "0")
                            color: ed.theme.crimson
                            font { family: ed.theme.mono; pixelSize: 11 }
                        }
                    }
                    MouseArea { id: micMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: ed.nb.request(ed.nb.recording.on ? "record_stop" : "record_start", { id: ed.note.id }) }
                }
                Rectangle {
                    width: 32; height: 32; radius: 8
                    color: ed.theme.mint
                    opacity: ask.text.trim() ? 1 : 0.4
                    Ico { anchors.centerIn: parent; name: "up"; size: 17; color: "#0b1012" }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: ask.accepted() }
                }
            }
        }
    }
}
