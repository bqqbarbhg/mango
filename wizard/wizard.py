from aiohttp import web, WSMsgType
import asyncio
import webbrowser
from argparse import ArgumentParser
from asyncio import subprocess
import shlex
import os
import sys
from collections import namedtuple
from subprocess import list2cmdline
import traceback
from PIL import Image
from io import BytesIO
import json
import re

def quote_arg(args):
    if sys.platform == "win32":
        return list2cmdline([args])
    else:
        return shlex.quote(args)

def flatten(items):
    for l in items:
        if isinstance(l, list):
            yield from flatten(l)
        else:
            yield l

def args_to_cmd(args):
    if sys.platform == "win32":
        return list2cmdline(args)
    else:
        return shlex.join(args)

def split_args(arg_str):
    if not arg_str:
        return []
    try:
        parts = shlex.split(arg_str)
        result = []
        chunk = []
        for part in parts:
            if part.startswith("-"):
                if chunk:
                    result.append(chunk)
                chunk = [part]
            else:
                chunk.append(part)
        result.append(chunk)
        return result
    except ValueError:
        return []

EnvVar = namedtuple("EnvVar", "name value")

loop = asyncio.new_event_loop()
g_args = None
g_settings = None
g_action_task = None
g_prev_dst_path = None
g_dst_path = None
g_model_paths = []
g_init_info = { }

pages_en = []
pages_jp = []

class EventValue:
    def __init__(self):
        if sys.version_info >= (3, 10):
            self.cond = asyncio.Condition()
        else:
            self.cond = asyncio.Condition(loop=loop)
        self.value = 0

    async def increment(self, value=1):
        async with self.cond:
            self.value += value
            self.cond.notify_all()

    async def wait(self, value):
        async with self.cond:
            while value >= self.value:
                await self.cond.wait()
            return self.value

log_gen = EventValue()
log_list = []

async def log(type: str, message: str):
    print(message, flush=True)
    log_list.append({ "type": type, "line": message })
    await log_gen.increment()

async def index(request):
    return web.FileResponse("wizard/index.html")

async def src_image(request):
    path = os.path.join(g_args.src, request.match_info["path"])
    with Image.open(path) as im:
        width, height = im.size
        aspect = width / height
        new_height = 160
        new_width = max(1, int(new_height * aspect))
        im2 = im.resize((new_width, new_height), resample=Image.BICUBIC)

        im_data = BytesIO()
        im2.save(im_data, "PNG")

        im2.close()
        im_data.seek(0)
        return web.Response(body=im_data, content_type="image/png")

def format_cmds(cmds):
    for cmd in cmds:
        if isinstance(cmd, list):
            yield list(format_cmds(cmd))
        else:
            yield quote_arg(cmd)

async def handle_action(action, ws):
    global g_settings
    global g_action_task
    try:
        act = action["action"]
        if act == "execute":
            try:
                await ws.send_json({
                    "type": "busy",
                    "busy": True,
                })
                cmds = get_init_commands(g_settings)
                await run_commands(cmds)
            finally:
                try:
                    await ws.send_json({
                        "type": "busy",
                        "busy": False,
                    })
                    g_action_task = None
                except:
                    pass
        elif act == "cancel":
            if g_action_task and not g_action_task.done():
                g_action_task.cancel()
        elif act == "settings":
            g_settings = action["settings"]
            cmds = get_init_commands(g_settings)
            await ws.send_json({
                "type": "commands",
                "commands": list(format_cmds(cmds)),
            })
        elif act == "save-info":
            info = action["info"]
            save_info(info)
    except asyncio.CancelledError:
        print(f"handle_action() cancelled: {action}")
    except Exception:
        print(f"handle_action() error: {action}")
        traceback.print_exc()

async def web_socket(request):
    global g_action_task

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    await ws.send_json({
        "type": "init",
        "data": {
            "pagesEn": pages_en,
            "pagesJp": pages_jp,
        },
        "info": g_init_info,
        "models": g_model_paths,
    })

    if g_settings:
        await ws.send_json({
            "type": "settings",
            "settings": g_settings,
        })

    if g_action_task and not g_action_task.done():
        await ws.send_json({
            "type": "busy",
            "busy": True,
        })

    async def process_log():
        try:
            value = 0
            start = 0
            local_list = None
            while True:
                value = await log_gen.wait(value)

                if log_list != local_list:
                    await ws.send_json({
                        "type": "clear-log",
                    })
                    local_list = log_list
                    start = 0

                logs = local_list[start:]
                start = len(local_list)
                await ws.send_json({
                    "type": "log",
                    "log": logs,
                })
        except asyncio.CancelledError:
            return
        except Exception:
            print("process_log() error")
            traceback.print_exc()

    log_task = asyncio.create_task(process_log())

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            data = msg.json()
            if "action" in data:
                act = data["action"]
                if act == "execute" and g_action_task and not g_action_task.done():
                    g_action_task.cancel()
                    g_action_task = None
                action_task = asyncio.create_task(handle_action(data, ws))
                if act == "execute":
                    g_action_task = action_task
        elif msg.type == WSMsgType.ERROR:
            break
        elif msg.type == WSMsgType.CLOSE:
            break
    log_task.cancel()

