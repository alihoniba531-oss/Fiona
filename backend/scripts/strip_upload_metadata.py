#!/usr/bin/env python3
"""只读盘点或原子清理旧广场媒体、聊天图片的元数据。"""
import argparse
from collections import Counter
import os
from pathlib import Path
import re
import stat
import sys

from PIL import Image

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
from utils.dotenv_config import select_dotenv_path


def configure_uploads(env_file: Path | None) -> Path:
    # Match admin_env's dotenv selection and non-overriding environment behavior,
    # without requiring an unrelated database or printing configuration paths.
    selected = select_dotenv_path(env_file, backend_dir=BACKEND_DIR)
    if selected is not None:
        load_dotenv(dotenv_path=selected, override=False)
    return Path(os.environ.get("FIONA_UPLOADS_DIR") or BACKEND_DIR / "uploads").expanduser().resolve()


def _eligible(path: Path) -> bool:
    return (
        path.is_file()
        and not path.is_symlink()
        and not path.name.startswith(".")
        and (path.name.startswith("plaza_") or re.fullmatch(r"[0-9a-fA-F]{32}\.[^.]+", path.name) is not None)
    )


def _gif_has_metadata(path: Path) -> bool:
    # Pillow exposes only the last application extension, so a later loop
    # block can hide an earlier XMP block. Inspect all block headers instead.
    with path.open("rb") as source:
        def read_exact(size):
            data = source.read(size)
            if len(data) != size:
                raise ValueError("truncated GIF block")
            return data

        def skip_subblocks():
            while size := read_exact(1)[0]:
                source.seek(size, os.SEEK_CUR)

        header = read_exact(13)
        if header[10] & 0x80:
            source.seek(3 * (1 << ((header[10] & 7) + 1)), os.SEEK_CUR)
        while True:
            block = read_exact(1)
            if block == b";":
                return False
            if block == b",":
                descriptor = read_exact(9)
                if descriptor[8] & 0x80:
                    source.seek(3 * (1 << ((descriptor[8] & 7) + 1)), os.SEEK_CUR)
                read_exact(1)  # LZW minimum code size.
                skip_subblocks()
            elif block == b"!":
                label = read_exact(1)[0]
                if label == 0xFF:
                    application = read_exact(read_exact(1)[0])
                    if application not in {b"NETSCAPE2.0", b"ANIMEXTS1.0"}:
                        return True
                elif label != 0xF9:  # Graphic control is playback; comments/text are metadata.
                    return True
                skip_subblocks()
            else:
                raise ValueError("invalid GIF block")


def _image_chunks_have_metadata(path: Path, ext: str) -> bool:
    # Unknown ancillary chunks can contain timestamps or private text even
    # when Pillow does not expose them in image.info.
    png_chunks = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"iCCP", b"tRNS"}
    webp_chunks = {b"VP8X", b"VP8 ", b"VP8L", b"ALPH", b"ANIM", b"ANMF", b"ICCP"}
    with path.open("rb") as source:
        source.seek(8 if ext == "png" else 12)
        while header := source.read(8):
            if len(header) != 8:
                raise ValueError("truncated image chunk")
            if ext == "png":
                size = int.from_bytes(header[:4], "big")
                kind = header[4:]
                if kind not in png_chunks:
                    return True
                source.seek(size + 4, os.SEEK_CUR)  # Chunk data and CRC.
                if kind == b"IEND":
                    return False
            else:
                kind = header[:4]
                size = int.from_bytes(header[4:], "little")
                if kind not in webp_chunks:
                    return True
                source.seek(size + (size % 2), os.SEEK_CUR)
    return False


def _has_image_metadata(path: Path, ext: str, media) -> bool:
    """Skip clean pixels while retaining ICC and animation playback fields."""
    media._validate_decodable_image(path, ext)
    if ext == "gif" and _gif_has_metadata(path):
        return True
    if ext in {"png", "webp"} and _image_chunks_have_metadata(path, ext):
        return True
    allowed = {"icc_profile", "loop", "duration", "timestamp", "background", "transparency", "version",
               "jfif", "jfif_version", "jfif_unit", "jfif_density", "adobe", "adobe_transform", "mp", "mpoffset"}
    with Image.open(path) as image:
        for index in range(getattr(image, "n_frames", 1)):
            image.seek(index)
            image.load()  # PNG text and GIF comments may follow pixel data.
            info = dict(image.info)
            extension = info.pop("extension", None)
            if extension and extension[0] not in {b"NETSCAPE2.0", b"ANIMEXTS1.0"}:
                return True
            if info.keys() - allowed or image.getexif() or getattr(image, "text", {}):
                return True
            for marker, data in getattr(image, "applist", []):
                if not ((marker == "APP0" and data.startswith(b"JFIF\x00")) or
                        (marker == "APP2" and data.startswith(b"ICC_PROFILE\x00")) or
                        (marker == "APP14" and data.startswith(b"Adobe"))):
                    return True
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--env-file", type=Path, metavar="PATH")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="只读盘点（默认）")
    mode.add_argument("--apply", action="store_true", help="原子改写符合范围的旧上传")
    args = parser.parse_args(argv)
    try:
        uploads = configure_uploads(args.env_file)
        if not uploads.is_dir():
            print("失败目录数：1")
            return 2
        # Configure before import: media reads its directory at import time.
        os.environ["FIONA_UPLOADS_DIR"] = str(uploads)
        from utils import media

        media.UPLOADS_DIR = str(uploads)
        candidates = sorted(path for path in uploads.iterdir() if _eligible(path))
        types = Counter()
        processed = failed = skipped = 0
        for path in candidates:
            temporary = None
            try:
                with path.open("rb") as source:
                    signature = source.read(8192)
                ext = media._sniff_image_ext(signature[:12])
                media_type = "image"
                if ext is None:
                    ext = media._sniff_video_ext(signature)
                    media_type = "video" if ext else "unknown"
                types[f"{media_type}/{ext or 'unknown'}"] += 1
                if not args.apply:
                    continue
                if ext is None:
                    raise ValueError("unsupported format")
                if media_type == "image" and not _has_image_metadata(path, ext, media):
                    skipped += 1
                    continue
                permissions = stat.S_IMODE(path.stat().st_mode)
                temporary = media._upload_temporary()
                media._process_upload(str(path), temporary, ext, media_type)
                os.chmod(temporary, permissions)
                os.replace(temporary, path)
                processed += 1
            except Exception:
                failed += 1
            finally:
                if temporary is not None:
                    media._unlink_upload(temporary)
        print(f"文件数：{len(candidates)}")
        for kind, count in sorted(types.items()):
            print(f"类型 {kind}：{count}")
        print(f"已处理：{processed}；失败：{failed}")
        print(f"已跳过无元数据文件：{skipped}")
        return 1 if args.apply and failed else 0
    except Exception as error:
        print(f"失败类型：{type(error).__name__}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
