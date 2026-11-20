#!/usr/bin/env python3
"""Wrap the official SDK emulator in a discoverable macOS app, locally only."""
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

if sys.platform != 'darwin':
    raise SystemExit('此预览入口用于 macOS；其他系统可使用 Android Studio 的 Device Manager。')
root = Path(__file__).resolve().parent.parent
sdk = Path(os.environ.get('ANDROID_HOME', root / '.toolchain/android-sdk'))
emulator = sdk / 'emulator'
source = emulator / 'qemu/darwin-aarch64/qemu-system-aarch64'
if not source.exists():
    raise SystemExit('未安装项目 ARM64 Android 模拟器，请先按 docs/android.md 安装。')
bundle = root / '.toolchain/Guanlan Test Emulator.app/Contents'
macos = bundle / 'MacOS'
macos.mkdir(parents=True, exist_ok=True)
binary = macos / 'qemu-system-aarch64'
if not binary.exists() or binary.stat().st_mtime_ns != source.stat().st_mtime_ns:
    shutil.copy2(source, binary)
link = macos / 'lib64'
if not link.exists():
    link.symlink_to(emulator / 'lib64', target_is_directory=True)
(bundle / 'Info.plist').write_bytes(plistlib.dumps({
    'CFBundleIdentifier':'cn.guanlan.testemulator', 'CFBundleName':'Guanlan Test Emulator',
    'CFBundleDisplayName':'观澜 Android 预览', 'CFBundleExecutable':'launcher',
    'CFBundlePackageType':'APPL', 'CFBundleVersion':'1.1', 'NSHighResolutionCapable':True,
}))
env = {
    'ANDROID_HOME':sdk,
    'ANDROID_USER_HOME':root / '.toolchain/android-user',
    'ANDROID_AVD_HOME':root / '.toolchain/android-user/avd',
    'ANDROID_EMULATOR_LAUNCHER_DIR':emulator,
    'DYLD_LIBRARY_PATH':':'.join(str(emulator / p) for p in ('lib64','lib64/qt/lib','lib64/gles_angle','lib64/vulkan')),
    'QT_QPA_PLATFORM_PLUGIN_PATH':emulator / 'lib64/qt/plugins',
}
code = '''#include <stdlib.h>
#include <unistd.h>
#include <stdio.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <libgen.h>
int main(void) {
char path[PATH_MAX]; uint32_t size=sizeof(path); _NSGetExecutablePath(path,&size);
char *directory=dirname(path); char executable[PATH_MAX];
snprintf(executable,sizeof(executable),"%s/qemu-system-aarch64",directory);
'''
for key, value in env.items():
    code += f'setenv({json.dumps(key)}, {json.dumps(str(value))}, 1);\n'
log = json.dumps(str(root / '.toolchain/emulator-bundle.log'))
code += f'freopen({log},"a",stdout); freopen({log},"a",stderr);\n'
code += '''char *args[]={executable,"-avd","Guanlan_Test","-no-snapshot","-no-boot-anim","-gpu","swiftshader","-no-audio",NULL};
execv(executable,args); perror("Unable to start Android preview"); return 1;
}
'''
launcher_source = root / '.toolchain/emulator-launcher.c'
if not launcher_source.exists() or launcher_source.read_text() != code or not (macos / 'launcher').exists():
    launcher_source.write_text(code)
    subprocess.run(['xcrun','clang',str(launcher_source),'-o',str(macos / 'launcher')],check=True)
print(bundle.parent)
