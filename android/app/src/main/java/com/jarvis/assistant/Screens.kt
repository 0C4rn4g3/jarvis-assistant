package com.jarvis.assistant

import android.view.HapticFeedbackConstants
import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.expandVertically
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.scaleIn
import androidx.compose.animation.scaleOut
import androidx.compose.animation.shrinkVertically
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.LocalTextSelectionColors
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.text.selection.TextSelectionColors
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.time.LocalTime

enum class Who { YOU, JARVIS, PHONE, NOTE }

data class Msg(val id: Int, val who: Who, val text: String)

data class LeadItem(
    val name: String = "",
    val url: String = "",
    val score: Int = 0,
    val issues: List<String> = emptyList(),
    val phone: String = "",
    val mapsUrl: String = "",
)

data class TodayInfo(
    val mediaTitle: String = "",
    val mediaArtist: String = "",
    val mediaStatus: String = "",
    val reminders: List<String> = emptyList(),
    val cpu: Int = 0,
    val ramGb: String = "",
    val gaming: Boolean = false,
    val jobText: String = "",
    val jobTime: String = "",
    val leads: List<LeadItem> = emptyList(),
)

/** Everything the screens show: plain values, so they render the same from the app or from fake data. */
data class Ui(
    val paired: Boolean = false,
    val state: State = State.UNPAIRED,
    val note: String = "",  // why pairing failed, or what the relay said
    val pc: String = "",
    val relay: String = "",
    val messages: List<Msg> = emptyList(),
    val working: Boolean = false,
    val key: String = "",
    val version: String = "",
    val today: TodayInfo = TodayInfo(),
)

class Actions(
    val ask: (String) -> Unit = {},
    val listen: () -> Unit = {},
    val stop: () -> Unit = {},
    val scan: () -> Unit = {},
    val pair: (String) -> Unit = {},
    val saveKey: (String) -> Unit = {},
    val unpair: () -> Unit = {},
    val mediaAction: (String) -> Unit = {},
    val refreshToday: () -> Unit = {},
    val scanLeads: (String) -> Unit = {},
    val cameraScan: () -> Unit = {},
    val pickScan: () -> Unit = {},
)

@Composable
fun JarvisApp(ui: Ui, act: Actions, sheetOpen: Boolean = false) {
    var sheet by remember { mutableStateOf(sheetOpen) }
    CompositionLocalProvider(LocalTextSelectionColors provides TextSelectionColors(J.accent, J.accentSoft)) {
        Backdrop(working = ui.working) {
            Crossfade(ui.paired, animationSpec = tween(200), label = "screen") { paired ->
                if (paired) Main(ui, act) { sheet = true } else Onboarding(ui, act)
            }
            Sheet(sheet && ui.paired, { sheet = false }) { Settings(ui, act) { sheet = false } }
        }
    }
}

// ---- onboarding

