// settings.gradle.kts

pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal() // For Gradle plugins
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS) // Recommended practice
    repositories {
        google()
        mavenCentral()
        // Add other repositories here if needed, e.g., JitPack
        // maven { url = uri("https://jitpack.io") }
    }
    // This enables the version catalog feature for your project
    // versionCatalogs {
    //     create("libs") {
    //         from(files("gradle/libs.versions.toml"))
    //     }
    // }
    // For newer Gradle versions (7.4+), enabling version catalogs might be automatic if libs.versions.toml exists,
    // or more simply done via:
    // Or may not be needed if libs.versions.toml is present
}

rootProject.name = "StarProvider" // Or your desired project name
include(":app") // Includes your 'app' module