pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

rootProject.name = "android-app"
include(":app")
include(":core:model")
include(":feature:checkout")
