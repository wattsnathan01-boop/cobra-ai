// Cobra overlay. Run with: qs -c cobra   (install.sh links ~/.config/quickshell/cobra here)
import QtQuick
import Quickshell

ShellRoot {
    Cobra { id: cobra }

    Popup { cobra: cobra }
}
