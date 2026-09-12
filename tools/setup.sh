#!/usr/bin/env bash
# 沙箱重置后一键恢复工具链（ffmpeg / 字体 / TTS 依赖）
# 用法: bash tools/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> 1/3 安装 Python 依赖 (edge-tts / aiohttp / certifi)"
pip install -q -r tools/requirements.txt

echo "==> 2/3 注册中文字体（烧字幕用）"
FONTS_DIR=/usr/share/fonts/google-noto-sans-cjk-fonts
if [ -d "$FONTS_DIR" ]; then
  echo "    系统字体已存在，跳过拷贝"
else
  sudo -n mkdir -p "$FONTS_DIR" 2>/dev/null || mkdir -p "$FONTS_DIR"
  cp tools/fonts/*.ttc "$FONTS_DIR/"
  fc-cache -f >/dev/null 2>&1 || true
fi

echo "==> 3/3 验证 ffmpeg"
./tools/ffmpeg/ffmpeg -version | head -1

echo "✅ 工具链就绪：ffmpeg=tools/ffmpeg/ffmpeg，字体=tools/fonts/，TTS=scripts/tts_gen.py"
