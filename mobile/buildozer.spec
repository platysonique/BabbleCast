[app]

title = BabbleCast
package.name = babblecast
package.domain = org.babblecast
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
source.include_patterns = main.py
version = 1.0.0

# Parent package (shared core) — build from repo root: buildozer -c mobile/buildozer.spec
requirements = python3,kivy,kivymd,pyjnius,android,hostpython3,numpy,zeroconf,websockets,opuslib,noisereduce,plyer

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,RECORD_AUDIO,MODIFY_AUDIO_SETTINGS,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE
android.api = 33
android.minapi = 24
android.ndk = 25b

[buildozer]

log_level = 2
warn_on_root = 1

# Run from repository root:
#   buildozer -c mobile/buildozer.spec android debug
# Ensure babblecast/ is on PYTHONPATH via p4a hook or copy step before release builds.
