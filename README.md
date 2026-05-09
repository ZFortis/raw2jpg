# RAW → JPG

从 RAW 照片文件中提取嵌入的 JPEG 预览图。支持单文件和批量处理，Web 界面操作。

## 功能

- **单文件提取** — 上传单个 RAW 文件，在线预览并下载 JPG
- **批量处理** — 一次上传多个 RAW 文件，逐一转换
- **单独下载** — 批量处理后每个文件可独立下载
- **ZIP 打包** — 批量转换成功后一键下载所有 JPG 的压缩包
- **拖拽上传** — 支持拖拽文件到页面，或点击选择

## 支持的格式

CR2 / NEF / ARW / DNG / RAF / ORF / RW2 / PEF / SRW / 3FR 等主流 RAW 格式。

## 安装

```bash
pip install -r requirements.txt
```

需要系统已安装 libraw。macOS 上：

```bash
brew install libraw
```

## 运行

```bash
python3 app.py
```

打开浏览器访问 http://127.0.0.1:8084

## 原理

利用 [rawpy](https://github.com/nekeep/rawpy)（libraw 的 Python 封装）读取 RAW 文件中的嵌入式 JPEG 缩略图。大多数相机的 RAW 文件内部都包含一张相机直出的 JPEG 预览图，本工具直接将其提取出来，无需重新解码 RAW 数据。
