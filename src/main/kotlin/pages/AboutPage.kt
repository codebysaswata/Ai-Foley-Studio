import androidx.compose.foundation.Image
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.hoverable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsHoveredAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.FastOutLinearInEasing
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.LinearOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.window.WindowDraggableArea
import androidx.compose.material.Text
import androidx.compose.material.Slider
import androidx.compose.material.SliderDefaults
import androidx.compose.material.LocalTextStyle
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.produceState
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameNanos
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.draganddrop.DragAndDropEvent
import androidx.compose.ui.draganddrop.DragAndDropTarget
import androidx.compose.ui.draganddrop.awtTransferable
import androidx.compose.foundation.draganddrop.dragAndDropTarget
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.painter.BitmapPainter
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.toComposeImageBitmap
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.layout.positionInRoot
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.loadImageBitmap
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.useResource
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.EmbeddedFontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.WindowPosition
import androidx.compose.ui.window.WindowScope
import androidx.compose.ui.window.WindowState
import androidx.compose.ui.window.application
import androidx.compose.ui.window.rememberDialogState
import androidx.compose.ui.window.rememberWindowState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.compose.ui.unit.DpSize
import java.awt.GraphicsEnvironment
import java.awt.Rectangle
import java.awt.Toolkit
import kotlin.math.abs
import java.awt.datatransfer.DataFlavor
import java.io.File
import java.io.RandomAccessFile
import org.jetbrains.skia.ColorAlphaType
import org.jetbrains.skia.ColorType
import org.jetbrains.skia.ImageInfo
import org.jetbrains.skia.Image as SkiaImage
import uk.co.caprica.vlcj.factory.MediaPlayerFactory
import uk.co.caprica.vlcj.factory.discovery.NativeDiscovery
import uk.co.caprica.vlcj.player.base.MediaPlayer
import uk.co.caprica.vlcj.player.base.MediaPlayerEventAdapter
import uk.co.caprica.vlcj.player.embedded.EmbeddedMediaPlayer
import uk.co.caprica.vlcj.player.embedded.videosurface.callback.BufferFormat
import uk.co.caprica.vlcj.player.embedded.videosurface.callback.BufferFormatCallbackAdapter
import uk.co.caprica.vlcj.player.embedded.videosurface.callback.RenderCallback
import uk.co.caprica.vlcj.player.embedded.videosurface.callback.format.RV32BufferFormat
import java.nio.ByteBuffer
import javax.swing.JFileChooser
import javax.swing.filechooser.FileNameExtensionFilter

@Composable
fun AboutPage(animationKey: String, onNavigate: (String) -> Unit) = AboutPageContent(animationKey, onNavigate)

