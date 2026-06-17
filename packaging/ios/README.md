# BabbleCast iOS

**Cannot be built from Linux.** Apple requires Xcode on macOS to compile and sign iOS apps.

## What works tonight without a Mac

- **Android**: build APK on Linux (`bash packaging/android/build.sh`) and sideload to your phone.
- **iOS**: not possible from this machine tonight.

## If you have a Mac

1. Install Xcode from the App Store.
2. `pip install kivy-ios buildozer`
3. Follow [Kivy iOS documentation](https://kivy.org/doc/stable/guide/packaging-ios.html).
4. Install on device via Xcode (free Apple ID) or TestFlight.

## Sideloading iOS (after you have an `.ipa`)

| Method | Needs |
|--------|--------|
| Xcode → Run on device | Mac + USB cable + Apple ID |
| TestFlight | Mac build + paid Developer account |
| AltStore / SideStore | Mac to create IPA, then sideload from phone |

There is no supported way to sideload iOS apps built entirely on Linux.
