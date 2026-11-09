// Her face in a ring that takes the colour of the current state, and comes alive: she breathes,
// blinks now and then, her eyes take the state's colour (mint listening, violet thinking,
// crimson speaking) and glow with your voice or hers, her scales shimmer while she thinks and
// her lips catch the light as she talks. The layers come from design/tools/avatar_layers.py.
import QtQuick
import QtQuick.Effects
import QtQuick.Shapes
import Quickshell.Widgets

Item {
    id: avatar

    property int size: 62
    property color ring: "white"
    property string mode: "idle"     // idle | listening | thinking | speaking
    property real level: 0           // mic or voice loudness, 0..1
    property bool alive: true        // false: just the still portrait
    property Theme theme: Theme {}

    readonly property bool animate: alive && visible
    readonly property bool fancy: size >= 40   // glow and shimmer only where you can see them
    readonly property real s: size - 8         // the portrait's size inside the ring
    readonly property color eyeColor: mode === "listening" ? theme.mint
                                    : mode === "thinking" ? theme.violet
                                    : theme.crimson
    // how much of the state colour is laid over her own red eyes
    readonly property real eyeTint: mode === "listening" ? 0.8
                                  : mode === "thinking" ? 0.55 + 0.3 * pulse
                                  : mode === "speaking" ? 0.25 + 0.6 * smoothLevel
                                  : 0
    readonly property real eyeGlow: mode === "listening" ? 0.55 + 0.45 * smoothLevel
                                  : mode === "thinking" ? 0.35 + 0.4 * pulse
                                  : mode === "speaking" ? 0.3 + 0.7 * smoothLevel
                                  : 0.18 + 0.14 * pulse

    property real breath: 0          // 0..1..0, slow
    property real pulse: 0           // 0..1..0, quicker while thinking
    property real smoothLevel: 0
    Behavior on smoothLevel { NumberAnimation { duration: 90 } }
    onLevelChanged: smoothLevel = Math.min(1, level * 1.6)

    width: size
    height: size

    SequentialAnimation on breath {
        running: avatar.animate
        loops: Animation.Infinite
        NumberAnimation { to: 1; duration: 2300; easing.type: Easing.InOutSine }
        NumberAnimation { to: 0; duration: 2300; easing.type: Easing.InOutSine }
    }
    SequentialAnimation on pulse {
        running: avatar.animate
        loops: Animation.Infinite
        NumberAnimation { to: 1; duration: avatar.mode === "thinking" ? 550 : 1800; easing.type: Easing.InOutSine }
        NumberAnimation { to: 0; duration: avatar.mode === "thinking" ? 550 : 1800; easing.type: Easing.InOutSine }
    }

    // ── blinking: every few seconds, sometimes twice, and when she starts listening ──
    function blink() {
        if (!animate || blinking.running) return
        blinking.twice = Math.random() < 0.2
        blinking.start()
    }
    Timer {
        running: avatar.animate
        repeat: true
        interval: 4000
        onTriggered: { interval = 2500 + Math.random() * 4500; avatar.blink() }
    }
    onModeChanged: if (mode === "listening") blink()
    SequentialAnimation {
        id: blinking
        property bool twice: false
        NumberAnimation { target: lids; property: "opacity"; to: 1; duration: 60; easing.type: Easing.InQuad }
        PauseAnimation { duration: 50 }
        NumberAnimation { target: lids; property: "opacity"; to: 0; duration: 110; easing.type: Easing.OutQuad }
        ScriptAction { script: if (blinking.twice) { blinking.twice = false; blinkAgain.start() } }
    }
    Timer { id: blinkAgain; interval: 140; onTriggered: blinking.start() }

    // ── the ring ──────────────────────────────────────────────────────────
    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: "transparent"
        border.color: avatar.ring
        border.width: 2
        Behavior on border.color { ColorAnimation { duration: 250 } }
    }

    ClippingRectangle {
        anchors.fill: parent
        anchors.margins: 4
        radius: width / 2
        color: "transparent"

        Item {
            id: face
            width: avatar.s
            height: avatar.s
            transformOrigin: Item.Center
            // breathing, leaning in to listen, and a little lift with her voice
            scale: 1.0 + 0.014 * avatar.breath
                   + (avatar.mode === "listening" ? 0.035 : 0)
                   + (avatar.mode === "speaking" ? 0.02 * avatar.smoothLevel : 0)
            Behavior on scale { NumberAnimation { duration: 160 } }

            Image {
                anchors.fill: parent
                source: Qt.resolvedUrl("assets/cobra-avatar.png")
                sourceSize: Qt.size(512, 512)
                fillMode: Image.PreserveAspectCrop
                smooth: true
            }

            Image {
                id: scaleMask
                anchors.fill: parent
                source: Qt.resolvedUrl("assets/cobra-scales.png")
                sourceSize: Qt.size(512, 512)
                visible: false
                layer.enabled: avatar.fancy
            }

            // her eyes in the state's colour (the layer is her eyes in white, so colouring it
            // keeps the slits and shading)
            Image {
                anchors.fill: parent
                source: Qt.resolvedUrl("assets/cobra-eyes.png")
                sourceSize: Qt.size(512, 512)
                opacity: avatar.eyeTint * (1 - lids.opacity)
                visible: opacity > 0.01
                Behavior on opacity { NumberAnimation { duration: 200 } }
                layer.enabled: true
                layer.effect: MultiEffect { colorization: 1.0; colorizationColor: avatar.eyeColor }
            }

            // and their glow spilling onto her face
            Image {
                anchors.fill: parent
                visible: avatar.fancy
                source: Qt.resolvedUrl("assets/cobra-eyes.png")
                sourceSize: Qt.size(512, 512)
                opacity: avatar.eyeGlow * (1 - 0.8 * lids.opacity)
                layer.enabled: avatar.fancy
                layer.effect: MultiEffect {
                    colorization: 1.0
                    colorizationColor: avatar.eyeColor
                    brightness: 0.4
                    blurEnabled: true
                    blur: 1.0
                    blurMax: 40
                    blurMultiplier: 0.5
                }
            }

            // her lips catching the light while she talks
            Shape {
                readonly property real r: avatar.s * 0.11
                x: avatar.s * 262 / 512 - r
                y: avatar.s * 356 / 512 - r * 0.6
                width: 2 * r
                height: 1.2 * r
                opacity: avatar.mode === "speaking" ? 0.15 + 0.6 * avatar.smoothLevel : 0
                visible: opacity > 0.01
                Behavior on opacity { NumberAnimation { duration: 90 } }
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    strokeColor: "transparent"
                    fillGradient: RadialGradient {
                        centerX: parent.width / 2; centerY: parent.height / 2
                        centerRadius: parent.width / 2
                        focalX: centerX; focalY: centerY
                        GradientStop { position: 0; color: Qt.alpha("#ff6a7f", 0.9) }
                        GradientStop { position: 1; color: Qt.alpha(avatar.theme.crimson, 0) }
                    }
                    PathAngleArc {
                        centerX: parent.width / 2; centerY: parent.height / 2
                        radiusX: parent.width / 2; radiusY: parent.height / 2
                        startAngle: 0; sweepAngle: 360
                    }
                }
            }

            // a band of light running over her scales: now and then when idle, steadily while
            // she thinks; and the scales glow with her voice
            Item {
                id: shimmer
                anchors.fill: parent
                visible: avatar.fancy
                layer.enabled: avatar.fancy
                layer.effect: MultiEffect { maskEnabled: true; maskSource: scaleMask }
                property real sweep: -0.5   // band position, -0.5..1.5 across her

                Rectangle {
                    anchors.fill: parent
                    color: avatar.theme.mint
                    opacity: avatar.mode === "speaking" ? 0.45 * avatar.smoothLevel
                             : avatar.mode === "listening" ? 0.25 : 0
                    Behavior on opacity { NumberAnimation { duration: 120 } }
                }
                Rectangle {
                    width: avatar.s * 0.4
                    height: avatar.s * 1.8
                    x: shimmer.sweep * avatar.s - width / 2
                    y: -avatar.s * 0.4
                    rotation: 24
                    opacity: avatar.mode === "thinking" ? 0.95 : 0.55
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: "transparent" }
                        GradientStop { position: 0.5; color: "#d8fff1" }
                        GradientStop { position: 1.0; color: "transparent" }
                    }
                }
                SequentialAnimation on sweep {
                    running: avatar.animate && avatar.fancy
                    loops: Animation.Infinite
                    NumberAnimation {
                        from: -0.5; to: 1.5
                        duration: avatar.mode === "thinking" ? 1300 : 2600
                        easing.type: Easing.InOutQuad
                    }
                    PauseAnimation { duration: avatar.mode === "thinking" ? 150 : 7000 }
                }
            }

            // eyelids, over everything on her face
            Image {
                id: lids
                anchors.fill: parent
                source: Qt.resolvedUrl("assets/cobra-lids.png")
                sourceSize: Qt.size(512, 512)
                opacity: 0
                smooth: true
            }
        }
    }
}
