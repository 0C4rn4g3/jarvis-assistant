import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import Jarvis

// Jarvis's window: a rail of pages on the left, the page on the right, the notch at the top of the screen.
Window {
    id: win
    property bool startShown: true
    property string page: "home"
    property bool needsSetup: false  // the first run: the setup screen covers the window until it's done or skipped
    readonly property bool maximized: visibility === Window.Maximized
    width: 1220
    height: 800
    minimumWidth: 900
    minimumHeight: 600
    visible: startShown
    title: "Jarvis"
    color: "transparent"
    property bool pinned: false
    flags: Qt.Window | Qt.FramelessWindowHint | (pinned ? Qt.WindowStaysOnTopHint : 0)
    onPinnedChanged: win.visible = true

    function present() { win.visible = true; show(); raise(); requestActivate() }
    function go(key) { page = key; if (key === "home") home.reload() }
    Component.onCompleted: Api.get("/api/settings", d => { win.needsSetup = !d.settings.setup_done; Theme.scale = d.settings.text_size || 1 })

    Connections {
        target: Backend
        function onShowRequested() { win.present() }
        function onToastRequested(text, bad) { toast.show(text, bad) }
    }

    Shortcut { sequence: "Ctrl+N"; onActivated: { Api.post("/api/new", {}, () => home.reload()); win.go("home") } }
    Shortcut { sequence: "Ctrl+1"; onActivated: win.go("home") }
    Shortcut { sequence: "Ctrl+2"; onActivated: win.go("chats") }
    Shortcut { sequence: "Ctrl+,"; onActivated: win.go("settings") }
    Shortcut { sequence: "F9"; onActivated: win.pinned = !win.pinned }
    Shortcut { sequence: "Ctrl+Shift+P"; onActivated: win.pinned = !win.pinned }
    Shortcut { sequence: "Escape"; enabled: Backend.state !== "idle"; onActivated: Backend.stop() }


    onPageChanged: pageIn.restart()

    Item {
        id: frame
        anchors.fill: parent
        readonly property real radius: win.maximized ? 0 : Theme.radiusWindow
        property color glow: Theme.stateColor(Backend.state)
        Behavior on glow { ColorAnimation { duration: 600; easing.type: Easing.OutCubic } }

        // the canvas: a deep navy gradient, light in Jarvis's colour of the moment from the top right, a warm hint below
        Shape {
            id: canvas
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            readonly property real big: Math.max(width, height)
            ShapePath {
                strokeWidth: -1
                fillGradient: LinearGradient {
                    x1: 0; y1: 0; x2: 0; y2: frame.height
                    GradientStop { position: 0; color: Theme.bgTop }
                    GradientStop { position: 1; color: Theme.bgBottom }
                }
                PathRectangle { width: frame.width; height: frame.height; radius: frame.radius }
            }
            ShapePath {
                strokeWidth: -1
                fillGradient: RadialGradient {
                    centerX: frame.width * 0.9; centerY: -frame.height * 0.08; focalX: centerX; focalY: centerY
                    centerRadius: canvas.big * 0.8
                    GradientStop { position: 0; color: Theme.alpha(frame.glow, 0.13) }
                    GradientStop { position: 0.45; color: Theme.alpha(frame.glow, 0.045) }
                    GradientStop { position: 1; color: Theme.alpha(frame.glow, 0) }
                }
                PathRectangle { width: frame.width; height: frame.height; radius: frame.radius }
            }
            ShapePath {
                strokeWidth: -1
                fillGradient: RadialGradient {
                    centerX: frame.width * 0.08; centerY: frame.height * 1.05; focalX: centerX; focalY: centerY
                    centerRadius: canvas.big * 0.75
                    GradientStop { position: 0; color: Theme.alpha(Theme.warm, 0.04) }
                    GradientStop { position: 1; color: Theme.alpha(Theme.warm, 0) }
                }
                PathRectangle { width: frame.width; height: frame.height; radius: frame.radius }
            }
        }

        // ---- the rail, floating over the canvas
        Glass {
            id: rail
            floating: true
            x: 12; y: 12
            width: 72; height: parent.height - 24
            radius: 20

            DragHandler { target: null; onActiveChanged: if (active) win.startSystemMove() }

            ColumnLayout {
                anchors { fill: parent; topMargin: 12; bottomMargin: 8 }
                spacing: 4

                Orb {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.preferredWidth: 46; Layout.preferredHeight: 46
                    mode: Backend.state
                    level: Backend.level
                    rings: false
                    TapHandler { onTapped: Backend.talk() }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                }
                Rectangle { Layout.alignment: Qt.AlignHCenter; Layout.preferredWidth: 32; Layout.preferredHeight: 1
                            Layout.topMargin: 8; Layout.bottomMargin: 8; color: Theme.stroke }

                Repeater {
                    model: [["home", "Home", "home"], ["chats", "Chats", "chats"], ["activity", "Activity", "activity"],
                            ["accounts", "Accounts", "accounts"], ["plugins", "Plugins", "plugins"], ["models", "Models", "cpu"],
                            ["memory", "Memory", "memory"], ["health", "Health", "pulse"]]
                    RailButton { required property var modelData; key: modelData[0]; label: modelData[1]; symbol: modelData[2] }
                }
                Item { Layout.fillHeight: true }
                RailButton { key: "settings"; label: "Settings"; symbol: "settings" }
            }
        }

        // ---- the page
        Item {
            anchors { left: rail.right; right: parent.right; top: parent.top; bottom: parent.bottom }

            Item {
                id: pages
                anchors.fill: parent
                transform: Translate { id: rise }
                ParallelAnimation {
                    id: pageIn
                    NumberAnimation { target: pages; property: "opacity"; from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic }
                    NumberAnimation { target: rise; property: "y"; from: 8; to: 0; duration: 200; easing.type: Easing.OutCubic }
                }
                StackLayout {
                    anchors.fill: parent
                    currentIndex: ["home", "chats", "activity", "accounts", "plugins", "models", "memory", "settings", "health"].indexOf(win.page)
                    HomePage { id: home }
                    Loader { active: win.page === "chats" || item; sourceComponent: ChatsPage {
                        onOpened: { home.reload(); win.go("home") }
                        onDeleted: id => { home.reload() }
                    } }
                    Loader { active: win.page === "activity" || item; sourceComponent: ActivityPage {} }
                    Loader { active: win.page === "accounts" || item; sourceComponent: AccountsPage {} }
                    Loader { active: win.page === "plugins" || item; sourceComponent: PluginsPage {} }
                    Loader { active: win.page === "models" || item; sourceComponent: ModelsPage {} }
                    Loader { active: win.page === "memory" || item; sourceComponent: MemoryPage {} }
                    Loader { active: win.page === "settings" || item; sourceComponent: SettingsPage { onSetupAgain: win.needsSetup = true } }
                    Loader { active: win.page === "health" || item; sourceComponent: HealthPage { onGoTo: key => win.go(key) } }
                }
            }
        }

        // resize from the edges and corners
        Repeater {
            model: [[Qt.LeftEdge, 0, 6, 0, 0], [Qt.RightEdge, 0, 6, 1, 0], [Qt.TopEdge, 1, 6, 0, 0], [Qt.BottomEdge, 1, 6, 0, 1],
                    [Qt.LeftEdge | Qt.TopEdge, 2, 12, 0, 0], [Qt.RightEdge | Qt.TopEdge, 2, 12, 1, 0],
                    [Qt.LeftEdge | Qt.BottomEdge, 2, 12, 0, 1], [Qt.RightEdge | Qt.BottomEdge, 2, 12, 1, 1]]
            MouseArea {
                required property var modelData
                visible: !win.maximized
                readonly property int kind: modelData[1]
                x: kind === 1 ? 12 : modelData[3] ? parent.width - width : 0
                y: kind === 0 ? 12 : modelData[4] ? parent.height - height : 0
                width: kind === 1 ? parent.width - 24 : modelData[2]
                height: kind === 0 ? parent.height - 24 : modelData[2]
                cursorShape: kind === 0 ? Qt.SizeHorCursor : kind === 1 ? Qt.SizeVerCursor
                           : (modelData[3] === modelData[4]) ? Qt.SizeFDiagCursor : Qt.SizeBDiagCursor
                onPressed: win.startSystemResize(modelData[0])
            }
        }

        Item {  // the top strip: drag to move, ModeSelector on left, window buttons on right
            id: top
            anchors { left: rail.right; right: parent.right; top: parent.top }
            height: 48
            z: 5.5
            DragHandler { target: null; onActiveChanged: if (active) win.startSystemMove() }
            TapHandler { onDoubleTapped: win.maximized ? win.showNormal() : win.showMaximized() }

            // subtle bottom hairline divider
            Rectangle {
                anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                height: 1
                color: Theme.stroke
            }

            ModeSelector {
                id: modeSel
                anchors { left: parent.left; leftMargin: 16; verticalCenter: parent.verticalCenter }
            }

            RowLayout {
                anchors { right: parent.right; rightMargin: 16; verticalCenter: parent.verticalCenter }
                spacing: 12

                WinButton {
                    symbol: "pin"
                    tip: win.pinned ? "Unpin window" : "Pin on top (Gaming HUD)"
                    active: win.pinned
                    onClicked: win.pinned = !win.pinned
                }

                Rectangle {
                    Layout.preferredWidth: 1; Layout.preferredHeight: 18
                    color: Theme.stroke
                    Layout.alignment: Qt.AlignVCenter
                }

                TrafficLightGroup {}
            }

        }


        Loader {
            anchors.fill: parent
            active: win.needsSetup
            z: 5
            sourceComponent: SetupWizard { onFinished: goTo => { win.needsSetup = false; if (goTo) win.go(goTo) } }
        }

        Toast { id: toast; z: 6; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 28 }

        Rectangle {  // the window's edge, over everything
            anchors.fill: parent
            z: 7
            visible: !win.maximized
            radius: frame.radius
            color: "transparent"
            border.width: 1
            border.color: Theme.strokeStrong
        }
    }

    component RailButton: AbstractButton {
        id: rb
        property string key
        property string label
        property string symbol
        readonly property bool current: win.page === key
        Layout.alignment: Qt.AlignHCenter
        Layout.preferredWidth: 60
        Layout.preferredHeight: 52
        Layout.maximumHeight: 52
        Layout.minimumHeight: 42
        Layout.fillHeight: true  // (so it can shrink in a short window)
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        onClicked: win.go(key)
        background: Rectangle {
            radius: 14
            color: rb.current ? Theme.accentSoft : rb.hovered ? Theme.glassHover : "transparent"
            border.width: 1
            border.color: rb.current ? Theme.alpha(Theme.accent, 0.45) : rb.hovered ? Theme.stroke : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            Behavior on border.color { ColorAnimation { duration: Theme.fast } }

            // Active indicator vertical pill on left edge
            Rectangle {
                visible: rb.current
                anchors { left: parent.left; leftMargin: 3; verticalCenter: parent.verticalCenter }
                width: 3; height: 16; radius: 1.5
                color: Theme.accent
            }
        }
        contentItem: Item {
            Column {
                anchors.centerIn: parent
                spacing: 3
                Icon { anchors.horizontalCenter: parent.horizontalCenter; name: rb.symbol; size: 19
                       color: rb.current ? Theme.accent : rb.hovered ? Theme.text : Theme.text2 }
                Text { anchors.horizontalCenter: parent.horizontalCenter; text: rb.label; font.family: Theme.font; font.pixelSize: Theme.px(10.5)
                       font.variableAxes: { "wght": rb.current ? 650 : 500 }; color: rb.current ? Theme.text : rb.hovered ? Theme.text : Theme.text2 }
            }
        }
        scale: down ? 0.95 : rb.hovered ? 1.02 : 1
        Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
    }

    component TrafficLightGroup: Row {
        id: tlg
        spacing: 8
        Layout.alignment: Qt.AlignVCenter
        property bool hoveredGroup: closeBtn.hovered || minBtn.hovered || maxBtn.hovered

        TrafficButton {
            id: closeBtn
            baseColor: Theme.trafficRed
            strokeColor: Theme.trafficStrokeRed
            glyphColor: "#4f0004"
            symbol: "close"
            tip: "Close (Jarvis keeps running in the tray)"
            groupHovered: tlg.hoveredGroup
            onClicked: win.hide()
        }
        TrafficButton {
            id: minBtn
            baseColor: Theme.trafficYellow
            strokeColor: Theme.trafficStrokeYellow
            glyphColor: "#563800"
            symbol: "min"
            tip: "Minimise"
            groupHovered: tlg.hoveredGroup
            onClicked: win.showMinimized()
        }
        TrafficButton {
            id: maxBtn
            baseColor: Theme.trafficGreen
            strokeColor: Theme.trafficStrokeGreen
            glyphColor: "#02420a"
            symbol: win.maximized ? "restore" : "max"
            tip: win.maximized ? "Restore" : "Maximise"
            groupHovered: tlg.hoveredGroup
            onClicked: win.maximized ? win.showNormal() : win.showMaximized()
        }
    }

    component TrafficButton: AbstractButton {
        id: tb
        property color baseColor
        property color strokeColor
        property color glyphColor
        property string symbol
        property string tip
        property bool groupHovered: false
        implicitWidth: 16; implicitHeight: 16
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        Tip { text: tb.tip; visible: tb.hovered }
        background: Rectangle {
            anchors.fill: parent
            radius: 8
            color: tb.baseColor
            border.width: 1
            border.color: tb.strokeColor
        }
        contentItem: Item {
            Icon {
                anchors.centerIn: parent
                name: tb.symbol
                size: 8
                color: tb.glyphColor
                opacity: tb.groupHovered ? 0.9 : 0
                Behavior on opacity { NumberAnimation { duration: Theme.fast } }
            }
        }
        scale: down ? 0.92 : 1
        Behavior on scale { NumberAnimation { duration: Theme.fast } }
    }

    component WinButton: AbstractButton {
        id: wb
        property string symbol
        property string tip
        property bool danger: false
        property bool active: false
        implicitWidth: 32; implicitHeight: 32
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        Tip { text: wb.tip; visible: wb.hovered }
        background: Rectangle {
            radius: 16
            color: wb.active ? Theme.accentSoft : wb.hovered ? Theme.glassHover : "transparent"
            border.width: 1
            border.color: wb.active ? Theme.alpha(Theme.accent, 0.45) : wb.hovered ? Theme.stroke : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            Behavior on border.color { ColorAnimation { duration: Theme.fast } }
        }
        contentItem: Item {
            Icon { anchors.centerIn: parent; name: wb.symbol; size: 15; color: wb.active ? Theme.accent : wb.hovered ? (wb.danger ? "white" : Theme.text) : Theme.text2 }
        }
        scale: down ? 0.94 : 1
        Behavior on scale { NumberAnimation { duration: Theme.fast } }
    }

}
