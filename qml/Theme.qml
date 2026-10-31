pragma Singleton
import QtQuick

// Jarvis's look ("Glass"): frosted surfaces over a deep navy canvas, cyan as the signature, orange while working.
QtObject {
    // canvas: macOS deep graphite canvas
    readonly property color bg: "#0c0d10"
    readonly property color bgTop: "#121318"
    readonly property color bgBottom: "#08080a"

    // glass: macOS Acrylic frosted glass
    readonly property color glass: "#0affffff"        // cards, rows, chips (0.04 alpha)
    readonly property color glassHover: "#14ffffff"   // cards hovered (0.08 alpha)
    readonly property color glassStrong: "#d914151a"  // floating: rail, composer, toasts (0.85 opacity graphite)
    readonly property color popover: "#f214151a"      // popovers and context menus
    readonly property color stroke: "#14ffffff"       // 1px etched glass hairline (0.08 alpha)
    readonly property color strokeStrong: "#26ffffff" // focused elements, active borders (0.15 alpha)
    readonly property color highlight: "#a6ff334b"   // specular red highlight catching top edge of glass
    readonly property color track: "#14ffffff"        // empty bars, meters, toggles off
    readonly property color shadow: "#66000000"       // elevation drop shadow

    // text: zinc optical scale
    readonly property color text: "#fbfcfd"           // crisp zinc white
    readonly property color text2: "#a1a1aa"          // zinc-400 silver
    readonly property color text3: "#63636e"          // zinc-500 muted caption

    // colour: Jarvis Signature Red preserved
    readonly property color accent: "#ff334b"       // Jarvis's red
    readonly property color accentSoft: "#26ff334b"
    readonly property color accentInk: "#ffffff"    // crisp text and icons on solid red
    readonly property color listen: "#ff5e72"
    readonly property color speak: "#ff5e72"
    readonly property color warm: "#ff9d3f"         // Jarvis's orange: working
    readonly property color warmSoft: "#24ff9d3f"
    readonly property color green: "#34d399"
    readonly property color red: "#ff334b"

    // macOS traffic light buttons
    readonly property color trafficRed: "#ff5f56"
    readonly property color trafficYellow: "#ffbd2e"
    readonly property color trafficGreen: "#27c93f"
    readonly property color trafficStrokeRed: "#e0443e"
    readonly property color trafficStrokeYellow: "#dea123"
    readonly property color trafficStrokeGreen: "#1aab29"

    // older names, kept for pages not yet moved over
    readonly property color panel: glassStrong
    readonly property color card: glass
    readonly property color cardHover: glassHover
    readonly property color raised: track
    readonly property color line: stroke
    readonly property color lineStrong: strokeStrong
    readonly property color dim: text2
    readonly property color faint: text3
    readonly property color ink: accentInk
    readonly property color accentDeep: "#c41b2c"

    readonly property string font: "Inter Variable"
    readonly property string mono: "JetBrainsMono Nerd Font"
    property real scale: 1.0  // Settings → Text size
    function px(n) { return Math.round(n * scale) }  // (font sizes stay whole pixels)

    readonly property int radiusWindow: 18
    readonly property int radius: 16         // cards
    readonly property int radiusControl: 10  // fields, selects, text areas
    readonly property int radiusSmall: 6

    readonly property int margin: 40         // around a page's content
    readonly property int pageWidth: 920     // a page's content column at most
    readonly property int pad: 20            // inside a card
    readonly property int gap: 16            // between cards
    readonly property int fast: 140          // hover and press, ms

    function stateColor(s) {
        return s === "listening" ? listen : s === "thinking" ? warm : s === "speaking" ? speak : accent
    }
    function stateName(s) {
        return s === "listening" ? "Listening" : s === "thinking" ? "Working" : s === "speaking" ? "Speaking" : "Ready"
    }
    function alpha(c, a) { return Qt.rgba(c.r, c.g, c.b, c.a * a) }  // (scales: alpha(glass, 0.5) is half as strong)
}
