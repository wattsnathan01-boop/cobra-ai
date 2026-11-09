// A Material Design icon from the Nerd Font, by name.
import QtQuick
import ".."

Text {
    property string name
    property int size: 14
    readonly property var codes: ({
        search: 0xF0349, plus: 0xF0415, bell: 0xF009A, bellOutline: 0xF009C, bellRing: 0xF009E,
        bellPlus: 0xF009D, calendar: 0xF00ED, today: 0xF00F6, image: 0xF02E9, imagePlus: 0xF087C,
        images: 0xF02F9, video: 0xF0567, play: 0xF040A, pause: 0xF03E4, paperclip: 0xF03E2,
        pin: 0xF0403, pinOutline: 0xF0931, trash: 0xF09E7, undo: 0xF054C, send: 0xF048A,
        box: 0xF0131, boxChecked: 0xF0132, close: 0xF0156, file: 0xF0224, doc: 0xF09EE,
        notebook: 0xF082E, notebookOutline: 0xF0EBF, diary: 0xF1A1D, sparkle: 0xF0674,
        mic: 0xF036C, stop: 0xF04DB, sun: 0xF0599, history: 0xF02DA, pencil: 0xF03EB,
        pencilPlus: 0xF0DEB, happy: 0xF01F5, neutral: 0xF01F6, sad: 0xF01F8, tag: 0xF04FC,
        you: 0xF0004, snooze: 0xF068E, open: 0xF03CC, chevron: 0xF0140, record: 0xF0EC2,
        speaker: 0xF057E, up: 0xF005D, circleChecked: 0xF0133, circle: 0xF0130,
        waveform: 0xF147D, voice: 0xF05CB, check: 0xF012C
    })
    text: codes[name] ? String.fromCodePoint(codes[name]) : ""
    font { family: "JetBrainsMono Nerd Font"; pixelSize: size }
}
