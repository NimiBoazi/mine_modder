# backend/agent/tools/repositories.py
from pathlib import Path
import re

FORGE_SETTINGS_GROOVY = """\
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.PREFER_PROJECT)
    repositories {
        maven { name = "Forge"; url = uri("https://maven.minecraftforge.net") }
        maven { name = "Minecraft libraries"; url = uri("https://libraries.minecraft.net") }
        maven { name = "Sponge"; url = uri("https://repo.spongepowered.org/repository/maven-public/") }
        mavenCentral()
        google()
    }
}
"""

FORGE_SETTINGS_KTS = """\
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.PREFER_PROJECT)
    repositories {
        maven("https://maven.minecraftforge.net") { name = "Forge" }
        maven("https://libraries.minecraft.net") { name = "Minecraft libraries" }
        maven("https://repo.spongepowered.org/repository/maven-public/") { name = "Sponge" }
        mavenCentral()
        google()
    }
}
"""

def patch_settings_repositories(ws: Path) -> str:
    groovy = ws / "settings.gradle"
    kts = ws / "settings.gradle.kts"

    if groovy.exists():
        text = groovy.read_text()
        if "dependencyResolutionManagement" in text:
            # Force PREFER_PROJECT if a mode is already present
            text = re.sub(
                r"repositoriesMode\.set\(RepositoriesMode\.\w+\)",
                "repositoriesMode.set(RepositoriesMode.PREFER_PROJECT)",
                text, count=1
            )
            # Ensure the common repos are present (idempotent append)
            if "maven.minecraftforge.net" not in text:
                text += "\n" + FORGE_SETTINGS_GROOVY
        else:
            text += ("\n" if text and not text.endswith("\n") else "") + FORGE_SETTINGS_GROOVY
        groovy.write_text(text)
        return "settings: dependencyResolutionManagement => PREFER_PROJECT (groovy)"

    # If a Kotlin settings file exists, patch that instead
    if kts.exists():
        text = kts.read_text()
        if "dependencyResolutionManagement" in text:
            text = re.sub(
                r"repositoriesMode\.set\(RepositoriesMode\.\w+\)",
                "repositoriesMode.set(RepositoriesMode.PREFER_PROJECT)",
                text, count=1
            )
            if "maven.minecraftforge.net" not in text:
                text += "\n" + FORGE_SETTINGS_KTS
        else:
            text += ("\n" if text and not text.endswith("\n") else "") + FORGE_SETTINGS_KTS
        kts.write_text(text)
        return "settings: dependencyResolutionManagement => PREFER_PROJECT (kts)"

    # If there is no settings file at all, create Groovy by default
    groovy.write_text(FORGE_SETTINGS_GROOVY)
    return "settings: created dependencyResolutionManagement => PREFER_PROJECT (groovy)"


def patch_forge_build_gradle_for_lwjgl_macos_patch(ws: Path) -> str:
    """
    Forge-only: allow Gradle to fetch the macOS patched LWJGL freetype from Forge's maven.
    Idempotent and safe to run multiple times.
    """
    # Prefer Groovy MDK, but handle KTS too.
    g = ws / "build.gradle"
    k = ws / "build.gradle.kts"
    target = g if g.exists() else (k if k.exists() else None)
    if not target:
        return "no build.gradle(.kts) found"

    txt = target.read_text()
    if "MM_LWJGL_MACOS_PATCH" in txt:
        return "already patched"

    # 1) Remove a broad LWJGL exclusiveContent pin to mavenCentral if present
    #    (keeps rest of the file intact). If not present, this is a no-op.
    txt2 = re.sub(
        r'(?s)exclusiveContent\s*\{\s*forRepository\s*\(\s*mavenCentral\s*\(\s*\)\s*\)\s*.*?includeGroup\s*[("\']org\.lwjgl[)"\'].*?\}',
        "// MM_LWJGL_MACOS_PATCH: removed LWJGL-only pin to mavenCentral for macOS\n",
        txt,
        count=1,
    )

    # 2) Add a narrow override for *just* lwjgl-freetype to come from Forge maven.
    if target.suffix == ".kts":
        snippet = '''
// MM_LWJGL_MACOS_PATCH (kts): allow Forge's patched macOS natives
repositories {
    exclusiveContent {
        forRepository(maven("https://maven.minecraftforge.net"))
        filter {
            includeModule("org.lwjgl", "lwjgl-freetype")
        }
    }
}
// /MM_LWJGL_MACOS_PATCH
'''
    else:
        # FIX: The forRepository method requires a closure, not a method call as an argument.
        # The 'maven { ... }' block should be *inside* the forRepository's curly braces.
        snippet = '''
// MM_LWJGL_MACOS_PATCH (groovy): allow Forge's patched macOS natives
repositories {
    exclusiveContent {
        forRepository {
            maven { url = "https://maven.minecraftforge.net" }
        }
        filter {
            includeModule("org.lwjgl", "lwjgl-freetype")
        }
    }
}
// /MM_LWJGL_MACOS_PATCH
'''

    target.write_text(txt2.rstrip() + "\n\n" + snippet)
    return f"applied LWJGL macOS patch to {target.name}"