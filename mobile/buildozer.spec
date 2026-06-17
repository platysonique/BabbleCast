[app]

title = BabbleCast
package.name = babblecast
package.domain = org.babblecast
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json
version = 1.0.0

requirements = python3,kivy,kivymd,pyjnius,android,hostpython3,sounddevice,numpy,zeroconf,websockets,opuslib,noisereduce,plyer

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,RECORD_AUDIO,MODIFY_AUDIO_SETTINGS,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.gradle_dependencies = 

[buildozer]

log_level = 2
warn_on_root = 1