@Composable
private fun Onboarding(ui: Ui, act: Actions) {
    BoxWithConstraints(Modifier.fillMaxSize().systemBarsPadding().imePadding()) {
        Column(
            Modifier.verticalScroll(rememberScrollState()).heightIn(min = maxHeight).padding(horizontal = 20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Spacer(Modifier.weight(1f).heightIn(min = 16.dp))
            Reactor(220.dp)
            Spacer(Modifier.height(12.dp))
            Text("Jarvis, on your phone", J.title, align = TextAlign.Center)
            Spacer(Modifier.height(10.dp))
            Text("Ask the Jarvis on your PC anything, from anywhere. Private, end to end.", J.body.copy(color = J.text2),
                align = TextAlign.Center, modifier = Modifier.widthIn(max = 300.dp))
            Spacer(Modifier.height(32.dp))
            Card {
                Step(1, md("On your PC, open\n**Settings → The Jarvis app**"))
                Divider()
                Step(2, md("Tap **Pair a phone**"))
                Divider()
                Step(3, md("Scan the code with this phone"))
            }
            Spacer(Modifier.weight(0.8f).heightIn(min = 28.dp))
            if (ui.note.isNotBlank()) {
                Text(ui.note, J.small.copy(color = J.warm), align = TextAlign.Center, modifier = Modifier.padding(bottom = 14.dp))
            }
            PastePair(act) { paste ->
                Primary("Scan pairing code", Ico.scan, Modifier.fillMaxWidth(), height = 48.dp, onClick = act.scan)
                Spacer(Modifier.height(6.dp))
                Ghost("Paste a pairing link", Modifier.fillMaxWidth(), paste)
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}

@Composable
private fun Step(n: Int, text: AnnotatedString) {
    Row(Modifier.fillMaxWidth().padding(vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(28.dp).background(J.accentSoft, CircleShape), contentAlignment = Alignment.Center) {
            Text("$n", J.label.copy(color = J.accent, fontSize = 13.sp))
        }
        Spacer(Modifier.width(14.dp))
        BasicText(text, style = J.body.copy(color = J.text2))
    }
}

/** A pairing link pasted by hand: the field opens under [content]'s buttons, filled from the clipboard when it holds one. */
@Composable
private fun PastePair(act: Actions, content: @Composable ColumnScope.(paste: () -> Unit) -> Unit) {
    val clipboard = LocalClipboardManager.current
    var open by remember { mutableStateOf(false) }
    var link by remember { mutableStateOf("") }
    Column(Modifier.fillMaxWidth()) {
        AnimatedVisibility(open, enter = fadeIn(tween(160)) + expandVertically(tween(200)), exit = fadeOut(tween(140)) + shrinkVertically(tween(200))) {
            Row(Modifier.padding(bottom = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                Field(link, { link = it }, "jarvis://pair#…", Modifier.weight(1f), done = { act.pair(link) })
                Spacer(Modifier.width(10.dp))
                Primary("Pair", null, enabled = link.isNotBlank()) { act.pair(link); open = false }
            }
        }
        content {
            link = clipboard.getText()?.text?.trim()?.takeIf { it.startsWith("jarvis://pair") } ?: link
            open = !open
        }
    }
}

// ---- main

@Composable
private fun Main(ui: Ui, act: Actions, onMenu: () -> Unit) {
    Column(Modifier.fillMaxSize().statusBarsPadding().imePadding()) {
        TopBar(ui, onMenu)
        AnimatedVisibility(ui.state == State.PC_OFFLINE || ui.state == State.NO_RELAY,
            enter = fadeIn() + expandVertically(), exit = fadeOut() + shrinkVertically()) { Banner(ui, onMenu) }
        Box(Modifier.weight(1f).fillMaxWidth()) {
            if (ui.messages.isEmpty() && !ui.working) Empty(ui, act) else Conversation(ui, act.stop)
            Column(Modifier.align(Alignment.BottomCenter).fillMaxWidth()
                .background(Brush.verticalGradient(0f to Color.Transparent, 0.4f to J.bgBottom.copy(alpha = 0.85f), 1f to J.bgBottom))
                .navigationBarsPadding().padding(start = 20.dp, end = 20.dp, top = 20.dp, bottom = 12.dp)) {
                Composer(act)
            }
        }
    }
}

@Composable
private fun TopBar(ui: Ui, onMenu: () -> Unit) {
    // (insets put the mini reactor's ring and the overflow dots on the 20dp gutter)
    Row(Modifier.fillMaxWidth().height(60.dp).padding(start = 18.dp, end = 7.dp), verticalAlignment = Alignment.CenterVertically) {
        val phoneOnly = ui.state != State.ONLINE && ui.key.isNotBlank()
        Reactor(24.dp, working = ui.working, dim = !online(ui), mini = true, modifier = Modifier.graphicsLayer { alpha = if (phoneOnly) 0.5f else 1f })
        Spacer(Modifier.width(12.dp))
        Text("Jarvis", J.heading)
        Spacer(Modifier.weight(1f).widthIn(min = 12.dp))
        StatusChip(ui, Modifier.widthIn(max = 210.dp))
        Spacer(Modifier.width(6.dp))
        Box(Modifier.size(40.dp).clip(CircleShape).press(onClick = onMenu), contentAlignment = Alignment.Center) {
            Icon(Ico.more, J.text2, 22.dp)
        }
    }
}

private fun online(ui: Ui) = ui.state == State.ONLINE || ui.key.isNotBlank()

private fun status(ui: Ui): Pair<Color, String> = when (ui.state) {
    State.ONLINE -> J.green to "Connected · ${ui.pc.ifBlank { "your PC" }}"
    State.CONNECTING -> J.text3 to "Connecting…"
    State.PC_OFFLINE -> if (ui.key.isNotBlank()) J.warm to "Phone only" else J.text3 to "PC offline"
    State.NO_RELAY -> J.red to "Relay unreachable"
    State.UNPAIRED -> J.text3 to "Not paired"
}

@Composable
private fun StatusChip(ui: Ui, modifier: Modifier = Modifier) {
    val (color, label) = status(ui)
    Row(modifier.height(32.dp).glass(CircleShape).padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        Dot(color, glow = ui.state == State.ONLINE)
        Spacer(Modifier.width(8.dp))
        Text(label, J.small, maxLines = 1)
    }
}

@Composable
private fun Dot(color: Color, glow: Boolean = false, pulse: Boolean = false) {
    val a = if (pulse) rememberInfiniteTransition(label = "dot").animateFloat(1f, 0.35f,
        infiniteRepeatable(tween(700, easing = FastOutSlowInEasing), RepeatMode.Reverse), label = "dot").value else 1f
    Box(Modifier.size(8.dp).drawBehind {
        if (glow) drawCircle(Brush.radialGradient(listOf(color.copy(alpha = 0.5f), Color.Transparent), center, size.minDimension * 1.3f), size.minDimension * 1.3f)
        drawCircle(color.copy(alpha = a))
    })
}

@Composable
private fun Banner(ui: Ui, openSettings: () -> Unit) {
    val relay = ui.state == State.NO_RELAY
    val key = ui.key.isNotBlank()
    val tint = if (relay) J.red else J.warm
    Row(Modifier.padding(start = 20.dp, end = 20.dp, bottom = 8.dp).fillMaxWidth().clip(RoundedCornerShape(20.dp))
        .background(tint.copy(alpha = 0.08f)).border(1.dp, tint.copy(alpha = 0.2f), RoundedCornerShape(20.dp))
        .then(if (key) Modifier else Modifier.press(onClick = openSettings)).padding(horizontal = 14.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Icon(if (relay) Ico.cloudOff else Ico.power, tint, 18.dp)
        Spacer(Modifier.width(12.dp))
        val what = if (relay) "Can't reach your relay" + (if (ui.note.isNotBlank()) " (${ui.note})" else "") else "Your PC is off"
        BasicText(buildAnnotatedString {
            withStyle(SpanStyle(color = J.text, fontWeight = FontWeight.Medium)) { append(what) }
            if (key) append(" — Gemini answers on the phone")
            else {
                append(". Nothing can run until it's back. ")
                withStyle(SpanStyle(color = J.accent, fontWeight = FontWeight.Medium)) { append("Add a Gemini key") }
            }
        }, style = J.small.copy(color = J.text2))
    }
}

private val SUGGESTIONS = listOf(
    Triple(Ico.camera, "Scan whiteboard / sketch", "Beam camera snap to PC"),
    Triple(Ico.calendar, "What's due soon?", "Classroom and calendar"),
    Triple(Ico.screen, "What's on my screen?", "A look at your PC"),
    Triple(Ico.mail, "Any new emails?", "Your inbox, summed up"),
)

@Composable
private fun Empty(ui: Ui, act: Actions) {
    val hour = remember { LocalTime.now().hour }
    // (fills the height so the group sits a little above centre, ending clear of the composer)
    BoxWithConstraints(Modifier.fillMaxSize()) { Column(Modifier.verticalScroll(rememberScrollState()).heightIn(min = maxHeight)
        .navigationBarsPadding().padding(start = 20.dp, end = 20.dp, top = 16.dp, bottom = 112.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        Spacer(Modifier.weight(1f))
        Reactor(150.dp, working = ui.working, dim = !online(ui))
        Spacer(Modifier.height(20.dp))
        Text(when (hour) { in 5..11 -> "Good morning"; in 12..17 -> "Good afternoon"; else -> "Good evening" }, J.display)
        Spacer(Modifier.height(8.dp))
        Text(if (ui.state == State.ONLINE) "Type or tap the mic. Your PC does the work." else "Ask anything. Jarvis answers as soon as it can.",
            J.body.copy(color = J.text2), align = TextAlign.Center)

        // Today Dashboard Hub (Music, Up Next, PC Stats)
        if (ui.today.mediaTitle.isNotBlank()) {
            Spacer(Modifier.height(20.dp))
            Row(
                Modifier.fillMaxWidth().glass(RoundedCornerShape(20.dp)).padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Box(Modifier.size(44.dp).background(J.accentSoft, RoundedCornerShape(12.dp)), contentAlignment = Alignment.Center) {
                    Icon(Ico.music, J.accent, 22.dp)
                }
                Spacer(Modifier.width(14.dp))
                Column(Modifier.weight(1f)) {
                    Text(ui.today.mediaTitle, J.button, maxLines = 1)
                    if (ui.today.mediaArtist.isNotBlank()) {
                        Text(ui.today.mediaArtist, J.small, maxLines = 1)
                    }
                }
                Spacer(Modifier.width(8.dp))
                Box(
                    Modifier.size(38.dp).background(J.accentSoft, CircleShape).clickable { act.mediaAction("PlayPause") },
                    contentAlignment = Alignment.Center
                ) {
                    Icon(if (ui.today.mediaStatus == "Playing") Ico.pause else Ico.play, J.accent, 18.dp)
                }
            }
        }

        if (ui.today.reminders.isNotEmpty()) {
            Spacer(Modifier.height(14.dp))
            Column(
                Modifier.fillMaxWidth().glass(RoundedCornerShape(20.dp)).padding(16.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Ico.calendar, J.accent, 16.dp)
                    Spacer(Modifier.width(8.dp))
                    Text("Up Next", J.heading)
                }
                Spacer(Modifier.height(10.dp))
                ui.today.reminders.take(3).forEach { rem ->
                    Text(rem, J.small.copy(color = J.text), maxLines = 2)
                    Spacer(Modifier.height(4.dp))
                }
            }
        }

        if (ui.today.cpu > 0 || ui.today.gaming) {
            Spacer(Modifier.height(14.dp))
            Row(
                Modifier.fillMaxWidth().glass(RoundedCornerShape(20.dp)).padding(14.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Ico.cpu, J.accent, 18.dp)
                    Spacer(Modifier.width(8.dp))
                    Text("PC: CPU ${ui.today.cpu}%  RAM ${ui.today.ramGb}", J.small.copy(fontWeight = FontWeight.Medium))
                }
                if (ui.today.gaming) {
                    Text("⚡ Gaming VRAM", J.label.copy(color = J.warm))
                } else {
                    Text("Ready", J.label.copy(color = J.green))
                }
            }
        }

        if (ui.state == State.ONLINE) {
            val uriHandler = LocalUriHandler.current
            Spacer(Modifier.height(14.dp))
            Column(
                Modifier.fillMaxWidth().glass(RoundedCornerShape(20.dp)).padding(16.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Ico.radar, J.accent, 18.dp)
                    Spacer(Modifier.width(8.dp))
                    Text("Job Radar", J.heading)
                    Spacer(Modifier.weight(1f))
                    Text(if (ui.today.jobTime.isNotBlank()) "Updated ${ui.today.jobTime}" else "Daily radar", J.label.copy(color = J.text3))
                }
                Spacer(Modifier.height(10.dp))
                Text(
                    if (ui.today.jobText.isNotBlank()) ui.today.jobText else "Scan Bucharest game dev & Minecraft freelance listings.",
                    J.small.copy(color = if (ui.today.jobText.isNotBlank()) J.text else J.text2, lineHeight = 18.sp)
                )
                Spacer(Modifier.height(12.dp))
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    listOf(
                        "Glassdoor" to "https://www.glassdoor.com/Job/bucharest-game-developer-jobs-SRCH_IL.0,9_IC3278546_KO10,24.htm",
                        "SpigotMC" to "https://www.spigotmc.org/forums/hiring-developers.55/",
                        "LinkedIn" to "https://www.linkedin.com/jobs/search/?keywords=game%20developer%20bucharest"
                    ).forEach { (name, url) ->
                        Row(
                            Modifier.glass(RoundedCornerShape(12.dp)).press { uriHandler.openUri(url) }.padding(horizontal = 10.dp, vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(name, J.label.copy(color = J.accent))
                            Spacer(Modifier.width(4.dp))
                            Icon(Ico.external, J.accent, 12.dp)
                        }
                    }
                }
            }
        }

        // Lead Hunter Dashboard Hub
        if (ui.state == State.ONLINE) {
            val uriHandler = LocalUriHandler.current
            var customNiche by remember { mutableStateOf("") }
            Spacer(Modifier.height(14.dp))
            Column(
                Modifier.fillMaxWidth().glass(RoundedCornerShape(20.dp)).padding(16.dp)
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Ico.sparkle, J.accent, 18.dp)
                    Spacer(Modifier.width(8.dp))
                    Text("Lead Hunter Radar", J.heading)
                    Spacer(Modifier.weight(1f))
                    Text("Lowest Traction", J.label.copy(color = J.warm))
                }
                Spacer(Modifier.height(6.dp))
                Text(
                    "Local businesses with missing web funnels & conversion leaks:",
                    J.small.copy(color = J.text2, lineHeight = 17.sp)
                )
                Spacer(Modifier.height(10.dp))

                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Field(customNiche, { customNiche = it }, "Search any niche or city...", Modifier.weight(1f), done = {
                        if (customNiche.isNotBlank()) act.scanLeads(customNiche.trim())
                    })
                    Spacer(Modifier.width(8.dp))
                    Box(
                        Modifier.size(44.dp).glass(CircleShape).press {
                            if (customNiche.isNotBlank()) act.scanLeads(customNiche.trim())
                        },
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(Ico.sparkle, J.accent, 18.dp)
                    }
                }
                Spacer(Modifier.height(12.dp))

                if (ui.today.leads.isNotEmpty()) {
                    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        ui.today.leads.take(8).forEach { lead ->
                            Row(
                                Modifier.fillMaxWidth().glass(RoundedCornerShape(12.dp)).padding(10.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Column(Modifier.weight(1f)) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text(lead.name, J.button.copy(fontSize = 13.5.sp), maxLines = 1)
                                        Spacer(Modifier.width(6.dp))
                                        Box(
                                            Modifier.clip(RoundedCornerShape(6.dp))
                                                .background(if (lead.score <= 30) J.accentSoft else J.warm.copy(alpha = 0.2f))
                                                .padding(horizontal = 6.dp, vertical = 2.dp)
                                        ) {
                                            Text(
                                                "${lead.score}/100",
                                                J.label.copy(color = if (lead.score <= 30) J.accent else J.warm, fontSize = 10.sp)
                                            )
                                        }
                                    }
                                    if (lead.issues.isNotEmpty()) {
                                        Spacer(Modifier.height(2.dp))
                                        Text(lead.issues.joinToString(" · "), J.label.copy(color = J.text3, fontSize = 11.sp), maxLines = 1)
                                    }
                                }
                                val gmaps = lead.mapsUrl.ifBlank {
                                    "https://www.google.com/maps/search/?api=1&query=" + java.net.URLEncoder.encode(lead.name + " Bucharest", "UTF-8")
                                }
                                Box(
                                    Modifier.size(34.dp).glass(CircleShape).press {
                                        uriHandler.openUri(gmaps)
                                    },
                                    contentAlignment = Alignment.Center
                                ) {
                                    Icon(Ico.pin, J.accent, 16.dp)
                                }
                                if (lead.url.isNotBlank() && lead.url != "No Website") {
                                    Spacer(Modifier.width(6.dp))
                                    Box(
                                        Modifier.size(34.dp).glass(CircleShape).press {
                                            val full = if (lead.url.startsWith("http")) lead.url else "https://${lead.url}"
                                            uriHandler.openUri(full)
                                        },
                                        contentAlignment = Alignment.Center
                                    ) {
                                        Icon(Ico.external, J.accent, 14.dp)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        Spacer(Modifier.height(28.dp))
        SUGGESTIONS.chunked(2).forEach { row ->
            Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min).padding(bottom = 12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                row.forEach { (icon, title, sub) ->
                    Column(Modifier.weight(1f).fillMaxHeight().glass(RoundedCornerShape(20.dp)).press {
                        if (title.contains("Scan", ignoreCase = true)) act.cameraScan() else act.ask(title)
                    }.padding(16.dp)) {
                        Box(Modifier.size(36.dp).background(J.accentSoft, CircleShape), contentAlignment = Alignment.Center) { Icon(icon, J.accent, 18.dp) }
                        Spacer(Modifier.weight(1f).heightIn(min = 14.dp))
                        Text(title, J.button.copy(lineHeight = 19.sp), maxLines = 1)
                        Spacer(Modifier.height(3.dp))
                        Text(sub, J.label.copy(fontWeight = FontWeight.Normal, letterSpacing = 0.sp), maxLines = 1)
                    }
                }
            }
        }
        Spacer(Modifier.weight(0.15f))
    } }
}

@Composable
private fun Conversation(ui: Ui, stop: () -> Unit) {
    val seen = remember { ui.messages.map { it.id }.toMutableSet() }  // (only messages that arrive later animate in)
    var wasWorking by remember { mutableStateOf(ui.working) }
    SideEffect { if (!ui.working) wasWorking = false }
    LazyColumn(Modifier.fillMaxSize(), reverseLayout = true,
        contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 12.dp, bottom = 140.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp, Alignment.Bottom)) {
        if (ui.working) item(key = "working") { Arrive(!wasWorking) { Working(stop) } }
        items(ui.messages.asReversed(), key = { it.id }) { m ->
            Arrive(remember(m.id) { seen.add(m.id) }) { Message(m) }
        }
    }
}

@Composable
private fun Arrive(fresh: Boolean, content: @Composable () -> Unit) {
    if (!fresh) return content()
    val a = remember { Animatable(0f) }
    LaunchedEffect(Unit) { a.animateTo(1f, tween(220, easing = FastOutSlowInEasing)) }
    Box(Modifier.graphicsLayer { alpha = a.value; translationY = (1 - a.value) * 8.dp.toPx() }) { content() }
}

@Composable
private fun Message(m: Msg) {
    when (m.who) {
        Who.YOU -> Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.CenterEnd) {
            Box(Modifier.fillMaxWidth(0.8f), contentAlignment = Alignment.CenterEnd) {
                val shape = RoundedCornerShape(20.dp, 20.dp, 6.dp, 20.dp)
                SelectionContainer {
                    Text(m.text, J.chat, modifier = Modifier.clip(shape).background(J.accentSoft).border(1.dp, J.accent.copy(alpha = 0.25f), shape)
                        .padding(horizontal = 15.dp, vertical = 10.dp))
                }
            }
        }
        Who.NOTE -> Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
            Text(m.text, J.small.copy(color = J.text3), align = TextAlign.Center, modifier = Modifier.widthIn(max = 280.dp).padding(vertical = 4.dp))
        }
        else -> Row(Modifier.fillMaxWidth().padding(end = 12.dp)) {
            Reactor(24.dp, mini = true)
            Spacer(Modifier.width(12.dp))
            Column {
                SelectionContainer { BasicText(md(m.text), style = J.chat) }
                if (m.who == Who.PHONE) Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Ico.phone, J.text3, 12.dp)
                    Spacer(Modifier.width(4.dp))
                    Text("on phone", J.label.copy(color = J.text3, fontSize = 11.sp))
                }
            }
        }
    }
}

@Composable
private fun Working(stop: () -> Unit) {
    val shift by rememberInfiniteTransition(label = "shimmer").animateFloat(-1f, 2f,
        infiniteRepeatable(tween(1600, easing = LinearEasing)), label = "shimmer")
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Reactor(24.dp, working = true, mini = true)
        Spacer(Modifier.width(12.dp))
        Row(Modifier.height(32.dp).glass(CircleShape).padding(horizontal = 13.dp), verticalAlignment = Alignment.CenterVertically) {
            Dot(J.warm, glow = true, pulse = true)
            Spacer(Modifier.width(9.dp))
            BasicText("Working on it…", style = J.small.copy(brush = Brush.linearGradient(
                listOf(J.text2, J.text2, J.text, J.text2, J.text2), Offset(shift * 260f - 260f, 0f), Offset(shift * 260f + 260f, 0f))))
        }
        Spacer(Modifier.weight(1f).widthIn(min = 12.dp))
        StopChip(stop)
    }
}

