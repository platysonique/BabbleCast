#!/usr/bin/env bash
# iOS build helper — requires macOS with Xcode and kivy-ios toolchain.
set -euo pipefail
echo "BabbleCast iOS build"
echo "1. Install kivy-ios: pip install kivy-ios"
echo "2. toolchain build python3 kivy numpy"
echo "3. toolchain create BabbleCast ../mobile"
echo "4. Add babblecast package to Xcode project and build"
echo "See: https://kivy.org/doc/stable/guide/packaging-ios.html"
