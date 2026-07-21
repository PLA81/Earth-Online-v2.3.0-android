# 用 GitHub Actions 生成 APK

本目录已经包含 `.github/workflows/android-apk.yml`。

1. 在 GitHub 新建一个空仓库。
2. 将本目录全部上传到仓库根目录。
3. 打开仓库的 **Actions** 页面。
4. 选择 **Build Android APK**。
5. 点击 **Run workflow**。
6. 构建完成后，在该次运行底部下载 `EarthOnline-v2.3.0-Android-arm64`。
7. 解压得到 APK，发送到安卓手机安装。

首次构建需要下载 Qt Android wheel、Android SDK 和 NDK，通常耗时较长。APK 是调试签名版本，适合个人安装测试；上架应用商店需要改为 release/AAB 并使用自己的签名证书。
