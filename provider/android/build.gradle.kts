// Top-level build file where you can add configuration options common to all sub-projects/modules.
// build.gradle.kts (Project: YourProjectRoot)

plugins {
    // It's common to declare these plugins here with 'apply false'
    // so that modules can apply them. The actual plugin versions are
    // managed in your libs.versions.toml file.

    // Assuming these aliases are defined in your libs.versions.toml
    alias(libs.plugins.android.application) apply false
    alias(libs.plugins.kotlin.android) apply false
    // alias(libs.plugins.android.library) apply false // Add if you plan to have library modules
}

// Optional: Define tasks or configurations common to all projects
// For example, a common clean task (though modern AGP handles this well)
/*
tasks.register("clean", Delete::class) {
    delete(rootProject.buildDir)
}
*/

// It's also common to configure repositories for all projects here,
// though this can also be in settings.gradle.kts's dependencyResolutionManagement
/*
allprojects {
    repositories {
        google()
        mavenCentral()
        // Add other repositories here if needed, e.g., JitPack
    }
}
*/