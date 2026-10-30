import QtQuick 2.15
import Lomiri.Components 1.3
import QMenuModel 1.0

Rectangle {
    id: bar
    objectName: "a50PixelStatusBar"
    color: "transparent"
    property Item backdropSource: null
    property real sampleY: height + units.dp(2)
    property real shadeOpacity: 0
    property date now: new Date()
    readonly property color ink: "white"
    readonly property string fontFamily: typeface.status === FontLoader.Ready ? typeface.name : "DejaVu Sans"
    readonly property real edgeInset: Math.min(width * 0.09, units.gu(4.2))
    readonly property string batteryLabel: power.header && power.header.valid && power.header.state ? (power.header.state.label || "") : ""
    readonly property int batteryPercent: batteryLabel.match(/\d+/) ? Math.max(0, Math.min(100, parseInt(batteryLabel.match(/\d+/)[0]))) : 0
    readonly property bool charging: power.deviceState && power.deviceState.valid && power.deviceState.state === "charging"
    readonly property string cellularIcon: network.sim2 && network.sim2.valid && network.sim2.state !== "no-simcard" ? network.sim2.state : (network.sim1 && network.sim1.valid ? network.sim1.state : "no-simcard")
    readonly property bool hasSim: cellularIcon !== "no-simcard"
    readonly property int signalBars: !hasSim ? 0 : /full|100/.test(cellularIcon) ? 4 : /high|75/.test(cellularIcon) ? 3 : /medium|50/.test(cellularIcon) ? 2 : /low|25/.test(cellularIcon) ? 1 : 0
    readonly property bool airplane: enabledState(network.airplane)
    readonly property bool wifiConnected: network.networkStatus && network.networkStatus.valid && network.networkStatus.state && network.networkStatus.state.icon && /nm-signal|wifi-/.test(String(network.networkStatus.state.icon[1][0]))
    readonly property string dataTechnology: network.sim2 && network.sim2.valid && network.sim2.state !== "no-simcard" ? (network.data2 && network.data2.valid ? String(network.data2.state) : "") : (network.data1 && network.data1.valid ? String(network.data1.state) : "")
    function enabledState(action) { return !!action && action.valid && !!action.state }
    FontLoader { source: Qt.resolvedUrl("fonts/Inter-Medium.ttf") }
    FontLoader { source: Qt.resolvedUrl("fonts/Inter-SemiBold.ttf") }
    FontLoader { source: Qt.resolvedUrl("fonts/Inter-Bold.ttf") }
    FontLoader { id: typeface; source: Qt.resolvedUrl("fonts/Inter-Regular.ttf") }
    Timer { interval: 1000; repeat: true; running: bar.visible; onTriggered: bar.now = new Date() }
    QDBusActionGroup {
        id: network; busType: DBus.SessionBus
        busName: "com.lomiri.indicator.network"; objectPath: "/com/lomiri/indicator/network"
        property var wifi: action("wifi.enable")
        property var airplane: action("airplane.enabled")
        property var sim1: action("modem.1::status-icon")
        property var sim2: action("modem.2::status-icon")
        property var networkStatus: action("phone.network-status")
        property var mobileData: action("mobiledata.enabled")
        property var data1: action("modem.1::connectivity-icon")
        property var data2: action("modem.2::connectivity-icon")
        Component.onCompleted: start()
    }
    QDBusActionGroup {
        id: power; busType: DBus.SessionBus
        busName: "org.ayatana.indicator.power"; objectPath: "/org/ayatana/indicator/power"
        property var header: action("_header")
        property var deviceState: action("device-state")
        Component.onCompleted: start()
    }
    QDBusActionGroup {
        id: bluetooth; busType: DBus.SessionBus
        busName: "org.ayatana.indicator.bluetooth"; objectPath: "/org/ayatana/indicator/bluetooth"
        property var power: action("bluetooth-enabled")
        Component.onCompleted: start()
    }
    QDBusActionGroup {
        id: sound; busType: DBus.SessionBus
        busName: "org.ayatana.indicator.sound"; objectPath: "/org/ayatana/indicator/sound"
        property var silent: action("silent-mode")
        Component.onCompleted: start()
    }
    Item {
        id: glyphs
        anchors.fill: parent
    Text {
        x: bar.edgeInset; anchors.verticalCenter: parent.verticalCenter
        text: Qt.formatTime(bar.now, "hh:mm")
        font.family: bar.fontFamily; font.pixelSize: units.gu(1.95); font.weight: Font.Medium
        color: bar.ink
        Accessible.name: "Время " + text
    }
    Row {
        id: indicators
        anchors.right: parent.right; anchors.rightMargin: bar.edgeInset
        anchors.verticalCenter: parent.verticalCenter
        height: units.gu(1.9); spacing: units.gu(0.65)
        transformOrigin: Item.Right
        scale: Math.min(1, Math.max(1, bar.width / 2 - units.gu(5) - bar.edgeInset) / Math.max(1, width))
        Icon {
            anchors.verticalCenter: parent.verticalCenter
            width: visible ? units.gu(1.45) : 0; height: units.gu(1.45)
            name: "audio-volume-muted"; color: bar.ink
            visible: bar.enabledState(sound.silent)
        }
        A50BluetoothGlyph {
            anchors.verticalCenter: parent.verticalCenter
            width: visible ? units.gu(1.35) : 0; height: units.gu(1.55)
            ink: bar.ink
            visible: bar.enabledState(bluetooth.power)
        }
        Icon {
            anchors.verticalCenter: parent.verticalCenter
            width: visible ? units.gu(1.65) : 0; height: units.gu(1.65)
            name: "network-wifi-symbolic"; color: bar.ink
            visible: bar.wifiConnected
        }
        Icon {
            anchors.verticalCenter: parent.verticalCenter
            width: visible ? units.gu(1.65) : 0; height: units.gu(1.65)
            name: "airplane-mode"; color: bar.ink; visible: bar.airplane
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            visible: !bar.airplane && bar.hasSim && !bar.wifiConnected && bar.enabledState(network.mobileData)
            text: /lte/.test(bar.dataTechnology) ? "4G" : /hspa/.test(bar.dataTechnology) ? "H+" : /umts/.test(bar.dataTechnology) ? "3G" : /edge/.test(bar.dataTechnology) ? "E" : ""
            font.family: bar.fontFamily; font.pixelSize: units.gu(1.1); font.weight: Font.Medium
            color: bar.ink
        }
        Item {
            width: visible ? units.gu(1.8) : 0; height: units.gu(1.7)
            anchors.verticalCenter: parent.verticalCenter; visible: !bar.airplane
            Accessible.name: bar.hasSim ? "Уровень сотового сигнала " + bar.signalBars + " из 4" : "Нет SIM-карты"
            Row {
                anchors.bottom: parent.bottom; spacing: units.gu(0.17)
                Repeater {
                    model: 4
                    Rectangle {
                        width: units.gu(0.3); height: units.gu(0.45 + index * 0.38)
                        anchors.bottom: parent.bottom
                        radius: units.dp(0.6)
                        color: index < bar.signalBars ? bar.ink : "#51594c"
                    }
                }
            }
            Rectangle {
                visible: !bar.hasSim
                x: units.gu(0.1); y: units.gu(0.75)
                width: units.gu(1.75); height: units.dp(1.5); rotation: -45; color: bar.ink
            }
        }
        Item {
            width: units.gu(1.25); height: units.gu(1.9)
            Rectangle {
                width: units.gu(0.55); height: units.dp(1.8)
                anchors.horizontalCenter: parent.horizontalCenter; color: bar.ink; radius: units.dp(0.6)
            }
            Rectangle {
                id: battery
                anchors { left: parent.left; right: parent.right; top: parent.top; topMargin: units.dp(2.4); bottom: parent.bottom }
                border.width: units.dp(1.1); border.color: bar.ink; radius: units.dp(1.7); color: "transparent"
                Rectangle {
                    x: units.dp(2.3); width: parent.width - units.dp(4.6)
                    anchors.bottom: parent.bottom; anchors.bottomMargin: units.dp(2.3)
                    height: Math.max(0, (parent.height - units.dp(4.6)) * bar.batteryPercent / 100)
                    color: bar.batteryPercent <= 15 ? "#ffb4ab" : bar.ink
                }
                Text {
                    anchors.centerIn: parent; text: "ϟ"; visible: bar.charging
                    font.pixelSize: units.gu(1.7); font.bold: true
                    color: bar.batteryPercent > 45 ? "#10140f" : bar.ink
                }
            }
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: bar.batteryLabel || "—"
            font.family: bar.fontFamily; font.pixelSize: units.gu(1.6); font.weight: Font.Medium
            color: bar.ink
            Accessible.name: "Аккумулятор " + text
        }
    }
    }

    // Extend the first row of the actual app/home scene into the reserved bar.
    // The scene source excludes the panel itself, avoiding a feedback loop.
    ShaderEffectSource {
        id: backdropTexture
        anchors.fill: parent
        sourceItem: bar.backdropSource
        sourceRect: {
            if (!bar.backdropSource) return Qt.rect(0, 0, bar.width, units.dp(2))
            var origin = bar.mapToItem(bar.backdropSource, 0, bar.sampleY)
            var x = Math.max(0, origin.x)
            var y = Math.max(0, Math.min(origin.y, bar.backdropSource.height - units.dp(2)))
            return Qt.rect(x, y, Math.max(1, Math.min(bar.width, bar.backdropSource.width - x)), units.dp(2))
        }
        textureSize: Qt.size(256, 2)
        live: true; smooth: true
        visible: false
    }
    ShaderEffect {
        anchors.fill: parent
        visible: bar.backdropSource !== null
        property var backgroundTexture: backdropTexture
        property real shadeAmount: bar.shadeOpacity
        fragmentShader: "
            varying highp vec2 qt_TexCoord0;
            uniform sampler2D backgroundTexture;
            uniform highp float shadeAmount;
            uniform lowp float qt_Opacity;
            void main() {
                lowp vec4 bg = texture2D(backgroundTexture, vec2(qt_TexCoord0.x, 0.5));
                lowp vec3 tinted = mix(bg.rgb, vec3(0.137, 0.067, 0.114), shadeAmount);
                gl_FragColor = vec4(tinted, bg.a) * qt_Opacity;
            }"
    }
    Rectangle {
        anchors.fill: parent
        color: "#33000000"
        visible: bar.backdropSource === null
    }
    ShaderEffectSource {
        id: glyphTexture
        sourceItem: glyphs
        hideSource: true
        live: true
        visible: false
    }
    ShaderEffect {
        anchors.fill: parent
        property var foregroundTexture: glyphTexture
        property var backgroundTexture: backdropTexture
        property real hasBackground: bar.backdropSource !== null ? 1 : 0
        property real shadeAmount: bar.shadeOpacity
        fragmentShader: "
            varying highp vec2 qt_TexCoord0;
            uniform sampler2D foregroundTexture;
            uniform sampler2D backgroundTexture;
            uniform lowp float qt_Opacity;
            uniform highp float hasBackground;
            uniform highp float shadeAmount;
            void main() {
                lowp vec4 glyph = texture2D(foregroundTexture, qt_TexCoord0);
                lowp vec3 bg = texture2D(backgroundTexture, vec2(qt_TexCoord0.x, 0.5)).rgb;
                bg = mix(bg, vec3(0.137, 0.067, 0.114), shadeAmount);
                lowp float luminance = dot(bg, vec3(0.2126, 0.7152, 0.0722));
                lowp vec3 ink = luminance > 0.58 && hasBackground > 0.5 ? vec3(0.06) : vec3(1.0);
                lowp float mask = max(glyph.r, max(glyph.g, glyph.b));
                gl_FragColor = vec4(ink * mask, mask) * qt_Opacity;
            }"
    }

}
