from __future__ import annotations

import argparse
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont


WIDTH = 1280
HEIGHT = 720
FPS = 24


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _frame(title: str, bullets: list[str], progress: float) -> np.ndarray:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#071426")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((54, 42, WIDTH - 54, HEIGHT - 42), 34, fill="#0d2038")
    draw.rounded_rectangle((88, 78, 310, 124), 22, fill="#14b8a6")
    draw.text((118, 84), "PaperPilot 学习视频", font=_font(24, True), fill="white")
    draw.text((92, 172), title, font=_font(58, True), fill="#f8fafc")
    y = 286
    for bullet in bullets:
        draw.ellipse((96, y + 12, 112, y + 28), fill="#38bdf8")
        draw.text((138, y), bullet, font=_font(34), fill="#dbeafe")
        y += 82
    draw.rounded_rectangle((92, 640, WIDTH - 92, 654), 7, fill="#1e3a5f")
    draw.rounded_rectangle(
        (92, 640, 92 + int((WIDTH - 184) * progress), 654),
        7,
        fill="#14b8a6",
    )
    draw.text((92, 674), "本地 MP4 · 用于聊天推荐与网页内播放演示", font=_font(20), fill="#94a3b8")
    return np.asarray(image)


def generate(output: Path) -> None:
    slides = [
        ("Transformer 基础", ["用注意力机制建模序列关系", "适用于文本理解与生成任务"]),
        ("自注意力机制", ["Query：当前要关注什么", "Key / Value：从上下文提取信息"]),
        ("编码器与解码器", ["编码器形成上下文表示", "解码器按步骤生成目标序列"]),
        ("阅读论文时怎么用", ["先定位任务、方法与实验结论", "再结合表格、公式和原文引用追问"]),
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    container = av.open(str(output), mode="w")
    stream = container.add_stream("libx264", rate=FPS)
    stream.width = WIDTH
    stream.height = HEIGHT
    stream.pix_fmt = "yuv420p"
    stream.options = {"crf": "23", "preset": "veryfast", "movflags": "+faststart"}
    frames_per_slide = FPS * 3
    total_frames = frames_per_slide * len(slides)
    for slide_index, (title, bullets) in enumerate(slides):
        for local_index in range(frames_per_slide):
            frame_index = slide_index * frames_per_slide + local_index
            progress = (frame_index + 1) / total_frames
            video_frame = av.VideoFrame.from_ndarray(
                _frame(title, bullets, progress),
                format="rgb24",
            )
            for packet in stream.encode(video_frame):
                container.mux(packet)
    for packet in stream.encode():
        container.mux(packet)
    container.close()
    print(f"DEMO_VIDEO_OK path={output} bytes={output.stat().st_size}")


def main() -> None:
    parser = argparse.ArgumentParser(description="生成PaperPilot本地学习视频样例")
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data/videos/transformer-demo.mp4",
    )
    args = parser.parse_args()
    generate(args.output.expanduser().resolve())


if __name__ == "__main__":
    main()
