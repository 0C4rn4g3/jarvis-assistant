import QtQuick
import QtQuick.Controls

// A small round glass chip: an optional icon (or status `dot`) and a label. `checked` (or `active`) lights it cyan.
AbstractButton {
    id: c
    property string symbol: ""
    property string dot: ""   // a StatusDot status, shown instead of an icon
    property bool active: checked
    property color ink: active ? Theme.accent : Theme.text2
    hoverEnabled: true
    focusPolicy: Qt.NoFocus
    implicitHeight: 32
    implicitWidth: row.implicitWidth + 26
    background: Rectangle {
        radius: height / 2
        color: c.active ? Theme.accentSoft : c.hovered ? Theme.glassHover : Theme.glass
        border.width: 1
        border.color: c.active ? Theme.alpha(Theme.accent, 0.45) : c.hovered ? Theme.strokeStrong : Theme.stroke
        Behavior on color { ColorAnimation { duration: Theme.fast } }
        Behavior on border.color { ColorAnimation { duration: Theme.fast } }
    }
    contentItem: Item {
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 7
            StatusDot { visible: c.dot !== ""; status: c.dot; anchors.verticalCenter: parent.verticalCenter }
            Icon { visible: c.symbol !== "" && c.dot === ""; name: c.symbol; size: 16; color: c.ink; anchors.verticalCenter: parent.verticalCenter }
            Text { text: c.text; visible: text !== ""; font.family: Theme.font; font.pixelSize: Theme.px(13); font.weight: 500; font.variableAxes: { "wght": 500 }
                   color: c.hovered && !c.active ? Theme.text : c.ink; anchors.verticalCenter: parent.verticalCenter }
        }
    }
    scale: down ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
}
