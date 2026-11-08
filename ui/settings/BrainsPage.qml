// Which models Cobra thinks with.
import QtQuick
import ".."

Column {
    id: page

    required property Cobra cobra
    property Theme theme: Theme {}
    readonly property var s: cobra.settings ? cobra.settings.brain : null
    readonly property var vram: s ? s.vram : ({})

    spacing: 28

    PageHeader {
        width: parent.width
        title: "Brains"
        subtitle: "Which models Cobra thinks with, and when she uses each one."
    }

    Row {
        width: parent.width
        spacing: 20

        Card {
            width: (parent.width - 20) / 2
            icon: 0xF0674  // creation (sparkles)
            title: "Claude"
            status: "not set up"
            tint: page.theme.muted
            Text {
                width: parent.width
                text: "Cobra is running local-only for now. Adding Claude (Opus 5.5 for real work, "
                      + "Haiku 5.5 for quick replies) needs an Anthropic API key, kept in your "
                      + "system keyring, never in a file."
                color: page.theme.muted
                wrapMode: Text.Wrap
                lineHeight: 1.3
                font { family: page.theme.mono; pixelSize: 12 }
            }
            Repeater {
                model: [["Model", page.cobra.settings ? page.cobra.settings.claude.model : ""],
                        ["Fast model", page.cobra.settings ? page.cobra.settings.claude.fast_model : ""]]
                Item {
                    required property var modelData
                    width: parent.width
                    height: 34
                    Rectangle { width: parent.width; height: 1; color: Qt.alpha(page.theme.text, 0.07) }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData[0]
                        color: page.theme.muted
                        font { family: page.theme.mono; pixelSize: 12 }
                    }
                    Text {
                        anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                        text: modelData[1]
                        color: page.theme.muted
                        font { family: page.theme.mono; pixelSize: 12 }
                    }
                }
            }
        }

        Card {
            width: (parent.width - 20) / 2
            icon: 0xF061A  // chip
            title: "Local · Ollama"
            status: page.s && page.s.ollama_up ? "running" : "not running"
            tint: page.s && page.s.ollama_up ? page.theme.violet : page.theme.crimson

            Item {
                width: parent.width
                height: 22
                Text {
                    text: "Endpoint"
                    color: page.theme.muted
                    font { family: page.theme.mono; pixelSize: 12 }
                }
                Text {
                    anchors.right: parent.right
                    text: page.s ? page.s.host.replace(/^https?:\/\//, "") : ""
                    color: page.theme.text
                    font { family: page.theme.mono; pixelSize: 12 }
                }
            }

            Repeater {
                model: page.s ? page.s.models : []
                Rectangle {
                    required property var modelData
                    readonly property bool on: page.s && modelData.name === page.s.model
                    readonly property real freeGb: page.vram.total_mb ? page.vram.total_mb / 1024 - 1.6 : 6
                    width: parent.width
                    height: 54
                    radius: 10
                    color: on ? Qt.alpha(page.theme.violet, 0.12) : Qt.alpha(page.theme.text, 0.03)
                    border.color: on ? Qt.alpha(page.theme.violet, 0.6) : Qt.alpha(page.theme.text, 0.08)
                    Rectangle {
                        id: dot
                        anchors { left: parent.left; leftMargin: 16; verticalCenter: parent.verticalCenter }
                        width: 14
                        height: 14
                        radius: 7
                        color: parent.on ? page.theme.violet : "transparent"
                        border.color: parent.on ? page.theme.violet : page.theme.muted
                        border.width: 1.5
                    }
                    Column {
                        anchors { left: dot.right; leftMargin: 14; verticalCenter: parent.verticalCenter }
                        spacing: 4
                        Text {
                            text: modelData.name
                            color: page.theme.text
                            font { family: page.theme.mono; pixelSize: 12; weight: Font.Medium }
                        }
                        Text {
                            text: modelData.size_gb + " GB · "
                                  + (modelData.size_gb <= parent.parent.freeGb ? "fits in VRAM with Whisper"
                                                                              : "too big to fit with Whisper")
                            color: page.theme.muted
                            font { family: page.theme.mono; pixelSize: 10 }
                        }
                    }
                    Text {
                        anchors { right: parent.right; rightMargin: 16; verticalCenter: parent.verticalCenter }
                        visible: page.cobra.busyKey === "local.model" && !parent.on
                        text: "…"
                        color: page.theme.muted
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: parent.on ? Qt.ArrowCursor : Qt.PointingHandCursor
                        onClicked: if (!parent.on) page.cobra.set("local.model", modelData.name)
                    }
                }
            }
            Text {
                width: parent.width
                text: "Add more with  ollama pull <model>  (e.g. gemma3:4b, also used for reading your screen later)."
                color: page.theme.muted
                wrapMode: Text.Wrap
                font { family: page.theme.mono; pixelSize: 10 }
            }

            Item {
                width: parent.width
                height: 40
                Column {
                    spacing: 4
                    Text {
                        text: "Think before answering"
                        color: page.theme.text
                        font { family: page.theme.mono; pixelSize: 12 }
                    }
                    Text {
                        text: "more careful, but slower to start talking"
                        color: page.theme.muted
                        font { family: page.theme.mono; pixelSize: 10 }
                    }
                }
                Toggle {
                    anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                    checked: page.s ? page.s.think : false
                    onToggled: on => page.cobra.set("local.think", on)
                }
            }

            Column {
                width: parent.width
                spacing: 8
                visible: page.vram.total_mb !== undefined
                Item {
                    width: parent.width
                    height: 16
                    Text {
                        text: "RTX 5060 VRAM"
                        color: page.theme.muted
                        font { family: page.theme.mono; pixelSize: 11 }
                    }
                    Text {
                        anchors.right: parent.right
                        text: page.vram.total_mb ? (page.vram.used_mb / 1024).toFixed(1) + " / "
                                                   + (page.vram.total_mb / 1024).toFixed(0) + " GB" : ""
                        color: page.theme.text
                        font { family: page.theme.mono; pixelSize: 11 }
                    }
                }
                Rectangle {
                    width: parent.width
                    height: 5
                    radius: 2.5
                    color: Qt.alpha(page.theme.text, 0.08)
                    Rectangle {
                        width: page.vram.total_mb ? parent.width * page.vram.used_mb / page.vram.total_mb : 0
                        height: parent.height
                        radius: parent.radius
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: page.theme.violet }
                            GradientStop { position: 1; color: page.theme.mint }
                        }
                    }
                }
            }
        }
    }

    Card {
        width: parent.width
        icon: 0xF062C  // source-branch
        title: "Auto routing"
        status: "needs Claude"
        tint: page.theme.muted
        Text {
            width: parent.width
            text: "Once Claude is set up, Cobra can pick for you: quick questions, timers and system "
                  + "info stay local; coding, files and long reasoning go to Claude; and “ask "
                  + "Claude” or “use local” always wins. Until then everything runs on "
                  + "your GPU."
            color: page.theme.muted
            wrapMode: Text.Wrap
            lineHeight: 1.3
            font { family: page.theme.mono; pixelSize: 12 }
        }
    }
}
