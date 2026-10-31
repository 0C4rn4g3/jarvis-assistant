import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import Jarvis

// Today at a glance: the time and weather, what's playing, what's next, and how the PC is doing.
// `compact` (a narrow window) folds it into one strip: the time, the weather and what's playing.
ScrollView {
    id: today
    property real latency: -1
    property bool compact: false
    signal wake(string phrase)
    property var info: ({})
    property var media: ({})
    property var stats: ({})
    property var now: new Date()
    readonly property var weather: info.weather || {}
    readonly property bool shown: visible && Window.window !== null && Window.window.visible
    contentWidth: width
    contentHeight: compact ? strip.implicitHeight : cards.implicitHeight
    clip: true
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    ScrollBar.vertical: Scroller { parent: today; x: today.width - width; height: today.availableHeight }

    function load() { Api.get("/api/today", t => { info = t; wake(t.wake || "Hey Jarvis") }) }
    function live() {
        Api.get("/api/media", d => media = d)
        Api.get("/api/system", d => stats = d)
    }
    function gb(bytes) { return (bytes / 1073741824).toFixed(1) }
    function sky(c) {  // a line icon for wttr.in's condition (its emoji clash with the icon set)
        c = String(c).toLowerCase()
        return /thunder/.test(c) ? "bolt" : /sun/.test(c) ? "sun" : /clear/.test(c) ? (today.now.getHours() < 6 || today.now.getHours() >= 19 ? "moon" : "sun") : "cloud"
    }
    Component.onCompleted: { load(); live() }
    Timer { interval: 60000; running: true; repeat: true; onTriggered: today.load() }
    Timer { interval: 3000; running: today.shown; repeat: true; triggeredOnStart: true; onTriggered: today.live() }
    Timer { interval: 1000; running: today.shown; repeat: true; triggeredOnStart: true; onTriggered: today.now = new Date() }
    Connections {
        target: Backend
        function onEvent(json) {
            let k = JSON.parse(json).kind
            if (k === "mode" || k === "game_project" || k === "goal_created" || k === "goal_updated" || k === "goal_deleted" || (k === "log" && json.indexOf("Reminder") >= 0)) today.load()
        }
    }


    Glass {
        id: strip
        visible: today.compact
        width: today.availableWidth
        implicitHeight: 56
        radius: 20
        RowLayout {
            anchors { fill: parent; leftMargin: 22; rightMargin: 10 }
            spacing: 12
            Txt { text: Qt.formatTime(today.now, "HH:mm"); kind: "heading"; font.features: { "tnum": 1 }; wrapMode: Text.NoWrap }
            Icon { visible: !!today.weather.temp; name: today.sky(today.weather.condition); size: 18; Layout.preferredWidth: 18; Layout.preferredHeight: 18; color: name === "sun" ? Theme.accent : Theme.text2 }
            Txt { visible: !!today.weather.temp; text: today.weather.temp || ""; kind: "small"; wrapMode: Text.NoWrap }
            Rectangle { visible: !!today.media.title; Layout.preferredWidth: 1; Layout.preferredHeight: 20; Layout.leftMargin: 4; Layout.rightMargin: 4; color: Theme.stroke }
            Icon { visible: !!today.media.title; name: "music"; size: 16; Layout.preferredWidth: 16; Layout.preferredHeight: 16; color: Theme.accent }
            Txt { text: today.media.title || ""; Layout.fillWidth: true; elide: Text.ElideRight; wrapMode: Text.NoWrap }
            IconButton { visible: !!today.media.title; symbol: today.media.status === "Playing" ? "pause" : "play"; tint: Theme.accentSoft; iconColor: Theme.accent
                         size: 36; glyph: 16; onClicked: Api.post("/api/media/PlayPause", {}, today.live) }
        }
    }

    ColumnLayout {
        id: cards
        visible: !today.compact
        width: today.availableWidth
        spacing: 12

        // the time and the weather
        Card {
            Layout.fillWidth: true
            ColumnLayout {
                width: parent.width
                spacing: 16
                ColumnLayout {
                    spacing: 2
                    Txt { text: Qt.formatTime(today.now, "HH:mm"); font.pixelSize: Theme.px(48); weight: 600; font.letterSpacing: -2
                          font.features: { "tnum": 1 }; lineHeight: 0.95 }
                    Txt { text: Qt.formatDate(today.now, "dddd, d MMMM"); kind: "small" }
                }
                Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.stroke; visible: !!today.weather.temp }
                RowLayout {
                    visible: !!today.weather.temp
                    spacing: 12
                    Icon { name: today.sky(today.weather.condition); size: 24; Layout.preferredWidth: 24; Layout.preferredHeight: 24; color: name === "sun" ? Theme.accent : Theme.text2 }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Txt { text: today.weather.condition || ""; weight: 600; Layout.fillWidth: true; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                        Txt { kind: "small"; text: "Feels " + (today.weather.feels || "") + " in " + (today.weather.place || "")
                              Layout.fillWidth: true; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                    }
                    Txt { text: today.weather.temp || ""; kind: "heading"; font.pixelSize: Theme.px(22); weight: 500; wrapMode: Text.NoWrap }
                }
            }
        }

        // Game Studio Hub (visible when in game_designer mode)
        Card {
            Layout.fillWidth: true
            visible: today.info.mode === "game_designer"
            ColumnLayout {
                width: parent.width
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Icon { name: "gamepad"; size: 20; color: Theme.accent }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Txt {
                            text: (today.info.game && today.info.game.name) ? today.info.game.name : "Game Designer Studio"
                            font.pixelSize: Theme.px(16)
                            weight: 600
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                        Txt {
                            kind: "small"
                            color: Theme.text3
                            text: (today.info.game ? (today.info.game.engine || "Game Engine") + " · " + (today.info.game.genre || "") : "Active Game Project")
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                    }
                    IconButton {
                        size: 28
                        glyph: 14
                        symbol: "external"
                        tip: "Open Project Folder"
                        tint: Theme.glass
                        iconColor: Theme.text2
                        onClicked: Api.post("/api/games/open", {}, () => Backend.toast("Opened project folder", false), e => Backend.toast(e.error || "Cannot open folder", true))
                    }
                    IconButton {
                        size: 28
                        glyph: 14
                        symbol: "sparkle"
                        tip: "Critique & Redesign HUD"
                        tint: Theme.accentSoft
                        iconColor: Theme.accent
                        onClicked: Api.post("/api/games/critique_hud", {})
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.stroke }

                Txt {
                    Layout.fillWidth: true
                    text: (today.info.game && today.info.game.summary)
                          ? today.info.game.summary
                          : "Design mechanics, balance loops, review HUDs, and expand the GDD."
                    color: Theme.text
                    wrapMode: Text.Wrap
                    lineHeight: 1.3
                }

                Flow {
                    width: parent.width
                    Layout.fillWidth: true
                    Layout.preferredHeight: childrenRect.height
                    spacing: 6
                    Chip {
                        text: "Critique & Redesign HUD"
                        symbol: "sparkle"
                        active: true
                        onClicked: Api.post("/api/games/critique_hud", {})
                    }
                    Chip {
                        text: "Brainstorm Loop"
                        symbol: "sparkle"
                        onClicked: Api.post("/api/ask", { text: "Brainstorm 3 new core loop twists or progression mechanics for " + (today.info.game ? today.info.game.name : "our game") })
                    }
                    Chip {
                        text: "Balance Math"
                        symbol: "pulse"
                        onClicked: Api.post("/api/ask", { text: "Help me calculate the balance curve, failure state timings, and difficulty scaling for " + (today.info.game ? today.info.game.name : "our game") })
                    }
                    Chip {
                        text: "Draft GDD Section"
                        symbol: "edit"
                        onClicked: Api.post("/api/ask", { text: "Draft a new detailed GDD section for " + (today.info.game ? today.info.game.name : "our game") + " detailing controls and failure states." })
                    }
                }
            }
        }

        // Lead Hunter Hub (visible when in lead_hunter mode or when leads exist)
        Card {
            Layout.fillWidth: true
            visible: !!(today.info && (today.info.mode === "lead_hunter" || (today.info.leads && today.info.leads.length > 0)))
            ColumnLayout {
                width: parent.width
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Icon { name: "radar"; size: 20; color: Theme.accent }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Txt {
                            text: "Lead Hunter Radar"
                            font.pixelSize: Theme.px(16)
                            weight: 600
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                        Txt {
                            kind: "small"
                            color: Theme.text3
                            text: "Lowest client traction businesses · Prime outreach"
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }
                    }
                    IconButton {
                        size: 28
                        glyph: 14
                        symbol: "send"
                        tip: "Push leads to paired phone"
                        tint: Theme.accentSoft
                        iconColor: Theme.accent
                        onClicked: Api.post("/api/leads/push", {}, () => Backend.toast("Leads pushed to phone", false))
                    }
                    IconButton {
                        size: 28
                        glyph: 14
                        symbol: "refresh"
                        tip: "Scan lowest traction leads"
                        tint: Theme.accentSoft
                        iconColor: Theme.accent
                        onClicked: Api.post("/api/leads/scan", { niche: "dental clinic" }, today.load)
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: Theme.stroke }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Field {
                        id: searchField
                        Layout.fillWidth: true
                        placeholderText: "Type keyword (e.g. gym, dentist, auto repair, plumber)..."
                        onAccepted: {
                            if (text.trim().length > 0) {
                                Api.post("/api/leads/scan", { niche: text.trim() }, today.load)
                            }
                        }
                    }
                    IconButton {
                        size: 44
                        glyph: 18
                        symbol: "search"
                        tip: "Search businesses"
                        tint: Theme.accentSoft
                        iconColor: Theme.accent
                        onClicked: {
                            if (searchField.text.trim().length > 0) {
                                Api.post("/api/leads/scan", { niche: searchField.text.trim() }, today.load)
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Repeater {
                        model: today.info.leads || []
                        delegate: Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: 70
                            radius: 12
                            color: Theme.panel
                            border.width: 1
                            border.color: Theme.stroke
                            clip: true

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 12
                                anchors.topMargin: 8
                                anchors.bottomMargin: 8
                                spacing: 10

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: 0
                                    Layout.alignment: Qt.AlignVCenter
                                    spacing: 3

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 6
                                        Txt {
                                            text: modelData.name
                                            weight: 600
                                            elide: Text.ElideRight
                                            Layout.fillWidth: true
                                            Layout.preferredWidth: 0
                                        }
                                        Rectangle {
                                            Layout.alignment: Qt.AlignVCenter
                                            implicitWidth: scoreTxt.implicitWidth + 8
                                            implicitHeight: 18
                                            radius: 9
                                            color: modelData.traction_score <= 30 ? "#33ff334b" : "#33ff9800"
                                            Txt {
                                                id: scoreTxt
                                                anchors.centerIn: parent
                                                text: modelData.traction_score + "/100"
                                                kind: "small"
                                                font.pixelSize: Theme.px(10)
                                                color: modelData.traction_score <= 30 ? Theme.accent : "#ff9800"
                                                weight: 600
                                            }
                                        }
                                        Txt {
                                            visible: !!modelData.copyright_year
                                            kind: "small"
                                            font.pixelSize: Theme.px(10)
                                            color: Theme.text3
                                            text: "© " + modelData.copyright_year
                                        }
                                    }

                                    Txt {
                                        kind: "small"
                                        color: Theme.text3
                                        text: (modelData.issues || []).join(" · ") || "Low client traction"
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                        Layout.preferredWidth: 0
                                    }
                                }

                                RowLayout {
                                    Layout.alignment: Qt.AlignVCenter | Qt.AlignRight
                                    spacing: 6

                                    IconButton {
                                        symbol: "pin"
                                        size: 32
                                        glyph: 15
                                        tip: "Open in Google Maps"
                                        tint: Theme.accentSoft
                                        iconColor: Theme.accent
                                        onClicked: {
                                            var gmaps = modelData.maps_url || ("https://www.google.com/maps/search/?api=1&query=" + encodeURIComponent(modelData.name + " " + (modelData.location || "Bucharest")))
                                            Qt.openUrlExternally(gmaps)
                                        }
                                    }

                                    IconButton {
                                        visible: modelData.url && modelData.url !== "No Website"
                                        symbol: "external"
                                        size: 32
                                        glyph: 14
                                        tip: "Open Website: " + (modelData.url || "")
                                        onClicked: {
                                            var full = (modelData.url || "").indexOf("http") === 0 ? modelData.url : ("https://" + modelData.url)
                                            Qt.openUrlExternally(full)
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        // what's playing
        Card {

            Layout.fillWidth: true
            visible: !!today.media.title
            RowLayout {  // (art, words and controls on one line, centred on the art)
                width: parent.width
                spacing: 12
                Item {
                    Layout.preferredWidth: 56; Layout.preferredHeight: 56
                    Rectangle {
                        anchors.fill: parent; radius: 12; visible: art.status !== Image.Ready
                        border.width: 1; border.color: Theme.stroke
                        gradient: Gradient {
                            GradientStop { position: 0; color: Theme.accentSoft }
                            GradientStop { position: 1; color: "#0e1822" }
                        }
                        Icon { anchors.centerIn: parent; name: "music"; size: 22; color: Theme.accent }
                    }
                    Image {
                        id: art
                        anchors.fill: parent
                        source: today.media.art || ""
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                        sourceSize: Qt.size(112, 112)
                        layer.enabled: status === Image.Ready
                        layer.effect: MultiEffect { maskEnabled: true; maskSource: artMask; maskThresholdMin: 0.5; maskSpreadAtMin: 1 }
                    }
                    Rectangle { id: artMask; anchors.fill: parent; radius: 12; visible: false; layer.enabled: true }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        Txt { kind: "label"; text: "Now playing"; wrapMode: Text.NoWrap }
                        Txt { kind: "label"; color: Theme.text3; text: "· " + (today.media.app || ""); visible: !!today.media.app
                              Layout.fillWidth: true; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                    }
                    Txt { text: today.media.title || ""; weight: 600; Layout.fillWidth: true; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                    Txt { kind: "small"; text: today.media.artist || today.media.app || ""; Layout.fillWidth: true; elide: Text.ElideRight
                          wrapMode: Text.NoWrap }
                }
                Row {
                    Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                    IconButton { anchors.verticalCenter: parent.verticalCenter; size: 28; glyph: 14; symbol: "prev"; tip: "Previous"
                                 onClicked: Api.post("/api/media/Previous", {}, today.live) }
                    IconButton { symbol: today.media.status === "Playing" ? "pause" : "play"; tint: Theme.accentSoft; iconColor: Theme.accent; size: 36; glyph: 16
                                 onClicked: Api.post("/api/media/PlayPause", {}, today.live) }
                    IconButton { anchors.verticalCenter: parent.verticalCenter; size: 28; glyph: 14; symbol: "next"; tip: "Next"
                                 onClicked: Api.post("/api/media/Next", {}, today.live) }
                }
            }
        }

        // what's next
        Card {
            Layout.fillWidth: true
            padding: 0
            ColumnLayout {
                width: parent.width
                spacing: 0
                Txt { kind: "label"; text: "Up next"; Layout.leftMargin: Theme.pad; Layout.topMargin: 16; Layout.bottomMargin: 4 }
                Txt { kind: "small"; color: Theme.text3; text: "Nothing scheduled. Try “remind me in 20 minutes to stretch”."
                      visible: !(today.info.reminders || []).length; Layout.fillWidth: true; Layout.margins: Theme.pad; Layout.topMargin: 4 }
                Repeater {
                    model: today.info.reminders || []
                    Item {
                        id: row
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        Layout.preferredHeight: 56
                        HoverHandler { id: over }
                        Rectangle { visible: row.index > 0; x: Theme.pad; width: parent.width - 2 * Theme.pad; height: 1; color: Theme.stroke }
                        Rectangle {
                            id: well
                            x: Theme.pad; anchors.verticalCenter: parent.verticalCenter
                            width: 36; height: 36; radius: 18
                            color: Theme.accentSoft
                            Icon { anchors.centerIn: parent; name: "bell"; size: 18; color: Theme.accent }
                        }
                        Column {
                            anchors { left: well.right; leftMargin: 12; right: cancel.left; rightMargin: 4; verticalCenter: parent.verticalCenter }
                            spacing: 1
                            Txt { text: row.modelData.text; width: parent.width; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                            Txt { kind: "small"; text: String(row.modelData.when).replace(/^./, ch => ch.toUpperCase()); width: parent.width; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                        }
                        IconButton {
                            id: cancel
                            anchors { right: parent.right; rightMargin: 12; verticalCenter: parent.verticalCenter }
                            opacity: over.hovered ? 1 : 0
                            Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                            size: 28; glyph: 14; symbol: "close"; tip: "Cancel this reminder"
                            onClicked: Api.post(`/api/reminders/${row.modelData.id}/cancel`, {}, today.load)
                        }
                    }
                }
                Item { Layout.preferredHeight: 6 }
            }
        }


        // persistent goals
        Card {
            Layout.fillWidth: true
            visible: !!(today.info && today.info.goals && today.info.goals.length > 0)
            ColumnLayout {
                width: parent.width
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Icon { name: "target"; size: 18; color: Theme.accent }
                    Txt { kind: "label"; text: "Persistent Goals"; Layout.fillWidth: true }
                    Txt {
                        kind: "small"
                        color: Theme.text3
                        text: (today.info.goals ? today.info.goals.length : 0) + " active"
                    }
                    IconButton {
                        size: 28
                        glyph: 14
                        symbol: "refresh"
                        tip: "Check goal progress"
                        onClicked: {
                            Api.post("/api/goals/nudge", {}, today.load)
                        }
                    }
                }

                Repeater {
                    model: today.info.goals || []
                    delegate: Rectangle {
                        id: goalCard
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: col.implicitHeight + 16
                        radius: 12
                        color: Theme.panel
                        border.width: 1
                        border.color: Theme.stroke

                        ColumnLayout {
                            id: col
                            anchors { fill: parent; margins: 10 }
                            spacing: 6

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Txt {
                                    text: goalCard.modelData.title
                                    weight: 600
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Txt {
                                    kind: "small"
                                    color: Theme.accent
                                    font.weight: 600
                                    text: Math.round((goalCard.modelData.progress || 0) * 100) + "%"
                                }
                            }

                            // Progress bar
                            Rectangle {
                                Layout.fillWidth: true
                                height: 5
                                radius: 2.5
                                color: Theme.track
                                Rectangle {
                                    width: parent.width * Math.min(1, Math.max(0.04, goalCard.modelData.progress || 0))
                                    height: parent.height
                                    radius: 2.5
                                    color: (goalCard.modelData.progress >= 1.0) ? Theme.accentSoft : Theme.accent
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                Txt {
                                    kind: "small"
                                    color: Theme.text3
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                    text: {
                                        var steps = goalCard.modelData.steps || [];
                                        var nextStep = steps.find(s => s.status === "pending" || s.status === "in_progress");
                                        return nextStep ? "Next: " + nextStep.title : "All milestones complete!";
                                    }
                                }
                                Txt {
                                    kind: "small"
                                    color: Theme.text3
                                    visible: !!goalCard.modelData.target_date
                                    text: "Due: " + (goalCard.modelData.target_date || "")
                                }
                            }
                        }
                    }
                }
            }
        }

        // job radar
        Card {
            Layout.fillWidth: true
            ColumnLayout {
                width: parent.width
                spacing: 12

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Icon { name: "radar"; size: 18; color: Theme.accent }
                    Txt { kind: "label"; text: "Job Radar"; Layout.fillWidth: true }
                    Txt {
                        kind: "small"
                        color: Theme.text3
                        text: (today.info.jobs && today.info.jobs.time) ? "Updated " + today.info.jobs.time : "Daily radar"
                    }
                    IconButton {
                        size: 28
                        glyph: 14
                        symbol: "refresh"
                        tip: "Scan for jobs now"
                        onClicked: {
                            Api.post("/api/checks/run", {}, () => {
                                today.load()
                            })
                        }
                    }
                }

                Txt {
                    Layout.fillWidth: true
                    text: (today.info.jobs && today.info.jobs.text) ? today.info.jobs.text : "No recent findings yet. Click Scan to search Bucharest game dev & Minecraft freelance listings."
                    color: (today.info.jobs && today.info.jobs.text) ? Theme.text : Theme.text3
                    wrapMode: Text.Wrap
                    lineHeight: 1.3
                }

                Flow {
                    width: parent.width
                    Layout.fillWidth: true
                    Layout.preferredHeight: childrenRect.height
                    spacing: 6
                    Chip {
                        text: "Glassdoor Bucharest"
                        symbol: "external"
                        onClicked: Qt.openUrlExternally("https://www.glassdoor.com/Job/bucharest-game-developer-jobs-SRCH_IL.0,9_IC3278546_KO10,24.htm")
                    }
                    Chip {
                        text: "SpigotMC Hiring"
                        symbol: "external"
                        onClicked: Qt.openUrlExternally("https://www.spigotmc.org/forums/hiring-developers.55/")
                    }
                    Chip {
                        text: "LinkedIn Game Dev"
                        symbol: "external"
                        onClicked: Qt.openUrlExternally("https://www.linkedin.com/jobs/search/?keywords=game%20developer%20bucharest")
                    }
                    Chip {
                        text: "Audit Faceless Niches"
                        symbol: "sparkle"
                        onClicked: Api.post("/api/ask", { text: "I'm planning to start a faceless Instagram page. Research the web and give me the best options for the niche based on RPM, retention, saturation, and monetization." })
                    }
                }
            }
        }

        // the PC
        Card {

            Layout.fillWidth: true
            visible: today.stats.mem_total !== undefined
            ColumnLayout {
                width: parent.width
                spacing: 14
                Txt { kind: "label"; text: "This PC" }
                Meter { label: "Processor"; value: (today.stats.cpu || 0) / 100; detail: Math.round(today.stats.cpu || 0) + "%" }
                Meter {
                    label: today.stats.gpu_name ? today.stats.gpu_name : "Graphics"
                    value: (today.stats.gpu_vram_used || 0) / Math.max(1, today.stats.gpu_vram_total || 1)
                    detail: (today.stats.gpu_vram_used ? (today.stats.gpu_vram_used / 1024).toFixed(1) : "0.0") + " of " + ((today.stats.gpu_vram_total || 0) / 1024).toFixed(0) + " GB VRAM"
                    visible: !!today.stats.gpu_name
                }
                Meter { label: "Memory"; value: (today.stats.mem_used || 0) / Math.max(1, today.stats.mem_total || 1)
                        detail: today.gb(today.stats.mem_used || 0) + " of " + today.gb(today.stats.mem_total || 0) + " GB" }
                Meter { label: "Disk"; value: (today.stats.disk_used || 0) / Math.max(1, today.stats.disk_total || 1)
                        detail: Math.round((today.stats.disk_total - today.stats.disk_used) / 1073741824) + " GB free" }
            }
        }

        // how fast Jarvis answered
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 8; Layout.rightMargin: 8
            spacing: 8
            visible: today.latency >= 0
            Icon { name: "bolt"; size: 14; Layout.preferredWidth: 14; Layout.preferredHeight: 14; color: Theme.text3 }
            Txt { kind: "small"; color: Theme.text3; Layout.fillWidth: true; font.features: { "tnum": 1 }
                  text: "Last answer started " + today.latency.toFixed(1) + " s after you finished" }
        }
        Item { Layout.preferredHeight: 12 }
    }

    component Meter: ColumnLayout {
        property string label
        property string detail
        property real value
        Layout.fillWidth: true
        spacing: 7
        RowLayout {
            Layout.fillWidth: true
            Txt { text: label; font.pixelSize: Theme.px(13); Layout.fillWidth: true }
            Txt { kind: "small"; text: detail; font.features: { "tnum": 1 } }
        }
        Rectangle {
            Layout.fillWidth: true
            height: 5; radius: 2.5
            color: Theme.track
            border.width: 1
            border.color: Theme.stroke
            Rectangle {
                width: parent.width * Math.min(1, Math.max(0.02, value)); height: parent.height; radius: 2.5
                color: value > 0.8 ? Theme.warm : Theme.accent
                Behavior on width { NumberAnimation { duration: 400; easing.type: Easing.OutCubic } }
            }
        }
    }
}
