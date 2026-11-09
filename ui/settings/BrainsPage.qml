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
            id: claudeCard
            readonly property var c: page.cobra.settings ? page.cobra.settings.claude : null
            readonly property bool ready: c && c.configured
            width: (parent.width - 20) / 2
            icon: 0xF0674  // creation (sparkles)
            title: "Claude"
            status: ready ? "connected" : "not set up"
            tint: ready ? page.theme.mint : page.theme.muted

            // not set up: how to add the key
            Text {
                visible: !claudeCard.ready
                width: parent.width
                text: "Needs an Anthropic API key (platform.claude.com → Settings → API Keys; add "
                      + "credit under Billing). Store it encrypted with this command in a "
                      + "terminal, paste the key when asked, then restart Cobra:"
                color: page.theme.muted
                wrapMode: Text.Wrap
                lineHeight: 1.3
                font { family: page.theme.mono; pixelSize: 12 }
            }
            Rectangle {
                visible: !claudeCard.ready
                width: parent.width
                height: cmd.implicitHeight + 24
                radius: 8
                color: Qt.rgba(0, 0, 0, 0.35)
                TextEdit {
                    id: cmd
                    anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter
                              margins: 12 }
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.WrapAnywhere
                    text: "cobractl claude-key"
                    color: page.theme.text
                    font { family: page.theme.mono; pixelSize: 12 }
                }
            }

            // set up: model, effort, spend
            Item {
                visible: claudeCard.ready
                width: parent.width
                height: 34
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Model"
                    color: page.theme.muted
                    font { family: page.theme.mono; pixelSize: 12 }
                }
                Row {
                    anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                    spacing: 6
                    Repeater {
                        model: claudeCard.c ? claudeCard.c.models : []
                        Button {
                            required property string modelData
                            label: modelData.replace("claude-", "").replace("-5-5", " 5.5")
                            filled: claudeCard.c && claudeCard.c.model === modelData
                            onClicked: page.cobra.set("claude.model", modelData)
                        }
                    }
                }
            }
            Item {
                visible: claudeCard.ready
                width: parent.width
                height: 34
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Effort"
                    color: page.theme.muted
                    font { family: page.theme.mono; pixelSize: 12 }
                }
                Row {
                    anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                    spacing: 6
                    Repeater {
                        model: ["low", "medium", "high"]
                        Button {
                            required property string modelData
                            label: modelData
                            tint: page.theme.violet
                            filled: claudeCard.c && claudeCard.c.effort === modelData
                            onClicked: page.cobra.set("claude.effort", modelData)
                        }
                    }
                }
            }
            Item {
                visible: claudeCard.ready
                width: parent.width
                height: 34
                Rectangle { width: parent.width; height: 1; color: Qt.alpha(page.theme.text, 0.07) }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Used this month"
                    color: page.theme.muted
                    font { family: page.theme.mono; pixelSize: 12 }
                }
                Text {
                    anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                    text: claudeCard.c ? "$" + claudeCard.c.spend_month.toFixed(2) : ""
                    color: page.theme.text
                    font { family: page.theme.mono; pixelSize: 13 }
                }
            }
            Text {
                visible: claudeCard.ready
                width: parent.width
                text: "Low effort keeps spoken replies quick; raise it for harder work. Opus 5.5 "
                      + "is $4 / $20 per million tokens, Haiku 5.5 $0.10 / $0.50."
                color: page.theme.muted
                wrapMode: Text.Wrap
                font { family: page.theme.mono; pixelSize: 10 }
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
        title: "Which brain answers"
        status: page.s ? page.s.mode : ""
        tint: page.theme.crimson

        Row {
            width: parent.width
            spacing: 12
            Repeater {
                model: [{ mode: "local", title: "Local", sub: "free, private, on your GPU" },
                        { mode: "auto", title: "Auto", sub: "quick things local, real work on Claude" },
                        { mode: "claude", title: "Claude", sub: "everything on Claude (paid)" }]
                Rectangle {
                    required property var modelData
                    readonly property bool on: page.s && page.s.mode === modelData.mode
                    readonly property bool can: modelData.mode === "local"
                                                || (page.cobra.settings && page.cobra.settings.claude.configured)
                    width: (parent.width - 24) / 3
                    height: 64
                    radius: 10
                    opacity: can ? 1 : 0.4
                    color: on ? Qt.alpha(page.theme.mint, 0.1) : Qt.alpha(page.theme.text, 0.03)
                    border.color: on ? Qt.alpha(page.theme.mint, 0.55) : Qt.alpha(page.theme.text, 0.08)
                    Column {
                        anchors { left: parent.left; leftMargin: 16; verticalCenter: parent.verticalCenter }
                        spacing: 5
                        Text {
                            text: modelData.title
                            color: page.theme.text
                            font { family: page.theme.mono; pixelSize: 13; weight: Font.Medium }
                        }
                        Text {
                            text: modelData.sub
                            color: page.theme.muted
                            font { family: page.theme.mono; pixelSize: 10 }
                        }
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: parent.can && !parent.on ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: if (parent.can && !parent.on) page.cobra.set("brain.mode", modelData.mode)
                    }
                }
            }
        }
        Text {
            width: parent.width
            text: "Auto keeps quick questions (media, volume, system info, windows, apps, memory, "
                  + "small talk) local and sends coding, files, explanations, writing and longer "
                  + "questions to Claude. Say \u201cask Claude\u201d or \u201cuse local\u201d to "
                  + "choose yourself. Your screen is always read locally."
            color: page.theme.muted
            wrapMode: Text.Wrap
            lineHeight: 1.3
            font { family: page.theme.mono; pixelSize: 12 }
        }
    }
}
