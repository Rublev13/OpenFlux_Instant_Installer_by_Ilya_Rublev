"""Real PNG -> actual shared Android 2.0.1 / Desktop 2.0.2 importer.

Downloads pinned public Kotlin sources into a temporary directory. Compiles the
unchanged decoder AND Profile.fromShare; no app UI or live document is used.
Илья Рублев — https://t.me/Rublev_YouTube
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

from test_profiles import Profiles, URL


REV = "2c7c41c5937125e2d8da661ad8c09e3ee174f48f"
BASE = "https://raw.githubusercontent.com/p1neappleXpress/OpenFluxClientShared/" + REV + "/src/"
SOURCES = {
    "commonMain/kotlin/io/openflux/desktop/model/ShareConfig.kt": "02d6105c0b36f739e18c8d7c5a0c7d1aab3b13ec3679a07291af69b16452da43",
    "commonMain/kotlin/io/openflux/desktop/model/Profile.kt": "ee23c8986fe43fdac77b120fc9ebd2b011674232156022a7722594a02243b88d",
    "commonMain/kotlin/io/openflux/desktop/model/TransportType.kt": "53b058d198f6c4cd0f02b623c1ece72cc480654c00ee8187e8ad9c807922da1a",
    "jvmSharedMain/kotlin/io/openflux/desktop/data/JvmShareLinkCodec.kt": "e709b8c3b1ed8e1bd68ca5271c841670a76bfb613a7a25de7181143166af199b",
}

POM = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>io.openflux.installer.tests</groupId><artifactId>import-check</artifactId><version>1</version>
  <properties><project.build.sourceEncoding>UTF-8</project.build.sourceEncoding></properties>
  <dependencies>
    <dependency><groupId>org.jetbrains.kotlin</groupId><artifactId>kotlin-stdlib</artifactId><version>2.1.21</version></dependency>
    <dependency><groupId>org.jetbrains.kotlinx</groupId><artifactId>kotlinx-serialization-json-jvm</artifactId><version>1.8.1</version></dependency>
  </dependencies>
  <build><sourceDirectory>src/main/kotlin</sourceDirectory><plugins>
    <plugin><groupId>org.jetbrains.kotlin</groupId><artifactId>kotlin-maven-plugin</artifactId><version>2.1.21</version>
      <configuration><jvmTarget>17</jvmTarget><compilerPlugins><plugin>kotlinx-serialization</plugin></compilerPlugins></configuration>
      <executions><execution><id>compile</id><phase>compile</phase><goals><goal>compile</goal></goals></execution></executions>
      <dependencies><dependency><groupId>org.jetbrains.kotlin</groupId><artifactId>kotlin-maven-serialization</artifactId><version>2.1.21</version></dependency></dependencies>
    </plugin>
    <plugin><groupId>org.codehaus.mojo</groupId><artifactId>exec-maven-plugin</artifactId><version>3.5.0</version></plugin>
  </plugins></build>
</project>
'''

HARNESS = r'''
import io.openflux.desktop.data.JvmShareLinkCodec
import io.openflux.desktop.model.*
import kotlinx.serialization.json.*
import java.io.File

fun main(args: Array<String>) {
    val codec = JvmShareLinkCodec()
    val cases = Json.parseToJsonElement(File(args[0]).readText()).jsonArray
    for (case in cases) {
        val item = case.jsonObject
        fun text(name: String) = item.getValue(name).jsonPrimitive.content
        val label = text("label")
        val expectedSession = item.getValue("session").jsonPrimitive.boolean
        val config = codec.decode(text("link"))
        check(config.secret == text("secret")) { "$label: secret lost by decoder" }
        check(config.context == text("context")) { "$label: context lost by decoder" }
        check(config.negotiate == expectedSession && config.codec == text("codec")) { "$label: mode lost" }
        val profile = Profile.fromShare(config, "synthetic", 0, ProfileSource.Qr)
        check(profile.secret == text("secret")) { "$label: secret lost by profile importer" }
        check(profile.effectiveContext() == text("context")) { "$label: different KDF context" }
        check(profile.codec.cliName == text("codec") && profile.session == expectedSession) { "$label: wrong profile mode" }
        check(profile.transport.cliName == text("transport") && profile.value == text("context")) { "$label: wrong editor/document" }
        check(profile.priority == 100 && profile.extras.isEmpty()) { "$label: unexpected extra transport" }
        check(profile.problems().isEmpty()) { "$label: imported profile is not connectable" }
        val again = Profile.fromShare(codec.decode(codec.encode(profile.toShare().getOrThrow())), "roundtrip", 0, ProfileSource.Link)
        check(again.secret == profile.secret && again.effectiveContext() == profile.effectiveContext()) { "$label: roundtrip changes encryption" }
        println("PASS: real PNG -> official Kotlin decode + Profile.fromShare -> $label")
    }
}
'''


def main():
    for name in ("mvn", "qrencode", "zbarimg"):
        if not shutil.which(name):
            raise SystemExit("Required CI tool is missing: " + name)
    fixture = Profiles()
    fixture.setUp()
    fixture.env = dict(os.environ)
    try:
        source_dir = fixture.root / "src/main/kotlin"
        source_dir.mkdir(parents=True)
        for path, expected in SOURCES.items():
            with urllib.request.urlopen(BASE + path, timeout=40) as response:
                source = response.read().decode().rstrip("\n") + "\n"
            if hashlib.sha256(source.encode()).hexdigest() != expected:
                raise SystemExit("Pinned Kotlin checksum mismatch: " + Path(path).name)
            (source_dir / Path(path).name).write_text(source)
        cases = []
        for mode in ("session", "ios"):
            for transport in ("yandex", "vyandex"):
                for suffix in ("", "/"):
                    stage = Path(tempfile.mkdtemp(dir=fixture.root))
                    result = fixture.shell('WORK="$1"; DOC_URL="$2"; TRANSPORT="$3"; PROFILE_MODE="$4"; '
                                           'set_profile_options; write_config; write_share', stage, URL + suffix, transport, mode)
                    if result.returncode:
                        raise SystemExit("Profile generation failed")
                    config = stage / "config"
                    qr = subprocess.run(["zbarimg", "--quiet", "--raw", str(config / "connection.png")],
                                        text=True, capture_output=True, timeout=20)
                    link = (config / "connection.txt").read_text().strip()
                    if qr.returncode or qr.stdout.strip() != link:
                        raise SystemExit("Real PNG does not decode to the generated link")
                    cases.append({"label": mode + "/" + transport + ("/slash" if suffix else ""),
                                  "link": qr.stdout, "secret": (config / "secret.txt").read_text().strip(),
                                  "context": URL + suffix, "codec": "legacy" if mode == "ios" else "batched",
                                  "session": mode == "session", "transport": transport})
        (fixture.root / "cases.json").write_text(json.dumps(cases))
        (source_dir / "Main.kt").write_text(HARNESS)
        (fixture.root / "pom.xml").write_text(POM)
        result = subprocess.run(["mvn", "-B", "-q", "--no-transfer-progress", "compile", "exec:java",
                                 "-Dexec.mainClass=MainKt", "-Dexec.args=cases.json"],
                                cwd=fixture.root, text=True, capture_output=True, timeout=300)
        if result.returncode:
            raise SystemExit("Official client harness failed:\n" + result.stdout + result.stderr)
        print(result.stdout, end="")
    finally:
        fixture.doCleanups()


if __name__ == "__main__":
    main()
