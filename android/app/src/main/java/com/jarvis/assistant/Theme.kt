package com.jarvis.assistant

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp

/** The "Glass" tokens shared with the desktop window (qml/Theme.qml). */
object J {
    val bg = Color(0xFF0C0D10)
    val bgTop = Color(0xFF121318)
    val bgBottom = Color(0xFF08080A)
    val glass = Color(0x0AFFFFFF)
    val glassHover = Color(0x14FFFFFF)
    val glassStrong = Color(0xD914151A)
    val sheet = Color(0xFF14151A)
    val stroke = Color(0x14FFFFFF)
    val strokeStrong = Color(0x26FFFFFF)
    val highlight = Color(0xA6FF334B)
    val text = Color(0xFFFBFCFD)
    val text2 = Color(0xFFA1A1AA)
    val text3 = Color(0xFF63636E)
    val accent = Color(0xFFFF334B)
    val accentSoft = Color(0x26FF334B)
    val accentInk = Color(0xFFFFFFFF)
    val listen = Color(0xFFFF5E72)
    val warm = Color(0xFFFF9D3F)
    val warmSoft = Color(0x24FF9D3F)
    val green = Color(0xFF34D399)
    val red = Color(0xFFFF334B)

    private val inter = FontFamily(
        Font(R.font.inter_regular, FontWeight.Normal),
        Font(R.font.inter_medium, FontWeight.Medium),
        Font(R.font.inter_semibold, FontWeight.SemiBold),
    )
    private val interDisplay = FontFamily(Font(R.font.inter_display, FontWeight.SemiBold))

    val display = TextStyle(fontFamily = interDisplay, fontWeight = FontWeight.SemiBold, fontSize = 36.sp, lineHeight = 42.sp, letterSpacing = (-0.8).sp, color = text)
    val title = TextStyle(fontFamily = interDisplay, fontWeight = FontWeight.SemiBold, fontSize = 28.sp, lineHeight = 34.sp, letterSpacing = (-0.5).sp, color = text)
    val heading = TextStyle(fontFamily = inter, fontWeight = FontWeight.SemiBold, fontSize = 17.sp, lineHeight = 22.sp, letterSpacing = (-0.2).sp, color = text)
    val body = TextStyle(fontFamily = inter, fontSize = 14.5.sp, lineHeight = 1.45.em, color = text)
    val chat = body.copy(fontSize = 15.sp)
    val small = TextStyle(fontFamily = inter, fontSize = 13.sp, lineHeight = 18.sp, color = text2)
    val label = TextStyle(fontFamily = inter, fontWeight = FontWeight.SemiBold, fontSize = 12.sp, lineHeight = 16.sp, letterSpacing = 0.3.sp, color = text2)
    val button = TextStyle(fontFamily = inter, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, lineHeight = 18.sp, color = text)
}

/** Line icons on a 24 grid, drawn in whatever tint the Icon gets. */
object Ico {
    private fun line(vararg paths: String, width: Float = 1.7f) = ImageVector.Builder(defaultWidth = 24.dp, defaultHeight = 24.dp, viewportWidth = 24f, viewportHeight = 24f).apply {
        paths.forEach {
            addPath(addPathNodes(it), fill = null, stroke = SolidColor(Color.White), strokeLineWidth = width,
                strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round, pathFillType = PathFillType.NonZero)
        }
    }.build()

    val mic = line("M12 3.5a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0v-5a3 3 0 0 0-3-3z", "M18.5 11.5a6.5 6.5 0 0 1-13 0", "M12 18v2.5")
    val send = line("M12 19V5.5", "M6.5 11L12 5.5 17.5 11", width = 2f)
    val more = line("M6 12h.01", "M12 12h.01", "M18 12h.01", width = 2.6f)
    val scan = line("M4 8.5V6a2 2 0 0 1 2-2h2.5", "M15.5 4H18a2 2 0 0 1 2 2v2.5", "M20 15.5V18a2 2 0 0 1-2 2h-2.5", "M8.5 20H6a2 2 0 0 1-2-2v-2.5", "M8 12h8")
    val link = line("M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1", "M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1")
    val calendar = line("M6 5.5h12a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7.5a2 2 0 0 1 2-2z", "M4 10h16", "M8.5 3.5v3.5", "M15.5 3.5v3.5")
    val screen = line("M5 4.5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z", "M9 20h6", "M12 16.5V20")
    val mute = line("M11 5.5L7 9H4.5v6H7l4 3.5v-13z", "M16 9.5l5 5", "M21 9.5l-5 5")
    val mail = line("M5 5.5h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2z", "M3.5 7.5L12 13l8.5-5.5")
    val power = line("M12 3.5v8", "M7 6.5a7.5 7.5 0 1 0 10 0")
    val cloudOff = line("M3 3l18 18", "M8.5 7.2A5.5 5.5 0 0 1 17 10.5h.5a3.5 3.5 0 0 1 2.4 6", "M17 19.5H7.5a4.5 4.5 0 0 1-1.6-8.7")
    val check = line("M5 12.5l4.5 4.5L19 7.5", width = 2f)
    val close = line("M6.5 6.5l11 11", "M17.5 6.5l-11 11", width = 2f)
    val phone = line("M8 3h8a1.5 1.5 0 0 1 1.5 1.5v15A1.5 1.5 0 0 1 16 21H8a1.5 1.5 0 0 1-1.5-1.5v-15A1.5 1.5 0 0 1 8 3z", "M11 18h2")
    val play = line("M5 3l14 9-14 9V3z")
    val pause = line("M6 4h4v16H6z", "M14 4h4v16h-4z")
    val music = line("M9 18V5l12-2v13", "M6 18a3 3 0 1 0 6 0 3 3 0 0 0-6 0z", "M18 16a3 3 0 1 0 6 0 3 3 0 0 0-6 0z")
    val cpu = line("M4 4h16v16H4z", "M9 9h6v6H9z", "M9 1v3", "M15 1v3", "M9 20v3", "M15 20v3", "M20 9h3", "M20 15h3", "M1 9h3", "M1 15h3")
    val camera = line("M21 19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h3.5l1.5-2h6l1.5 2H19a2 2 0 0 1 2 2v11z", "M12 17a4 4 0 1 0 0-8 4 4 0 0 0 0 8z")
    val sparkle = line("M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z")
    val radar = line("M12 2a10 10 0 1 0 10 10", "M12 12l7-7", "M12 6a6 6 0 1 0 6 6", "M12 10a2 2 0 1 0 2 2")
    val external = line("M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6", "M15 3h6v6", "M10 14L21 3")
    val pin = line("M12 2a7 7 0 0 0-7 7c0 5.25 7 13 7 13s7-7.75 7-13a7 7 0 0 0-7-7z", "M12 6a3 3 0 1 0 0 6 3 3 0 0 0 0-6z")
}
