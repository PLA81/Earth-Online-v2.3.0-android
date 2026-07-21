# Android APK 构建

本项目使用 Qt 官方 `pyside6-android-deploy`。目标架构为大多数现代安卓手机使用的 `arm64-v8a / aarch64`。

需要：

- Linux 或 macOS
- Python 3.11+
- Java 17 或 21
- PySide6 6.11.1 Android aarch64 wheel
- shiboken6 6.11.1 Android aarch64 wheel
- Android SDK、NDK 26.1.10909125、Android 34 平台和 Build Tools 35.0.0

准备好环境后运行：

```bash
./build_android.sh
```

调试模式输出 APK；发布到应用商店时将 `pysidedeploy.spec` 的 `[buildozer] mode` 改为 `release`，输出 AAB，并按 Android 官方流程签名。
