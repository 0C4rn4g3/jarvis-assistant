import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import Jarvis

// The conversation (or, before it starts, Jarvis's reactor and some ideas), the message box, and today at a glance.
Item {
    id: home
    property var attachments: []
    property string wake: "Hey Jarvis"
    property real latency: -1
    property int userMessageCount: 0
    readonly property bool hasChat: userMessageCount > 0
    readonly property bool wide: width > 1000  // (narrower, today folds into a strip above the conversation)
    readonly property real column: Math.min(760, talk.width - 2 * Theme.margin)

    function reload() {
        Api.get("/api/conversation", c => {
            list.model = null  // (refilled detached, so a reload doesn't animate every message in)
            messages.clear()
            home.userMessageCount = 0
            const raw = (c && c.messages) || []
            for (let i = 0; i < raw.length; i++) {
                const m = raw[i]
                if (m.who === "tool") {
                    let toolSteps = [m.label || Backend.toolLabel(m.text)]
                    while (i + 1 < raw.length && raw[i + 1].who === "tool") {
                        i++
                        toolSteps.push(raw[i].label || Backend.toolLabel(raw[i].text))
                    }
                    messages.append({
                        who: "activity",
                        text: toolSteps.length > 1 ? ("Executed " + toolSteps.length + " steps") : ("Used 1 tool: " + toolSteps[0]),
                        caption: "done",
                        steps: toolSteps.join("\n"),
                        time: m.time || Date.now() / 1000
                    })
                } else {
                    add(m)
                }
            }
            list.model = messages
            list.positionViewAtEnd()
        })
    }
    function add(m) {
        if (!["you", "jarvis", "tool", "activity", "system", "thinking", "image"].includes(m.who)) return
        if (m.who === "you" || m.who === "jarvis" || m.who === "image") home.userMessageCount++

        if (m.who === "tool" || m.who === "activity") {
            const stepName = m.label || (m.who === "tool" ? Backend.toolLabel(m.text) : (m.steps || m.text))
            if (messages.count > 0 && messages.get(messages.count - 1).who === "activity") {
                const lastIdx = messages.count - 1
                const prev = messages.get(lastIdx)
                const currentSteps = prev.steps ? (prev.steps + "\n" + stepName) : stepName
                messages.setProperty(lastIdx, "steps", currentSteps)
                messages.setProperty(lastIdx, "text", "Working on it… (" + stepName + ")")
                messages.setProperty(lastIdx, "caption", "working")
                return
            } else {
                messages.append({
                    who: "activity",
                    text: m.text ? m.text : ("Working on it… (" + stepName + ")"),
                    caption: m.caption || "working",
                    steps: m.steps || stepName,
                    time: m.time || Date.now() / 1000
                })
                return
            }
        }

        if (m.who === "jarvis" && messages.count > 0 && messages.get(messages.count - 1).who === "activity") {
            const lastIdx = messages.count - 1
            const act = messages.get(lastIdx)
            const count = act.steps ? act.steps.split("\n").length : 1
            messages.setProperty(lastIdx, "caption", "done")
            messages.setProperty(lastIdx, "text", count === 1 ? ("Used 1 tool: " + act.steps) : ("Executed " + count + " steps"))
        }

        messages.append({ who: m.who, text: String(m.text || ""), caption: String(m.caption || ""), steps: String(m.steps || ""), time: m.time || Date.now() / 1000 })
    }
    function send(text) {
        text = text.trim()
        if (!text && !attachments.length) return
        const note = attachments.map(p => `(attached: ${p})`).join(" ")
        Backend.send((text + " " + note).trim())
        attachments = []
    }
    onVisibleChanged: if (visible) reload()
    Component.onCompleted: reload()

    ListModel { id: messages }
    Connections {
        target: Backend
        function onEvent(json) {
            const e = JSON.parse(json)
            if (e.kind === "log") {
                const atEnd = list.atYEnd || list.contentHeight < list.height
                home.add(e)
                if (atEnd) Qt.callLater(list.positionViewAtEnd)
            } else if (e.kind === "latency") home.latency = e.seconds
        }
    }

    DropArea {
        id: drop
        anchors.fill: parent
        onDropped: drop => { home.attachments = home.attachments.concat(drop.urls.map(u => decodeURIComponent(String(u).replace("file://", "")))) }
    }
    FileDialog {
        id: picker
        fileMode: FileDialog.OpenFiles
        title: "Attach files for Jarvis"
        onAccepted: home.attachments = home.attachments.concat(selectedFiles.map(u => decodeURIComponent(String(u).replace("file://", ""))))
    }

    // ---- the conversation
    Item {
        id: talk
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom; right: home.wide ? today.left : parent.right
                  rightMargin: home.wide ? 8 : 0 }

        Item {  // before anything is said: the reactor, a greeting and some ideas
            id: hero
            anchors { left: parent.left; right: parent.right; top: parent.top; topMargin: home.wide ? 46 : 116; bottom: composer.top; bottomMargin: 12 }
            visible: !home.hasChat
            opacity: visible ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 250 } }

            Column {
                anchors.centerIn: parent
                width: home.column
                Orb {
                    anchors.horizontalCenter: parent.horizontalCenter
                    // (the outer ring is 84% of the item: 262 gives a ~220 px reactor, smaller only when the height is short)
                    width: Math.max(130, Math.min(262, hero.height - ideas.height - 150)); height: width
                    mode: Backend.state
                    level: Backend.level
                    TapHandler { onTapped: Backend.talk() }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                }
                Item { width: 1; height: 20 }
                Txt {
                    anchors.horizontalCenter: parent.horizontalCenter
                    kind: "display"
                    text: Backend.state === "idle" ? greeting() : Theme.stateName(Backend.state) + "…"
                    function greeting() {
                        const h = new Date().getHours()
                        return h < 5 ? "Up late?" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening"
                    }
                }
                Item { width: 1; height: 8 }
                Txt {
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: Theme.text2
                    font.pixelSize: Theme.px(15)
                    text: Backend.state === "idle" ? `Say “${home.wake}”, tap the reactor, or type below`
                        : Backend.state === "listening" ? (Backend.listening ? "Go ahead, I'm listening" : "Paused")
                        : Backend.state === "speaking" ? `Say “${home.wake}” to cut in` : "On it"
                }
                Item { width: 1; height: 18 }

                // System notice banner (e.g. model quota notice) shown cleanly without hiding the home reactor
                Rectangle {
                    visible: messages.count > 0 && !home.hasChat
                    anchors.horizontalCenter: parent.horizontalCenter
                    width: parent.width
                    implicitHeight: Math.max(36, noticeRow.implicitHeight + 14)
                    radius: Theme.radiusControl
                    color: Theme.alpha(Theme.accent, 0.08)
                    border.width: 1
                    border.color: Theme.alpha(Theme.accent, 0.25)
                    RowLayout {
                        id: noticeRow
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 8
                        spacing: 8
                        Icon { name: "bolt"; size: 16; color: Theme.accent }
                        Txt {
                            Layout.fillWidth: true
                            kind: "small"
                            color: Theme.text
                            text: messages.count > 0 ? messages.get(messages.count - 1).text : ""
                            wrapMode: Text.Wrap
                        }
                        IconButton {
                            size: 24
                            glyph: 12
                            symbol: "close"
                            tip: "Dismiss"
                            onClicked: Api.post("/api/new", {}, () => home.reload())
                        }
                    }
                }
                Item { visible: messages.count > 0 && !home.hasChat; width: 1; height: 14 }

                Grid {
                    id: ideas
                    width: parent.width
                    columns: width > 640 ? 3 : 2
                    spacing: 12
                    Repeater {
                        model: [["sun", "Brief me", "Weather and your schedule"], ["calendar", "What's due this week?", "From Google Classroom"],
                                ["mail", "Any new emails?", "Your Gmail inbox"], ["screen", "What's on my screen?", "Jarvis takes a look"],
                                ["sparkle", "Best faceless niches", "RPM & retention breakdown"], ["image", "Paint a rainy city", "Make a picture"]]
                        Suggestion { required property var modelData; width: (ideas.width - (ideas.columns - 1) * ideas.spacing) / ideas.columns
                                     symbol: modelData[0]; title: modelData[1]; hint: modelData[2] }
                    }
                }
            }
        }

        Pill {
            id: fresh
            anchors { top: parent.top; topMargin: home.wide ? 52 : 62; right: parent.right; rightMargin: (parent.width - home.column) / 2 }
            visible: home.hasChat
            implicitHeight: 36
            text: "New chat"
            symbol: "plus"
            onClicked: Api.post("/api/new", {}, () => home.reload())
        }

        ListView {
            id: list
            anchors { left: parent.left; right: parent.right; top: fresh.bottom; topMargin: home.wide ? 4 : 14; bottom: composer.top; bottomMargin: 4 }
            visible: home.hasChat
            clip: true
            model: messages
            topMargin: 8
            bottomMargin: 16
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: Scroller {}
            delegate: Message { width: ListView.view.width; column: home.column }
            add: Transition {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 220; easing.type: Easing.OutCubic }
                NumberAnimation { property: "rise"; from: 8; to: 0; duration: 220; easing.type: Easing.OutCubic }
            }
            footer: Item {  // while Jarvis works: a warm reactor, a pulsing "Working on it…" chip and Stop
                id: busy
                readonly property bool on: Backend.state === "thinking"
                width: ListView.view.width
                height: on ? 48 : 0
                visible: on
                onOnChanged: if (on) Qt.callLater(list.positionViewAtEnd)
                Item {
                    x: (parent.width - home.column) / 2
                    width: home.column; height: 32
                    anchors.verticalCenter: parent.verticalCenter
                    Orb { width: 24; height: 24; anchors.verticalCenter: parent.verticalCenter; rings: false; mode: "thinking" }
                    Rectangle {
                        x: 36  // (the text column, like the tool chips)
                        width: working.implicitWidth + 26; height: 32; radius: 16
                        color: Theme.glass
                        border.width: 1
                        border.color: Theme.stroke
                        Row {
                            id: working
                            anchors.centerIn: parent
                            spacing: 9
                            StatusDot {
                                anchors.verticalCenter: parent.verticalCenter
                                status: "working"
                                SequentialAnimation on opacity {
                                    running: busy.on; loops: Animation.Infinite
                                    NumberAnimation { to: 0.35; duration: 700; easing.type: Easing.InOutSine }
                                    NumberAnimation { to: 1; duration: 700; easing.type: Easing.InOutSine }
                                }
                            }
                            Txt { anchors.verticalCenter: parent.verticalCenter; text: "Working on it…"; color: Theme.text2
                                  font.pixelSize: Theme.px(13); wrapMode: Text.NoWrap }
                        }
                    }
                    Chip { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                           symbol: "stop"; text: "Stop"; ink: Theme.warm; onClicked: Backend.stop() }
                }
            }
        }

        Composer {
            id: composer
            anchors { bottom: parent.bottom; bottomMargin: 24; horizontalCenter: parent.horizontalCenter }
            width: home.column
            stopShown: list.visible && Backend.state === "thinking"  // (the Stop chip under the conversation)
            attachments: home.attachments
            onSubmitted: text => home.send(text)
            onAttach: picker.open()
            onRemoved: path => home.attachments = home.attachments.filter(p => p !== path)
        }

        Rectangle {  // dragging files over Jarvis
            anchors { fill: parent; topMargin: 46; margins: 16 }
            visible: drop.containsDrag
            radius: Theme.radius
            color: Theme.alpha(Theme.accentSoft, 0.6)
            border.width: 1
            border.color: Theme.alpha(Theme.accent, 0.5)
            Column {
                anchors.centerIn: parent
                spacing: 10
                Icon { anchors.horizontalCenter: parent.horizontalCenter; name: "attach"; size: 28; color: Theme.accent }
                Txt { kind: "heading"; text: "Drop to attach" }
            }
        }
    }

    Today {
        id: today
        x: home.wide ? home.width - width - 12 : (home.width - home.column) / 2
        y: 52
        width: home.wide ? 350 : home.column - (fresh.visible ? fresh.width + 12 : 0)
        height: home.wide ? home.height - y - 24 : 56
        compact: !home.wide
        latency: home.latency
        onWake: phrase => home.wake = phrase
    }

    component Suggestion: AbstractButton {
        id: s
        property string symbol
        property string title
        property string hint
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        implicitHeight: 76
        onClicked: Backend.send(title)
        background: Glass {
            color: s.hovered ? Theme.glassHover : Theme.glass
            border.color: s.hovered ? Theme.alpha(Theme.accent, 0.3) : Theme.stroke
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            Behavior on border.color { ColorAnimation { duration: Theme.fast } }
        }
        contentItem: Item {
            Rectangle {
                id: well
                x: 16; anchors.verticalCenter: parent.verticalCenter
                width: 36; height: 36; radius: 18
                color: s.hovered ? Theme.alpha(Theme.accent, 0.22) : Theme.accentSoft
                Icon { anchors.centerIn: parent; name: s.symbol; size: 18; color: Theme.accent }
            }
            Column {
                anchors { left: well.right; leftMargin: 12; right: parent.right; rightMargin: 14; verticalCenter: parent.verticalCenter }
                spacing: 3
                Txt { text: s.title; width: parent.width; weight: 600; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                Txt { text: s.hint; kind: "small"; font.pixelSize: Theme.px(12); width: parent.width; elide: Text.ElideRight; wrapMode: Text.NoWrap }
            }
        }
        scale: down ? 0.97 : 1
        Behavior on scale { NumberAnimation { duration: Theme.fast; easing.type: Easing.OutCubic } }
    }
}
