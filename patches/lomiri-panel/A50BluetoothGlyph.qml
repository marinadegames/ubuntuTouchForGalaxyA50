import QtQuick 2.15
Canvas {
    id: glyph
    property color ink: "white"
    onInkChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        ctx.scale(width / 24, height / 24)
        ctx.strokeStyle = ink
        ctx.lineWidth = 2.1
        ctx.lineCap = "round"
        ctx.lineJoin = "round"
        ctx.beginPath()
        ctx.moveTo(7, 7); ctx.lineTo(17, 17); ctx.lineTo(12, 22)
        ctx.lineTo(12, 2); ctx.lineTo(17, 7); ctx.lineTo(7, 17)
        ctx.stroke()
    }
}
