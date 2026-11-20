#!/bin/sh
# User-invoked development preview. Only installs/opens this project's APK and AVD.
set -eu
cd "$(dirname "$0")/.."
PROJECT_DIR="$PWD"
export ANDROID_HOME="${ANDROID_HOME:-$PROJECT_DIR/.toolchain/android-sdk}"
export ANDROID_USER_HOME="$PROJECT_DIR/.toolchain/android-user"
export ANDROID_AVD_HOME="$ANDROID_USER_HOME/avd"
APK="$PROJECT_DIR/dist/android/guanlan-0.3.1.apk"
ADB="$ANDROID_HOME/platform-tools/adb"
if [ ! -f "$APK" ]; then
  echo '请先运行 ./scripts/build-android.sh 生成 APK。'; exit 1
fi
if [ ! -f "$ANDROID_AVD_HOME/Guanlan_Test.ini" ]; then
  echo '请先按 docs/android.md 创建 Guanlan_Test 模拟器。'; exit 1
fi
.venv312/bin/python scripts/prepare-android-preview.py
open -a "$PROJECT_DIR/.toolchain/Guanlan Test Emulator.app"
echo '正在打开 Android 手机预览，首次启动需要稍等…'
DEVICE='127.0.0.1:5555'
ready=0
for attempt in $(seq 1 90); do
  "$ADB" -P 5038 connect "$DEVICE" >/dev/null 2>&1 || true
  avd=$("$ADB" -P 5038 -s "$DEVICE" shell getprop ro.boot.qemu.avd_name 2>/dev/null | tr -d '\r' || true)
  boot=$("$ADB" -P 5038 -s "$DEVICE" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || true)
  if [ "$avd" = 'Guanlan_Test' ] && [ "$boot" = '1' ]; then ready=1; break; fi
  sleep 1
done
if [ "$ready" != 1 ]; then
  echo '未能连接项目模拟器。若仍有旧的无窗口测试实例，请先退出它再重试。'; exit 1
fi
"$ADB" -P 5038 -s "$DEVICE" install -r "$APK"
"$ADB" -P 5038 -s "$DEVICE" shell am start -n cn.guanlan.monitor/.MainActivity
echo '观澜已打开。鼠标点击相当于手机触摸；模拟手机与电脑网页版分别保存数据。'