@Composable
private fun StopChip(onClick: () -> Unit) {
    Row(Modifier.height(32.dp).glass(CircleShape).press(onClick = onClick).padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(8.dp).background(J.warm, RoundedCornerShape(2.dp)))
        Spacer(Modifier.width(8.dp))
        Text("Stop", J.button.copy(color = J.warm, fontSize = 13.sp))
    }
}

@Composable
private fun Composer(act: Actions) {
    var text by remember { mutableStateOf("") }
    val view = LocalView.current
    val send = {
        if (text.isNotBlank()) {
            view.performHapticFeedback(HapticFeedbackConstants.KEYBOARD_TAP)
            act.ask(text.trim())
            text = ""
        }
    }
    Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).floating(RoundedCornerShape(28.dp)).padding(start = 20.dp, end = 8.dp, top = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically) {
        BasicTextField(text, { text = it }, Modifier.weight(1f).padding(vertical = 6.dp), textStyle = J.chat, maxLines = 5,
            cursorBrush = SolidColor(J.accent),
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send), keyboardActions = KeyboardActions(onSend = { send() }),
            decorationBox = { inner -> Box { if (text.isEmpty()) Text("Ask Jarvis", J.chat.copy(color = J.text3)); inner() } })
        Spacer(Modifier.width(8.dp))
        Round(Ico.camera, Color(0x12FFFFFF), J.text, act.cameraScan)
        Spacer(Modifier.width(8.dp))
        Round(Ico.mic, Color(0x12FFFFFF), J.text, act.listen)
        AnimatedVisibility(text.isNotBlank(), enter = fadeIn(tween(140)) + scaleIn(tween(140), 0.6f), exit = fadeOut(tween(140)) + scaleOut(tween(140), 0.6f)) {
            Row { Spacer(Modifier.width(8.dp)); Round(Ico.send, J.accent, J.accentInk, send) }
        }
    }
}

