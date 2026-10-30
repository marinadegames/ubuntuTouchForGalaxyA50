import QtQuick 2.15
import Lomiri.Components 1.3
import QMenuModel 1.0
import "Indicators"

Rectangle {
    id: root
    objectName: "a50QuickSettings"
    color: "transparent"
    signal closeRequested()
    property bool showNotifications: false
    property bool expanded: true
    readonly property bool sliderDragging: brightnessSlider.interacting || volumeSlider.interacting
    property date now: new Date()
    readonly property color foreground: "#fff7f2"
    readonly property color secondary: "#dcc8d6"

    readonly property string fontFamily: typeface.status === FontLoader.Ready ? typeface.name : "DejaVu Sans"
    FontLoader { source: Qt.resolvedUrl("fonts/Inter-Medium.ttf") }
    FontLoader { source: Qt.resolvedUrl("fonts/Inter-SemiBold.ttf") }
    FontLoader { source: Qt.resolvedUrl("fonts/Inter-Bold.ttf") }
    FontLoader { id: typeface; source: Qt.resolvedUrl("fonts/Inter-Regular.ttf") }

    function ready(action) { return !!action && action.valid && action.enabled !== false }
    function state(action) { return ready(action) ? !!action.state : false }
    function subtitle(action) { return ready(action) ? (state(action) ? "Включено" : "Выключено") : "Недоступно" }
    // Switches must activate their handlers. Updating the state alone can change
    // the displayed boolean without changing the underlying service setting.
    function toggle(action, booleanParameter) {
        if (!ready(action)) return
        if (booleanParameter) action.activate(!action.state)
        else action.activate()
    }
    function activate(action) { if (ready(action)) { closeRequested(); action.activate() } }
    Timer { interval: 1000; repeat: true; running: root.visible; onTriggered: root.now = new Date() }

    QDBusActionGroup {
        id: network; busType: DBus.SessionBus
        busName: "com.lomiri.indicator.network"; objectPath: "/com/lomiri/indicator/network"
        property var wifi: action("wifi.enable")
        property var carrier1: action("modem.1::status-label")
        property var carrier2: action("modem.2::status-label")
        property var sim1: action("modem.1::status-icon")
        property var sim2: action("modem.2::status-icon")
        readonly property string carrierName: sim2 && sim2.valid && sim2.state !== "no-simcard" && carrier2 && carrier2.valid ? String(carrier2.state) : (carrier1 && carrier1.valid ? String(carrier1.state) : "")
        readonly property bool hasSim: (sim1 && sim1.valid && sim1.state !== "no-simcard") || (sim2 && sim2.valid && sim2.state !== "no-simcard")
        property var data: action("mobiledata.enabled")
        property var airplane: action("airplane.enabled")
        property var wifiSettings: action("wifi.settings")
        property var cellularSettings: action("cellular.settings")
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
        property var volume: action("volume")
        property var settings: action("phone-settings")
        Component.onCompleted: start()
    }
    QDBusActionGroup {
        id: power; busType: DBus.SessionBus
        busName: "org.ayatana.indicator.power"; objectPath: "/org/ayatana/indicator/power"
        property var brightness: action("brightness")
        property var automatic: action("auto-brightness")
        property var torch: action("flashlight")
        property var header: action("_header")
        Component.onCompleted: start()
    }
    QDBusActionGroup {
        id: display; busType: DBus.SessionBus
        busName: "org.ayatana.indicator.display"; objectPath: "/org/ayatana/indicator/display"
        property var rotation: action("rotation-lock")
        Component.onCompleted: start()
    }

    Item {
        id: content
        anchors.fill: parent
        anchors.leftMargin: units.gu(2); anchors.rightMargin: units.gu(2)
        visible: !root.showNotifications
        readonly property bool wide: root.width > root.height
        Column {
            id: controls
            anchors { left: parent.left; right: parent.right; top: parent.top }
            spacing: units.gu(1.1)
            Item {
                width: parent.width; height: content.wide ? 0 : units.gu(5.5)
                visible: !content.wide
                Text {
                    x: units.gu(0.7); y: units.gu(0.45)
                    text: Qt.formatDate(root.now, "ddd, d MMM")
                    font.family: root.fontFamily; font.pixelSize: units.gu(1.65); font.weight: Font.Medium
                    color: root.foreground
                }
                Text {
                    x: units.gu(0.7); y: units.gu(3.0)
                    text: network.hasSim ? network.carrierName : "Нет SIM-карты"
                    font.family: root.fontFamily; font.pixelSize: units.gu(1.3); color: root.secondary
                }
            }
            A50QuickSlider {
                id: brightnessSlider; objectName: "a50BrightnessSlider"
                width: parent.width; fontFamily: root.fontFamily
                title: "Яркость"; iconName: "display-brightness-max"
                minimum: 0.04; available: root.ready(power.brightness)
                value: available ? Number(power.brightness.state) : 0.3
                onUserChanged: if (available) power.brightness.updateState(Math.max(0.04, value))
            }
            Grid {
                width: parent.width; columns: content.wide ? 4 : 2; spacing: units.gu(1.2)
                readonly property real tileWidth: (width - (columns - 1) * spacing) / columns
                readonly property real tileHeight: content.wide ? units.gu(7) : units.gu(9.2)
                A50QuickTile {
                    width: parent.tileWidth; height: parent.tileHeight; fontFamily: root.fontFamily
                    title: "Wi-Fi"; iconName: "network-wifi-symbolic"
                    selected: root.state(network.wifi); available: root.ready(network.wifi)
                    subtitle: root.subtitle(network.wifi)
                    onTriggered: root.toggle(network.wifi)
                    onSettingsRequested: root.activate(network.wifiSettings)
                }
                A50QuickTile {
                    width: parent.tileWidth; height: parent.tileHeight; fontFamily: root.fontFamily
                    title: "Bluetooth"; iconName: "bluetooth-active"
                    selected: root.state(bluetooth.power); available: root.ready(bluetooth.power)
                    subtitle: root.subtitle(bluetooth.power)
                    onTriggered: root.toggle(bluetooth.power, true)
                    onSettingsRequested: { root.closeRequested(); Qt.openUrlExternally("settings:///bluetooth") }
                }
                A50QuickTile {
                    width: parent.tileWidth; height: parent.tileHeight; fontFamily: root.fontFamily
                    title: "Интернет"; iconName: "phone-symbolic"
                    selected: root.state(network.data); available: root.ready(network.data) && network.hasSim && !root.state(network.airplane)
                    subtitle: network.hasSim ? root.subtitle(network.data) : "Нет SIM-карты"
                    onTriggered: root.toggle(network.data)
                    onSettingsRequested: root.activate(network.cellularSettings)
                }
                A50QuickTile {
                    width: parent.tileWidth; height: parent.tileHeight; fontFamily: root.fontFamily
                    title: "Авиарежим"; iconName: "airplane-mode"
                    selected: root.state(network.airplane); available: root.ready(network.airplane)
                    subtitle: root.subtitle(network.airplane)
                    onTriggered: root.toggle(network.airplane)
                }
                A50QuickTile {
                    objectName: "a50SilentTile"
                    width: parent.tileWidth; height: parent.tileHeight; fontFamily: root.fontFamily
                    title: "Без звука"; iconName: "audio-volume-muted"
                    selected: root.state(sound.silent); available: root.ready(sound.silent)
                    subtitle: root.subtitle(sound.silent)
                    onTriggered: root.toggle(sound.silent, true)
                    onSettingsRequested: root.activate(sound.settings)
                }
                A50QuickTile {
                    objectName: "a50TorchTile"
                    width: parent.tileWidth; height: parent.tileHeight; fontFamily: root.fontFamily
                    title: "Фонарик"; iconName: root.state(power.torch) ? "torch-on" : "torch-off"
                    selected: root.state(power.torch); available: root.ready(power.torch)
                    subtitle: root.subtitle(power.torch)
                    onTriggered: if (root.ready(power.torch)) power.torch.activate(!power.torch.state)
                }
                A50QuickTile {
                    width: parent.tileWidth; height: parent.tileHeight; fontFamily: root.fontFamily
                    title: "Поворот экрана"; iconName: "orientation-lock-disabled"
                    selected: root.ready(display.rotation) && !root.state(display.rotation); available: root.ready(display.rotation)
                    subtitle: selected ? "Автоматически" : "Заблокирован"
                    onTriggered: root.toggle(display.rotation, true)
                }
                A50QuickTile {
                    width: parent.tileWidth; height: parent.tileHeight; fontFamily: root.fontFamily
                    title: "Автояркость"; iconName: "display-brightness-symbolic"
                    selected: root.state(power.automatic); available: root.ready(power.automatic)
                    subtitle: root.subtitle(power.automatic)
                    onTriggered: root.toggle(power.automatic, true)
                }
            }
            A50QuickSlider {
                id: volumeSlider
                width: parent.width; fontFamily: root.fontFamily
                title: "Громкость"; iconName: "audio-volume-medium"
                available: root.ready(sound.volume)
                value: available ? Number(sound.volume.state) : 0
                onUserChanged: if (available) sound.volume.updateState(value)
            }
            Text {
                x: units.gu(0.7); width: parent.width; height: units.gu(2.4)
                text: "Уведомления"; color: root.secondary
                font.family: root.fontFamily; font.pixelSize: units.gu(1.45)
            }
        }
        Item {
            id: footer
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; bottomMargin: units.gu(0.5) }
            height: units.gu(6)
            Rectangle {
                anchors { right: parent.right; verticalCenter: parent.verticalCenter }
                width: units.gu(5.5); height: width; radius: width / 2; color: "#aa332831"
                Icon { anchors.centerIn: parent; width: units.gu(2.3); height: width; name: "settings"; color: root.foreground }
                Accessible.role: Accessible.Button; Accessible.name: "Настройки"
                MouseArea { anchors.fill: parent; onClicked: { root.closeRequested(); Qt.openUrlExternally("settings:///") } }
            }
        }
        Rectangle {
            id: notificationArea
            anchors.left: parent.left; anchors.right: parent.right
            y: controls.height + units.gu(0.7)
            height: Math.max(0, footer.y - y - units.gu(0.8))
            readonly property bool empty: !notificationLoader.item || notificationLoader.item.menuContentHeight < units.gu(3)
            radius: units.gu(2); color: empty ? "transparent" : "#662c1c29"; clip: true
            Text {
                anchors.centerIn: parent; visible: notificationArea.empty
                text: "Нет уведомлений"; color: root.secondary
                font.family: root.fontFamily; font.pixelSize: units.gu(1.5)
            }
            Loader {
                id: notificationLoader
                anchors.fill: parent; anchors.margins: units.gu(0.4)
                active: !root.showNotifications
                opacity: notificationArea.empty ? 0 : 1
                sourceComponent: PanelMenuPage {
                    submenuIndex: 0
                    menuModel: inlineMessages.menuModel
                    theme.name: "Lomiri.Components.Themes.SuruDark"
                    factory: IndicatorMenuItemFactory {
                        indicator: "ayatana-indicator-messages"
                        rootModel: inlineMessages.menuModel
                    }
                    IndicatorDelegate {
                        id: inlineMessages
                        busName: "org.ayatana.indicator.messages"
                        actionsObjectPath: "/org/ayatana/indicator/messages"
                        menuObjectPath: "/org/ayatana/indicator/messages/phone"
                    }
                }
            }
        }
    }

    Item {
        anchors.fill: parent; visible: root.showNotifications
        Item {
            id: notificationHeader
            width: parent.width; height: units.gu(8)
            Icon { x: units.gu(2.5); anchors.verticalCenter: parent.verticalCenter; width: units.gu(2.5); height: width; name: "back"; color: root.foreground }
            Text { x: units.gu(7); anchors.verticalCenter: parent.verticalCenter; text: "Уведомления"; font.family: root.fontFamily; font.pixelSize: units.gu(2.1); color: root.foreground; font.weight: Font.Medium }
            MouseArea { x: 0; width: units.gu(7); height: parent.height; onClicked: root.showNotifications = false }
        }
        Loader {
            anchors { top: notificationHeader.bottom; bottom: parent.bottom; left: parent.left; right: parent.right }
            active: root.showNotifications
            sourceComponent: PanelMenuPage {
                submenuIndex: 0
                menuModel: notificationIndicator.menuModel
                factory: IndicatorMenuItemFactory {
                    indicator: "ayatana-indicator-messages"
                    rootModel: notificationIndicator.menuModel
                }
                IndicatorDelegate {
                    id: notificationIndicator
                    busName: "org.ayatana.indicator.messages"
                    actionsObjectPath: "/org/ayatana/indicator/messages"
                    menuObjectPath: "/org/ayatana/indicator/messages/phone"
                }
            }
        }
    }
}
