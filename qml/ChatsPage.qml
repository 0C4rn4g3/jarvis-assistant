import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import Jarvis

// Past conversations: search them, read one, pick it up where it left off, or delete it.
Item {
    id: page
    signal opened()
    signal deleted(string id)
    property var items: []
    property string current: ""
    property string selected: ""
    property var preview: null
    property bool confirming: false

    function load() {
        const q = search.text.trim()
        Api.get(q ? "/api/search?q=" + encodeURIComponent(q) : "/api/sessions", d => {
            items = q ? d : d.sessions
            if (!q) current = d.current
            if (items.length && !items.some(s => s.id === selected)) pick(items[0].id)
            if (!items.length) { selected = ""; preview = null }
        })
    }
    function pick(id) {
        selected = id
        confirming = false
        Api.get("/api/sessions/" + id, s => preview = s)
    }
    function ago(t) {
        const s = Date.now() / 1000 - t
        return s < 60 ? "just now" : s < 3600 ? Math.round(s / 60) + " min ago" : s < 86400 ? Math.round(s / 3600) + " h ago"
             : Qt.formatDate(new Date(t * 1000), "d MMM")
    }
    function plain(t) {  // a leading emoji in a notice clashes with the line icons
        return String(t || "").replace(/^(?:[\u2300-\u27bf\u2b00-\u2bff]|[\ud83c-\ud83e][\udc00-\udfff])\ufe0f?\s*/, "")
    }
    onVisibleChanged: if (visible) load()
    Component.onCompleted: load()
    Timer { id: debounce; interval: 250; onTriggered: page.load() }

    ColumnLayout {
        anchors { top: parent.top; bottom: parent.bottom; horizontalCenter: parent.horizontalCenter; margins: Theme.margin }
        width: Math.min(parent.width - 2 * Theme.margin, Theme.pageWidth)
        spacing: 24

        PageHeader {
            Layout.fillWidth: true
            title: "Chats"
            hint: "Every conversation is saved here. Open one to carry on where you left off."
            Pill { text: "New chat"; symbol: "plus"; kind: "primary"; onClicked: Api.post("/api/new", {}, () => page.opened()) }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.gap

            Card {  // the list
                Layout.preferredWidth: Math.round(Math.min(320, Math.max(280, parent.width * 0.34)))
                Layout.fillHeight: true
                padding: 8
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8
                    Field {
                        id: search
                        Layout.fillWidth: true
                        Layout.topMargin: 12  // its bottom lines up with the divider under the preview's header
                        placeholderText: "Search conversations"
                        leftPadding: 40
                        onTextChanged: debounce.restart()
                        Icon { name: "search"; size: 16; color: search.activeFocus ? Theme.accent : Theme.text3; x: 14; anchors.verticalCenter: parent.verticalCenter }
                    }
                    ListView {
                        id: list
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: page.items
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: Scroller {}
                        delegate: AbstractButton {
                            id: row
                            required property var modelData
                            required property int index
                            readonly property bool chosen: page.selected === modelData.id
                            readonly property bool nextChosen: index + 1 < page.items.length && page.items[index + 1].id === page.selected
                            width: ListView.view.width
                            height: 58
                            hoverEnabled: true
                            onClicked: page.pick(modelData.id)
                            background: Item {
                                Rectangle {
                                    anchors.fill: parent
                                    radius: Theme.radiusControl
                                    color: row.chosen ? Theme.accentSoft : row.hovered ? Theme.glassHover : "transparent"
                                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                                }
                                Rectangle {
                                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: 12; rightMargin: 12 }
                                    height: 1
                                    color: Theme.stroke
                                    visible: row.index < page.items.length - 1 && !row.chosen && !row.nextChosen && !row.hovered
                                }
                            }
                            contentItem: Item { ColumnLayout {
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width
                                spacing: 3
                                RowLayout {
                                    Layout.leftMargin: 12; Layout.rightMargin: 12
                                    spacing: 8
                                    Txt { text: row.modelData.title; weight: 500
                                          elide: Text.ElideRight; wrapMode: Text.NoWrap; Layout.fillWidth: true }
                                    Rectangle { visible: row.modelData.id === page.current; Layout.leftMargin: 4; width: 6; height: 6; radius: 3; color: Theme.accent }
                                    Txt { Layout.leftMargin: 4; kind: "small"; font.pixelSize: Theme.px(12); color: row.chosen ? Theme.text2 : Theme.text3
                                          text: row.modelData.id === page.current ? "Now" : page.ago(row.modelData.updated); wrapMode: Text.NoWrap }
                                }
                                Txt {
                                    Layout.leftMargin: 12; Layout.rightMargin: 12; Layout.fillWidth: true
                                    kind: "small"; elide: Text.ElideRight; wrapMode: Text.NoWrap
                                    text: row.modelData.match ? row.modelData.match : row.modelData.count + (row.modelData.count === 1 ? " message" : " messages")
                                }
                            } }
                        }
                        ColumnLayout {
                            anchors.centerIn: parent
                            width: parent.width - 32
                            visible: !page.items.length
                            spacing: 10
                            Icon { Layout.alignment: Qt.AlignHCenter; name: search.text ? "search" : "chats"; size: 22; color: Theme.text3 }
                            Txt { Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; kind: "small"
                                  text: search.text ? "Nothing matches that" : "No conversations yet" }
                        }
                    }
                }
            }

            Card {  // the conversation picked
                Layout.fillWidth: true
                Layout.fillHeight: true
                padding: 0
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0
                    visible: page.preview !== null
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 64
                        Layout.leftMargin: Theme.pad
                        Layout.rightMargin: 14
                        spacing: 8
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            Txt { kind: "heading"; text: page.preview ? page.preview.title : ""; Layout.fillWidth: true; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                            Txt { kind: "small"; text: page.preview ? Qt.formatDateTime(new Date(page.preview.updated * 1000), "dddd d MMMM · HH:mm") : ""
                                  Layout.fillWidth: true; elide: Text.ElideRight; wrapMode: Text.NoWrap }
                        }
                        IconButton {
                            visible: !page.confirming
                            symbol: "trash"; tip: "Delete"
                            iconColor: hovered ? Theme.red : color
                            onClicked: { page.confirming = true; undo.restart() }
                        }
                        Pill {
                            visible: page.confirming
                            text: "Click again to delete"
                            kind: "danger"
                            symbol: "trash"
                            onClicked: Api.post(`/api/sessions/${page.selected}/delete`, {}, () => {
                                const delId = page.selected;
                                Backend.toast("Conversation deleted", false);
                                page.load();
                                page.deleted(delId);
                            })
                            Timer { id: undo; interval: 4000; onTriggered: page.confirming = false }
                        }
                        Pill { text: "Open"; kind: "primary"; symbol: "arrow-right"; visible: page.selected !== page.current
                               onClicked: Api.post(`/api/sessions/${page.selected}/open`, {}, () => page.opened()) }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.stroke }
                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        ListView {
                            id: talk
                            anchors.fill: parent
                            clip: true
                            topMargin: 8
                            bottomMargin: 28
                            boundsBehavior: Flickable.StopAtBounds
                            ScrollBar.vertical: Scroller {}
                            model: page.preview ? page.preview.messages.filter(m => ["you", "jarvis", "tool", "system", "image"].includes(m.who)) : []
                            property bool follow: true
                            onModelChanged: follow = true
                            onContentHeightChanged: if (follow) Qt.callLater(toEnd)  // opens on the latest turn, like a chat
                            function toEnd() { contentY = Math.max(originY - topMargin, originY + contentHeight + bottomMargin - height) }
                            onMovementStarted: follow = false
                            // messages fade out at the card's edges instead of being cut off (the software renderer has no shaders)
                            layer.enabled: GraphicsInfo.api !== GraphicsInfo.Software
                            layer.effect: MultiEffect { maskEnabled: true; maskSource: fade; maskThresholdMin: 0.01; maskSpreadAtMin: 1 }
                            delegate: Message {
                                required property var modelData
                                width: ListView.view.width
                                who: modelData.who; caption: String(modelData.caption || ""); time: modelData.time || 0
                                text: modelData.who === "system" ? page.plain(modelData.text) : String(modelData.text || "")
                            }
                        }
                        Rectangle {
                            id: fade
                            anchors.fill: parent
                            visible: false
                            layer.enabled: true
                            gradient: Gradient {
                                GradientStop { position: 0; color: "transparent" }
                                GradientStop { position: 12 / Math.max(1, fade.height); color: "white" }
                                GradientStop { position: 1 - 40 / Math.max(1, fade.height); color: "white" }
                                GradientStop { position: 1; color: "transparent" }
                            }
                        }
                    }
                }
                ColumnLayout {
                    anchors.centerIn: parent
                    visible: page.preview === null
                    spacing: 12
                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        width: 40; height: 40; radius: 20
                        color: Theme.accentSoft
                        Icon { anchors.centerIn: parent; name: "chats"; size: 20; color: Theme.accent }
                    }
                    Txt { Layout.alignment: Qt.AlignHCenter; kind: "small"; text: "Pick a conversation to read it" }
                }
            }
        }
    }
}
