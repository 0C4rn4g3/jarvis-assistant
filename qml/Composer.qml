import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Jarvis

// The message box: Enter sends, Shift+Enter starts a new line; attach files, talk, or stop Jarvis.
Glass {
    id: c
    property var attachments: []
    property bool stopShown: false  // (Stop is already on screen elsewhere)
    signal submitted(string text)
    signal attach()
    signal removed(string path)
    readonly property bool busy: Backend.state !== "idle"
    readonly property bool typed: input.text.trim() !== "" || attachments.length > 0
    floating: true
    implicitHeight: Math.max(54, col.implicitHeight + 14)
    radius: 24
    border.color: input.activeFocus ? Theme.alpha(Theme.accent, 0.45) : Theme.strokeStrong
    Behavior on border.color { ColorAnimation { duration: Theme.fast } }

    ColumnLayout {
        id: col
        anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 8; rightMargin: 8 }
        spacing: 8
        Flow {  // attached files
            Layout.fillWidth: true
            Layout.leftMargin: 8
            Layout.topMargin: 4
            visible: c.attachments.length > 0
            spacing: 6
            Repeater {
                model: c.attachments
                Rectangle {
                    required property string modelData
                    height: 30; radius: 15
                    width: name.implicitWidth + 64
                    color: Theme.glass
                    border.width: 1
                    border.color: Theme.stroke
                    Icon { x: 11; anchors.verticalCenter: parent.verticalCenter; name: "attach"; size: 14; color: Theme.text2 }
                    Txt { id: name; x: 31; anchors.verticalCenter: parent.verticalCenter; kind: "small"; color: Theme.text
                          text: modelData.split("/").pop(); wrapMode: Text.NoWrap }
                    IconButton { anchors.right: parent.right; anchors.rightMargin: 3; anchors.verticalCenter: parent.verticalCenter
                                 size: 24; glyph: 12; symbol: "close"; tip: "Remove"; onClicked: c.removed(modelData) }
                }
            }
        }
        RowLayout {
            spacing: 6
            IconButton { size: 40; symbol: "attach"; tip: "Attach files (or drop them here)"; onClicked: c.attach() }
            ScrollView {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(Math.max(40, input.implicitHeight), 5 * 22 + 18)
                TextArea {
                    id: input
                    placeholderText: "Ask Jarvis"
                    placeholderTextColor: Theme.text3
                    color: Theme.text
                    font.family: Theme.font
                    font.pixelSize: Theme.px(15)
                    wrapMode: TextEdit.Wrap
                    selectionColor: Theme.alpha(Theme.accent, 0.4)
                    selectedTextColor: Theme.text
                    verticalAlignment: TextEdit.AlignVCenter
                    leftPadding: 4
                    background: null
                    focus: true
                    Keys.onReturnPressed: event => {
                        if (event.modifiers & Qt.ShiftModifier) { event.accepted = false; return }
                        c.submitted(text)
                        text = ""
                    }
                }
            }
            IconButton {
                size: 40
                symbol: Backend.listening ? "pause" : "mic"
                tip: Backend.listening ? "Pause listening" : "Talk to Jarvis"
                tint: Backend.listening ? Theme.listen : Theme.glass
                iconColor: Backend.listening ? Theme.accentInk : hovered ? Theme.text : Theme.text2
                Rectangle {  // the voice level
                    z: -1
                    anchors.centerIn: parent
                    width: parent.width; height: width; radius: width / 2
                    visible: Backend.listening
                    color: "transparent"
                    border.width: 2
                    border.color: Theme.alpha(Theme.listen, 0.45)
                    scale: 1 + Math.min(1, Backend.level) * 0.3
                    Behavior on scale { NumberAnimation { duration: 90 } }
                }
                onClicked: Backend.listening ? Backend.pause() : Backend.talk()
            }
            IconButton {
                readonly property bool stopping: c.busy && !c.typed && !c.stopShown
                visible: c.typed || stopping
                size: 40
                symbol: stopping ? "stop" : "send"
                tint: stopping ? Theme.warmSoft : Theme.accent
                iconColor: stopping ? Theme.warm : Theme.accentInk
                tip: stopping ? "Stop (Esc)" : "Send (Enter)"
                Rectangle { anchors.fill: parent; radius: width / 2; visible: parent.stopping; color: "transparent"
                            border.width: 1; border.color: Theme.alpha(Theme.warm, 0.4) }
                onClicked: { if (stopping) Backend.stop(); else { c.submitted(input.text); input.text = "" } }
            }
        }
    }
}