@Composable
private fun AboutPageContent(animationKey: String, onNavigate: (String) -> Unit) {
    var revealed by remember(animationKey) { mutableStateOf(false) }
    LaunchedEffect(animationKey) { revealed = true }
    val heroAlpha by animateFloatAsState(
        targetValue = if (revealed) 1f else 0f,
        animationSpec = tween(520, easing = FastOutSlowInEasing), label = "aboutHeroAlpha"
    )
    val heroOffset by animateDpAsState(
        targetValue = if (revealed) 0.dp else 38.dp,
        animationSpec = tween(620, easing = FastOutSlowInEasing), label = "aboutHeroOffset"
    )
    val heroTransition = rememberInfiniteTransition(label = "aboutHeroFloat")
    val heroFloat by heroTransition.animateFloat(
        initialValue = -7f, targetValue = 7f,
        animationSpec = infiniteRepeatable(tween(1067, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "aboutHeroIdleFloat"
    )

    BoxWithConstraints(Modifier.fillMaxSize().background(CanvasCream)) {
        val compact = maxWidth < 1450.dp
        val narrow = maxWidth < 1100.dp
        val pagePadding = if (narrow) 42.dp else if (compact) 64.dp else 96.dp
        val titleSize = if (narrow) 43.sp else if (compact) 52.sp else 62.sp
        val heroHeight = if (narrow) 430.dp else if (compact) 445.dp else 470.dp
        // Scrollable so the three info cards are never squeezed on shorter windows
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState())) {
            Box(Modifier.fillMaxWidth().height(heroHeight)) {
                Image(
                    painter = painterResource("images/about-hero.png"), contentDescription = null,
                    modifier = Modifier.align(Alignment.CenterEnd)
                        .padding(end = if (narrow) (-50).dp else 10.dp)
                        .graphicsLayer { alpha = heroAlpha; translationY = heroFloat.dp.toPx() }
                        .width(if (narrow) 460.dp else if (compact) 590.dp else 690.dp)
                        .height(if (narrow) 350.dp else if (compact) 400.dp else 450.dp),
                    contentScale = ContentScale.Fit,
                    alpha = if (narrow) .20f else if (compact) .58f else 1f
                )
                Column(
                    modifier = Modifier.align(Alignment.CenterStart).graphicsLayer { alpha = heroAlpha; translationY = heroOffset.toPx() }
                        .widthIn(max = if (narrow) 760.dp else if (compact) 850.dp else 970.dp)
                        .padding(start = pagePadding),
                    horizontalAlignment = Alignment.Start
                ) {
                    Image(
                        painter = painterResource("images/eyebrow-logo.png"), contentDescription = "AI-Powered Foley Generation",
                        modifier = Modifier.width(if (narrow) 272.dp else 330.dp).height(if (narrow) 42.dp else 51.dp),
                        contentScale = ContentScale.Fit
                    )
                    Spacer(Modifier.height(17.dp))
                    Text("Bringing Videos to Life", color = Ink, fontSize = titleSize,
                        lineHeight = titleSize, fontWeight = FontWeight.Black, letterSpacing = (-2).sp)
                    Text(buildAnnotatedString {
                        append("with ")
                        pushStyle(SpanStyle(color = Copper, fontWeight = FontWeight.Black))
                        append("Intelligent Sound")
                        pop()
                    }, color = Ink, fontSize = titleSize, lineHeight = titleSize, fontWeight = FontWeight.Black, letterSpacing = (-2).sp)
                    Spacer(Modifier.height(18.dp))
                    Text(
                        "AI Foley Studio is an AI-powered Foley generation tool that automatically\ncreates realistic, context-aware sound effects for your videos using\nadvanced deep learning. It turns silent footage into an immersive\naudio-visual experience, locally and securely on your device.",
                        color = Color(0xFF554640), fontSize = if (narrow) 14.sp else 16.sp,
                        lineHeight = if (narrow) 20.sp else 24.sp
                    )
                    Spacer(Modifier.height(21.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                        StaticButton("Try it now  →", dark = true, enableHoverLift = true,
                            padding = PaddingValues(horizontal = 29.dp, vertical = 16.dp), fontSize = 18.sp,
                            onClick = { onNavigate("Get Started") })
                        StaticButton("View Features", dark = false, enableHoverLift = true,
                            padding = PaddingValues(horizontal = 27.dp, vertical = 16.dp), fontSize = 18.sp,
                            onClick = { onNavigate("Features") })
                    }
                }
            }
            AboutCards(revealed, compact, narrow)
        }
    }
}

@Composable
private fun AboutCards(revealed: Boolean, compact: Boolean, narrow: Boolean) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = if (narrow) 32.dp else if (compact) 54.dp else 88.dp, vertical = 12.dp),
        horizontalArrangement = Arrangement.spacedBy(if (narrow) 12.dp else 18.dp)
    ) {
        AboutInfoCard("Our Vision", "images/about-vision.png", 0, revealed, Modifier.weight(1f)) {
            Text("To make high-quality Foley and sound design accessible, automatic and offline for creators, students and professionals.",
                color = Ink, fontSize = if (narrow) 12.sp else 14.sp, lineHeight = if (narrow) 17.sp else 20.sp)
        }
        AboutInfoCard("How it Works", "images/about-how-it-works.png", 1, revealed, Modifier.weight(1f)) {
            Row(
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(17.dp)).background(Color(0xFFE7D1BA))
                    .padding(horizontal = 14.dp, vertical = 20.dp),
                horizontalArrangement = Arrangement.SpaceEvenly,
                verticalAlignment = Alignment.CenterVertically
            ) {
                WorkflowStep("Upload\nVideo")
                WorkflowArrow()
                WorkflowStep("Generate\nAudio")
                WorkflowArrow()
                WorkflowStep("Process &\nSync")
                WorkflowArrow()
                WorkflowStep("Export\nMP4")
            }
        }
        AboutInfoCard("Build With", "images/about-build-with.png", 2, revealed, Modifier.weight(1f)) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TechBadge("Python", Modifier.weight(1f)); TechBadge("FastAPI", Modifier.weight(1f)); TechBadge("PyTorch", Modifier.weight(1f))
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TechBadge("MMAudio", Modifier.weight(1f)); TechBadge("FFmpeg", Modifier.weight(1f)); TechBadge("Kotlin", Modifier.weight(1f))
                }
            }
        }
    }
}

@Composable
private fun AboutInfoCard(title: String, image: String, index: Int, revealed: Boolean, modifier: Modifier, content: @Composable () -> Unit) {
    val cardAlpha by animateFloatAsState(if (revealed) 1f else 0f, tween(500, 160 + index * 100, FastOutSlowInEasing), label = "aboutCardAlpha$index")
    val slide by animateDpAsState(if (revealed) 0.dp else 28.dp, tween(560, 160 + index * 100, FastOutSlowInEasing), label = "aboutCardSlide$index")
    val scale by animateFloatAsState(if (revealed) 1f else .91f, tween(560, 160 + index * 100, FastOutSlowInEasing), label = "aboutCardScale$index")
    Column(
        modifier = modifier.height(250.dp)
            .graphicsLayer { alpha = cardAlpha; translationY = slide.toPx(); scaleX = scale; scaleY = scale }
            .clip(RoundedCornerShape(26.dp)).background(Sand).border(2.dp, CardBorder, RoundedCornerShape(26.dp)).padding(20.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(13.dp)) {
            Image(painterResource(image), null, Modifier.size(72.dp), contentScale = ContentScale.Fit)
            Text(title, color = Ink, fontSize = 25.sp, fontWeight = FontWeight.Black)
        }
        Spacer(Modifier.height(11.dp))
        content()
    }
}

@Composable
private fun WorkflowStep(label: String) = Text(label, color = Ink, fontSize = 13.sp, lineHeight = 17.sp, fontWeight = FontWeight.Medium)

@Composable
private fun WorkflowArrow() = Text("→", color = Ink, fontSize = 22.sp, fontWeight = FontWeight.SemiBold)

@Composable
private fun TechBadge(label: String, modifier: Modifier = Modifier) {
    Box(modifier.height(42.dp).clip(RoundedCornerShape(8.dp)).background(Color.White).border(2.dp, CardBorder, RoundedCornerShape(8.dp)), contentAlignment = Alignment.Center) {
        Text(label, color = Ink, fontSize = 13.sp, fontWeight = FontWeight.Bold)
    }
}
