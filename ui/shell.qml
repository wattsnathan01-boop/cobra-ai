// Cobra overlay. Run with: qs -n -c cobra   (install.sh links ~/.config/quickshell/cobra here)
import QtQuick
import Quickshell

ShellRoot {
    Cobra { id: cobra }

    Popup { cobra: cobra }
    Hud { cobra: cobra }
    Confirm { cobra: cobra }
    Settings { cobra: cobra }
    Notebook { cobra: cobra }
    ScreenEdge { cobra: cobra }
    Point { cobra: cobra }
}
