# iOS build — requires macOS with Xcode and Apple Developer account.
#
# Cannot be built on Linux. On a Mac:
#
#   brew install autoconf automake libtool pkg-config
#   pip install kivy-ios
#   cd mobile
#   toolchain create BabbleCast ../..
#   toolchain build python3 kivy numpy zeroconf websockets opuslib
#   toolchain run BabbleCast ../main.py
#
# Sideload options (after building .ipa on Mac):
#   - TestFlight (Apple Developer $99/yr)
#   - AltStore / SideStore (free, 7-day resign cycle)
#   - Xcode direct install to your iPhone (free Apple ID, 7-day limit)
#
# BabbleCast uses the same Python core as Android; iOS audio would need
# AVAudioEngine via pyobjus (not yet implemented — chat + discovery work;
# voice requires macOS build session to add ios_engine.py).

echo "iOS builds require macOS + Xcode. See packaging/ios/README.md"
