#!/usr/bin/env python3
"""TTS 配音生成工具（edge-tts，免 key）。

用法:
    python3 scripts/tts_gen.py "文案正文" -o output.mp3
    python3 scripts/tts_gen.py 文案.txt -o output.mp3          # 从文件读
    python3 scripts/tts_gen.py "文案" -o out.mp3 -v zh-CN-YunxiNeural -r +10% -p +5Hz

音色推荐（搞笑配音场景）:
    zh-CN-YunxiNeural    男·阳光（默认，解说吐槽向）
    zh-CN-XiaoyiNeural   女·活泼
    zh-CN-YunjianNeural  男·浑厚（电影感）
    zh-CN-XiaoxiaoNeural 女·自然
"""
import argparse
import asyncio
import ssl
import sys

# 沙箱 CA 证书链不完整，edge-tts 硬编码 _SSL_CTX 会握手失败 → patch 掉验证
import aiohttp
import edge_tts
import edge_tts.communicate as comm

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE
comm._SSL_CTX = _ctx


async def _gen(text: str, voice: str, rate: str, pitch: str, out: str) -> None:
    conn = aiohttp.TCPConnector(ssl=False)
    c = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, connector=conn)
    await c.save(out)


def main() -> int:
    ap = argparse.ArgumentParser(description="edge-tts 配音生成")
    ap.add_argument("text", help="文案文本或文本文件路径")
    ap.add_argument("-o", "--output", default="output.mp3", help="输出 mp3 路径")
    ap.add_argument("-v", "--voice", default="zh-CN-YunxiNeural", help="音色")
    ap.add_argument("-r", "--rate", default="+10%", help="语速，如 +10%% / -5%%")
    ap.add_argument("-p", "--pitch", default="+0Hz", help="音调，如 +5Hz")
    args = ap.parse_args()

    text = args.text
    if not text.endswith(".mp3") and ("\n" not in text) and len(text) < 200 and text.endswith((".txt", ".md")):
        text = open(text, encoding="utf-8").read().strip()
    if not text:
        print("文案为空", file=sys.stderr)
        return 1

    asyncio.run(_gen(text, args.voice, args.rate, args.pitch, args.output))
    print(f"✅ 已生成 {args.output} ({len(text)} 字)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
