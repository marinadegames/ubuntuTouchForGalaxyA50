import QtQuick 2.15
import Lomiri.Components 1.3

Item {
    id: slider
    property string title
    property string iconName
    property string fontFamily: "Inter"
    property real value: 0
    property real minimum: 0
    property bool available: true
    property real dragValue: value
    readonly property real shownValue: Math.max(0, Math.min(1, touch.pressed ? dragValue : value))
    readonly property bool interacting: touch.pressed
    signal userChanged(real value)
    height: units.gu(7.9)
    opacity: available ? 1 : 0.5
    Accessible.role: Accessible.Slider
    Accessible.name: title + ", " + Math.round(shownValue * 100) + "%"
    Text {
        x: units.gu(0.8); y: units.gu(0.25)
        text: slider.title; color: "#dcc8d6"
        font.family: slider.fontFamily; font.pixelSize: units.gu(1.4); font.weight: Font.Medium
    }
    Text {
        anchors.right: parent.right; anchors.rightMargin: units.gu(0.8)
        y: units.gu(0.25); text: Math.round(slider.shownValue * 100) + "%"
        font.family: slider.fontFamily; font.pixelSize: units.gu(1.4); color: "#dcc8d6"
    }
    Rectangle {
        id: track
        y: units.gu(2.65); width: parent.width; height: units.gu(4.5)
        readonly property real handlePosition: height / 2 + slider.shownValue * (width - height)
        radius: height / 2; color: "#9944313f"
        Rectangle {
            width: track.handlePosition + track.height / 2
            height: parent.height; radius: height / 2; color: "#f4a183"
        }
        Rectangle {
            x: track.handlePosition - width / 2
            anchors.verticalCenter: parent.verticalCenter
            width: units.gu(0.32); height: units.gu(2.5); radius: width / 2
            color: "#4b1b24"
        }
        Icon {
            x: units.gu(1.2); anchors.verticalCenter: parent.verticalCenter
            width: units.gu(2.1); height: width; name: slider.iconName
            color: "#4b1b24"
        }
    }
    MouseArea {
        id: touch
        anchors.fill: parent; enabled: slider.available
        preventStealing: true
        propagateComposedEvents: false
        function moveTo(x) {
            slider.dragValue = Math.max(slider.minimum, Math.min(1, (x - track.height / 2) / Math.max(1, track.width - track.height)))
        }
        onPressed: { moveTo(mouse.x); slider.userChanged(slider.dragValue) }
        onPositionChanged: if (pressed) moveTo(mouse.x)
        onReleased: slider.userChanged(slider.dragValue)
        onCanceled: slider.dragValue = slider.value
    }
    Timer { interval: 80; repeat: true; running: touch.pressed; onTriggered: slider.userChanged(slider.dragValue) }
}
