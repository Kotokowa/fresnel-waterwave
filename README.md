# 水波场恢复 · Water Wave Lab

- [工作台](https://kotokowa.github.io/FresnelWaterwave/) · [使用教程](https://kotokowa.github.io/FresnelWaterwave/guide.html)
- [离线版与 GPU 加速器](https://kotokowa.github.io/FresnelWaterwave/offline-download.html) · [GitHub Releases](https://github.com/Kotokowa/FresnelWaterwave/releases)
- [小工具主页](https://kotokowa.github.io/webtools/) · [原工作台入口](https://kotokowa.github.io/webtools/water-wave/)

从棋盘格图像和视频恢复水面相对高度，支持单帧、批处理、波场测量与聚焦分析。浏览器可直接运行；也可下载离线版或使用本机 Python 和可选的 NVIDIA GPU 加速。

## 构建与验证

需要 Node.js 22+。执行 `npm test`、`npm run build`，用静态服务器打开 `dist/water-wave/`。Python 测试先安装 `requirements-waterwave.txt`，再执行 `python -m unittest discover -s tests -p 'test_waterwave*.py'`。本机服务的安装方式见[加速器说明](docs/native-accelerator.md)。

GitHub Pages 由 `main` 分支的工作流构建。发布新的签名离线包前，需要在本仓库的 Actions Secrets 配置与现有公钥对应的 `WATERWAVE_SIGNING_KEY`。已迁移的历史安装包沿用原签名和 `SHA256SUMS.txt`。
