import org.jetbrains.compose.desktop.application.dsl.TargetFormat

plugins {
    kotlin("jvm") version "2.0.21"
    id("org.jetbrains.compose") version "1.7.0"
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.21"
}

group = "studio.aifoley"
version = "1.0.30"

// Keep generated files out of the OneDrive-synced source folder on Windows.
// OneDrive can temporarily lock Kotlin's compiled classes while syncing them.
val localAppData = System.getenv("LOCALAPPDATA")
if (localAppData != null) {
    buildDir = file("$localAppData/AiFoleyStudio/build")
} else {
    buildDir = file(".build")
}

dependencies {
    implementation(compose.desktop.currentOs)
    implementation("uk.co.caprica:vlcj:4.8.3")   // in-app video playback (needs VLC installed on the PC)
    implementation("io.ktor:ktor-client-core-jvm:3.0.3")
    implementation("io.ktor:ktor-client-cio-jvm:3.0.3")
    implementation("io.ktor:ktor-client-content-negotiation-jvm:3.0.3")
    implementation("io.ktor:ktor-serialization-kotlinx-json-jvm:3.0.3")
}

kotlin {
    jvmToolchain(21)
}

compose.desktop {
    application {
        mainClass = "MainKt"
        buildTypes {
            release {
                // Compose 1.7.0 bundles ProGuard 7.2.2, which cannot process Java 21 bytecode.
                // This local desktop installer does not require code obfuscation.
                proguard {
                    isEnabled.set(false)
                }
            }
        }
        nativeDistributions {
            targetFormats(TargetFormat.Msi, TargetFormat.Exe)
            packageName = "AI Foley Studio"
            packageVersion = "1.0.30"
            description = "AI-powered Foley generation for video creators"
            vendor = "AI Foley Studio"
            modules("java.net.http", "jdk.unsupported")   // backend upload (HTTP) + video player support in the installed app

            windows {
                // App logo shown on the installer, the .exe, the desktop shortcut, Start menu and taskbar
                iconFile.set(project.file("src/main/resources/images/logo.ico"))
                shortcut = true                 // desktop shortcut
                menu = true                     // Start menu entry
                menuGroup = "AI Foley Studio"   // Start menu folder
            }
        }
    }
}
