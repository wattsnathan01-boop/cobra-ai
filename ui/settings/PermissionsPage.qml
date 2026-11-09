// What Cobra may do without asking, and which folders her file tools can use.
import QtQuick
import ".."

Column {
    id: page

    required property Cobra cobra
    property Theme theme: Theme {}
    readonly property var p: cobra.settings ? cobra.settings.permissions : null

    function level(tool) {
        if (!p) return "ask"
        const t = p.tools.find(x => x.name === tool)
        return t ? t.level : "ask"
    }

    // grouped like the design; changing a group sets every tool in it
    readonly property var groups: [
        { icon: 0xF0208, title: "See your screen", sub: "Screenshots for the local vision model \u00b7 eye badge in waybar",
          tools: ["screen_look", "screen_watch"] },
        { icon: 0xF0A10, title: "System info", sub: "Sensors, nvidia-smi, battery",
          tools: ["system_stats"] },
        { icon: 0xF05B6, title: "Windows & apps", sub: "Focus, move and open apps via hyprctl",
          tools: ["hypr_windows", "hypr_action", "apps_launch"] },
        { icon: 0xF05AD, title: "Close windows", sub: "Unsaved work in them may be lost",
          tools: ["hypr_close"] },
        { icon: 0xF075A, title: "Media & volume", sub: "playerctl, volume, brightness",
          tools: ["media", "volume", "brightness"] },
        { icon: 0xF0219, title: "Read files", sub: "Only in allowed folders (below)",
          tools: ["files_read", "files_list", "files_search"] },
        { icon: 0xF0DEB, title: "Write & edit files", sub: "Shows a diff before saving",
          tools: ["files_write"] },
        { icon: 0xF018D, title: "Run commands", sub: "Shell commands as your user · always asks",
          tools: ["shell_run"], noAlways: true },
        { icon: 0xF0565, title: "sudo & system changes", sub: "Packages, services, /etc · always asks",
          tools: ["sudo_run"], noAlways: true },
        { icon: 0xF03D3, title: "Install software", sub: "pacman and the AUR \u00b7 always asks, then your password",
          tools: ["packages_install"], noAlways: true },
        { icon: 0xF0A7A, title: "Delete files", sub: "To the trash, even inside allowed folders",
          tools: ["files_delete"] },
        { icon: 0xF0306, title: "Passwords & keyring", sub: "No tool can reach them",
          tools: [], fixed: "never" },
    ]

    spacing: 28

    PageHeader {
        width: parent.width
        title: "Permissions"
        subtitle: "What Cobra is allowed to do. “Ask first” shows a confirm pop-up "
                  + "before anything happens."
    }

    Rectangle {
        width: parent.width
        height: rows.implicitHeight
        radius: 16
        color: Qt.rgba(1, 1, 1, 0.025)
        border.color: Qt.alpha(page.theme.text, 0.1)
        clip: true
        Column {
            id: rows
            width: parent.width
            Repeater {
                model: page.groups
                Item {
                    required property var modelData
                    required property int index
                    readonly property string lvl: modelData.fixed || page.level(modelData.tools[0])
                    readonly property color tint: lvl === "always" ? page.theme.mint
                                                : lvl === "ask" ? page.theme.violet : page.theme.crimson
                    width: rows.width
                    height: 64
                    Rectangle {
                        visible: index > 0
                        width: parent.width
                        height: 1
                        color: Qt.alpha(page.theme.text, 0.07)
                    }
                    Rectangle {
                        id: icon
                        anchors { left: parent.left; leftMargin: 20; verticalCenter: parent.verticalCenter }
                        width: 34
                        height: 34
                        radius: 9
                        color: Qt.alpha(parent.tint, 0.12)
                        Text {
                            anchors.centerIn: parent
                            text: String.fromCodePoint(modelData.icon)
                            color: parent.parent.tint
                            font { family: page.theme.mono; pixelSize: 16 }
                        }
                    }
                    Column {
                        anchors { left: icon.right; leftMargin: 16; verticalCenter: parent.verticalCenter }
                        spacing: 4
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
                    Segment {
                        anchors { right: parent.right; rightMargin: 20; verticalCenter: parent.verticalCenter }
                        value: parent.lvl
                        locked: modelData.fixed !== undefined
                        disabled: modelData.noAlways ? ["always"] : []
                        onPicked: lvl => modelData.tools.forEach(t => page.cobra.set("permission." + t, lvl))
                    }
                }
            }
        }
    }

    // tools from connected apps (MCP servers like Pencil): one row each
    readonly property var grouped: groups.reduce((all, g) => all.concat(g.tools), [])
    readonly property var others: p ? p.tools.filter(t => grouped.indexOf(t.name) < 0) : []

    Card {
        visible: page.others.length > 0
        width: parent.width
        icon: 0xF0431  // power-plug
        title: "Connected apps"
        status: page.others.length + " tools"
        tint: page.theme.violet
        Text {
            width: parent.width
            text: "Tools from apps listed in ~/.config/cobra/mcp.json. Ones the app marks as "
                  + "read-only start as Always; anything that changes things asks first."
            color: page.theme.muted
            wrapMode: Text.Wrap
            font { family: page.theme.mono; pixelSize: 11 }
        }
        Repeater {
            model: page.others
            Item {
                required property var modelData
                width: parent.width
                height: 44
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.name.replace("__", " \u203a ")
                    color: page.theme.text
                    font { family: page.theme.mono; pixelSize: 12 }
                }
                Segment {
                    anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                    value: modelData.level
                    onPicked: lvl => page.cobra.set("permission." + modelData.name, lvl)
                }
            }
        }
    }

    Card {
        width: parent.width
        icon: 0xF0209  // eye-off
        title: "Screen privacy"
        tint: page.theme.crimson
        readonly property var hide: page.cobra.settings ? page.cobra.settings.screen.hide : []

        Text {
            width: parent.width
            text: "Windows whose name or title contains any of these are blacked out before Cobra "
                  + "looks. Screenshots never leave this laptop."
            color: page.theme.muted
            wrapMode: Text.Wrap
            font { family: page.theme.mono; pixelSize: 11 }
        }
        Flow {
            width: parent.width
            spacing: 8
            Repeater {
                model: parent.parent.hide
                Rectangle {
                    required property string modelData
                    width: word.implicitWidth + 40
                    height: 28
                    radius: 14
                    color: Qt.alpha(page.theme.crimson, 0.1)
                    border.color: Qt.alpha(page.theme.crimson, 0.3)
                    Text {
                        id: word
                        anchors { left: parent.left; leftMargin: 12; verticalCenter: parent.verticalCenter }
                        text: modelData
                        color: page.theme.text
                        font { family: page.theme.mono; pixelSize: 11 }
                    }
                    Text {
                        anchors { right: parent.right; rightMargin: 10; verticalCenter: parent.verticalCenter }
                        text: "\u2715"
                        color: page.theme.muted
                        font { family: page.theme.mono; pixelSize: 10 }
                        MouseArea {
                            anchors { fill: parent; margins: -6 }
                            cursorShape: Qt.PointingHandCursor
                            onClicked: page.cobra.set("screen.hide",
                                page.cobra.settings.screen.hide.filter(h => h !== modelData))
                        }
                    }
                }
            }
        }
        Rectangle {
            width: parent.width
            height: 40
            radius: 8
            color: Qt.rgba(0, 0, 0, 0.3)
            border.color: hideInput.activeFocus ? Qt.alpha(page.theme.crimson, 0.5) : Qt.alpha(page.theme.text, 0.1)
            TextInput {
                id: hideInput
                anchors { fill: parent; leftMargin: 14; rightMargin: 14 }
                verticalAlignment: TextInput.AlignVCenter
                color: page.theme.text
                font { family: page.theme.mono; pixelSize: 12 }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: hideInput.text === ""
                    text: "+  Hide windows containing\u2026 (e.g. a bank's name, Enter)"
                    color: page.theme.crimson
                    font: hideInput.font
                }
                Keys.onReturnPressed: {
                    const w = text.trim().toLowerCase()
                    if (w) page.cobra.set("screen.hide", page.cobra.settings.screen.hide.concat([w]))
                    text = ""
                }
            }
        }
    }

    Card {
        width: parent.width
        icon: 0xF0256  // folder-open
        title: "Allowed folders"
        status: ""

        Repeater {
            model: page.p ? page.p.allowed : []
            Rectangle {
                required property string modelData
                readonly property bool exists: page.p && page.p.exists[modelData]
                width: parent.width
                height: 40
                radius: 8
                color: Qt.alpha(page.theme.text, 0.035)
                Text {
                    anchors { left: parent.left; leftMargin: 14; verticalCenter: parent.verticalCenter }
                    text: modelData + (parent.exists ? "" : "    (doesn't exist yet)")
                    color: parent.exists ? page.theme.text : page.theme.muted
                    font { family: page.theme.mono; pixelSize: 12 }
                }
                Text {
                    anchors { right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                    text: "✕"
                    color: removeMouse.containsMouse ? page.theme.crimson : page.theme.muted
                    font { family: page.theme.mono; pixelSize: 12 }
                    MouseArea {
                        id: removeMouse
                        anchors { fill: parent; margins: -8 }
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: page.cobra.set("files.allowed", page.p.allowed.filter(a => a !== modelData))
                    }
                }
            }
        }

        Rectangle {
            width: parent.width
            height: 40
            radius: 8
            color: Qt.rgba(0, 0, 0, 0.3)
            border.color: folder.activeFocus ? Qt.alpha(page.theme.mint, 0.5) : Qt.alpha(page.theme.text, 0.1)
            TextInput {
                id: folder
                anchors { fill: parent; leftMargin: 14; rightMargin: 14 }
                verticalAlignment: TextInput.AlignVCenter
                color: page.theme.text
                font { family: page.theme.mono; pixelSize: 12 }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: folder.text === ""
                    text: "+  Add folder, e.g. ~/notes  (Enter)"
                    color: page.theme.mint
                    font: folder.font
                }
                Keys.onReturnPressed: {
                    const f = text.trim()
                    if (f && page.p.allowed.indexOf(f) < 0)
                        page.cobra.set("files.allowed", page.p.allowed.concat([f]))
                    text = ""
                }
            }
        }
        Text {
            width: parent.width
            text: "Cobra's own settings and logs, ~/.ssh, keyrings and browser profiles stay off-limits "
                  + "even inside these."
            color: page.theme.muted
            wrapMode: Text.Wrap
            font { family: page.theme.mono; pixelSize: 10 }
        }
    }
}
