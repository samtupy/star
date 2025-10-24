// Module-level build file
// build.gradle.kts (Module: app)

plugins {
    // Apply the plugins declared in the root build.gradle.kts
    // or directly by their ID if not using the root declaration pattern
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    // If you had defined an alias for compose, e.g., in libs.versions.toml as
    // kotlin-compose = { id = "org.jetbrains.kotlin.plugin.compose", version.ref = "kotlin" }
    // You might also add: id("org.jetbrains.kotlin.plugin.compose")
    // However, with modern AGP and composeOptions, it's often implicitly handled.
}

android {
    namespace = "com.star.provider"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.star.provider"
        minSdk = 32 // Ensure this is appropriate for the APIs used
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false // Set to true for actual releases
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }

    kotlinOptions {
        jvmTarget = "1.8"
    }

    buildFeatures {
        compose = true
    }

    composeOptions {
        // Ensure this version is compatible with your Kotlin and Compose BOM versions
        // Refer to: https://developer.android.com/jetpack/androidx/releases/compose-kotlin
        kotlinCompilerExtensionVersion = "1.5.3" // Example, update to your required version
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    // Core Android & Jetpack Compose Dependencies (from version catalog)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom)) // Ensure this BOM version is up-to-date
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation("androidx.compose.material3:material3:1.2.1") // Or your current M3 version
    implementation("androidx.compose.material:material-icons-core:1.6.7") // Or latest
    implementation("androidx.compose.material:material-icons-extended:1.6.7") // Or latest - for all icons
    // Added Dependencies for STAR Provider Service (explicitly versioned for clarity, or add to TOML)
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.json:json:20231013")
    implementation("com.google.code.gson:gson:2.10.1")

    // Testing Dependencies (from version catalog)
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(platform(libs.androidx.compose.bom)) // For Compose testing
    androidTestImplementation(libs.androidx.ui.test.junit4)
    debugImplementation(libs.androidx.ui.tooling)
    debugImplementation(libs.androidx.ui.test.manifest)
}