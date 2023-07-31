from PIL import Image, ImageFilter
import itertools
import numpy as np
import argparse
import glob
import os
import multiprocessing
from collections import namedtuple
from open_ex import open_ex
import json

def enumerate_crops(array, crop_size):
    arr_size = array.shape
    for dy in range(arr_size[0] - crop_size[1] + 1):
        for dx in range(arr_size[1] - crop_size[0] + 1):
            yield array[dy:dy+crop_size[1], dx:dx+crop_size[0], :], (dx, dy)

def enumerate_matches(data_a, data_b, crop_size) -> float:
    for crop_a, offset_a in enumerate_crops(data_a, crop_size):
        for crop_b, offset_b in enumerate_crops(data_b, crop_size):
            delta = np.subtract(crop_a, crop_b, dtype=np.float32)
            yield np.sum(delta*delta), offset_a, offset_b

def scale_size(size, scale):
    return (round(size[0] * scale), round(size[1] * scale))

def scale_to_height(size, height):
    return (round(size[0] * (height / size[1])), height)

def get_crop_middle(size, crop_size):
    dx = (size[0] - crop_size[0]) // 2
    dy = (size[1] - crop_size[1]) // 2
    return dx, dy, dx + crop_size[0], dy + crop_size[1]

MatchContext = namedtuple("MatchContext", "data_a img_b crop_size")

mp_ctx = None
mp_queue = None
mp_pool = None
mp_threads = 0
mp_token = 0
mp_task_amount = None
mp_task_counter = None

def mp_init(queue, task_counter, task_amount):
    global mp_queue
    global mp_task_counter
    global mp_task_amount
    mp_queue = queue
    mp_task_counter = task_counter
    mp_task_amount = task_amount

def test_size(ctx, size):
    crop_size = ctx.crop_size
    img_b = ctx.img_b.resize(size)

    data_a = ctx.data_a
    data_b = np.asarray(img_b)

    best_err = np.Infinity
    best_offset = (0,0)

    for err, offset_a, offset_b in enumerate_matches(data_a, data_b, crop_size):
        if err < best_err:
            best_err = err
            best_offset = offset_b
    
    return best_err, size, best_offset

def mp_test_size(args):
    global mp_token
    global mp_ctx

    size, token = args

    if token > mp_token:
        mp_token = token
        mp_ctx = mp_queue.get()

    return test_size(mp_ctx, size)

