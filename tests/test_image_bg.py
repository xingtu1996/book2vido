"""图片铺底（bg_images）单元测试：不依赖 ollama / 网络 / 真书，纯 Pillow。"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from book2vido import config, visualizer
from book2vido.visualizer import PillowProvider


class _Scene:
    def __init__(self, keyword="", text="", concept=""):
        self.keyword = keyword
        self.text = text
        self.concept = concept


def _mk_img(path: Path, color):
    Image.new("RGB", (200, 200), color).save(path)


def test_bg_images_default_empty():
    # 默认应走纯色底，不带任何铺底
    assert config.load()["visual"]["bg_images"] == []


def test_pillow_provider_accepts_bg_images_kw():
    # providers.build 用 **cfg["visual"] 构造 viz，必须能接收 bg_images 而不报错
    kw = dict(config.load()["visual"])
    kw.update(icons=False, allow_network=False)
    p = PillowProvider(**kw)
    assert p.bg_images == []


def test_card_uses_bg_image_and_cycles():
    with _tmp() as d:
        blue = Path(d) / "blue.png"
        green = Path(d) / "green.png"
        _mk_img(blue, (0, 0, 255))
        _mk_img(green, (0, 255, 0))
        out = Path(d) / "out"
        out.mkdir()

        p = PillowProvider(bg_images=[str(blue), str(green)], theme="ink",
                           icons=False, allow_network=False)

        card_b0 = p.card(_Scene(keyword="测试", text="这是测试铺底"), 1, out)   # -> blue
        card_b1 = p.card(_Scene(keyword="测试", text="这是测试铺底"), 2, out)   # -> green
        assert Path(card_b0).exists() and Path(card_b1).exists()

        # 两张用了不同背景图 → 字节必不同（证明铺底生效 + 循环）
        assert Path(card_b0).read_bytes() != Path(card_b1).read_bytes()

        # 画布尺寸正确
        assert Image.open(card_b0).size == (1080, 1920)

        # 纯色底版本应与铺底版本不同（用独立输出目录，避免同 idx 覆盖同名文件）
        out2 = Path(d) / "out2"
        out2.mkdir()
        plain = PillowProvider(theme="ink", icons=False, allow_network=False)
        card_plain = plain.card(_Scene(keyword="测试", text="这是测试铺底"), 1, out2)
        assert Path(card_plain).read_bytes() != Path(card_b0).read_bytes()


def test_bad_bg_path_falls_back_to_solid():
    with _tmp() as d:
        out = Path(d) / "out"
        out.mkdir()
        p = PillowProvider(bg_images=["/nope/does-not-exist.png"], theme="ink",
                           icons=False, allow_network=False)
        # 路径非法不应抛异常，回退纯色底
        card = p.card(_Scene(keyword="k", text="t"), 1, out)
        assert Path(card).exists()


def test_explicit_bg_override():
    with _tmp() as d:
        img = Path(d) / "x.png"
        _mk_img(img, (255, 0, 0))
        out = Path(d) / "out"
        out.mkdir()
        p = PillowProvider(theme="ink", icons=False, allow_network=False)  # 无 bg_images
        card = p.card(_Scene(keyword="k", text="t"), 1, out, bg_image=str(img))
        assert Path(card).exists()


class _tmp:
    """极简临时目录上下文（避开 pytest.tmpdir 的 import 抖动）。"""
    def __enter__(self):
        import tempfile
        self._d = tempfile.mkdtemp()
        return self._d
    def __exit__(self, *a):
        import shutil
        shutil.rmtree(self._d, ignore_errors=True)
