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
fun GetStartedPage(animationKey: String, selectedVideo: File?, onSelectedVideoChange: (File?) -> Unit, generatedVideo: File?, onGeneratedVideoChange: (File?) -> Unit) = GenerationStudioContent(animationKey, selectedVideo, onSelectedVideoChange, generatedVideo, onGeneratedVideoChange)

@Composable
private fun GenerationStudioContent(
    animationKey: String,
    selectedVideo: File?,
    onSelectedVideoChange: (File?) -> Unit,
    generatedVideo: File?,
    onGeneratedVideoChange: (File?) -> Unit
) {
    var revealed by remember(animationKey) { mutableStateOf(false) }
    var analysed by remember { mutableStateOf(false) }
    var chunkDurationSeconds by remember { mutableStateOf(4) }
    var volume by remember { mutableStateOf(.5f) }
    var generationMessage by remember { mutableStateOf("Ready to create your Foley audio") }
    var generationProgress by remember { mutableStateOf(0f) }
    LaunchedEffect(animationKey) { revealed = true }

    val scope = rememberCoroutineScope()
    var generating by remember { mutableStateOf(false) }
    val latestVideo by rememberUpdatedState(selectedVideo)
    val player = remember { PreviewPlayer() }
    DisposableEffect(Unit) { onDispose { player.release() } }

    // What the preview plays: the generated MP4 once it exists, otherwise the uploaded video
    val source = generatedVideo ?: selectedVideo
    LaunchedEffect(source) {
        player.stop()
        source?.let { player.loadThumbnail(it) }
    }
    LaunchedEffect(volume) { player.setVolume(volume) }

    // Real length of that video (0 until a video is chosen)
    val videoDuration by produceState(0f, source) {
        value = 0f
        value = source?.let { video -> withContext(Dispatchers.IO) { readVideoDurationSeconds(video) } } ?: 0f
    }

    // Uploads the MP4 file to the backend (as a file, not base64) and keeps the MP4 it sends back
    fun generate() {
        val video = selectedVideo
        if (video == null) { generationMessage = "Select a video first"; return }
        if (generating) return
        generating = true
        generationProgress = 0f
        player.stop()
        generationMessage = "Checking backend connection…"
        scope.launch {
            val result = runCatching {
                BackendApi(BackendConfig.load()).use { api ->
                    if (!api.checkReady()) error("Backend is not ready at ${BackendConfig.load().baseUrl}.")
                    generationMessage = "Uploading original video…"
                    generationProgress = 2f
                    val created = api.createJob(video, "", chunkDurationSeconds)
                    while (true) {
                        val job = api.job(created.id)
                        generationProgress = job.progressPercent.coerceIn(0f, 100f)
                        generationMessage = when (job.status) {
                            "queued" -> "Queued for generation…"
                            "running" -> "${job.stage ?: "Generating Foley audio"} — ${job.progressPercent.toInt()}%"
                            "succeeded" -> "Downloading generated result…"
                            "failed", "cancelled" -> error(job.error ?: "Foley generation ${job.status}.")
                            else -> "Processing…"
                        }
                        if (job.status == "succeeded") {
                            val artifact = api.artifacts(created.id).firstOrNull {
                                it.mediaType.equals("video/mp4", true) || it.name.endsWith(".mp4", true)
                            } ?: error("The job finished but did not provide an MP4 artifact.")
                            return@use api.download(artifact)
                        }
                        delay(1_500)
                    }
                    error("Job polling stopped unexpectedly.")
                }
            }
            generating = false
            if (latestVideo != video) return@launch   // the video was changed while we waited
            result.onSuccess {
                onGeneratedVideoChange(it)
                generationProgress = 100f
                generationMessage = "Your Foley video is ready — press Preview or Download MP4"
            }.onFailure {
                generationProgress = 0f
                generationMessage = "Generation failed. " + (it.message ?: "Unknown error").take(110)
            }
        }
    }

    fun startPreview() {
        val video = source
        if (video == null) { generationMessage = "Upload a video first"; return }
        player.play(video)
    }

    fun download() {
        val result = generatedVideo
        if (result == null) { generationMessage = "Generate your video first, then download it"; return }
        runCatching { saveMp4As(result, "AI_Foley_${selectedVideo?.nameWithoutExtension ?: "video"}.mp4") }
            .onSuccess { saved -> if (saved != null) generationMessage = "Saved as ${saved.name}" }
            .onFailure { generationMessage = "Could not save the file. " + (it.message ?: "").take(80) }
    }
    val headerAlpha by animateFloatAsState(if (revealed) 1f else 0f, tween(480, easing = FastOutSlowInEasing), label = "studioHeaderAlpha")
    val headerOffset by animateDpAsState(if (revealed) 0.dp else 30.dp, tween(580, easing = FastOutSlowInEasing), label = "studioHeaderOffset")

    BoxWithConstraints(Modifier.fillMaxSize().background(CanvasCream)) {
        val compact = maxWidth < 1450.dp
        val narrow = maxWidth < 1120.dp
        val horizontal = if (narrow) 30.dp else if (compact) 54.dp else 82.dp
        // Panels never get shorter than 600dp; on short windows the page scrolls instead of squashing the buttons
        val panelsHeight = (maxHeight - 200.dp).coerceAtLeast(600.dp)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = horizontal)) {
            Box(Modifier.fillMaxWidth().padding(vertical = if (compact) 16.dp else 26.dp)) {
                Column(Modifier.align(Alignment.CenterStart).graphicsLayer { alpha = headerAlpha; translationY = headerOffset.toPx() }) {
                    Image(painterResource("images/studio-get-started.png"), "Get started",
                        Modifier.width(210.dp).height(42.dp), contentScale = ContentScale.Fit)
                    Spacer(Modifier.height(10.dp))
                    Text(buildAnnotatedString {
                        append("Create ")
                        pushStyle(SpanStyle(color = Copper, fontWeight = FontWeight.Black))
                        append("AI Foley Audio")
                        pop()
                        append(" for Your Video")
                    }, color = Ink, fontSize = if (compact) 38.sp else 48.sp, lineHeight = if (compact) 43.sp else 55.sp, fontWeight = FontWeight.Black, letterSpacing = (-1.5).sp)
                    Spacer(Modifier.height(7.dp))
                    Text("Upload a video, analyse it, and bring your video to life with realistic sound effects.",
                        color = Color(0xFF554640), fontSize = if (compact) 14.sp else 17.sp)
                }
            }
            Row(Modifier.fillMaxWidth().padding(bottom = 14.dp).height(panelsHeight), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                StudioSettingsPanel(Modifier.weight(.27f), revealed, 0, chunkDurationSeconds, volume, { chunkDurationSeconds = it }, { volume = it })
                StudioGenerationPanel(Modifier.weight(.46f), revealed, 1, analysed, generating,
                    selectedVideo = selectedVideo, onSelectedVideoChange = onSelectedVideoChange,
                    onVideoChange = {
                        analysed = false
                        onGeneratedVideoChange(null)
                        generationMessage = "Ready to create your Foley audio"
                    },
                    onAnalyse = {
                        analysed = true
                        generationMessage = "Video analysis complete — ready to generate"
                    }
                ) {
                    generate()
                }
                StudioExportPanel(
                    Modifier.weight(.27f), revealed, 2, generationMessage, generating, generationProgress,
                    player, source, videoDuration, { startPreview() }, { download() }
                )
            }
        }
    }
}

