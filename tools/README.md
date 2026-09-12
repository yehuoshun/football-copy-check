# tools/ — 工具链固化目录（防沙箱重置丢失）

沙箱重建会清空系统级安装（pip 包、/usr/share/fonts、/usr/local/bin），
本目录把这些依赖固化进仓库，重置后一条命令恢复。

## 内容

| 路径 | 说明 | 体积 |
|------|------|------|
| `ffmpeg/ffmpeg` | ffmpeg 7.0.2 静态二进制（含 subtitles/drawtext 滤镜） | ~80MB |
| `fonts/NotoSansCJK-Regular.ttc` | 中文字体（烧字幕用） | ~19MB |
| `fonts/NotoSansCJK-Bold.ttc` | 中文字体粗体 | ~20MB |
| `requirements.txt` | TTS 依赖：edge-tts / aiohttp / certifi | - |
| `setup.sh` | 一键恢复脚本 | - |

## 恢复步骤（沙箱重置后）

```bash
cd code/football-copy-check
bash tools/setup.sh
```

## 使用约定

- **ffmpeg**：一律用 `./tools/ffmpeg/ffmpeg`（不要依赖系统 PATH，重置后系统版会丢）
- **字体**：烧字幕时 `fontfile=tools/fonts/NotoSansCJK-Bold.ttc` 直接指定路径，
  不依赖 fc 注册（指定路径最稳）
- **TTS**：`python3 scripts/tts_gen.py "文案" -o out.mp3`
  （沙箱 CA 证书链不完整，脚本已内置 SSL 验证 patch，勿删）

## 来源备忘（重新下载时用）

- ffmpeg: `pip install imageio-ffmpeg` 后取
  `site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2`
- 字体: `sudo dnf install -y google-noto-sans-cjk-fonts`
  路径 `/usr/share/fonts/google-noto-sans-cjk-fonts/`
- TTS: `pip install edge-tts aiohttp certifi`
