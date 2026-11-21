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
fun FeaturesPage(animationKey: String) = FeaturesPageContent(animationKey)

private data class WorkflowFeature(val title: String, val description: String, val image: String)

private val workflowFeatures = listOf(
    WorkflowFeature("Video Input", "Upload short (5–20s) silent video\nfor Foley generation.", "images/feature-video-input.png"),
    WorkflowFeature("AI Sound Generation", "Generate realistic, context-aware\nFoley sound using AI Foley Studio.", "images/feature-ai-sound.png"),
    WorkflowFeature("Audio Post-Processing", "Auto timing correction, trimming\nand loudness normalization.", "images/feature-audio-processing.png"),
    WorkflowFeature("Video Export", "Merge the generated audio with\nyour video and export as MP4.", "images/feature-video-export.png"),
    WorkflowFeature("Output Validation", "Automatically verify the final video\nfor quality and compatibility.", "images/feature-output-validation.png"),
    WorkflowFeature("Fast & Offline", "Runs locally on Windows with\nno cloud or internet dependency.", "images/feature-fast-offline.png")
)

@Composable
private fun FeaturesPageContent(animationKey: String) {
    var revealed by remember(animationKey) { mutableStateOf(false) }
    LaunchedEffect(animationKey) { revealed = true }
    val heroAlpha by animateFloatAsState(
        targetValue = if (revealed) 1f else 0f,
        animationSpec = tween(520, easing = FastOutSlowInEasing), label = "featuresHeroAlpha"
    )
    val heroSlide by animateDpAsState(
        targetValue = if (revealed) 0.dp else 44.dp,
        animationSpec = tween(620, easing = FastOutSlowInEasing), label = "featuresHeroSlide"
    )
    val featuresFloat = rememberInfiniteTransition(label = "featuresHeroFloat")
    val heroFloat by featuresFloat.animateFloat(
        initialValue = -7f,
        targetValue = 7f,
        animationSpec = infiniteRepeatable(
            animation = tween(1067, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "featuresHeroFloatY"
    )
    BoxWithConstraints(modifier = Modifier.fillMaxWidth().background(CanvasCream)) {
        val compact = maxWidth < 1250.dp
        Column(modifier = Modifier.fillMaxWidth()) {
            Box(
                modifier = Modifier.fillMaxWidth().height(if (compact) 350.dp else 380.dp)
                    .padding(horizontal = if (compact) 52.dp else 96.dp)
            ) {
                Image(
                    painter = painterResource("images/features-hero.png"),
                    contentDescription = "AI Foley Studio workflow",
                    modifier = Modifier.align(Alignment.BottomEnd)
                        .width(if (compact) 570.dp else 660.dp)
                        .height(if (compact) 316.dp else 365.dp)
                        .graphicsLayer {
                            alpha = heroAlpha
                            val pop = if (revealed) 1f else .94f
                            scaleX = pop
                            scaleY = pop
                            translationY = heroSlide.toPx() + heroFloat.dp.toPx()
                        },
                    contentScale = ContentScale.Fit
                )
                Column(
                    modifier = Modifier.align(Alignment.CenterStart).widthIn(max = if (compact) 610.dp else 760.dp)
                        .graphicsLayer { alpha = heroAlpha; translationY = heroSlide.toPx() }
                ) {
                    Image(
                        painter = painterResource("images/eyebrow-logo.png"),
                        contentDescription = "AI-Powered Foley Generation",
                        modifier = Modifier.width(if (compact) 290.dp else 362.dp).height(if (compact) 45.dp else 56.dp),
                        contentScale = ContentScale.Fit
                    )
                    Spacer(Modifier.height(18.dp))
                    Text(
                        text = "Powerful Features for",
                        color = Ink,
                        fontSize = if (compact) 42.sp else 50.sp,
                        lineHeight = if (compact) 48.sp else 57.sp,
                        fontWeight = FontWeight.Black,
                        letterSpacing = (-1).sp
                    )
                    Text(
                        text = "AI Foley Generation",
                        color = Copper,
                        fontSize = if (compact) 42.sp else 50.sp,
                        lineHeight = if (compact) 48.sp else 57.sp,
                        fontWeight = FontWeight.Black,
                        letterSpacing = (-1).sp
                    )
                    Spacer(Modifier.height(12.dp))
                    Text(
                        text = "A complete, intelligent workflow to generate, process\nand export realistic sound for your videos.",
                        color = Color(0xFF554640),
                        fontSize = if (compact) 15.sp else 17.sp,
                        lineHeight = if (compact) 22.sp else 25.sp
                    )
                }
            }
            WorkflowGrid(revealed, compact)
        }
    }
}

@Composable
private fun WorkflowGrid(revealed: Boolean, compact: Boolean) {
    Column(
        modifier = Modifier.fillMaxWidth().background(Sand)
            .padding(horizontal = if (compact) 44.dp else 96.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            WorkflowCard(workflowFeatures[0], Modifier.weight(1f), revealed, 0)
            WorkflowCard(workflowFeatures[1], Modifier.weight(1f), revealed, 1)
            WorkflowCard(workflowFeatures[2], Modifier.weight(1f), revealed, 2)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            WorkflowCard(workflowFeatures[3], Modifier.weight(1f), revealed, 3)
            WorkflowCard(workflowFeatures[4], Modifier.weight(1f), revealed, 4)
            WorkflowCard(workflowFeatures[5], Modifier.weight(1f), revealed, 5)
        }
    }
}

@Composable
private fun WorkflowCard(feature: WorkflowFeature, modifier: Modifier, revealed: Boolean, index: Int) {
    val cardAlpha by animateFloatAsState(
        targetValue = if (revealed) 1f else 0f,
        animationSpec = tween(520, delayMillis = 180 + index * 85, easing = FastOutSlowInEasing), label = "workflowCardAlpha$index"
    )
    val cardSlide by animateDpAsState(
        targetValue = if (revealed) 0.dp else 25.dp,
        animationSpec = tween(520, delayMillis = 180 + index * 85, easing = FastOutSlowInEasing), label = "workflowCardSlide$index"
    )
    val cardScale by animateFloatAsState(
        targetValue = if (revealed) 1f else .90f,
        animationSpec = tween(520, delayMillis = 180 + index * 85, easing = FastOutSlowInEasing), label = "workflowCardPop$index"
    )
    Row(
        modifier = modifier.height(112.dp)
            .graphicsLayer { alpha = cardAlpha; translationY = cardSlide.toPx(); scaleX = cardScale; scaleY = cardScale }
            .clip(RoundedCornerShape(22.dp)).background(CanvasCream)
            .border(2.dp, CardBorder, RoundedCornerShape(22.dp)).padding(horizontal = 16.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(13.dp)
    ) {
        Image(
            painter = painterResource(feature.image), contentDescription = null,
            modifier = Modifier.size(62.dp), contentScale = ContentScale.Fit
        )
        Column {
            Text(feature.title, color = Ink, fontSize = 16.sp, lineHeight = 19.sp, fontWeight = FontWeight.ExtraBold)
            Spacer(Modifier.height(3.dp))
            Text(feature.description, color = Color(0xFF554640), fontSize = 10.sp, lineHeight = 13.sp)
        }
    }
}

