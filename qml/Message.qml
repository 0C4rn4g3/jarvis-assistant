import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import Jarvis

// One line of the conversation: your words on the right, Jarvis's on the left, tools and notices quietly in between.
Item {
    id: m
    required property string who
    required property string text
    required property string caption
    required property real time
    readonly property bool mine: who === "you"
    property real column: Math.min(width - 80, 760)
    property real rise: 0  // (the list animates new messages in with it)
    readonly property int gap: who === "you" ? 20 : who === "jarvis" ? 10 : who === "system" ? 14 : who === "thinking" ? 4 : (who === "activity" || who === "tool") ? 6 : 8
    implicitHeight: body.implicitHeight + gap
    transform: Translate { y: m.rise }

    function linkify(t) {  // plain text with links made clickable, for Markdown
        return t.replace(/(^|\s)(https?:\/\/[^\s<>()]+)/g, "$1<$2>")
    }

    HoverHandler { id: hover }
    Loader {
        id: body
        x: (m.width - m.column) / 2
        y: m.gap
        width: m.column
        sourceComponent: m.who === "you" ? you : m.who === "jarvis" ? jarvis : m.who === "image" ? picture : (m.who === "tool" || m.who === "activity") ? activity
                       : m.who === "system" ? note : thinking
    }

    Component {
        id: you
        Item {
            implicitHeight: bubble.height
            IconButton {
                anchors.right: bubble.left
                anchors.rightMargin: 8
                anchors.verticalCenter: bubble.verticalCenter
                opacity: hover.hovered ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                size: 28; glyph: 14; symbol: "copy"; tip: "Copy"
                onClicked: Backend.copy(m.text)
            }
            Rectangle {
                id: bubble
                anchors.right: parent.right
                width: Math.min(words.implicitWidth, parent.width * 0.7 - 32) + 32
                height: words.implicitHeight + 22
                radius: Theme.radius
                bottomRightRadius: 6
                color: Theme.accentSoft
                border.width: 1
                border.color: Theme.alpha(Theme.accent, 0.25)
                Txt { id: words; x: 16; anchors.verticalCenter: parent.verticalCenter; width: parent.width - 32
                      text: m.text; textFormat: Text.PlainText; font.pixelSize: Theme.px(15); lineHeight: 1.1 }
            }
        }
    }
    Component {
        id: jarvis
        Item {
            implicitHeight: Math.max(24, said.implicitHeight)
            Orb { width: 24; height: 24; y: 1; rings: false; mode: "idle" }
            Txt {
                id: said
                x: 36
                width: parent.width - 36
                text: m.linkify(m.text)
                textFormat: Text.MarkdownText
                font.pixelSize: Theme.px(15)
                lineHeight: 1.3
            }
            IconButton {
                x: parent.width + 8
                opacity: hover.hovered ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                size: 28; glyph: 14; symbol: "copy"; tip: "Copy"
                onClicked: Backend.copy(m.text)
            }
        }
    }
    Component {
        id: activity
        Item {
            id: actItem
            property bool expanded: false
            readonly property var stepList: {
                var raw = (typeof model !== "undefined" && model && model.steps) ? model.steps : ""
                return raw ? raw.split("\n") : []
            }
            readonly property bool isWorking: m.caption === "working"
            implicitHeight: actCol.implicitHeight

            Column {
                id: actCol
                x: 36
                spacing: 8
                width: Math.min(m.column - 36, 560)

                AbstractButton {
                    id: pillBtn
                    hoverEnabled: true
                    focusPolicy: Qt.NoFocus
                    implicitHeight: 32
                    implicitWidth: pillRow.implicitWidth + 24
                    background: Rectangle {
                        radius: 16
                        color: pillBtn.hovered ? Theme.glassHover : Theme.glass
                        border.width: 1
                        border.color: pillBtn.hovered ? Theme.strokeStrong : Theme.stroke
                        Behavior on color { ColorAnimation { duration: Theme.fast } }
                        Behavior on border.color { ColorAnimation { duration: Theme.fast } }
                    }
                    contentItem: Item {
                        Row {
                            id: pillRow
                            anchors.centerIn: parent
                            spacing: 8
                            StatusDot {
                                status: actItem.isWorking ? "working" : "ok"
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: m.text ? m.text : Backend.toolLabel(m.text)
                                font.family: Theme.font
                                font.pixelSize: Theme.px(13)
                                font.weight: 500
                                color: pillBtn.hovered ? Theme.text : Theme.text2
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Icon {
                                visible: actItem.stepList.length > 0
                                name: actItem.expanded ? "chevron" : "chevron-right"
                                size: 14
                                color: Theme.text3
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }
                    onClicked: if (actItem.stepList.length > 0) actItem.expanded = !actItem.expanded
                }

                Column {
                    id: stepsCol
                    visible: actItem.expanded && actItem.stepList.length > 0
                    spacing: 6
                    leftPadding: 12
                    topPadding: 2
                    bottomPadding: 4

                    Repeater {
                        model: actItem.stepList
                        Row {
                            spacing: 10
                            Rectangle {
                                width: 5
                                height: 5
                                radius: 2.5
                                color: Theme.accent
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                text: modelData
                                font.family: Theme.font
                                font.pixelSize: Theme.px(12.5)
                                color: Theme.text2
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }
                    }
                }
            }
        }
    }
    Component {
        id: note
        Item {
            implicitHeight: words.implicitHeight + 12
            Rectangle {
                anchors.centerIn: parent
                width: Math.min(words.implicitWidth, parent.width - 28) + 28
                height: parent.height
                radius: height / 2
                color: Theme.alpha(Theme.glass, 0.7)
                border.width: 1
                border.color: Theme.alpha(Theme.stroke, 0.7)
                Txt {
                    id: words
                    anchors.centerIn: parent
                    width: Math.min(implicitWidth, parent.parent.width - 28)
                    kind: "small"
                    color: Theme.text2
                    horizontalAlignment: Text.AlignHCenter
                    // (without the emoji background notices start with: they clash with the line icons)
                    text: m.linkify(m.text.replace(/^(?:[\u2300-\u27bf\u2b00-\u2bff]|[\ud83c-\ud83e][\udc00-\udfff])\ufe0f?\s*/, ""))
                    textFormat: Text.MarkdownText
                }
            }
        }
    }
    Component {
        id: thinking
        Txt { leftPadding: 36; kind: "small"; color: Theme.text3; font.italic: true; text: m.linkify(m.text); textFormat: Text.MarkdownText }
    }
    Component {
        id: picture
        Column {
            leftPadding: 36
            topPadding: 4
            spacing: 8
            Item {
                width: Math.min(img.implicitWidth, 420); height: width * (img.implicitHeight / Math.max(1, img.implicitWidth))
                Image {
                    id: img
                    anchors.fill: parent
                    source: "file://" + m.text
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    sourceSize.width: 840
                    layer.enabled: true
                    layer.effect: MultiEffect { maskEnabled: true; maskSource: mask; maskThresholdMin: 0.5; maskSpreadAtMin: 1 }
                }
                Rectangle { id: mask; anchors.fill: parent; radius: 16; visible: false; layer.enabled: true }
                Rectangle { anchors.fill: parent; radius: 16; color: "transparent"; border.width: 1; border.color: Theme.stroke }
                TapHandler { onTapped: Backend.open(m.text) }
                HoverHandler { cursorShape: Qt.PointingHandCursor }
            }
            Txt { kind: "small"; text: m.caption; visible: m.caption !== ""; width: 420 }
        }
    }
}
