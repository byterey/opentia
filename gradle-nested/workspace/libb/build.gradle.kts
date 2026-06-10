plugins {
    id("org.jetbrains.kotlin.jvm")
}

dependencies {
    implementation(project(":libs:liba"))

    testImplementation("junit:junit:4.13.2")
}