@Composable
private fun StudioSettingsPanel(modifier: Modifier, revealed: Boolean, index: Int, chunkDurationSeconds: Int, volume: Float, onChunkDurationChange: (Int) -> Unit, onVolumeChange: (Float) -> Unit) {
    var durationText by remember { mutableStateOf(chunkDurationSeconds.toString()) }
    var volumeText by remember { mutableStateOf((volume * 100).toInt().toString()) }
    StudioPanel(modifier, revealed, index) {
        StudioPanelTitle("Generation Settings", "images/studio-settings.png")
        Spacer(Modifier.height(18.dp))
        Text("Processing Chunk Duration", color = Ink, fontSize = 20.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(12.dp))
        StudioSlider((chunkDurationSeconds - 1) / 7f, { updated ->
            val seconds = (1 + updated * 7f).toInt()
            onChunkDurationChange(seconds)
            durationText = seconds.toString()
        }) {
            StudioNumericInput(durationText, "s") { entered ->
                if (entered.length <= 1 && entered.all { it.isDigit() }) {
                    durationText = entered
                    entered.toIntOrNull()?.let { seconds ->
                        val constrained = seconds.coerceIn(1, 8)
                        onChunkDurationChange(constrained)
                        if (seconds != constrained) durationText = constrained.toString()
                    }
                }
            }
        }
        Text("Splits long videos into 1–8 second processing chunks", color = Color(0xFF554640), fontSize = 12.sp)
        Spacer(Modifier.height(25.dp))
        Text("Preview Volume", color = Ink, fontSize = 20.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(12.dp))
        StudioSlider(volume, { updated ->
            onVolumeChange(updated)
            volumeText = (updated * 100).toInt().toString()
        }) {
            StudioNumericInput(volumeText, "%") { entered ->
                if (entered.length <= 3 && entered.all { it.isDigit() }) {
                    volumeText = entered
                    entered.toFloatOrNull()?.let { percentage -> onVolumeChange((percentage / 100f).coerceIn(0f, 1f)) }
                }
            }
        }
        Text("Adjust the generated-video preview volume", color = Color(0xFF554640), fontSize = 12.sp)
    }
}

