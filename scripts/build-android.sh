#!/bin/sh
# Local tools and secrets stay in the ignored .toolchain/ and android/ files.
set -eu
cd "$(dirname "$0")/.."
PROJECT_DIR="$PWD"
if [ -z "${JAVA_HOME:-}" ]; then
  for candidate in "$PROJECT_DIR"/.toolchain/*/Contents/Home; do
    if [ -x "$candidate/bin/javac" ]; then
      JAVA_HOME="$candidate"
      export JAVA_HOME
      break
    fi
  done
fi
if [ -z "${JAVA_HOME:-}" ]; then
  echo '请安装 JDK 17，并设置 JAVA_HOME。参考 docs/android.md。'
  exit 1
fi
export ANDROID_HOME="${ANDROID_HOME:-$PROJECT_DIR/.toolchain/android-sdk}"
export ANDROID_USER_HOME="${ANDROID_USER_HOME:-$PROJECT_DIR/.toolchain/android-user}"
export GRADLE_USER_HOME="${GRADLE_USER_HOME:-$PROJECT_DIR/.toolchain/gradle-user}"
export PATH="$JAVA_HOME/bin:$PATH"
if [ ! -f android/signing.properties ]; then
  echo '请先运行 scripts/create-android-signing.py 生成并备份本机签名密钥。'
  exit 1
fi
if [ -x .toolchain/gradle-8.13/bin/gradle ]; then
  GRADLE_COMMAND="$PROJECT_DIR/.toolchain/gradle-8.13/bin/gradle"
else
  GRADLE_COMMAND="$PROJECT_DIR/android/gradlew"
fi
"$GRADLE_COMMAND" -p android --no-daemon testReleaseUnitTest lintRelease assembleRelease "$@"
mkdir -p dist/android
cp android/app/build/outputs/apk/release/app-release.apk dist/android/guanlan-0.3.1.apk
"$ANDROID_HOME/build-tools/35.0.0/apksigner" verify --verbose --print-certs dist/android/guanlan-0.3.1.apk
shasum -a 256 dist/android/guanlan-0.3.1.apk > dist/android/guanlan-0.3.1.apk.sha256
echo "APK 已生成：$PROJECT_DIR/dist/android/guanlan-0.3.1.apk"
