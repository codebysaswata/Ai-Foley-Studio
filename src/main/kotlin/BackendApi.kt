import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.cio.CIO
import io.ktor.client.plugins.HttpTimeout
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.post
import io.ktor.client.request.prepareGet
import io.ktor.client.request.setBody
import io.ktor.client.request.forms.MultiPartFormDataContent
import io.ktor.client.request.forms.formData
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentDisposition
import io.ktor.http.ContentType
import io.ktor.http.Headers
import io.ktor.http.HttpHeaders
import io.ktor.http.isSuccess
import kotlinx.io.asSource
import kotlinx.io.buffered
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import java.io.File
import java.io.FileInputStream
import java.util.Properties

/** Local-only settings. This file is intentionally outside the project and Git repository. */
data class BackendConfig(val baseUrl: String, val apiToken: String) {
    companion object {
        private val configFile: File
            get() = File(System.getenv("APPDATA") ?: System.getProperty("user.home"), "AI Foley Studio/config.properties")

        fun load(): BackendConfig {
            val properties = Properties()
            if (configFile.isFile) configFile.inputStream().use(properties::load)
            return BackendConfig(
                baseUrl = (properties.getProperty("backend.baseUrl") ?: "http://10.88.9.242:8000").trim().trimEnd('/'),
                apiToken = (properties.getProperty("backend.apiToken") ?: "").trim()
            )
        }

        fun locationHint() = configFile.absolutePath
    }
}

data class BackendJob(val id: String, val status: String, val stage: String?, val progressPercent: Float, val error: String?)
data class BackendArtifact(val name: String, val mediaType: String, val downloadUrl: String)

private val backendJson = Json { ignoreUnknownKeys = true }

private fun JsonObject.string(name: String): String? = this[name]?.jsonPrimitive?.contentOrNull
private fun JsonObject.float(name: String): Float = this[name]?.jsonPrimitive?.contentOrNull?.toFloatOrNull() ?: 0f

class BackendApi(private val config: BackendConfig) : AutoCloseable {
    private val client = HttpClient(CIO) {
        install(HttpTimeout) {
            connectTimeoutMillis = 10_000
            // Ktor requires positive values. Jobs are polled in short requests, while the streamed
            // upload is allowed a generous 30 minutes for large videos on a private LAN.
            requestTimeoutMillis = 30 * 60 * 1_000L
            socketTimeoutMillis = 30 * 60 * 1_000L
        }
    }

    private fun path(path: String) = config.baseUrl + path

    private fun requireToken() {
        require(config.apiToken.isNotBlank()) {
            "API token missing. Add backend.apiToken to ${BackendConfig.locationHint()}"
        }
    }

    private fun authenticated(responseBuilder: io.ktor.client.request.HttpRequestBuilder) {
        requireToken()
        responseBuilder.header(HttpHeaders.Authorization, "Bearer ${config.apiToken}")
        responseBuilder.header(HttpHeaders.Accept, ContentType.Application.Json)
    }

    suspend fun checkReady(): Boolean {
        val response = client.get(path("/health/ready"))
        return response.status.isSuccess() && backendJson.parseToJsonElement(response.bodyAsText()).jsonObject.string("status") == "ready"
    }

    suspend fun createJob(video: File, prompt: String, chunkSeconds: Int): BackendJob {
        require(chunkSeconds in 1..8) { "Processing chunk duration must be from 1 to 8 seconds." }
        val response = client.post(path("/api/v1/jobs")) {
            authenticated(this)
            setBody(MultiPartFormDataContent(formData {
                append("prompt_override", prompt)
                append("chunk_seconds", chunkSeconds.toString())
                append("export_video", "true")
                append("negative_prompt", "music, speech")
                appendInput("video", Headers.build {
                    append(HttpHeaders.ContentType, contentTypeFor(video).toString())
                    append(HttpHeaders.ContentDisposition, ContentDisposition.File.withParameter(ContentDisposition.Parameters.FileName, video.name).toString())
                }, video.length()) { FileInputStream(video).asSource().buffered() }
            }))
        }
        return response.requireObject("Could not create the Foley job.").toJob()
    }

    suspend fun job(jobId: String): BackendJob {
        val response = client.get(path("/api/v1/jobs/$jobId")) { authenticated(this) }
        return response.requireObject("Could not read job status.").toJob()
    }

    suspend fun artifacts(jobId: String): List<BackendArtifact> {
        val response = client.get(path("/api/v1/jobs/$jobId/artifacts")) { authenticated(this) }
        val objectValue = response.requireObject("Could not read generated artifacts.")
        val items = objectValue["artifacts"]?.jsonArray ?: JsonArray(emptyList())
        return items.mapNotNull { element ->
            val item = element.jsonObject
            val name = item.string("name") ?: return@mapNotNull null
            val mediaType = item.string("media_type") ?: "application/octet-stream"
            val url = item.string("download_url") ?: return@mapNotNull null
            BackendArtifact(name, mediaType, url)
        }
    }

    suspend fun download(artifact: BackendArtifact): File {
        val extension = artifact.name.substringAfterLast('.', "bin")
        val folder = File(System.getProperty("java.io.tmpdir"), "AI Foley Studio").apply { mkdirs() }
        val target = File.createTempFile("foley_", ".$extension", folder).apply { deleteOnExit() }
        client.prepareGet(path(artifact.downloadUrl)) { authenticated(this) }.execute { response ->
            if (!response.status.isSuccess()) throw backendError(response, "Could not download ${artifact.name}.")
            target.writeBytes(response.body())
        }
        return target
    }

    private suspend fun HttpResponse.requireObject(prefix: String): JsonObject {
        if (!status.isSuccess()) throw backendError(this, prefix)
        return backendJson.parseToJsonElement(bodyAsText()).jsonObject
    }

    private suspend fun backendError(response: HttpResponse, prefix: String): IllegalStateException {
        val text = runCatching { response.bodyAsText() }.getOrDefault("")
        val detail = runCatching {
            backendJson.parseToJsonElement(text).jsonObject["error"]?.jsonObject?.string("message")
        }.getOrNull()
        return IllegalStateException("$prefix HTTP ${response.status.value}${detail?.let { ": $it" } ?: ""}")
    }

    private fun JsonObject.toJob() = BackendJob(
        id = string("job_id") ?: error("Backend response has no job_id."),
        status = string("status") ?: "unknown",
        stage = string("processing_stage"),
        progressPercent = float("progress_percent"),
        error = string("error_message")
    )

    override fun close() = client.close()

    private fun contentTypeFor(file: File): ContentType = when (file.extension.lowercase()) {
        "mov" -> ContentType("video", "quicktime")
        "avi" -> ContentType("video", "x-msvideo")
        "mkv" -> ContentType("video", "x-matroska")
        else -> ContentType("video", "mp4")
    }
}
