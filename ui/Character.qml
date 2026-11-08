// The Cobra Queen: her face inside a ring of voice bars, framed by the hood.
// The bars follow your mic while listening and her voice while speaking, sweep round while
// she thinks, and breathe slowly when idle. The hood flares with her voice.
import QtQuick
import QtQuick.Shapes

Item {
    id: root

    property string mode: "idle"
    property real level: 0          // mic or voice loudness, 0..1
    property Theme theme: Theme {}

    readonly property color accent: theme.accent(mode)
    readonly property int bars: 72
    readonly property real ringRadius: 150
    property var lengths: Array(bars).fill(0.1)
    property real smoothLevel: 0
    property int tick: 0

    implicitWidth: 600
    implicitHeight: 640

    Timer {
        interval: 33
        repeat: true
        running: root.visible
        onTriggered: {
            root.tick++
            root.smoothLevel += (root.level - root.smoothLevel) * 0.3
            const next = root.lengths.slice()
            for (let i = 0; i < root.bars; i++) {
                let target
                if (root.mode === "thinking") {
                    // a bright patch sweeping round the ring
                    const d = ((i - root.tick * 1.2) % root.bars + root.bars) % root.bars
                    target = 0.12 + 0.55 * Math.exp(-Math.pow(Math.min(d, root.bars - d) / 5, 2))
                } else if (root.mode === "listening" || root.mode === "speaking") {
                    const shape = 0.55 + 0.45 * Math.sin(i * 0.9 + root.tick * 0.25)
                    target = 0.08 + root.smoothLevel * shape * (0.6 + Math.random() * 0.8)
                } else {
                    target = 0.1 + 0.06 * Math.sin(i * 0.5 + root.tick * 0.05)
                }
                next[i] += (Math.min(1, target) - next[i]) * 0.35
            }
            root.lengths = next
        }
    }

    // ── hood ──────────────────────────────────────────────────────────────
    Item {
        id: hood
        anchors.fill: parent
        transformOrigin: Item.Center
        scale: 1 + root.smoothLevel * 0.035 + (root.mode === "listening" ? 0.015 : 0)
        Behavior on scale { NumberAnimation { duration: 120 } }

        Repeater {
            model: [{ inset: 0, width: 2.5, alpha: 0.9 }, { inset: 52, width: 1, alpha: 0.35 }]
            Shape {
                required property var modelData
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer
                readonly property real w: width
                readonly property real h: height
                readonly property real i: modelData.inset
                ShapePath {
                    strokeWidth: modelData.width
                    fillColor: "transparent"
                    capStyle: ShapePath.RoundCap
                    strokeGradient: LinearGradient {
                        x1: 0; y1: 0; x2: 0; y2: h
                        GradientStop { position: 0.0; color: Qt.alpha(root.theme.mint, modelData.alpha) }
                        GradientStop { position: 0.55; color: Qt.alpha(root.theme.violet, modelData.alpha) }
                        GradientStop { position: 1.0; color: Qt.alpha(root.theme.violet, 0) }
                    }
                    // round crown, then the hood narrows and flares out at the bottom
                    startX: w * 0.33 + i * 0.6; startY: h
                    PathCubic {
                        x: w * 0.02 + i; y: h * 0.42
                        control1X: w * 0.16 + i; control1Y: h * 0.82
                        control2X: w * 0.02 + i; control2Y: h * 0.62
                    }
                    PathArc {
                        x: w * 0.98 - i; y: h * 0.42
                        radiusX: w * 0.48 - i; radiusY: h * 0.42 - i * 0.7
                        useLargeArc: false
                    }
                    PathCubic {
                        x: w * 0.67 - i * 0.6; y: h
                        control1X: w * 0.98 - i; control1Y: h * 0.62
                        control2X: w * 0.84 - i; control2Y: h * 0.82
                    }
                }
            }
        }

        // the crimson markings either side, like the eyespots on a cobra's hood
        Repeater {
            model: [-1, 1]
            Shape {
                required property int modelData
                x: root.width / 2 + modelData * 228 - 15
                y: root.height * 0.30
                width: 30
                height: 100
                opacity: 0.55 + (root.mode === "speaking" ? root.smoothLevel * 0.45 : 0)
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    strokeWidth: 1.5
                    strokeColor: root.theme.crimson
                    fillColor: Qt.alpha(root.theme.crimson, 0.08)
                    startX: 15; startY: 0
                    PathQuad { x: 15; y: 100; controlX: modelData < 0 ? -12 : 42; controlY: 50 }
                    PathQuad { x: 15; y: 0; controlX: modelData < 0 ? 22 : 8; controlY: 50 }
                }
            }
        }
    }

    // ── face, rings and bars, centred in the crown ────────────────────────
    Item {
        id: core
        width: 2 * (root.ringRadius + 60)
        height: width
        x: (root.width - width) / 2
        y: root.height * 0.42 - height / 2 + 30

        Repeater {
            model: root.bars
            Rectangle {
                required property int index
                readonly property real deg: index / root.bars * 360
                readonly property real len: 10 + 48 * root.lengths[index]
                // mint on the left, through violet, to crimson on the right
                readonly property real side: (Math.sin(deg * Math.PI / 180) + 1) / 2
                width: 3
                height: len
                radius: 1.5
                antialiasing: true
                color: side < 0.5 ? Qt.tint(root.theme.mint, Qt.alpha(root.theme.violet, side * 2))
                                  : Qt.tint(root.theme.violet, Qt.alpha(root.theme.crimson, (side - 0.5) * 2))
                opacity: 0.85
                x: core.width / 2 - width / 2
                y: core.height / 2 - root.ringRadius - len
                transform: Rotation {
                    origin.x: 1.5
                    origin.y: root.ringRadius + len
                    angle: deg
                }
            }
        }

        // two partial arcs turning in opposite directions around her face
        Repeater {
            model: [{ r: 128, sweep: 250, color: "violet", dir: 1, speed: 14000 },
                    { r: 136, sweep: 110, color: "mint", dir: -1, speed: 9000 }]
            Shape {
                required property var modelData
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    strokeWidth: 3
                    strokeColor: Qt.alpha(modelData.color === "mint" ? root.theme.mint
                                                                     : root.theme.violet, 0.85)
                    fillColor: "transparent"
                    capStyle: ShapePath.RoundCap
                    PathAngleArc {
                        centerX: core.width / 2; centerY: core.height / 2
                        radiusX: modelData.r; radiusY: modelData.r
                        startAngle: 0; sweepAngle: modelData.sweep
                    }
                }
                RotationAnimator on rotation {
                    from: 0; to: 360 * modelData.dir
                    duration: root.mode === "thinking" ? modelData.speed / 4 : modelData.speed
                    loops: Animation.Infinite
                    running: root.visible
                }
            }
        }

        Avatar {
            anchors.centerIn: parent
            size: 236
            ring: root.accent
        }
    }
}
