plugins {
    id("org.jetbrains.kotlin.jvm")
}

dependencies {
    implementation(project(":core:model"))

    testImplementation("junit:junit:4.13.2")
}
