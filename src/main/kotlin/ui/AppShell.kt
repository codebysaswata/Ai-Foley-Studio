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

internal fun runStudio() = application {
    // Start at 90% of the area above the taskbar, so Maximize has room to grow
    val startSize = remember {
        val usable = usableScreenArea(GraphicsEnvironment.getLocalGraphicsEnvironment().defaultScreenDevice.defaultConfiguration).second
        DpSize(minOf(1920.dp, usable.width * 0.9f), minOf(1080.dp, usable.height * 0.9f))
    }
    val state = rememberWindowState(size = startSize, position = WindowPosition(Alignment.Center))
    // App logo for the taskbar / Alt+Tab. Loaded safely: if the file is missing the app still starts.
    val appIcon = remember {
        runCatching { BitmapPainter(useResource("images/app-icon.png", ::loadImageBitmap)) }.getOrNull()
    }
    Window(
        onCloseRequest = ::exitApplication,
        title = "AI Foley Studio",
        icon = appIcon,
        state = state,
        undecorated = true,
        resizable = true
    ) {
        LandingPage(state, ::exitApplication)
    }
}

@Composable
@OptIn(ExperimentalFoundationApi::class)
internal fun WindowScope.LandingPage(windowState: WindowState, onClose: () -> Unit) {
    var selectedNav by remember { mutableStateOf("Home") }
    var selectedVideo by remember { mutableStateOf<File?>(null) }   // kept when switching tabs
    var generatedVideo by remember { mutableStateOf<File?>(null) }  // the MP4 returned by the backend
    val navigate: (String) -> Unit = { destination -> selectedNav = destination }
    CompositionLocalProvider(LocalTextStyle provides TextStyle(fontFamily = Poppins)) {
        Column(
            modifier = Modifier.fillMaxSize().background(CanvasCream)
        ) {
            DesktopHeader(windowState, onClose)
            MainNavigation(selectedNav, navigate)
            when (selectedNav) {
                "Features" -> FeaturesPage(selectedNav)
                "Get Started" -> GetStartedPage(selectedNav, selectedVideo, { selectedVideo = it }, generatedVideo, { generatedVideo = it })
                "About" -> AboutPage(selectedNav, navigate)
                else -> HomePage(selectedNav, navigate, Modifier.fillMaxWidth().weight(1f))
            }
        }
    }
}

