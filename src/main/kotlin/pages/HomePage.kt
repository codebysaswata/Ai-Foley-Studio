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
fun HomePage(animationKey: String, onNavigate: (String) -> Unit, modifier: Modifier = Modifier) {
    Column(modifier.verticalScroll(rememberScrollState())) {
        Hero(animationKey, onNavigate)
        FeatureStrip()
    }
}

@Composable
private fun Hero(
    animationKey: String,
    onNavigate: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    var heroArtworkVisible by remember(animationKey) { mutableStateOf(false) }
    LaunchedEffect(animationKey) { heroArtworkVisible = true }
    val entranceAlpha by animateFloatAsState(
        targetValue = if (heroArtworkVisible) 1f else 0f,
        animationSpec = tween(durationMillis = 620, easing = FastOutSlowInEasing),
        label = "heroArtworkAlpha"
    )
    val entranceOffset by animateDpAsState(
        targetValue = if (heroArtworkVisible) 0.dp else 54.dp,
        animationSpec = tween(durationMillis = 720, easing = FastOutSlowInEasing),
        label = "heroArtworkOffset"
    )
    val entranceScale by animateFloatAsState(
        targetValue = if (heroArtworkVisible) 1f else 0.92f,
        animationSpec = tween(durationMillis = 720, easing = FastOutSlowInEasing),
        label = "heroArtworkScale"
    )
    val floatTransition = rememberInfiniteTransition(label = "heroArtworkFloat")
    val idleFloat by floatTransition.animateFloat(
        initialValue = -7f,
        targetValue = 7f,
        animationSpec = infiniteRepeatable(
            animation = tween(durationMillis = 1067, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "heroArtworkIdleFloat"
    )
    BoxWithConstraints(modifier = modifier.fillMaxWidth().background(CanvasCream)) {
        val heroHeight = when {
            maxWidth < 720.dp -> 510.dp
            maxWidth < 1150.dp -> 525.dp
            maxWidth < 1450.dp -> 545.dp
            else -> 560.dp
        }
        val compact = maxWidth < 1450.dp
        val narrow = maxWidth < 1000.dp
        Box(Modifier.fillMaxWidth().height(heroHeight)) {
        Image(
            painter = painterResource("images/hero-decoration.png"),
            contentDescription = null,
            modifier = Modifier
                .align(if (compact) Alignment.BottomEnd else Alignment.CenterEnd)
                .padding(end = if (narrow) (-80).dp else if (compact) 4.dp else 28.dp,
                    bottom = if (narrow) 2.dp else if (compact) 18.dp else 0.dp)
                // animated values are read in the draw phase -> no recomposition per frame
                .graphicsLayer {
                    alpha = entranceAlpha
                    scaleX = entranceScale
                    scaleY = entranceScale
                    translationY = entranceOffset.toPx() + idleFloat.dp.toPx()
                }
                .width(if (narrow) 500.dp else if (compact) 630.dp else 790.dp)
                .height(if (narrow) 276.dp else if (compact) 348.dp else 437.dp),
            contentScale = ContentScale.Fit,
            alpha = if (narrow) 0.18f else if (compact) 0.6f else 1f
        )
        Column(
            modifier = Modifier.align(Alignment.CenterStart)
                .widthIn(max = if (narrow) 860.dp else if (compact) 900.dp else 980.dp)
                .padding(start = if (narrow) 32.dp else if (compact) 54.dp else 96.dp, top = 0.dp),
            horizontalAlignment = Alignment.Start
        ) {
            Image(
                painter = painterResource("images/eyebrow-logo.png"),
                contentDescription = "AI-Powered Foley Generation",
                modifier = Modifier.width(if (narrow) 272.dp else 362.dp)
                    .height(if (narrow) 42.dp else 56.dp), contentScale = ContentScale.Fit
            )
            Spacer(Modifier.height(if (narrow) 14.dp else 20.dp))
            Text(
                text = "Ai Foley Studio", color = Burgundy,
                fontSize = if (narrow) 50.sp else if (compact) 63.sp else 72.sp,
                lineHeight = if (narrow) 54.sp else if (compact) 68.sp else 78.sp,
                fontWeight = FontWeight.Black, letterSpacing = (-2).sp
            )
            Spacer(Modifier.height(11.dp))
            Text(
                text = "Bring Your Videos to Life", color = Ink,
                fontSize = if (narrow) 33.sp else if (compact) 39.sp else 44.sp,
                lineHeight = if (narrow) 38.sp else if (compact) 46.sp else 51.sp,
                fontWeight = FontWeight.SemiBold, letterSpacing = (-1).sp
            )
            Text(
                text = buildAnnotatedString {
                    append("with ")
                    pushStyle(SpanStyle(color = Copper, fontWeight = FontWeight.ExtraBold))
                    append("AI-Powered")
                    pop()
                    append(" Sound Effects")
                },
                color = Ink, fontSize = if (narrow) 33.sp else if (compact) 39.sp else 44.sp,
                lineHeight = if (narrow) 38.sp else if (compact) 46.sp else 51.sp,
                fontWeight = FontWeight.SemiBold, letterSpacing = (-1).sp
            )
            Spacer(Modifier.height(if (narrow) 12.dp else 17.dp))
            Text(
                text = "Generate realistic and high-quality Foley sound\nfor your videos, effortlessly.",
                color = Color(0xFF554640), fontSize = if (narrow) 15.sp else 18.sp,
                lineHeight = if (narrow) 22.sp else 27.sp
            )
            Spacer(Modifier.height(if (narrow) 18.dp else 23.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(if (narrow) 12.dp else 20.dp)) {
                StaticButton("Try it now  →", dark = true, enableHoverLift = true,
                    padding = PaddingValues(horizontal = if (narrow) 20.dp else 30.dp, vertical = if (narrow) 13.dp else 19.dp),
                    fontSize = if (narrow) 15.sp else 20.sp,
                    onClick = { onNavigate("Get Started") })
                StaticButton("Learn More", dark = false, enableHoverLift = true,
                    padding = PaddingValues(horizontal = if (narrow) 20.dp else 30.dp, vertical = if (narrow) 13.dp else 19.dp),
                    fontSize = if (narrow) 15.sp else 20.sp,
                    onClick = { onNavigate("About") })
            }
        }
        }
    }
}

private data class Feature(val title: String, val detail: String, val image: String)

private val features = listOf(
    Feature("AI-Powered\nGeneration", "Context-aware sounds\nfor every scene.", "images/feature-ai-generation.png"),
    Feature("High Quality\nAudio", "Crisp, cinematic results\nready for your edit.", "images/feature-audio.png"),
    Feature("Easy to\nUse", "Describe the moment,\nthen bring it to life.", "images/feature-easy.png"),
    Feature("Perfect for\nAI-Creators", "A faster sound workflow\nfor every storyteller.", "images/feature-creators.png")
)

@Composable
internal fun FeatureStrip(modifier: Modifier = Modifier) {
    var cardsVisible by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { cardsVisible = true }
    BoxWithConstraints(modifier = modifier.fillMaxWidth().background(Sand)) {
        val medium = maxWidth < 1250.dp
        val narrow = maxWidth < 720.dp
        val cardHeight = if (narrow) 128.dp else if (medium) 136.dp else 128.dp
        Column(
            modifier = Modifier.fillMaxWidth().padding(
                horizontal = if (narrow) 24.dp else if (medium) 42.dp else 82.dp,
                vertical = if (narrow) 16.dp else 10.dp
            ),
            verticalArrangement = Arrangement.spacedBy(if (narrow) 12.dp else 14.dp)
        ) {
            if (narrow) {
                features.forEachIndexed { index, feature ->
                    FeatureCard(feature, Modifier.fillMaxWidth(), cardHeight, cardsVisible, index)
                }
            } else if (medium) {
                Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                    FeatureCard(features[0], Modifier.weight(1f), cardHeight, cardsVisible, 0)
                    FeatureCard(features[1], Modifier.weight(1f), cardHeight, cardsVisible, 1)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                    FeatureCard(features[2], Modifier.weight(1f), cardHeight, cardsVisible, 2)
                    FeatureCard(features[3], Modifier.weight(1f), cardHeight, cardsVisible, 3)
                }
            } else {
                Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) {
                    FeatureCard(features[0], Modifier.weight(1f), cardHeight, cardsVisible, 0)
                    FeatureCard(features[1], Modifier.weight(1f), cardHeight, cardsVisible, 1)
                    FeatureCard(features[2], Modifier.weight(1f), cardHeight, cardsVisible, 2)
                    FeatureCard(features[3], Modifier.weight(1f), cardHeight, cardsVisible, 3)
                }
            }
        }
    }
}

@Composable
private fun FeatureCard(
    feature: Feature,
    modifier: Modifier,
    height: androidx.compose.ui.unit.Dp,
    visible: Boolean,
    index: Int
) {
    val cardAlpha by animateFloatAsState(
        targetValue = if (visible) 1f else 0f,
        animationSpec = tween(360, delayMillis = 180 + index * 90, easing = FastOutSlowInEasing),
        label = "homeFeatureAlpha$index"
    )
    val cardOffset by animateDpAsState(
        targetValue = if (visible) 0.dp else 28.dp,
        animationSpec = tween(520, delayMillis = 180 + index * 100, easing = FastOutSlowInEasing),
        label = "homeFeatureSlide$index"
    )
    val cardScale by animateFloatAsState(
        targetValue = if (visible) 1f else .90f,
        animationSpec = tween(520, delayMillis = 180 + index * 100, easing = FastOutSlowInEasing),
        label = "homeFeaturePop$index"
    )
    Row(
        modifier = modifier.height(height)
            .graphicsLayer { alpha = cardAlpha; translationY = cardOffset.toPx(); scaleX = cardScale; scaleY = cardScale }
            .clip(RoundedCornerShape(25.dp)).background(CanvasCream)
            .border(2.dp, CardBorder, RoundedCornerShape(25.dp)).padding(horizontal = 20.dp, vertical = 13.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        Image(
            painter = painterResource(feature.image), contentDescription = null,
            modifier = Modifier.size(if (height <= 130.dp) 72.dp else 80.dp), contentScale = ContentScale.Fit
        )
        Column {
            Text(feature.title, color = Ink, fontSize = 18.sp, lineHeight = 22.sp, fontWeight = FontWeight.ExtraBold)
            Spacer(Modifier.height(5.dp))
            Text(feature.detail, color = Color(0xFF66524A), fontSize = 11.sp, lineHeight = 15.sp)
        }
    }
}