@Composable
private fun Round(icon: ImageVector, fill: Color, tint: Color, onClick: () -> Unit, size: Dp = 40.dp, iconSize: Dp = 20.dp) {
    Box(Modifier.size(size).clip(CircleShape).background(fill).press(onClick = onClick), contentAlignment = Alignment.Center) { Icon(icon, tint, iconSize) }
}

// ---- settings sheet

@Composable
private fun BoxScope.Sheet(visible: Boolean, onDismiss: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    BackHandler(visible, onDismiss)
    AnimatedVisibility(visible, Modifier.matchParentSize(), enter = fadeIn(tween(200)), exit = fadeOut(tween(200))) {
        Box(Modifier.fillMaxSize().background(Color(0x8C000000)).clickable(remember { MutableInteractionSource() }, null, onClick = onDismiss))
    }
    AnimatedVisibility(visible, Modifier.align(Alignment.BottomCenter),
        enter = slideInVertically(tween(260, easing = FastOutSlowInEasing)) { it } + fadeIn(tween(200)),
        exit = slideOutVertically(tween(220)) { it } + fadeOut(tween(200))) {
        val shape = RoundedCornerShape(topStart = 28.dp, topEnd = 28.dp)
        Column(Modifier.fillMaxWidth().statusBarsPadding().padding(top = 40.dp).clip(shape).background(J.sheet)
            .border(1.dp, Brush.verticalGradient(listOf(J.strokeStrong, Color.Transparent), endY = 120f), shape)
            .clickable(remember { MutableInteractionSource() }, null) {}
            .navigationBarsPadding().imePadding().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp)) {
            Box(Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 6.dp), contentAlignment = Alignment.Center) {
                Box(Modifier.size(36.dp, 4.dp).background(Color(0x33FFFFFF), CircleShape))
            }
            content()
        }
    }
}