@Composable
private fun WindowScope.DesktopHeader(windowState: WindowState, onClose: () -> Unit) {
    // Custom maximize: the built-in WindowPlacement.Maximized covers the taskbar on undecorated windows
    val scope = rememberCoroutineScope()
    var maximized by remember { mutableStateOf(false) }
    var animating by remember { mutableStateOf(false) }
    var restoreBounds by remember { mutableStateOf<Rectangle?>(null) }

    fun setWindowOpacity(value: Float) {
        runCatching { window.opacity = value.coerceIn(0f, 1f) }
    }

    var savedBounds by remember { mutableStateOf<Rectangle?>(null) }   // window bounds before minimizing

    fun currentBounds() = Rectangle(window.x, window.y, window.width, window.height)

    fun applyBounds(from: Rectangle, to: Rectangle, f: Float) {
        fun mix(a: Int, b: Int) = (a + (b - a) * f).toInt()
        windowState.position = WindowPosition(mix(from.x, to.x).dp, mix(from.y, to.y).dp)
        windowState.size = DpSize(mix(from.width, to.width).dp, mix(from.height, to.height).dp)
    }

    // Smoothly animates the window bounds (used for maximize / restore)
    fun animateBoundsTo(target: Rectangle) {
        if (animating) return
        animating = true
        val from = currentBounds()
        scope.launch {
            try {
                Animatable(0f).animateTo(1f, tween(280, easing = FastOutSlowInEasing)) { applyBounds(from, target, value) }
                applyBounds(target, target, 1f)
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (_: Throwable) {
            } finally {
                animating = false
            }
        }
    }

    fun usableBounds() = usableScreenBounds(window.graphicsConfiguration)

    // True when a window already fills the area above the taskbar
    fun nearUsable(r: Rectangle): Boolean {
        val u = usableBounds()
        return abs(r.x - u.x) <= 8 && abs(r.y - u.y) <= 8 && abs(r.width - u.width) <= 8 && abs(r.height - u.height) <= 8
    }

    fun defaultBounds(): Rectangle {
        val u = usableBounds()
        val w = (u.width * .9f).toInt()
        val h = (u.height * .9f).toInt()
        return Rectangle(u.x + (u.width - w) / 2, u.y + (u.height - h) / 2, w, h)
    }

    fun toggleMaximize() {
        if (animating) return
        if (nearUsable(currentBounds())) {
            // Already filling the screen: go back to the saved size (or a normal centred size)
            animateBoundsTo(restoreBounds?.takeIf { !nearUsable(it) } ?: defaultBounds())
            maximized = false
        } else {
            restoreBounds = currentBounds()
            animateBoundsTo(usableBounds())
            maximized = true
        }
    }

    // Keep the Maximize/Restore icon right even if the window was resized or dragged by hand
    LaunchedEffect(windowState.size, windowState.position) {
        if (!animating) maximized = nearUsable(currentBounds())
    }

    // Minimize: the window slides down towards the taskbar while fading out, then minimizes.
    // (Only position + opacity are animated - never the size - and any animation error is swallowed,
    // so the window can always minimize / come back instead of crashing the app.)
    val slideDistance = 70
    fun minimizeAnimated() {
        if (animating) return
        animating = true
        val from = currentBounds()
        savedBounds = from
        scope.launch {
            try {
                Animatable(0f).animateTo(1f, tween(220, easing = FastOutLinearInEasing)) {
                    windowState.position = WindowPosition(from.x.dp, (from.y + slideDistance * value).dp)
                    setWindowOpacity(1f - value)
                }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (_: Throwable) {
            } finally {
                windowState.isMinimized = true
                animating = false
            }
        }
    }

    // Restore from the taskbar: the window rises back to its old position while fading in.
    // (On app start there is nothing saved, so it just fades in.)
    LaunchedEffect(windowState.isMinimized) {
        if (!windowState.isMinimized) {
            val target = savedBounds
            animating = true
            try {
                if (target != null) {
                    Animatable(0f).animateTo(1f, tween(250, easing = LinearOutSlowInEasing)) {
                        windowState.position = WindowPosition(target.x.dp, (target.y + slideDistance * (1f - value)).dp)
                        setWindowOpacity(value)
                    }
                } else {
                    Animatable(0f).animateTo(1f, tween(220, easing = FastOutSlowInEasing)) { setWindowOpacity(value) }
                }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (_: Throwable) {
            } finally {
                if (target != null) runCatching { windowState.position = WindowPosition(target.x.dp, target.y.dp) }
                savedBounds = null
                setWindowOpacity(1f)   // never leave the window invisible
                animating = false
            }
        }
    }

    WindowDraggableArea(
        modifier = Modifier.fillMaxWidth().height(48.dp).background(HeaderPeach)
    ) {
        Row(
            modifier = Modifier.fillMaxSize().padding(start = 32.dp, end = 14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Image(
                painter = painterResource("images/window-logo.png"),
                contentDescription = "AI Foley Studio",
                modifier = Modifier.width(204.dp).height(40.dp),
                contentScale = ContentScale.Fit
            )
            Spacer(Modifier.weight(1f))
            WindowControl(WindowControlType.Minimize) { minimizeAnimated() }
            WindowControl(if (maximized) WindowControlType.Restore else WindowControlType.Maximize) {
                toggleMaximize()
            }
            WindowControl(WindowControlType.Close, onClose)
        }
    }
}

@Composable
private fun WindowControl(type: WindowControlType, onClick: () -> Unit) {
    Box(
        modifier = Modifier.width(48.dp).fillMaxHeight().clickable(onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        Canvas(Modifier.size(22.dp)) {
            val iconColor = Burgundy.copy(alpha = 0.88f)
            val stroke = 1.7.dp.toPx()
            when (type) {
                WindowControlType.Minimize -> drawLine(
                    color = iconColor,
                    start = Offset(size.width * .22f, size.height * .67f),
                    end = Offset(size.width * .78f, size.height * .67f),
                    strokeWidth = stroke,
                    cap = StrokeCap.Round
                )
                WindowControlType.Maximize -> drawRoundRect(
                    color = iconColor,
                    topLeft = Offset(size.width * .23f, size.height * .21f),
                    size = Size(size.width * .54f, size.height * .58f),
                    cornerRadius = CornerRadius(3.dp.toPx(), 3.dp.toPx()),
                    style = Stroke(width = stroke)
                )
                WindowControlType.Restore -> {
                    drawRoundRect(
                        color = iconColor,
                        topLeft = Offset(size.width * .18f, size.height * .30f),
                        size = Size(size.width * .47f, size.height * .50f),
                        cornerRadius = CornerRadius(2.dp.toPx(), 2.dp.toPx()),
                        style = Stroke(width = stroke)
                    )
                    drawRoundRect(
                        color = iconColor,
                        topLeft = Offset(size.width * .35f, size.height * .18f),
                        size = Size(size.width * .47f, size.height * .50f),
                        cornerRadius = CornerRadius(2.dp.toPx(), 2.dp.toPx()),
                        style = Stroke(width = stroke)
                    )
                }
                WindowControlType.Close -> {
                    drawLine(iconColor, Offset(size.width * .25f, size.height * .25f), Offset(size.width * .75f, size.height * .75f), stroke, StrokeCap.Round)
                    drawLine(iconColor, Offset(size.width * .75f, size.height * .25f), Offset(size.width * .25f, size.height * .75f), stroke, StrokeCap.Round)
                }
            }
        }
    }
}

private val ButtonShape18 = RoundedCornerShape(18.dp)

private enum class WindowControlType { Minimize, Maximize, Restore, Close }

@Composable
private fun MainNavigation(selectedNav: String, onNavigate: (String) -> Unit) {
    var navigationOriginX by remember { mutableStateOf(0f) }
    val indicatorTargets = remember { mutableStateMapOf<String, NavigationIndicatorTarget>() }
    val activeTarget = indicatorTargets[selectedNav]
    val indicatorX by animateFloatAsState(
        targetValue = (activeTarget?.x ?: navigationOriginX) - navigationOriginX,
        animationSpec = tween(durationMillis = 420, easing = FastOutSlowInEasing),
        label = "navigationIndicatorX"
    )
    val indicatorWidth by animateFloatAsState(
        targetValue = activeTarget?.width ?: 0f,
        animationSpec = tween(durationMillis = 420, easing = FastOutSlowInEasing),
        label = "navigationIndicatorWidth"
    )
    BoxWithConstraints(
        modifier = Modifier.fillMaxWidth().background(CanvasCream).border(1.dp, Color(0xFFF0E0D0))
            .onGloballyPositioned { navigationOriginX = it.positionInRoot().x }
    ) {
        val compact = maxWidth < 1320.dp
        val narrow = maxWidth < 920.dp
        val navHeight = if (narrow) 76.dp else if (compact) 82.dp else 88.dp
        Row(
            modifier = Modifier.fillMaxWidth().height(navHeight)
                .padding(horizontal = if (narrow) 24.dp else if (compact) 42.dp else 82.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Image(
                painter = painterResource("images/nav-logo.png"),
                contentDescription = "AI Foley Studio",
                modifier = Modifier.width(if (narrow) 245.dp else if (compact) 298.dp else 357.dp)
                    .height(if (narrow) 43.dp else if (compact) 53.dp else 63.dp),
                contentScale = ContentScale.Fit
            )
            Spacer(Modifier.weight(1f))
            if (!narrow) {
                NavigationLabel(
                    "Home", selected = selectedNav == "Home", height = navHeight, compact = compact,
                    onMeasured = { x, width -> indicatorTargets["Home"] = NavigationIndicatorTarget(x, width) }
                ) { onNavigate("Home") }
                Spacer(Modifier.width(if (compact) 30.dp else 64.dp))
                NavigationLabel(
                    "Features", selected = selectedNav == "Features", height = navHeight, compact = compact,
                    onMeasured = { x, width -> indicatorTargets["Features"] = NavigationIndicatorTarget(x, width) }
                ) { onNavigate("Features") }
                Spacer(Modifier.width(if (compact) 30.dp else 64.dp))
                NavigationLabel(
                    "About", selected = selectedNav == "About", height = navHeight, compact = compact,
                    onMeasured = { x, width -> indicatorTargets["About"] = NavigationIndicatorTarget(x, width) }
                ) { onNavigate("About") }
                Spacer(Modifier.width(if (compact) 30.dp else 62.dp))
            }
            Box(modifier = Modifier.onGloballyPositioned {
                indicatorTargets["Get Started"] = NavigationIndicatorTarget(
                    x = it.positionInRoot().x,
                    width = it.size.width.toFloat()
                )
            }) {
                StaticButton(
                    label = "Get Started  →", dark = true,
                    padding = PaddingValues(horizontal = if (narrow) 17.dp else if (compact) 24.dp else 34.dp,
                        vertical = if (narrow) 12.dp else if (compact) 15.dp else 18.dp),
                    fontSize = if (narrow) 14.sp else if (compact) 17.sp else 20.sp,
                    onClick = { onNavigate("Get Started") }
                )
            }
        }
        Canvas(
            modifier = Modifier.align(Alignment.BottomStart).fillMaxWidth().height(if (compact) 5.dp else 7.dp)
        ) {
            if (indicatorWidth > 0f) {
                drawRoundRect(
                    color = Burgundy,
                    topLeft = Offset(indicatorX, 0f),
                    size = Size(indicatorWidth, size.height),
                    cornerRadius = CornerRadius(size.height, size.height)
                )
            }
        }
    }
}

@Composable
private fun NavigationLabel(
    label: String,
    selected: Boolean = false,
    height: androidx.compose.ui.unit.Dp,
    compact: Boolean,
    onMeasured: (Float, Float) -> Unit,
    onClick: () -> Unit
) {
    Box(
        modifier = Modifier.width(if (compact) 78.dp else 96.dp)
            .height(height)
            .onGloballyPositioned { onMeasured(it.positionInRoot().x, it.size.width.toFloat()) }
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = label, color = Ink, fontSize = if (compact) 17.sp else 22.sp,
            fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal
        )
    }
}

private data class NavigationIndicatorTarget(val x: Float, val width: Float)

