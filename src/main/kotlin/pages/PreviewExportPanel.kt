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
private fun PreviewPicture(player: PreviewPlayer, modifier: Modifier) {
    val frame = player.frame
    if (frame != null) {
        Image(frame, null, modifier, contentScale = ContentScale.Fit)
    } else {
        Image(painterResource("images/studio-preview-hero.png"), null, modifier, contentScale = ContentScale.Fit)
    }
}

@Composable
private fun PreviewControls(
    playing: Boolean, muted: Boolean, progress: () -> Float, totalSeconds: Float, isFullscreen: Boolean,
    onTogglePlay: () -> Unit, onToggleMute: () -> Unit, onToggleFullscreen: () -> Unit, onSeek: (Float) -> Unit,
    modifier: Modifier = Modifier
) {
    Column(modifier) {
        Box(Modifier.fillMaxWidth().height(14.dp).pointerInput(Unit) {
            detectTapGestures { tap -> onSeek((tap.x / size.width).coerceIn(0f, 1f)) }
        }, contentAlignment = Alignment.CenterStart) {
            Box(Modifier.fillMaxWidth().height(4.dp).clip(RoundedCornerShape(5.dp)).background(Color(0x99FFFFFF))) {
                Box(Modifier.fillMaxWidth(progress().coerceIn(0f, 1f)).fillMaxHeight().background(Color.White))
            }
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(if (playing) "❚❚" else "▶", color = Color.White, fontSize = 17.sp,
                modifier = Modifier.clickable(onClick = onTogglePlay).padding(6.dp))
            Text("${(progress() * totalSeconds).toInt()} / ${totalSeconds.toInt()}s", color = Color.White, fontSize = 11.sp)
            Spacer(Modifier.weight(1f))
            Text(if (muted) "🔇" else "🔊", color = Color.White, fontSize = 13.sp,
                modifier = Modifier.clickable(onClick = onToggleMute).padding(6.dp))
            Text(if (isFullscreen) "✕" else "⛶", color = Color.White, fontSize = 15.sp,
                modifier = Modifier.clickable(onClick = onToggleFullscreen).padding(6.dp))
        }
    }
}

@Composable
internal fun StudioExportPanel(
    modifier: Modifier,
    revealed: Boolean,
    index: Int,
    message: String,
    generating: Boolean,
    generationProgress: Float,
    player: PreviewPlayer,
    source: File?,
    fallbackDurationSeconds: Float,
    onPreview: () -> Unit,
    onDownload: () -> Unit
) {
    val videoInteraction = remember { MutableInteractionSource() }
    val videoHovered by videoInteraction.collectIsHoveredAsState()
    val controlsAlpha by animateFloatAsState(if (videoHovered) 1f else 0f, tween(170, easing = FastOutSlowInEasing), label = "videoControlsAlpha")
    val controlsOffset by animateDpAsState(if (videoHovered) 0.dp else 8.dp, tween(170, easing = FastOutSlowInEasing), label = "videoControlsOffset")
    val displayedProgress by animateFloatAsState(
        targetValue = generationProgress.coerceIn(0f, 100f),
        // The backend reports progress per processing stage/chunk, so values can legitimately
        // jump. Ease each update over a few seconds rather than visibly snapping at 5% or 65%.
        animationSpec = tween(3_500, easing = FastOutSlowInEasing),
        label = "generationProgress"
    )
    var fullscreen by remember { mutableStateOf(false) }
    // Real length reported by the player once the video is loaded; until then the length read from the file
    val totalSeconds = if (player.lengthSeconds > 0f) player.lengthSeconds else fallbackDurationSeconds

    if (fullscreen) {
        val screen = remember { Toolkit.getDefaultToolkit().screenSize }
        Dialog(
            onCloseRequest = { fullscreen = false },
            state = rememberDialogState(position = WindowPosition(0.dp, 0.dp), size = DpSize(screen.width.dp, screen.height.dp)),
            undecorated = true,
            resizable = false,
            onKeyEvent = { event ->
                if (event.key == Key.Escape && event.type == KeyEventType.KeyUp) { fullscreen = false; true } else false
            }
        ) {
            CompositionLocalProvider(LocalTextStyle provides TextStyle(fontFamily = Poppins)) {
                Box(Modifier.fillMaxSize().background(Color(0xFF1B100B)), contentAlignment = Alignment.Center) {
                    PreviewPicture(player, Modifier.fillMaxSize().padding(bottom = 90.dp))
                    PreviewControls(
                        player.playing, player.muted, { player.progress }, totalSeconds, true,
                        { player.togglePlay(source) }, { player.toggleMute() }, { fullscreen = false }, { player.seek(it) },
                        Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(horizontal = 48.dp, vertical = 28.dp)
                    )
                }
            }
        }
    }

    StudioPanel(modifier, revealed, index) {
        StudioPanelTitle("Preview & Export", "images/studio-preview-export.png")
        Spacer(Modifier.height(17.dp))
        // Preview shrinks on short windows (instead of pushing the 3rd button out of the panel)
        Box(
            Modifier.fillMaxWidth().weight(1f, fill = false).heightIn(min = 90.dp, max = 190.dp)
                .clip(RoundedCornerShape(16.dp)).background(Color(0xFF352118))
                .hoverable(videoInteraction)
                .clickable(interactionSource = videoInteraction, indication = null, enabled = !generating) { player.togglePlay(source) },
            contentAlignment = Alignment.Center
        ) {
            PreviewPicture(player, Modifier.fillMaxSize().padding(7.dp))
            PreviewControls(
                player.playing, player.muted, { player.progress }, totalSeconds, false,
                { player.togglePlay(source) }, { player.toggleMute() }, { fullscreen = true }, { player.seek(it) },
                Modifier.align(Alignment.BottomCenter).graphicsLayer { alpha = controlsAlpha; translationY = controlsOffset.toPx() }
                    .fillMaxWidth().padding(horizontal = 10.dp, vertical = 6.dp)
            )
            if (generating) {
                PreviewBufferingOverlay(message, displayedProgress, Modifier.fillMaxSize())
            }
        }
        Spacer(Modifier.height(12.dp))
        Text(
            player.notice ?: message, color = Copper, fontSize = 12.sp, fontWeight = FontWeight.Medium,
            maxLines = 3, overflow = TextOverflow.Ellipsis
        )
        if (generating) {
            Spacer(Modifier.height(6.dp))
            Box(Modifier.fillMaxWidth().height(6.dp).clip(RoundedCornerShape(8.dp)).background(Color(0xFFF4C693))) {
                Box(Modifier.fillMaxWidth(displayedProgress / 100f).fillMaxHeight().background(Copper))
            }
        }
        Spacer(Modifier.height(9.dp))
        StudioAction("Preview", "images/studio-preview.png", Burgundy) { onPreview() }
        Spacer(Modifier.height(9.dp))
        StudioOutlineAction("Download MP4", "images/studio-download.png", onClick = onDownload)
    }
}