@Composable
private fun ColumnScope.Settings(ui: Ui, act: Actions, close: () -> Unit) {
    Row(Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 16.dp), verticalAlignment = Alignment.CenterVertically) {
        Text("Settings", J.title, modifier = Modifier.weight(1f))
        Round(Ico.close, J.glass, J.text2, close, size = 34.dp, iconSize = 16.dp)
    }
    val (color, label) = status(ui)
    Card {
        Row(Modifier.padding(top = 2.dp, bottom = 14.dp), verticalAlignment = Alignment.CenterVertically) {
            Dot(color, glow = ui.state == State.ONLINE)
            Spacer(Modifier.width(10.dp))
            Text(label.substringBefore(" · "), J.heading.copy(fontSize = 15.sp))
        }
        Divider()
        Detail("Your PC", ui.pc.ifBlank { "Not connected yet" })
        Divider()
        Detail("Relay", ui.relay.ifBlank { "—" })
        Spacer(Modifier.height(14.dp))
        PastePair(act) { paste ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Secondary("Pair again", Ico.scan, Modifier.weight(1f)) { close(); act.scan() }
                Secondary("Paste link", Ico.link, Modifier.weight(1f), paste)
            }
        }
    }
    Spacer(Modifier.height(12.dp))
    var key by remember(ui.key) { mutableStateOf(ui.key) }
    var shown by remember { mutableStateOf(false) }
    Card {
        Text("Gemini key for when the PC is off", J.heading.copy(fontSize = 15.sp))
        Spacer(Modifier.height(4.dp))
        Text("Your own key from aistudio.google.com. It stays on this phone and is only used while your PC can't be reached.", J.small)
        Spacer(Modifier.height(14.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Field(key, { key = it }, "Paste your API key", Modifier.weight(1f), secret = !shown, done = { act.saveKey(key) },
                trailing = { if (key.isNotEmpty()) Text(if (shown) "Hide" else "Show", J.label.copy(color = J.text3), modifier = Modifier.clickable { shown = !shown }.padding(8.dp)) })
            if (key.trim() != ui.key) {
                Spacer(Modifier.width(10.dp))
                Primary("Save", null) { act.saveKey(key) }
            }
        }
        if (ui.key.isNotBlank() && key.trim() == ui.key) Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(Ico.check, J.green, 14.dp)
            Spacer(Modifier.width(6.dp))
            Text("Saved", J.label.copy(color = J.green, letterSpacing = 0.sp))
        }
    }
    Spacer(Modifier.height(12.dp))
    Row(Modifier.fillMaxWidth().height(44.dp).glass(CircleShape).press { close(); act.unpair() }, horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically) {
        Text("Unpair this phone", J.button.copy(color = J.red))
    }
    Text("Jarvis ${ui.version} · end-to-end encrypted", J.small.copy(color = J.text3, fontSize = 12.sp), align = TextAlign.Center,
        modifier = Modifier.fillMaxWidth().padding(top = 18.dp, bottom = 16.dp))
}

