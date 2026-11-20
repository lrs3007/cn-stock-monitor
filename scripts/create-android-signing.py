#!/usr/bin/env python3
"""Generate one persistent personal release signing key; never overwrite it."""
import os
from pathlib import Path
import secrets
import shutil
import subprocess

root = Path(__file__).resolve().parent.parent
config = root / 'android/signing.properties'
keystore = root / 'android/guanlan-release.jks'
if config.exists() or keystore.exists():
    raise SystemExit('已存在签名配置或密钥；保留现有文件，以便 APK 可以覆盖升级。')
java = os.environ.get('JAVA_HOME')
candidates = list((root / '.toolchain').glob('*/Contents/Home/bin/keytool'))
keytool = str(Path(java) / 'bin/keytool') if java else str(candidates[0]) if candidates else shutil.which('keytool')
if not keytool:
    raise SystemExit('请先安装 JDK 17。')
password = secrets.token_urlsafe(32)
environment = {**os.environ, 'GUANLAN_KEY_PASSWORD': password}
subprocess.run([keytool, '-genkeypair', '-keystore', str(keystore), '-storetype', 'JKS',
                '-alias', 'guanlan', '-keyalg', 'RSA', '-keysize', '3072', '-validity', '10000',
                '-dname', 'CN=Guanlan Personal, O=Guanlan',
                '-storepass:env', 'GUANLAN_KEY_PASSWORD', '-keypass:env', 'GUANLAN_KEY_PASSWORD'],
               env=environment, check=True)
keystore.chmod(0o600)
with os.fdopen(os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as file:
    file.write(f'storeFile=guanlan-release.jks\nstorePassword={password}\nkeyAlias=guanlan\nkeyPassword={password}\n')
print('本机签名密钥已生成。请私下备份 android/guanlan-release.jks 和 android/signing.properties；不要提交或分享。')