def match_images(img_a, img_b):
    global mp_token

    relative_crop_amount = 0.2

    res_a = img_a.size
    res_b = (img_b.size[0] // 2, img_b.size[1] // 2)

    crop_size = scale_size(res_a, 1.0 - relative_crop_amount)
    crop_rect = get_crop_middle(res_a, crop_size)
    img_a = img_a.crop(crop_rect)

    res_b_scales = set()
    for scale_int in range(-25, 25):
        scale = 1.0 + relative_crop_amount * (scale_int/100)
        b_size = scale_size(res_b, scale)
        if b_size[0] >= crop_size[0] and b_size[1] >= crop_size[1]:
            res_b_scales.add(b_size)

    res_b_scales = sorted(res_b_scales)

    data_a = np.asarray(img_a)
    ctx = MatchContext(data_a, img_b, crop_size)

    best = (np.Infinity, (0, 0), (0, 0))

    if mp_pool:
        mp_token += 1
        mp_args = [(s, mp_token) for s in res_b_scales]

        try:
            while True:
                mp_queue.get_nowait()
        except:
            pass

        for _ in range(mp_threads):
            mp_queue.put(ctx)

        for result in mp_pool.imap_unordered(mp_test_size, mp_args, chunksize=1):
            if result < best:
                best = result
    else:
        for size in res_b_scales:
            result = test_size(ctx, size)
            if result < best:
                best = result

    error, size, offset = best

    if error < np.Infinity:
        error = error / (crop_size[0]*crop_size[1]) / (255*255)
        scale = (size[0] / res_b[0], size[1] / res_b[1])
        offset = (-(offset[0] - crop_rect[0]) / size[0], -(offset[1] - crop_rect[1]) / size[1])

    return error, (scale, offset)

def compare_images(path_jp, path_en):
    with Image.open(path_jp) as img_a:
        with Image.open(path_en) as img_b:
            img_a = img_a.convert("RGB")
            img_b = img_b.convert("RGB")

            return match_images(img_a, img_b)

class Counter:
    def __init__(self):
        self.val = multiprocessing.Value('i', 0)

    def set(self, value):
        with self.val.get_lock():
            self.val.value = value

    def increment(self, n=1):
        with self.val.get_lock():
            value = self.val.value
            self.val.value += n
        return value

    @property
    def value(self):
        return self.val.value

def resize_image(src_path, dst_path, height, factor):
    with Image.open(src_path) as img:
        progress = (mp_task_counter.increment(1) + 1) / mp_task_amount.value
        print(f"{dst_path} <{progress*100:.1f}%>")
        size = scale_to_height(img.size, height*factor)
        img = img.convert("RGB")
        img = img.filter(ImageFilter.GaussianBlur(min(*img.size) * (0.5 / height)))
        img = img.resize(size)
        img.save(dst_path)

def main(args):

    temp_dir = os.path.join("temp", "match")
    os.makedirs(temp_dir, exist_ok=True)

    files_jp = glob.glob(os.path.join(args.base, args.jp))
    files_en = glob.glob(os.path.join(args.base, args.en))

    resized_jp = [os.path.join(temp_dir, f"jp_{i:03}.png") for i in range(len(files_jp))]
    resized_en = [os.path.join(temp_dir, f"en_{i:03}.png") for i in range(len(files_en))]

    height = 150

    print("-- Resizing images...")
    if not args.skip_resize:
        en_tasks = ((s, d, height, 1) for s,d in zip(files_jp, resized_jp))
        jp_tasks = ((s, d, height, 2) for s,d in zip(files_en, resized_en))
        tasks = list(itertools.chain(en_tasks, jp_tasks))
        mp_task_counter.set(0)
        mp_task_amount.set(len(tasks))
        if mp_pool:
            mp_pool.starmap_async(resize_image, tasks).wait()
        else:
            for task in tasks:
                resize_image(*task)

    def rel(path):
        return os.path.relpath(path, args.base,)
    
    pages = []

    print("-- Matching images...")
    en_base = 0
    num_files = min(len(files_jp), len(resized_jp))
    for jp_index, (jp_src, jp_tmp) in enumerate(zip(files_jp, resized_jp)):
        best_err = args.error_limit
        best_index = -1
        best_transform = None

        deltas = [1,2,0,-1,-2,3,-3,4,-4,5,-5]

        for delta in deltas:
            index = en_base + delta
            if 0 <= index < len(resized_en):
                en_tmp = resized_en[en_base + delta]
                err, transform = compare_images(jp_tmp, en_tmp)
                print(f"{delta:+2}: {err:0.3f}")
                if err < best_err:
                    best_err = err
                    best_index = index
                    best_transform = transform
                    if err < args.sure_limit: break

        progress = (jp_index+1) / num_files * 100
        if best_index >= 0:
            en_src = files_en[best_index]
            en_tmp = resized_en[best_index]
            print(rel(jp_src), rel(en_src), f"<{progress:.1f}%>")

            scale, offset = best_transform

            pages.append({
                "jp": rel(jp_src),
                "en": rel(en_src),
                "transform": {
                    "scale": scale,
                    "offset": offset,
                }
            })

            if args.save_match:
                with Image.open(jp_tmp) as img_jp:
                    with Image.open(en_tmp) as img_en:
                        size_jp = img_jp.size
                        size_en = (int(img_en.size[0] * scale[0] * 0.5), int(img_en.size[1] * scale[1] * 0.5))
                        img_en = img_en.resize(size_en)
                        offset_en = (int(size_en[0] * -offset[0]), int(size_en[1] * -offset[1]))
                        crop = (offset_en[0], offset_en[1], offset_en[0]+size_jp[0], offset_en[1]+size_jp[1])
                        img_match = Image.blend(img_jp, img_en.crop(crop), alpha=0.5)
                        path = os.path.join(temp_dir, f"match_{jp_index:03}.png")
                        img_match.save(path)

            en_base = best_index
        else:
            print(rel(jp_src), f"<{progress:.1f}%>")

            pages.append({
                "jp": rel(jp_src),
            })

    output = os.path.join(args.base, args.o)

    desc = { }
    if os.path.exists(output):
        with open_ex(output, "rt") as f:
            desc = json.load(f)

    desc["pages"] = pages

    with open_ex(output, "wt") as f:
        json.dump(desc, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert pages to a Mango-readable form")
    parser.add_argument("--base", metavar="dir/", help="Base directory")
    parser.add_argument("--jp", default="jp/*", metavar="jp/*.jpg", help="Japanese source pages")
    parser.add_argument("--en", default="en/*", metavar="en/*.jpg", help="English source pages")
    parser.add_argument("-o", default="mango-desc.json", metavar="desc.json", help="Description file to write")
    parser.add_argument("--threads", type=int, default=1, metavar="num", help="Number of threads to use")
    parser.add_argument("--skip-resize", action="store_true", help="Use cached resized images")
    parser.add_argument("--sure-limit", type=float, default=0.025, help="Limit of error that is sure to be the same")
    parser.add_argument("--error-limit", type=float, default=0.1, help="Maximum error to accept a page")
    parser.add_argument("--save-match", action="store_true", help="Save temporary match images")
    args = parser.parse_args()

    mp_queue = multiprocessing.Queue(args.threads)
    mp_task_counter = Counter()
    mp_task_amount = Counter()

    if args.threads > 1:
        with multiprocessing.Pool(args.threads, mp_init, (mp_queue, mp_task_counter, mp_task_amount)) as pool:
            mp_pool = pool
            mp_threads = args.threads
            main(args)
    else:
        main(args)
