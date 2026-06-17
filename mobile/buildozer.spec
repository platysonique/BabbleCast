[app]

title = BabbleCast
package.name = babblecast
package.domain = org.babblecast
package.main = main.py
source.dir = ..
source.include_exts = py,png,jpg,kv,atlas,json
source.include_patterns = babblecast/*,mobile/*,main.py,assets/*
source.exclude_dirs = tests,packaging,.venv,.git,.cache,dist,build,mobile/bin,mobile/.buildozer,scripts,GoonFiles
source.exclude_patterns = *.spec,*.md,requirements*.txt,pyproject.toml,LICENSE
version = 1.0.0

icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/splash.png

requirements = python3==3.11.8,hostpython3==3.11.8,kivy==2.3.1,kivymd==1.2.0,pyjnius,android,numpy,zeroconf,websockets,libopus,opuslib,plyer,sqlite3,openssl
p4a.local_recipes = p4a-recipes

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,RECORD_AUDIO,MODIFY_AUDIO_SETTINGS,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,ACCESS_FINE_LOCATION,BLUETOOTH,BLUETOOTH_CONNECT,FOREGROUND_SERVICE,WAKE_LOCK
android.api = 33
android.minapi = 24
android.ndk = 26b
android.sdk_path = /home/papaya/Android/Sdk
android.ndk_path = /home/papaya/Android/ndk/26.1.10909125
android.accept_sdk_license = True
android.archs = arm64-v8a
android.debug_artifact = apk

[buildozer]

log_level = 2
warn_on_root = 1