@Composable
private fun Detail(name: String, value: String) {
    Row(Modifier.fillMaxWidth().height(52.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(name, J.body.copy(color = J.text2))
        Spacer(Modifier.width(16.dp))
        Text(value, J.body, Modifier.weight(1f), align = TextAlign.End, maxLines = 1)
    }
}

// ---- pieces

/** Glass: a faint white fill, a hairline that catches more light along its top edge. */
private fun Modifier.glass(shape: Shape, fill: Color = J.glass) = clip(shape).background(fill)
    .border(1.dp, Brush.verticalGradient(listOf(J.stroke.copy(alpha = 0.16f), J.stroke, J.stroke)), shape)

/** Floating glass (composer): stronger and lifted by a soft shadow, since there's no blur behind it. */
private fun Modifier.floating(shape: Shape) = drawBehind {
    val y = 10.dp.toPx()
    for (i in 1..4) drawRoundRect(Color.Black.copy(alpha = 0.09f), Offset(-i * 2f, y - i * 2f + 4f), Size(size.width + i * 4f, size.height + i * 4f), CornerRadius(size.height / 2 + i * 2f))
}.glass(shape, J.glassStrong).border(1.dp, Brush.verticalGradient(listOf(J.strokeStrong, J.stroke)), shape)

private fun Modifier.press(enabled: Boolean = true, onClick: () -> Unit) = composed {
    val source = remember { MutableInteractionSource() }
    val down by source.collectIsPressedAsState()
    val s by animateFloatAsState(if (down) 0.97f else 1f, tween(140), label = "press")
    graphicsLayer { scaleX = s; scaleY = s; alpha = if (down) 0.85f else 1f }.clickable(source, null, enabled, onClick = onClick)
}

@Composable
private fun Card(content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.fillMaxWidth().glass(RoundedCornerShape(20.dp)).padding(horizontal = 16.dp, vertical = 14.dp), content = content)
}

