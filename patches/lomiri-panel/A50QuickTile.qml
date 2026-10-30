import QtQuick 2.15
import Lomiri.Components 1.3
Rectangle {
    id: tile
    property string title
    property string subtitle
    property string iconName
    property string fontFamily: "Inter"
    property bool selected: false
    property bool available: true
    property bool prominent: false
    property color accentColor: "#e95420"
    signal triggered()
    signal settingsRequested()
    height: units.gu(9.2)
    radius: units.gu(2)
    color: selected ? accentColor : "#aa332831"
    opacity: available ? 1 : 0.46
    Behavior on color { ColorAnimation { duration: 130 } }
    scale: touch.pressed ? 0.98 : 1
    Behavior on scale { NumberAnimation { duration: 100 } }
    readonly property color ink: "white"
    Accessible.role: Accessible.Button
    Accessible.name: title + ", " + subtitle
    Accessible.onPressAction: if (available) triggered()
    Item {
        x: units.gu(1.8); anchors.verticalCenter: parent.verticalCenter
        width: units.gu(2.6); height: units.gu(2.8)
        Icon {
            anchors.centerIn: parent; width: parent.width; height: width
            name: tile.iconName; color: tile.ink
            visible: tile.iconName !== "bluetooth-active"
        }
        A50BluetoothGlyph {
            anchors.fill: parent; ink: tile.ink
            visible: tile.iconName === "bluetooth-active"
        }
    }
    Column {
        x: units.gu(6.2); anchors.verticalCenter: parent.verticalCenter
        width: parent.width - x - units.gu(1.8)
        spacing: units.gu(0.55)
        Text {
            width: parent.width; text: tile.title
            wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight
            font.family: tile.fontFamily; font.pixelSize: units.gu(1.65); font.weight: tile.selected ? Font.Bold : Font.DemiBold
            color: tile.ink
        }
        Text {
            width: parent.width; text: tile.subtitle; elide: Text.ElideRight
            font.family: tile.fontFamily; font.pixelSize: units.gu(1.25); font.weight: tile.selected ? Font.DemiBold : Font.Medium
            color: tile.selected ? "white" : "#dcc8d6"
        }
    }
    MouseArea {
        id: touch; anchors.fill: parent; enabled: tile.available
        onClicked: tile.triggered()
        onPressAndHold: tile.settingsRequested()
    }
}
