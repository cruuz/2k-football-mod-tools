# XEXLoaderWV Java 21 compatibility patch

The installed XEXLoaderWV release was compiled as Java class version 67
(Java 23), but this Ghidra installation is intentionally run on Java 21 (class
version 65). APF 2K8 also exposes an upstream integer-overflow bug: the loader's
normal-compression convenience method estimates the output as
`compressedSize * 100` in a signed 32-bit `int`. APF's 37,717,546-byte LZX
stream therefore becomes a negative length.

The patched `XEXHeader.java` uses the exact image size in the XEX security
header. Rebuild all published sources for Java 21, overlay the patched class,
and update the installed JAR:

```bash
rm -rf /tmp/xexloaderwv-java21
mkdir -p /tmp/xexloaderwv-java21/src /tmp/xexloaderwv-java21/classes
unzip -q tools/vendor/ghidra_12.1.2_PUBLIC/Ghidra/Extensions/XEXLoaderWV/lib/XEXLoaderWV-src.zip \
  -d /tmp/xexloaderwv-java21/src
cp tools/xexloaderwv-java21/src/main/java/xexloaderwv/XEXHeader.java \
  /tmp/xexloaderwv-java21/src/src/main/java/xexloaderwv/XEXHeader.java
CP=$(find tools/vendor/ghidra_12.1.2_PUBLIC -name '*.jar' -printf '%p:')
javac --release 21 -proc:none -cp "$CP" \
  -d /tmp/xexloaderwv-java21/classes \
  $(find /tmp/xexloaderwv-java21/src/src/main/java -name '*.java' -print)
jar --update \
  --file tools/vendor/ghidra_12.1.2_PUBLIC/Ghidra/Extensions/XEXLoaderWV/lib/XEXLoaderWV.jar \
  -C /tmp/xexloaderwv-java21/classes .
```

`javap -verbose xexloaderwv.XEXLoaderWVLoader` should then report major
version 65.
