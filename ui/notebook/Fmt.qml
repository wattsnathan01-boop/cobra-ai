// Date helpers shared by the notebook pages.
import QtQuick

QtObject {
    function parse(iso) { return iso ? new Date(iso) : null }
    function sameDay(a, b) {
        return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
    }
    function hm(d) { return Qt.formatTime(d, "HH:mm") }
    // "Today 18:42", "Yesterday", "Mon", "9 Nov"
    function when(iso) {
        const d = parse(iso)
        if (!d || isNaN(d)) return ""
        const now = new Date()
        if (sameDay(d, now)) return "Today " + hm(d)
        const y = new Date(now); y.setDate(now.getDate() - 1)
        if (sameDay(d, y)) return "Yesterday"
        if ((now - d) < 6 * 86400000 && d < now) return Qt.formatDate(d, "ddd")
        return Qt.formatDate(d, "d MMM")
    }
    // reminder times: "18:30", "Thu 12 · 09:00", "overdue"
    function due(iso) {
        const d = parse(iso)
        if (!d || isNaN(d)) return ""
        const now = new Date()
        if (sameDay(d, now)) return hm(d)
        const t = new Date(now); t.setDate(now.getDate() + 1)
        if (sameDay(d, t)) return "Tomorrow " + hm(d)
        return Qt.formatDate(d, "ddd d MMM") + " " + hm(d)
    }
    function dayKey(d) { return Qt.formatDate(d, "yyyy-MM-dd") }
    function isToday(iso) { const d = parse(iso); return d && sameDay(d, new Date()) }
}
