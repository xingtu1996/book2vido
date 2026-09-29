"""合成：FFmpeg 把信息卡序列 + 语音轨拼成竖版 mp4。本地，零成本。"""
import subprocess
from pathlib import Path

from . import binpaths
from .models import MediaClip


def compose(clips: list[MediaClip], out_path: str, work_dir: str | None = None) -> str:
    """clips: `list[MediaClip]`；也兼容旧的三元组 `(png, audio, duration)`（走 `from_any`）。

    为什么改用 MediaClip 而不是裸 tuple（T2V-002）：
    三元组靠**位置**对齐——把 `(png, audio, dur)` 写成 `(audio, png, dur)` **不会报错**，
    只会产出一条静默出错的片子。字段有名字，写错顺序就会被 Python 抓住。

    work_dir: 本次运行的中间产物目录（卡/语音/clip 都放这里，避免 batch 互相覆盖）。
    list.txt 一律写绝对路径，规避 FFmpeg concat demuxer 对相对路径的二次解析坑。
    """
    out_path = Path(out_path)
    work = Path(work_dir) if work_dir else (out_path.parent / "_clips")
    work.mkdir(parents=True, exist_ok=True)
    clips = [MediaClip.from_any(c) for c in clips]

    # 定位 ffmpeg：内置 vendor → 环境变量 → 常见路径 → PATH（不写死绝对路径）
    ff = binpaths.ffmpeg()

    files = []
    for i, c in enumerate(clips):
        clip = work / f"clip_{i:03d}.mp4"
        subprocess.run(
            [
                ff, "-nostdin", "-y", "-loop", "1", "-i", c.image, "-i", c.audio,
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-t", str(c.duration), "-shortest", str(clip),
            ],
            check=True,
        )
        files.append(clip)

    listf = work / "list.txt"
    with open(listf, "w", encoding="utf-8") as f:
        for c in files:
            f.write(f"file '{c.resolve()}'\n")

    subprocess.run(
        [ff, "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", str(listf), "-c", "copy", str(out_path)],
        check=True,
    )
    return str(out_path)