async def log_stream(type, stream):
    while not stream.at_eof():
        line = await stream.readline()
        line = line.decode("utf-8", errors="replace").rstrip()
        await log(type, line)

async def execute(cmd):
    cmd = list(flatten(cmd))
    line = args_to_cmd(cmd)
    await log("exec", f"$ {line}")
    env = { **os.environ }
    env["PYTHONUNBUFFERED"] = "1"
    proc = await subprocess.create_subprocess_exec(
        cmd[0], *cmd[1:],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env)

    tasks = [
        proc.wait(),
        log_stream("out", proc.stdout),
        log_stream("err", proc.stderr),
    ]
    try:
        code, *_ = await asyncio.gather(*tasks)
        if code == 0:
            await log("exec-ok", f"$ Succeeded"),
        else:
            await log("exec-fail", f"$ Failed with code: {code}"),
    except asyncio.CancelledError:
        await log("exec-fail", f"$ Cancelled"),
        proc.kill()
        raise

def copy_cover(cover_src, dst_path):
    cover_hi_dst = os.path.join(dst_path, "cover-high.png")
    cover_lo_dst = os.path.join(dst_path, "cover.jpg")

    with Image.open(cover_src) as cover_image:
        cover_image.save(cover_hi_dst, format="PNG")

        MAX_WIDTH = 300
        MAX_HEIGHT = 400

        width, height = cover_image.size
        aspect = width / height
        if aspect > MAX_WIDTH / MAX_HEIGHT:
            if width > MAX_WIDTH:
                width = MAX_WIDTH
                height = int(width / aspect)
        else:
            if height > MAX_HEIGHT:
                height = MAX_HEIGHT
                width = int(height * aspect)
        if (width, height) != cover_image.size:
            cover_result = cover_image.resize((width, height), Image.BICUBIC)
        else:
            cover_result = cover_image

        cover_result.save(cover_lo_dst, format="JPEG", quality=95)
        if cover_result != cover_image:
            cover_result.close()


