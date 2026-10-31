import QtQuick
import QtQuick.Effects

// A frosted surface: a faint fill, a hairline, and light catching its top edge. `floating` for things that hover over
// the page (rail, composer, toasts, menus): a stronger fill and a soft shadow.
Rectangle {
    id: g
    property bool floating: false
    color: floating ? Theme.glassStrong : Theme.glass
    radius: Theme.radius
    border.width: 1
    border.color: floating ? Theme.strokeStrong : Theme.stroke

    Behavior on color { ColorAnimation { duration: Theme.fast } }
    Behavior on border.color { ColorAnimation { duration: Theme.fast } }

    RectangularShadow {
        visible: g.floating
        z: -1
        anchors.fill: parent
        radius: g.radius
        blur: 32
        offset.y: 8
        color: Theme.shadow
    }
    Rectangle {  // specular top edge highlight
        x: g.radius; y: 0
        width: Math.max(0, g.width - 2 * g.radius); height: 1
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "transparent" }
            GradientStop { position: 0.15; color: Theme.highlight }
            GradientStop { position: 0.85; color: Theme.highlight }
            GradientStop { position: 1; color: "transparent" }
        }
    }
}
