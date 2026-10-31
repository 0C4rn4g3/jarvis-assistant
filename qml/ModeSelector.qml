import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Jarvis

// Pill button in the top bar to switch between Default Assistant and Videogame Designer mode,
// and dynamically switch or create game development projects.
Item {
    id: root
    property string currentMode: "default"
    property var activeGame: ({})
    property var projects: []

    signal modeChanged(string mode)
    signal projectChanged(string slug)

    implicitHeight: 32
    implicitWidth: pill.implicitWidth

    function refresh() {
        Api.get("/api/modes", d => {
            if (!d) return
            root.currentMode = d.mode || "default"
            root.projects = d.projects || []
            let act = (d.projects || []).find(p => p.id === d.active_project)
            root.activeGame = act || (d.projects && d.projects[0]) || {}
        })
    }

    Component.onCompleted: refresh()

    Connections {
        target: Backend
        function onEvent(json) {
            let evt = JSON.parse(json)
            if (evt.kind === "mode" || evt.kind === "game_project") refresh()
        }
    }

    AbstractButton {
        id: pill
        anchors.fill: parent
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        implicitWidth: row.implicitWidth + 24
        onClicked: pop.visible ? pop.close() : pop.open()

        background: Rectangle {
            radius: 16
            color: root.currentMode === "game_designer" ? Theme.accentSoft : pill.hovered ? Theme.glassHover : Theme.glass
            border.width: 1
            border.color: root.currentMode === "game_designer" ? Theme.alpha(Theme.accent, 0.4) : Theme.stroke
            Behavior on color { ColorAnimation { duration: Theme.fast } }
        }

        contentItem: RowLayout {
            id: row
            anchors.centerIn: parent
            spacing: 7
            Icon {
                name: root.currentMode === "game_designer" ? "gamepad" : "sparkle"
                size: 15
                color: root.currentMode === "game_designer" ? Theme.accent : Theme.text2
            }
            Text {
                text: root.currentMode === "game_designer"
                      ? (root.activeGame.name ? root.activeGame.name : "Game Designer")
                      : "Assistant"
                font.family: Theme.font
                font.pixelSize: Theme.px(12)
                font.weight: 600
                color: root.currentMode === "game_designer" ? Theme.text : Theme.text2
                elide: Text.ElideRight
                Layout.maximumWidth: 160
            }
            Icon {
                name: "chevron"
                size: 12
                color: Theme.text3
                rotation: pop.visible ? 180 : 0
                Behavior on rotation { NumberAnimation { duration: Theme.fast } }
            }
        }
    }

    Popup {
        id: pop
        y: pill.height + 6
        x: Math.min(0, root.width - width)
        width: 290
        padding: 8
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: Glass {
            floating: true
            color: Theme.popover
            radius: Theme.radiusControl
            border.color: Theme.strokeStrong
        }

        contentItem: ColumnLayout {
            spacing: 6
            width: parent.width

            // Mode Section
            Txt { kind: "label"; text: "JARVIS MODE"; Layout.leftMargin: 6; Layout.topMargin: 2 }

            RowLayout {
                Layout.fillWidth: true
                spacing: 4

                AbstractButton {
                    id: btnAssistant
                    Layout.fillWidth: true
                    implicitHeight: 34
                    hoverEnabled: true
                    onClicked: {
                        Api.post("/api/modes/switch", { mode: "default" }, () => {
                            root.refresh()
                            pop.close()
                        })
                    }
                    background: Rectangle {
                        radius: 8
                        color: root.currentMode === "default" ? Theme.accentSoft : btnAssistant.hovered ? Theme.glassHover : "transparent"
                    }
                    contentItem: RowLayout {
                        anchors.centerIn: parent
                        spacing: 6
                        Icon { name: "sparkle"; size: 14; color: root.currentMode === "default" ? Theme.accent : Theme.text3 }
                        Text { text: "Assistant"; font.family: Theme.font; font.pixelSize: Theme.px(12); font.weight: 500
                               color: root.currentMode === "default" ? Theme.text : Theme.text2 }
                    }
                }

                AbstractButton {
                    id: btnDesigner
                    Layout.fillWidth: true
                    implicitHeight: 34
                    hoverEnabled: true
                    onClicked: {
                        Api.post("/api/modes/switch", { mode: "game_designer" }, () => {
                            root.refresh()
                            pop.close()
                        })
                    }
                    background: Rectangle {
                        radius: 8
                        color: root.currentMode === "game_designer" ? Theme.accentSoft : btnDesigner.hovered ? Theme.glassHover : "transparent"
                    }
                    contentItem: RowLayout {
                        anchors.centerIn: parent
                        spacing: 6
                        Icon { name: "gamepad"; size: 14; color: root.currentMode === "game_designer" ? Theme.accent : Theme.text3 }
                        Text { text: "Game Designer"; font.family: Theme.font; font.pixelSize: Theme.px(12); font.weight: 500
                               color: root.currentMode === "game_designer" ? Theme.text : Theme.text2 }
                    }
                }

            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.stroke; Layout.topMargin: 4; Layout.bottomMargin: 4 }

            // Projects Section (always visible or highlighted in Game Designer mode)
            RowLayout {
                Layout.fillWidth: true
                Layout.leftMargin: 6
                Txt { kind: "label"; text: "GAME PROJECTS"; Layout.fillWidth: true }
                Txt { kind: "small"; color: Theme.text3; text: root.projects.length + " loaded"; Layout.rightMargin: 6 }
            }

            Repeater {
                model: root.projects
                Item {
                    id: projItem
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    Layout.preferredHeight: 38

                    AbstractButton {
                        id: btnProj
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            Api.post("/api/games/select", { slug: projItem.modelData.id }, () => {
                                if (root.currentMode !== "game_designer") {
                                    Api.post("/api/modes/switch", { mode: "game_designer" }, root.refresh)
                                } else {
                                    root.refresh()
                                }
                                pop.close()
                            })
                        }
                        background: Rectangle {
                            radius: 8
                            color: projItem.modelData.active && root.currentMode === "game_designer"
                                   ? Theme.alpha(Theme.accent, 0.18)
                                   : btnProj.hovered ? Theme.glassHover : "transparent"
                        }
                        contentItem: RowLayout {
                            anchors { fill: parent; leftMargin: 8; rightMargin: 8 }
                            spacing: 8
                            Icon {
                                name: "gamepad"
                                size: 15
                                color: projItem.modelData.active && root.currentMode === "game_designer" ? Theme.accent : Theme.text3
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Text {
                                    text: projItem.modelData.name || projItem.modelData.id
                                    font.family: Theme.font
                                    font.pixelSize: Theme.px(12)
                                    font.weight: projItem.modelData.active ? 600 : 500
                                    color: projItem.modelData.active && root.currentMode === "game_designer" ? Theme.accent : Theme.text
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                                Text {
                                    text: (projItem.modelData.engine || "Game") + (projItem.modelData.genre ? " · " + projItem.modelData.genre : "")
                                    font.family: Theme.font
                                    font.pixelSize: Theme.px(10)
                                    color: Theme.text3
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }
                            Icon {
                                name: "check"
                                size: 14
                                color: Theme.accent
                                visible: projItem.modelData.active && root.currentMode === "game_designer"
                            }
                        }
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.stroke; Layout.topMargin: 2; Layout.bottomMargin: 2 }

            // Add Project Button
            AbstractButton {
                id: btnNewProj
                Layout.fillWidth: true
                implicitHeight: 32
                hoverEnabled: true
                onClicked: {
                    pop.close()
                    newGameDialog.open()
                }
                background: Rectangle {
                    radius: 8
                    color: btnNewProj.hovered ? Theme.glassHover : "transparent"
                }

                contentItem: RowLayout {
                    anchors.centerIn: parent
                    spacing: 6
                    Icon { name: "plus"; size: 13; color: Theme.accent }
                    Text {
                        text: "New Game Project…"
                        font.family: Theme.font
                        font.pixelSize: Theme.px(12)
                        font.weight: 500
                        color: Theme.text
                    }
                }
            }
        }
    }

    // Modal dialog to create a new project
    Popup {
        id: newGameDialog
        anchors.centerIn: Overlay.overlay
        width: 380
        padding: 20
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape
        background: Glass {
            floating: true
            color: Theme.popover
            radius: Theme.radiusWindow
            border.color: Theme.strokeStrong
        }

        contentItem: ColumnLayout {
            spacing: 14
            width: parent.width

            RowLayout {
                Layout.fillWidth: true
                Icon { name: "gamepad"; size: 20; color: Theme.accent }
                Txt { kind: "heading"; text: "New Game Project"; Layout.fillWidth: true }
            }

            Txt {
                kind: "small"
                color: Theme.text3
                text: "Jarvis will scaffold a Game Design Document (GDD) and switch to Game Designer Mode."
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }

            Txt { kind: "label"; text: "Game Name" }
            Field {
                id: nameField
                Layout.fillWidth: true
                placeholderText: "e.g. Neon Drifter"
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Txt { kind: "label"; text: "Engine" }
                    Field {
                        id: engineField
                        Layout.fillWidth: true
                        placeholderText: "Unity, Unreal Engine 5, Godot"
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 4
                    Txt { kind: "label"; text: "Genre" }
                    Field {
                        id: genreField
                        Layout.fillWidth: true
                        placeholderText: "Co-op, MMO, Roguelike"
                    }
                }
            }


            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 8
                spacing: 8
                Item { Layout.fillWidth: true }
                Chip {
                    text: "Cancel"
                    onClicked: newGameDialog.close()
                }
                Chip {
                    text: "Create & Switch"
                    active: true
                    enabled: nameField.text.trim().length > 0
                    onClicked: {
                        let payload = {
                            name: nameField.text.trim(),
                            engine: engineField.text.trim() || "Unity",
                            genre: genreField.text.trim() || "Video Game"
                        }
                        Api.post("/api/games/new", payload, () => {
                            Api.post("/api/modes/switch", { mode: "game_designer" }, () => {
                                root.refresh()
                                newGameDialog.close()
                                nameField.text = ""
                                engineField.text = ""
                                genreField.text = ""
                            })
                        })
                    }
                }
            }
        }
    }
}