def save_info(info_forms):
    info = info_forms["info"]
    chapters = info_forms["chapters"]["chapters"]

    cover_rel = info["cover"]
    if cover_rel:
        cover_src = os.path.join(g_args.src, cover_rel)
        copy_cover(cover_src, g_dst_path)

    chapter_start = info["chapterStart"]

    def find_page(path):
        try:
            if path.startswith("jp/"):
                return pages_jp.index(path[3:])
        except ValueError:
            pass
        return None

    def make_chapter(ix, c):
        return {
            "title": {
                "en": c["titleEn"],
                "jp": c["titleJp"],
            },
            "startPage": find_page(c["page"]),
            "index": chapter_start + ix,
        }

    result = {
        "title": {
            "en": info["titleEn"],
            "jp": info["titleJp"],
        },
        "volume": info["volume"],
        "startPage": find_page(info["firstPage"]),
        "chapters": [make_chapter(ix, c) for ix, c in enumerate(chapters)],
    }

    dst_path = os.path.join(g_dst_path, "mango-info.json")
    with open(dst_path, "wt", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

def get_init_commands(opts):
    cmds = []

    settings = opts["settings"]
    threads = str(settings["threads"])

    root = g_args.src
    src_jp_1x_path = "jp"
    src_jp_2x_path = "jp_2x"

    upscale = opts["upscale"]
    do_upscale = upscale["enabled"]

    if sys.platform == "win32":
        python_exe = "python"
    else:
        python_exe = "python3"

    if do_upscale:
        ratio = upscale["ratio"]
        model = upscale["model"]
        args = [
            [
                python_exe,
                "mango_upscale.py",
            ],
            [
                os.path.join(root, src_jp_1x_path),
            ],
            [
                "-o",
                os.path.join(root, src_jp_2x_path),
            ],
            [
                "--model",
                model,
            ],
        ]
        if ratio < 2:
            downscale = ratio / 2.0
            args += [
                [
                    "--downscale",
                    str(downscale),
                ],
            ]
        args += split_args(upscale.get("args", ""))
        cmds.append(args)

    setup = opts["setup"]
    if setup["enabled"]:
        sure_limit = setup["sureLimit"]
        args = [
            [
                python_exe,
                "mango_init.py",
            ],
            [
                "--base",
                g_args.src,
            ],
        ]

        if do_upscale:
            args += [
                [
                    "--jp",
                    os.path.join(src_jp_2x_path, "*"),
                ],
            ]

        args += [
            [
                "--sure-limit",
                str(sure_limit),
            ],
            [
                "--threads",
                threads,
            ],
        ]
        args += split_args(setup.get("args", ""))
        cmds.append(args)

    ocr = opts["ocr"]
    if ocr["enabled"]:
        args = [
            [
                python_exe,
                "mangofy.py",
            ],
            [
                os.path.join(g_args.src, "mango-desc.json"),
            ],
            [
                "-o",
                g_dst_path,
            ],
            [
                "--gcp-credentials",
                ocr["credentials"],
            ],
            [
                "--threads",
                threads,
            ],
        ]
        args += split_args(ocr.get("args", ""))
        cmds.append(args)

    copy = opts["copy"]
    if copy["enabled"]:
        args = [
            [
                python_exe,
                "mango_copy.py",
            ],
            [
                os.path.join(g_args.src, "mango-desc.json"),
            ],
            [
                "-o",
                g_dst_path,
            ],
        ]
        args += split_args(copy.get("args", ""))
        cmds.append(args)

    compress = opts["compress"]
    if compress["enabled"]:
        args = [
            [
                python_exe,
                "mango_compress.py",
            ],
            [
                g_dst_path,
            ],
        ]
        args += split_args(compress.get("args", ""))
        cmds.append(args)

    return cmds

async def run_commands(cmds):
    global log_list
    log_list = []
    await log_gen.increment()
    for cmd in cmds:
        await execute(cmd)

def valid_model(path):
    return all(os.path.exists(os.path.join(path, p)) for p in [
        "image.pth", "kanji.pth", "select.pth",
    ])

if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("src", help="Source directory")
    parser.add_argument("-o", help="Destination directory")
    parser.add_argument("-op", help="Destination parent directory, expects the suffix of src to be /Manga/Vol-N")
    g_args = parser.parse_args()

    if g_args.o:
        g_dst_path = g_args.o
    elif g_args.op:
        src_head, src_vol = os.path.split(g_args.src.rstrip("/\\"))
        src_head, src_name = os.path.split(src_head)

        g_dst_path = os.path.join(g_args.op, src_name, src_vol)

        m = re.match(r"(?i)(vol)-(\d+)", src_vol)
        if m:
            vol_str = m.group(1)
            volume = int(m.group(2))
            if volume > 0:
                prev_vol = f"{vol_str}-{volume - 1}"
                g_prev_dst_path = os.path.join(g_args.op, src_name, prev_vol)
    else:
        raise RuntimeError("Need to specify either -o or -op")

    if g_prev_dst_path:
        prev_info = os.path.join(g_prev_dst_path, "mango-info.json")
        try:
            with open(prev_info, "rt", encoding="utf-8") as f:
                info = json.load(f)
                last_chapter = max(c.get("index", -1) for c in info["chapters"])
                title = info.get("title", { })
                volume = info.get("volume", -1)
                g_init_info = {
                    "chapterStart": last_chapter + 1,
                    "titleEn": title.get("en", ""),
                    "titleJp": title.get("jp", ""),
                    "volume": volume + 1,
                }
        except FileNotFoundError:
            pass

    for root, dirs, files in os.walk("models"):
        for d in dirs:
            dir_path = os.path.join(root, d)
            if valid_model(dir_path):
                g_model_paths.append(dir_path)
    g_model_paths.sort()

    os.makedirs(g_dst_path, exist_ok=True)

    app = web.Application()
    app.add_routes([
        web.get("/", index),
        web.static("/src/", g_args.src),
        web.get("/src-img/{path:.*}", src_image),
        web.get("/ws", web_socket),
        web.static("/", "wizard"),
    ])

    def listdir_maybe(path):
        try:
            return os.listdir(path)
        except FileNotFoundError:
            return []

    pages_en = sorted(listdir_maybe(os.path.join(g_args.src, "en")))
    pages_jp = sorted(listdir_maybe(os.path.join(g_args.src, "jp")))

    async def on_startup(_):
        webbrowser.open("http://localhost:8080")

    app.on_startup.append(on_startup)

    web.run_app(app, loop=loop)
    
