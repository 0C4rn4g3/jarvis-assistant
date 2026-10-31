import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Jarvis

// What Jarvis did in this conversation, step by step: tools, notices and its own thinking, newest first.
Item {
    id: page
    property var speeds: []
    property var subagents: []

    function load() {
        Api.get("/api/conversation", c => {
            steps.clear()
            for (const m of c.messages) add(m)
        })
        loadSubagents()
    }
    function loadSubagents() {
        Api.get("/api/subagents", res => {
            if (res && res.subagents) page.subagents = res.subagents
        })
    }
    function add(m) {
        if (!["tool", "system", "thinking"].includes(m.who)) return
        steps.insert(0, { who: m.who, text: String(m.text), time: m.time || Date.now() / 1000 })
    }
    function plain(t) {  // a leading emoji in a notice clashes with the line icons
        return t.replace(/^(?:[\u2300-\u27bf\u2b00-\u2bff]|[\ud83c-\ud83e][\udc00-\udfff])\ufe0f?\s*/, "")
    }
    Component.onCompleted: load()
    onVisibleChanged: if (visible) load()
    ListModel { id: steps }
    Connections {
        target: Backend
        function onEvent(json) {
            const e = JSON.parse(json)
            if (e.kind === "log") page.add(e)
            else if (e.kind === "latency") page.speeds = page.speeds.concat([e.seconds]).slice(-20)
            else if (e.kind === "subagent_progress" || e.kind === "subagent_finished" || e.kind === "subagent_spawned") page.loadSubagents()
        }
    }
    Timer {
        interval: 2000
        running: page.visible && page.subagents && page.subagents.some(s => s.status === "running")
        repeat: true
        onTriggered: page.loadSubagents()
    }

    ColumnLayout {
        anchors { top: parent.top; bottom: parent.bottom; horizontalCenter: parent.horizontalCenter; margins: Theme.margin }
        width: Math.min(parent.width - 2 * Theme.margin, Theme.pageWidth)
        spacing: 24

        PageHeader {
            Layout.fillWidth: true
            title: "Activity"
            hint: "Every step Jarvis takes in this conversation, as it happens."
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.gap

            Card {  // the steps, newest first, on a timeline through their icons; as tall as they are, up to the page
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.maximumHeight: steps.count ? list.contentHeight + 2 * padding : Number.POSITIVE_INFINITY
                Layout.alignment: Qt.AlignTop
                padding: 8
                ListView {
                    id: list
                    anchors.fill: parent
                    clip: true
                    model: steps
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: Scroller {}
                    delegate: Item {
                        id: step
                        required property string who
                        required property string text
                        required property real time
                        required property int index
                        readonly property color tint: who === "tool" ? Theme.warm : who === "thinking" ? Theme.accent : Theme.text2
                        width: ListView.view.width
                        height: Math.max(56, title.implicitHeight + 32)
                        Rectangle {
                            anchors.fill: parent
                            radius: Theme.radiusControl
                            color: hover.hovered ? Theme.glassHover : "transparent"
                            Behavior on color { ColorAnimation { duration: Theme.fast } }
                        }
                        HoverHandler { id: hover }
                        Tip { text: step.text; visible: step.who === "tool" && hover.hovered }
                        Rectangle {  // the timeline
                            x: 27; y: step.index === 0 ? 28 : 0
                            width: 1; height: (step.index === steps.count - 1 ? 28 : step.height) - y
                            color: Theme.stroke
                        }
                        Rectangle {
                            x: 12; y: 12
                            width: 32; height: 32; radius: 16
                            color: Qt.tint(Theme.bg, Theme.alpha(step.tint, 0.16))  // opaque, so the timeline stops at its edge
                            border.width: 1
                            border.color: Theme.alpha(step.tint, 0.2)
                            Icon { anchors.centerIn: parent; size: 16; color: step.tint
                                   name: step.who === "tool" ? "wrench" : step.who === "thinking" ? "sparkle" : "bell" }
                        }
                        Txt {
                            id: title
                            x: 56
                            width: parent.width - x - when.width - 28
                            anchors.verticalCenter: parent.verticalCenter
                            text: step.who === "tool" ? Backend.toolLabel(step.text) : page.plain(step.text)
                            weight: step.who === "thinking" ? 400 : 500
                            color: step.who === "thinking" ? Theme.text2 : Theme.text
                            maximumLineCount: 4
                            elide: Text.ElideRight
                        }
                        Txt {
                            id: when
                            anchors { right: parent.right; rightMargin: 16; baseline: title.baseline }
                            kind: "small"; font.pixelSize: Theme.px(12); font.features: { "tnum": 1 }; color: Theme.text3; wrapMode: Text.NoWrap
                            text: Qt.formatTime(new Date(step.time * 1000), "HH:mm:ss")
                        }
                        Rectangle {
                            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: 56; rightMargin: 12 }
                            height: 1
                            color: Theme.stroke
                            visible: step.index < steps.count - 1 && !hover.hovered
                        }
                    }
                    footer: Item {
                        width: ListView.view.width
                        visible: steps.count > 0
                        height: hint.implicitHeight + 24
                        Txt {
                            id: hint
                            y: 16
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            kind: "small"; color: Theme.text3
                            text: "New steps appear at the top as Jarvis works"
                        }
                    }
                    ColumnLayout {
                        anchors.centerIn: parent
                        width: parent.width - 32
                        visible: steps.count === 0
                        spacing: 12
                        Rectangle {
                            Layout.alignment: Qt.AlignHCenter
                            width: 40; height: 40; radius: 20
                            color: Theme.accentSoft
                            Icon { anchors.centerIn: parent; name: "activity"; size: 20; color: Theme.accent }
                        }
                        Txt { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; kind: "small"; text: "Nothing yet: ask Jarvis something" }
                    }
                }
            }

            ColumnLayout {
                Layout.preferredWidth: 280
                Layout.alignment: Qt.AlignTop
                spacing: Theme.gap

                Card {
                    Layout.fillWidth: true
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 10
                        RowLayout {
                            Layout.fillWidth: true
                            Icon { name: "cpu"; size: 16; color: Theme.accent }
                            Txt { kind: "label"; text: "Background Swarm"; Layout.fillWidth: true }
                            IconButton {
                                size: 28; glyph: 13
                                symbol: "refresh"
                                tip: "Refresh subagents"
                                onClicked: page.loadSubagents()
                            }
                        }
                        Txt {
                            kind: "small"; color: Theme.text3
                            text: page.subagents && page.subagents.length > 0
                                  ? (page.subagents.filter(s => s.status === "running").length + " active · " + page.subagents.length + " total")
                                  : "Autonomous background agents run here."
                        }
                        ListView {
                            Layout.fillWidth: true
                            implicitHeight: Math.min(240, Math.max(48, count * 56))
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            model: page.subagents || []
                            spacing: 6
                            delegate: Rectangle {
                                id: subagentDelegate
                                required property var modelData
                                width: ListView.view ? ListView.view.width : 260
                                height: 50
                                radius: Theme.radiusControl
                                color: Theme.glassHover
                                border.width: 1
                                border.color: modelData.status === "running" ? Theme.alpha(Theme.accent, 0.4) : Theme.stroke

                                ColumnLayout {
                                    anchors { fill: parent; margins: 6 }
                                    spacing: 3

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 6

                                        Rectangle {
                                            width: 8; height: 8; radius: 4
                                            color: modelData.status === "running" ? Theme.listen :
                                                   modelData.status === "completed" ? Theme.accent :
                                                   modelData.status === "failed" ? Theme.red : Theme.warm
                                        }

                                        Txt {
                                            Layout.fillWidth: true
                                            text: modelData.task || "Subagent"
                                            font.pixelSize: Theme.px(12)
                                            weight: 600
                                            elide: Text.ElideRight
                                            color: Theme.text
                                        }

                                        Txt {
                                            visible: modelData.status === "running"
                                            font.pixelSize: Theme.px(11)
                                            font.features: { "tnum": 1 }
                                            text: (modelData.progress || 0) + "%"
                                            color: Theme.accent
                                        }

                                        IconButton {
                                            visible: modelData.status === "running"
                                            size: 22; glyph: 10
                                            symbol: "close"
                                            tip: "Cancel task"
                                            onClicked: {
                                                Api.post("/api/subagents/cancel", { id: modelData.id }, () => {
                                                    page.loadSubagents()
                                                })
                                            }
                                        }
                                    }

                                    Rectangle {
                                        visible: modelData.status === "running"
                                        Layout.fillWidth: true
                                        height: 3
                                        radius: 1.5
                                        color: Theme.stroke
                                        Rectangle {
                                            width: parent.width * Math.max(0.05, Math.min(1.0, (modelData.progress || 0) / 100))
                                            height: parent.height
                                            radius: 1.5
                                            color: Theme.listen
                                        }
                                    }

                                    Txt {
                                        Layout.fillWidth: true
                                        font.pixelSize: Theme.px(10)
                                        color: Theme.text3
                                        elide: Text.ElideRight
                                        text: modelData.status === "running"
                                              ? (modelData.progress_label || modelData.current_step || "Running in background…")
                                              : (modelData.status + (modelData.completed_at ? (" · " + Qt.formatTime(new Date(modelData.completed_at * 1000), "HH:mm:ss")) : ""))
                                    }
                                }
                            }
                        }
                    }
                }

                Card {
                    Layout.fillWidth: true
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 10
                        RowLayout {
                            Layout.fillWidth: true
                            Txt { kind: "label"; text: "Execution DAG"; Layout.fillWidth: true }
                            Chip {
                                symbol: "refresh-cw"
                                text: "Rollback"
                                onClicked: {
                                    Api.post("/api/security/rollback", {}, res => {
                                        page.load()
                                    })
                                }
                            }
                        }
                        Txt {
                            kind: "small"; color: Theme.text3
                            text: "Active multi-step execution pipeline & latency graph."
                        }
                        ListView {
                            Layout.fillWidth: true
                            implicitHeight: Math.min(220, Math.max(70, count * 36))
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            model: steps
                            delegate: Item {
                                id: dagNode
                                required property string who
                                required property string text
                                required property real time
                                required property int index
                                readonly property bool isTool: who === "tool"
                                visible: who === "tool" || who === "thinking"
                                width: ListView.view ? ListView.view.width : 260
                                height: visible ? 34 : 0
                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 4
                                    anchors.rightMargin: 4
                                    spacing: 8
                                    Rectangle {
                                        width: 8; height: 8; radius: 4
                                        color: dagNode.isTool ? Theme.listen : Theme.accent
                                    }
                                    Txt {
                                        Layout.fillWidth: true
                                        text: dagNode.isTool ? Backend.toolLabel(dagNode.text) : "Plan / Reasoning"
                                        kind: "small"
                                        elide: Text.ElideRight
                                        color: Theme.text
                                    }
                                    Txt {
                                        kind: "small"
                                        font.pixelSize: Theme.px(11)
                                        text: Qt.formatTime(new Date(dagNode.time * 1000), "HH:mm:ss")
                                        color: Theme.text3
                                    }
                                }
                            }
                        }
                    }
                }

                Card {  // shows up with the first timed reply
                    Layout.fillWidth: true
                    visible: page.speeds.length > 0
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 6
                        Txt { kind: "label"; text: "Reply speed" }
                        Row {
                            spacing: 4
                            Txt {
                                id: average
                                text: page.speeds.length ? (page.speeds.reduce((a, b) => a + b, 0) / page.speeds.length).toFixed(2) : ""
                                kind: "display"; font.features: { "tnum": 1 }; wrapMode: Text.NoWrap
                            }
                            Txt { text: "s"; kind: "heading"; weight: 500; color: Theme.text2; anchors.baseline: average.baseline }
                        }
                        Txt { kind: "small"; Layout.fillWidth: true; lineHeight: 1.15
                              text: `Averaged over the last ${page.speeds.length} replies: from the end of what you said to Jarvis's first word.` }
                        Item { Layout.fillHeight: true }
                        Item {
                            id: chart
                            Layout.fillWidth: true
                            implicitHeight: 64
                            visible: page.speeds.length > 1
                            Row {
                                anchors.bottom: parent.bottom
                                spacing: 4
                                Repeater {
                                    model: page.speeds
                                    Rectangle {
                                        required property real modelData
                                        width: Math.floor((chart.width - 19 * 4) / 20); height: Math.max(4, Math.min(64, modelData * 24)); radius: 3
                                        anchors.bottom: parent.bottom
                                        color: modelData < 1.2 ? Theme.listen : modelData < 2.5 ? Theme.warm : Theme.red
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        Item { Layout.fillHeight: true; visible: steps.count > 0 }  // the room a short list of steps leaves free
    }
}