@Composable
private fun Divider() = Box(Modifier.fillMaxWidth().height(1.dp).background(J.stroke))

@Composable
private fun Text(text: String, style: TextStyle, modifier: Modifier = Modifier, align: TextAlign = TextAlign.Start, maxLines: Int = Int.MAX_VALUE) =
    BasicText(text, modifier, style.copy(textAlign = align), maxLines = maxLines, overflow = TextOverflow.Ellipsis)

@Composable
private fun Icon(icon: ImageVector, tint: Color, size: Dp) = Image(icon, null, Modifier.size(size), colorFilter = ColorFilter.tint(tint))

@Composable
private fun Primary(text: String, icon: ImageVector?, modifier: Modifier = Modifier, height: Dp = 44.dp, enabled: Boolean = true, onClick: () -> Unit) {
    Row(modifier.height(height).then(if (enabled) Modifier.clip(CircleShape).background(J.accent) else Modifier.glass(CircleShape))
        .press(enabled, onClick).padding(horizontal = 20.dp), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
        val ink = if (enabled) J.accentInk else J.text3
        if (icon != null) { Icon(icon, ink, 20.dp); Spacer(Modifier.width(10.dp)) }
        Text(text, J.button.copy(color = ink))
    }
}

@Composable
private fun Secondary(text: String, icon: ImageVector, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Row(modifier.height(44.dp).glass(CircleShape).press(onClick = onClick).padding(horizontal = 16.dp),
        horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
        Icon(icon, J.text2, 18.dp)
        Spacer(Modifier.width(8.dp))
        Text(text, J.button)
    }
}