@Composable
@OptIn(ExperimentalFoundationApi::class, ExperimentalComposeUiApi::class)
private fun StudioGenerationPanel(
    modifier: Modifier,
    revealed: Boolean,
    index: Int,
    analysed: Boolean,
    generating: Boolean,
    selectedVideo: File?,
    onSelectedVideoChange: (File?) -> Unit,
    onVideoChange: () -> Unit,
    onAnalyse: () -> Unit,
    onGenerate: () -> Unit
) {
    var isDragging by remember { mutableStateOf(false) }
    var uploadError by remember { mutableStateOf("") }
    val bufferingTransition = rememberInfiniteTransition(label = "studioBuffering")
    val bufferingRotation by bufferingTransition.animateFloat(
        initialValue = 0f, targetValue = 360f,
        animationSpec = infiniteRepeatable(tween(800, easing = LinearEasing)),
        label = "studioBufferingRotation"
    )

    val allowedExtensions = setOf("mp4", "mov", "avi", "mkv")

    fun selectVideo(file: File): Boolean {
        if (!file.isFile || file.extension.lowercase() !in allowedExtensions) {
            uploadError = "Unsupported file. Choose MP4, MOV, AVI or MKV."
            return false
        }

        onSelectedVideoChange(file)
        uploadError = ""
        onVideoChange()
        return true
    }

    fun clearVideo() {
        onSelectedVideoChange(null)
        uploadError = ""
        onVideoChange()
    }

    fun openVideoPicker() {
        val chooser = JFileChooser().apply {
            dialogTitle = "Select Your Video"
            isAcceptAllFileFilterUsed = false
            fileFilter = FileNameExtensionFilter(
                "Video Files (MP4, MOV, AVI, MKV)",
                "mp4", "mov", "avi", "mkv"
            )
        }

        if (chooser.showOpenDialog(null) == JFileChooser.APPROVE_OPTION) {
            selectVideo(chooser.selectedFile)
        }
    }

    val dropTarget = remember {
        object : DragAndDropTarget {
            // Highlight only while the cursor is actually over the drop zone
            override fun onEntered(event: DragAndDropEvent) {
                isDragging = true
                uploadError = ""
            }

            override fun onExited(event: DragAndDropEvent) {
                isDragging = false
            }

            override fun onEnded(event: DragAndDropEvent) {
                isDragging = false
            }

            override fun onDrop(event: DragAndDropEvent): Boolean {
                isDragging = false
                val files = runCatching {
                    event.awtTransferable.getTransferData(DataFlavor.javaFileListFlavor) as? List<*>
                }.getOrNull()?.filterIsInstance<File>().orEmpty()

                if (files.isEmpty()) {
                    uploadError = "Could not read the dropped file."
                    return false
                }
                // If several files are dropped, use the first valid video
                val video = files.firstOrNull { it.isFile && it.extension.lowercase() in allowedExtensions }
                return if (video != null) selectVideo(video) else selectVideo(files.first())
            }
        }
    }

    StudioPanel(modifier, revealed, index) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Image(painterResource("images/studio-upload-only.png"), null, Modifier.size(30.dp), contentScale = ContentScale.Fit)
            Column {
                Text("Upload Only", color = Ink, fontSize = 22.sp, fontWeight = FontWeight.ExtraBold)
                Text("Upload a silent video and let AI Foley Studio analyse it automatically.", color = Color(0xFF554640), fontSize = 12.sp)
            }
        }
        Spacer(Modifier.height(14.dp))

        // FRONTEND-ONLY DRAG-AND-DROP UPLOAD AREA
        BoxWithConstraints(
            Modifier.fillMaxWidth().weight(1f)
                .clip(RoundedCornerShape(18.dp))
                .background(
                    when {
                        isDragging -> Color(0xFFFFE4CA)
                        selectedVideo != null -> Color(0xFFFFF1E3)
                        else -> Color(0xFFFFF8F0)
                    }
                )
                .border(
                    width = if (isDragging) 2.dp else 1.dp,
                    color = if (isDragging) Burgundy else CardBorder,
                    shape = RoundedCornerShape(18.dp)
                )
                .dottedStudioBorder(RoundedCornerShape(18.dp))
                .clickable(
                    interactionSource = remember { MutableInteractionSource() },
                    indication = null,
                    enabled = selectedVideo == null
                ) { openVideoPicker() }
                .dragAndDropTarget(
                    shouldStartDragAndDrop = { event ->
                        event.awtTransferable.isDataFlavorSupported(DataFlavor.javaFileListFlavor)
                    },
                    target = dropTarget
                )
                .padding(8.dp),
            contentAlignment = Alignment.Center
        ) {
            // Short zone (e.g. Prompt mode): shrink content so the button is never clipped
            val tight = maxHeight < 235.dp
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                if (generating) {
                    Image(
                        painterResource("images/studio-buffering.png"), "Generating",
                        Modifier.size(if (tight) 34.dp else 48.dp).graphicsLayer { rotationZ = bufferingRotation },
                        contentScale = ContentScale.Fit
                    )
                    Spacer(Modifier.height(8.dp))
                    Text("Generating Foley Audio…", color = Ink, fontSize = if (tight) 16.sp else 20.sp, fontWeight = FontWeight.Bold)
                    Text("Please keep this window open", color = Color(0xFF554640), fontSize = 12.sp)
                } else if (selectedVideo == null) {
                    Image(
                        painterResource("images/studio-upload-section.png"),
                        contentDescription = null,
                        modifier = Modifier.size(if (tight) 32.dp else 58.dp),
                        contentScale = ContentScale.Fit
                    )
                    Spacer(Modifier.height(if (tight) 3.dp else 7.dp))
                    Text(
                        if (isDragging) "Drop Your Video Here" else "Upload Your Video",
                        color = Ink, fontSize = if (tight) 17.sp else 21.sp, fontWeight = FontWeight.Bold
                    )
                    Text(
                        if (isDragging) "Release to select your video" else "Drag & drop a video here or click to browse",
                        color = Color(0xFF554640), fontSize = if (tight) 11.sp else 12.sp
                    )
                } else {
                    Text("✓", color = Color(0xFF39804A), fontSize = if (tight) 24.sp else 38.sp, fontWeight = FontWeight.Bold)
                    if (!tight) Spacer(Modifier.height(4.dp))
                    Text("Video Selected", color = Ink, fontSize = if (tight) 17.sp else 21.sp, fontWeight = FontWeight.Bold)
                    Text(
                        selectedVideo?.name.orEmpty(),
                        color = Burgundy, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
                        maxLines = 1
                    )
                    Text("Ready to continue", color = Color(0xFF554640), fontSize = 11.sp)
                }

                Spacer(Modifier.height(if (tight) 3.dp else 7.dp))
                Text(
                    uploadError.ifEmpty {
                        "Supported: MP4, MOV, AVI, MKV"
                    },
                    color = if (uploadError.isNotEmpty()) Burgundy else Color(0xFF81756D),
                    fontSize = 10.sp
                )
                Spacer(Modifier.height(if (tight) 6.dp else 10.dp))

                if (generating) {
                    // Generation is in progress; controls are intentionally disabled.
                } else if (selectedVideo == null) {
                    StudioAction(
                        "Upload Video", "images/studio-upload-button.png", Burgundy,
                        onClick = { openVideoPicker() }
                    )
                } else {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(Modifier.weight(1f)) {
                            StudioAction(
                                "Change Video", "images/studio-upload-button.png", Burgundy,
                                onClick = { openVideoPicker() }
                            )
                        }
                        Box(
                            Modifier.weight(0.65f).height(49.dp)
                                .clip(RoundedCornerShape(16.dp))
                                .background(CanvasCream)
                                .border(1.dp, CardBorder, RoundedCornerShape(16.dp))
                                .clickable { clearVideo() },
                            contentAlignment = Alignment.Center
                        ) {
                            Text("Remove", color = Burgundy, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }

        Spacer(Modifier.height(12.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            StudioAction(
                "Analyse Video", "images/studio-analyse.png", Burgundy,
                Modifier.weight(1f),
                enabled = !generating,
                onClick = {
                    if (selectedVideo == null) uploadError = "Select a video first." else onAnalyse()
                }
            )
            StudioOutlineAction(
                "Generate Video", "images/studio-generate.png",
                Modifier.weight(1f), enabled = analysed && !generating, onClick = onGenerate
            )
        }
    }
}