@Composable
internal fun StudioPanel(modifier: Modifier, revealed: Boolean, index: Int, content: @Composable androidx.compose.foundation.layout.ColumnScope.() -> Unit) {
    val panelAlpha by animateFloatAsState(if (revealed) 1f else 0f, tween(450, 130 + index * 100, FastOutSlowInEasing), label = "studioPanelAlpha$index")
    val offset by animateDpAsState(if (revealed) 0.dp else 25.dp, tween(540, 130 + index * 100, FastOutSlowInEasing), label = "studioPanelOffset$index")
    val scale by animateFloatAsState(if (revealed) 1f else .93f, tween(540, 130 + index * 100, FastOutSlowInEasing), label = "studioPanelScale$index")
    Column(modifier.graphicsLayer { alpha = panelAlpha; translationY = offset.toPx(); scaleX = scale; scaleY = scale }.clip(RoundedCornerShape(24.dp)).background(Sand).border(2.dp, CardBorder, RoundedCornerShape(24.dp)).padding(18.dp), content = content)
}

@Composable
internal fun StudioPanelTitle(title: String, image: String) = Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(11.dp)) {
    Image(painterResource(image), null, Modifier.size(52.dp), contentScale = ContentScale.Fit)
    Text(title, color = Ink, fontSize = 21.sp, fontWeight = FontWeight.ExtraBold)
}

@Composable
internal fun StudioSlider(progress: Float, onValueChange: (Float) -> Unit, valueField: @Composable () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        BoxWithConstraints(
            Modifier.weight(1f).height(30.dp).pointerInput(Unit) {
                detectTapGestures { point ->
                    onValueChange((point.x / size.width.toFloat()).coerceIn(0f, 1f))
                }
            }.pointerInput(Unit) {
                detectDragGestures(
                    onDragStart = { point -> onValueChange((point.x / size.width.toFloat()).coerceIn(0f, 1f)) },
                    onDrag = { change, _ ->
                        onValueChange((change.position.x / size.width.toFloat()).coerceIn(0f, 1f))
                    }
                )
            }
        ) {
            Box(Modifier.align(Alignment.CenterStart).fillMaxWidth().height(6.dp).clip(RoundedCornerShape(8.dp)).background(Color(0xFFF4C693))) {
                Box(Modifier.fillMaxWidth(progress).fillMaxHeight().background(Copper))
            }
            Box(Modifier.align(Alignment.CenterStart).offset(x = (maxWidth - 22.dp) * progress).size(22.dp).clip(RoundedCornerShape(50)).background(Copper))
        }
        valueField()
    }
}

