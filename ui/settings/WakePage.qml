// "Cobra, …": on/off, how easily it triggers, and how long she waits after just her name.
import QtQuick
import ".."

Column {
    id: page

    required property Cobra cobra
    property Theme theme: Theme {}
    readonly property var s: cobra.settings ? cobra.settings.wake : null

    spacing: 28

    PageHeader {
        width: parent.width
        title: "Wake word"
        subtitle: "Say “Cobra, …” instead of holding SUPER+C. The mic stays open while "
                  + "this is on; anything that doesn't start with her name is dropped straight away "
                  + "and never saved or logged."
    }

    Card {
        width: parent.width
        icon: 0xF0003  // access-point
        title: "Listen for “Cobra”"
        status: page.s && page.s.enabled ? "listening" : "off"
        tint: page.s && page.s.enabled ? page.theme.mint : page.theme.muted

        Item {
            width: parent.width
            height: 40
            Column {
                spacing: 4
                Text {
                    text: "Wake word"
                    color: page.theme.text
                    font { family: page.theme.mono; pixelSize: 13 }
                }
                Text {
                    text: "SUPER+C push-to-talk works either way"
                    color: page.theme.muted
                    font { family: page.theme.mono; pixelSize: 10 }
                }
            }
            Toggle {
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                checked: page.s ? page.s.enabled : false
                enabled: page.s ? page.s.available : false
                onToggled: on => page.cobra.set("wake.enabled", on)
            }
        }

        Rectangle { width: parent.width; height: 1; color: Qt.alpha(page.theme.text, 0.07) }

        Column {
            width: parent.width
            spacing: 12
            Item {
                width: parent.width
                height: 18
                Text {
                    text: "Sensitivity"
                    color: page.theme.text
                    font { family: page.theme.mono; pixelSize: 13 }
                }
                Text {
                    anchors.right: parent.right
                    text: page.s ? (1 - page.s.threshold).toFixed(2) : ""
                    color: page.theme.muted
                    font { family: page.theme.mono; pixelSize: 11 }
                }
            }
            // left = needs louder speech (ignores noise), right = hears quieter speech
            Slider {
                width: parent.width
                from: 0.2
                to: 0.7
                value: page.s ? 0.9 - page.s.threshold : 0.4
                onMoved: v => page.cobra.set("wake.threshold", Math.round((0.9 - v) * 100) / 100)
            }
            Item {
                width: parent.width
                height: 14
                Text {
                    text: "ignores more noise"
                    color: page.theme.muted
                    font { family: page.theme.mono; pixelSize: 10 }
                }
                Text {
                    anchors.right: parent.right
                    text: "hears quieter speech"
                    color: page.theme.muted
                    font { family: page.theme.mono; pixelSize: 10 }
                }
            }
        }

        Rectangle { width: parent.width; height: 1; color: Qt.alpha(page.theme.text, 0.07) }

        Column {
            width: parent.width
            spacing: 12
            Item {
                width: parent.width
                height: 18
                Text {
                    text: "After just “Cobra”, wait for the question"
                    color: page.theme.text
                    font { family: page.theme.mono; pixelSize: 13 }
                }
                Text {
                    anchors.right: parent.right
                    text: page.s ? page.s.follow_up_seconds + " s" : ""
                    color: page.theme.muted
                    font { family: page.theme.mono; pixelSize: 11 }
                }
            }
            Slider {
                width: parent.width
                from: 3
                to: 20
                stepSize: 1
                value: page.s ? page.s.follow_up_seconds : 8
                onMoved: v => page.cobra.set("wake.follow_up_seconds", Math.round(v))
            }
        }
    }

    Card {
        width: parent.width
        icon: 0xF036C  // microphone
        title: "If she misses you"
        tint: page.theme.violet
        Text {
            width: parent.width
            text: "Move Sensitivity right. If she wakes up when nobody said her name, move it left. "
                  + "A mic that's turned up too far distorts your voice: try  amixer -c 0 sset "
                  + "'Internal Mic Boost' 0  and  amixer -c 0 sset Capture 80%."
            color: page.theme.muted
            wrapMode: Text.Wrap
            lineHeight: 1.3
            font { family: page.theme.mono; pixelSize: 12 }
        }
    }
}
