import argparse
import os
import subprocess
import shlex
import sys
from struct import pack
from PIL import Image
import json
import math
from collections import namedtuple

mango_enc_exes = [
    "data/mango-enc.exe",
    "data/mango-enc",
]

def args_to_cmd(args):
    if sys.platform == "win32":
        return subprocess.list2cmdline(args)
    else:
        return shlex.join(args)

AtlasEntry = namedtuple("AtlasEntry", "im x y")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Root path to convert files in")
    parser.add_argument("--exe", help="Encoder executable")
    parser.add_argument("--skip-compress", action="store_true", help="Skip image compression")
    parser.add_argument("--skip-pack", action="store_true", help="Skip image packing")
    args = parser.parse_args()

    exe = args.exe
    if not exe:
        for exe_name in mango_enc_exes:
            if os.path.exists(exe_name):
                exe = exe_name
                print(f"Autodetected: --exe {exe_name}")
                break
    if not exe:
        raise RuntimeError("Could not find encoder exe by default name, use --exe to specify manually")

    def file_exists(name):
        return os.path.exists(os.path.join(args.path, name))

    page_exts = ["png", "jpg", "jpeg"]

    page_ext = ""
    for ext in page_exts:
        first_name = f"page001.{ext}"
        if file_exists(first_name):
            page_ext = ext
    if not page_ext:
        raise RuntimeError("Could not find the first page")
    num_pages = 1
    while file_exists(f"page{num_pages+1:03}.{page_ext}"):
        num_pages += 1
    print(f"Found {num_pages} .{page_ext} pages")

    if not args.skip_compress:
        for page in range(num_pages):
            file = f"page{page+1:03}.{page_ext}"
            path = os.path.join(args.path, file)
            exe_args = [exe, path, "--format", "mips"]
            print(f"$ {args_to_cmd(exe_args)}")
            subprocess.check_call(exe_args)

    def read_bytes(name):
        with open(os.path.join(args.path, name), "rb") as f:
            return f.read()

    content_json = {
        "pages": [],
        "files": [],
    }

    batch_sizes = [
        1, 1, 2, 4,
    ]

    for mip in range(4):
        batch_size = batch_sizes[mip]
        for fmt_ext in ("eac", "bc4"):
            mips_json = {
                "mipLevel": mip,
                "format": fmt_ext,
                "batch": batch_size > 1,
                "pages": [],
            }
            content_json["files"].append(mips_json)

            for base in range(0, num_pages, batch_size):
                count = min(num_pages - base, batch_size)
                data = [read_bytes(f"page{n+1:03}.{fmt_ext}.{mip}.mip") for n in range(base, base + count)]
                print(f"{mip}.{base}")

                if batch_size > 1:
                    name = f"pages{base+1:03}.{fmt_ext}.{mip}.mips"
                    mips_json["pages"].append({
                        "base": base,
                        "count": count,
                        "name": name,
                    })

                    if not args.skip_pack:
                        header = bytearray()
                        header += b"msv0"
                        header += pack("<I", len(data))

                        offset = len(header) + 8*len(data)
                        for d in data:
                            size = len(d)
                            header += pack("<II", offset, size)
                            offset += size

                        with open(os.path.join(args.path, name), "wb") as f:
                            f.write(header)
                            for d in data:
                                f.write(d)
                else:
                    name = f"page{base+1:03}.{fmt_ext}.{mip}.mip"
                    mips_json["pages"].append(name)

    atlas_max_height = 96
    atlas_max_width = 96
    atlas_aspect = atlas_max_width / atlas_max_height

    thumb_max_height = 350
    thumb_max_width = 350
    thumb_aspect = thumb_max_width / thumb_max_height

    atlas_pad = 4

    atlas_min_width = math.floor(math.sqrt(num_pages)) * atlas_max_width
    atlas_width = 1
    while atlas_width < atlas_min_width:
        atlas_width *= 2

    atlas_x = 0
    atlas_y = 0

    atlas_entries = []

    for page in range(num_pages):
        file = f"page{page+1:03}.{page_ext}"
        path = os.path.join(args.path, file)
        page_json = { }
        print(page)

        with Image.open(path) as im:
            width, height = im.size

            aspect = width / height
            if aspect < atlas_aspect:
                atlas_h = atlas_max_height
                atlas_w = int(math.floor(atlas_h * aspect))
            else:
                atlas_w = atlas_max_width
                atlas_h = int(math.floor(atlas_w / aspect))

            if atlas_x + atlas_w + atlas_pad > atlas_width:
                atlas_x = 0
                atlas_y += atlas_max_height + atlas_pad

            atlas_im = im.resize((atlas_w, atlas_h), Image.BICUBIC)
            atlas_entries.append(AtlasEntry(atlas_im, atlas_x, atlas_y))

            if aspect < thumb_aspect:
                thumb_h = thumb_max_height
                thumb_w = int(math.floor(thumb_h * aspect))
            else:
                thumb_w = atlas_max_width
                thumb_h = int(math.floor(thumb_w / aspect))

            thumb_im = im.resize((thumb_w, thumb_h), Image.BICUBIC)
            thumb_im.save(os.path.join(args.path, f"page{page+1:03}.thumb.jpg"), quality=30)

            page_json["atlasX"] = atlas_x
            page_json["atlasY"] = atlas_y
            page_json["atlasW"] = atlas_w
            page_json["atlasH"] = atlas_h
            page_json["width"] = width
            page_json["height"] = height

            atlas_x += atlas_w + atlas_pad

        content_json["pages"].append(page_json)

    atlas_height = atlas_y + atlas_max_height + atlas_pad

    atlas_im = Image.new("L", (atlas_width, atlas_height), 255)
    for entry in atlas_entries:
        atlas_im.paste(entry.im, (entry.x, entry.y))
    atlas_im.save(os.path.join(args.path, "atlas.png"))

    content_json["atlas"] = {
        "width": atlas_width,
        "height": atlas_height,
    }

    if True:
        path = os.path.join(args.path, "atlas.png")
        exe_args = [exe, path, "--format", "ktx"]
        print(f"$ {args_to_cmd(exe_args)}")
        subprocess.check_call(exe_args)

    with open(os.path.join(args.path, "mango-content.json"), "wt") as f:
        json.dump(content_json, f, indent=2)