@Composable
private fun PreviewBufferingOverlay(message: String, progress: Float, modifier: Modifier = Modifier) {
    val transition = rememberInfiniteTransition(label = "previewBuffering")
    val rotation by transition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(tween(850, easing = LinearEasing)),
        label = "previewBufferingRotation"
    )
    Box(modifier.background(Color(0xCC1B100B)), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Image(
                painterResource("images/studio-buffering.png"),
                contentDescription = "Processing",
                modifier = Modifier.size(46.dp).graphicsLayer { rotationZ = rotation },
                contentScale = ContentScale.Fit
            )
            Spacer(Modifier.height(11.dp))
            Text("Processing your video", color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
            Text("${progress.toInt()}% · ${message.substringBefore(" — ")}", color = HeaderPeach, fontSize = 11.sp, maxLines = 1)
        }
    }
}

@Composable
internal fun StudioNumericInput(value: String, suffix: String, onSubmit: () -> Unit = {}, onValueChange: (String) -> Unit) {
    val focusManager = LocalFocusManager.current
    Row(Modifier.clip(RoundedCornerShape(8.dp)).background(Color.White).border(1.dp, CardBorder, RoundedCornerShape(8.dp)).padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        BasicTextField(
            value = value,
            onValueChange = onValueChange,
            textStyle = TextStyle(color = Ink, fontSize = 14.sp, fontFamily = Poppins),
            modifier = Modifier.width(38.dp).onKeyEvent { event ->
                if (event.key == Key.Enter && event.type == KeyEventType.KeyUp) {
                    onSubmit()
                    focusManager.clearFocus()
                    true
                } else {
                    false
                }
            }
        )
        Text(suffix, color = Ink, fontSize = 14.sp)
    }
}

@Composable
private fun StudioModeButton(label: String, image: String, selected: Boolean, modifier: Modifier, onClick: () -> Unit) {
    Row(modifier.height(52.dp).clip(RoundedCornerShape(26.dp)).background(Color.Transparent).clickable(onClick = onClick), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center) {
        Image(painterResource(image), null, Modifier.size(22.dp), contentScale = ContentScale.Fit)
        Spacer(Modifier.width(6.dp)); Text(label, color = if (selected) Color.White else Copper, fontSize = 15.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
internal fun StudioAction(label: String, image: String, color: Color, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val hovered by interaction.collectIsHoveredAsState()
    val lift by animateDpAsState(if (enabled && hovered) (-4).dp else 0.dp, tween(160, easing = FastOutSlowInEasing), label = "studioHover$label")
    Row(modifier.fillMaxWidth().graphicsLayer { translationY = lift.toPx() }.shadow(if (enabled && hovered) 7.dp else 0.dp, RoundedCornerShape(16.dp)).then(if (enabled) Modifier.hoverable(interaction).clickable(interactionSource = interaction, indication = null, onClick = onClick) else Modifier).height(49.dp).clip(RoundedCornerShape(16.dp)).background(if (enabled) color else Color(0xFFBFA8A0)), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center) {
        Image(painterResource(image), null, Modifier.size(24.dp), contentScale = ContentScale.Fit)
        Spacer(Modifier.width(8.dp)); Text(label, color = Color.White, fontSize = 16.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
internal fun StudioOutlineAction(label: String, image: String, modifier: Modifier = Modifier, enabled: Boolean = true, onClick: () -> Unit) {
    val interaction = remember { MutableInteractionSource() }
    val hovered by interaction.collectIsHoveredAsState()
    val lift by animateDpAsState(if (enabled && hovered) (-4).dp else 0.dp, tween(160, easing = FastOutSlowInEasing), label = "studioOutlineHover$label")
    Row(modifier.fillMaxWidth().graphicsLayer { translationY = lift.toPx() }.shadow(if (enabled && hovered) 7.dp else 0.dp, RoundedCornerShape(16.dp)).then(if (enabled) Modifier.hoverable(interaction).clickable(interactionSource = interaction, indication = null, onClick = onClick) else Modifier).height(49.dp).clip(RoundedCornerShape(16.dp)).background(if (enabled) CanvasCream else Color(0xFFF4E5D8)).border(2.dp, Color(0xFFF4C693), RoundedCornerShape(16.dp)), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center) {
        Image(painterResource(image), null, Modifier.size(23.dp), contentScale = ContentScale.Fit)
        Spacer(Modifier.width(7.dp)); Text(if (enabled) label else "🔒 Analyse first", color = if (enabled) Ink else Color(0xFF8C7669), fontSize = 15.sp, fontWeight = FontWeight.Bold)
    }
}

internal fun Modifier.dottedStudioBorder(shape: RoundedCornerShape): Modifier = drawBehind {
    val stroke = 2.dp.toPx()
    drawRoundRect(
        color = Color(0xFFF4C493),
        topLeft = Offset(stroke / 2, stroke / 2),
        size = Size(size.width - stroke, size.height - stroke),
        cornerRadius = CornerRadius(18.dp.toPx()),
        style = Stroke(
            width = stroke,
            cap = StrokeCap.Round,
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(1.dp.toPx(), 6.dp.toPx()))
        )
    )
}