@Composable
private fun Ghost(text: String, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Box(modifier.height(44.dp).clip(CircleShape).press(onClick = onClick), contentAlignment = Alignment.Center) {
        Text(text, J.button.copy(color = J.text2))
    }
}

@Composable
private fun Field(value: String, onChange: (String) -> Unit, placeholder: String, modifier: Modifier = Modifier, secret: Boolean = false,
                  done: () -> Unit = {}, trailing: @Composable () -> Unit = {}) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(12.dp)
    BasicTextField(value, onChange, modifier.height(44.dp).onFocusChanged { focused = it.isFocused }
        .drawBehind {
            if (focused) drawRoundRect(J.accentSoft, Offset(-1.5.dp.toPx(), -1.5.dp.toPx()), Size(size.width + 3.dp.toPx(), size.height + 3.dp.toPx()),
                CornerRadius(13.5.dp.toPx()), style = Stroke(3.dp.toPx()))
        }
        .clip(shape).background(J.glass).border(1.dp, if (focused) J.accent else J.stroke, shape),
        textStyle = J.body, singleLine = true, cursorBrush = SolidColor(J.accent),
        visualTransformation = if (secret) PasswordVisualTransformation() else VisualTransformation.None,
        keyboardOptions = KeyboardOptions(keyboardType = if (secret) KeyboardType.Password else KeyboardType.Uri, imeAction = ImeAction.Done),
        keyboardActions = KeyboardActions(onDone = { done() }),
        decorationBox = { inner ->
            Row(Modifier.fillMaxSize().padding(start = 14.dp, end = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.weight(1f)) { if (value.isEmpty()) Text(placeholder, J.body.copy(color = J.text3), maxLines = 1); inner() }
                trailing()
            }
        })
}

/** **bold** spans, the only markdown replies use. */
private fun md(text: String) = buildAnnotatedString {
    text.split("**").forEachIndexed { i, part -> if (i % 2 == 1) withStyle(SpanStyle(fontWeight = FontWeight.SemiBold, color = J.text)) { append(part) } else append(part) }
}
