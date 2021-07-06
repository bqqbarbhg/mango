from PIL import Image, ImageFilter
import numpy as np
import argparse
import glob
import os

def enumerate_crops(array, crop_size):
    arr_size = array.shape
    for dy in range(arr_size[0] - crop_size[1] + 1):
        for dx in range(arr_size[1] - crop_size[0] + 1):
            yield array[dy:dy+crop_size[1], dx:dx+crop_size[0], :], (dx, dy)

def enumerate_matches(img_a, img_b, crop_size) -> float:
    data_a = np.asarray(img_a)
    data_b = np.asarray(img_b)

    for crop_a, d_a in enumerate_crops(data_a, crop_size):
        for crop_b, d_b in enumerate_crops(data_b, crop_size):
            delta = np.subtract(crop_a, crop_b, dtype=np.float32)
            yield np.sum(delta*delta), d_a, d_b

def fit_size(image_size, ref_size):
    scale_x = ref_size[0] / image_size[0]
    scale_y = ref_size[1] / image_size[1]
    if image_size[1] * scale_x <= ref_size[1]:
        return (ref_size[0], int(image_size[1] * scale_x))
    elif image_size[1] * scale_x <= ref_size[1]:
        return (int(image_size[0] * scale_y), ref_size[1])
    else:
        return ref_size


def compare_images(path_jp, path_en):
    best_match = None
    best_err = np.Infinity

    crop_amount = 10
    ref_size = (100, 150)

    with Image.open(path_jp) as img_a:
        with Image.open(path_en) as img_b:
            crop_size = (ref_size[0] - crop_amount*2, ref_size[1] - crop_amount*2)

            img_a_size = fit_size(img_a.size, ref_size)
            img_a_x = (ref_size[0] - img_a_size[0]) // 2 + crop_amount
            img_a_y = (ref_size[1] - img_a_size[1]) // 2 + crop_amount
            a_crop = (img_a_x, img_a_y, img_a_x+crop_size[0], img_a_y+crop_size[1])
            img_a = img_a.convert("RGB")
            img_b = img_b.convert("RGB")

            img_a = img_a.filter(ImageFilter.GaussianBlur(min(*img_a.size) * 0.003))
            img_b = img_b.filter(ImageFilter.GaussianBlur(min(*img_b.size) * 0.003))

            b_temp_size = fit_size(img_b.size, img_a_size)
            img_b = img_b.resize(b_temp_size)

            img_a = img_a.resize(img_a_size).crop(a_crop)

            b_scale_size = (int(ref_size[0]*1.1), int(ref_size[1]*1.1))
            prev_b_ref_size = (b_scale_size[0] + 1, b_scale_size[1] + 1)

            for shrink in range(1000):
                scale = 0.999 ** shrink
                b_ref_size = (round(b_scale_size[0] * scale), round(b_scale_size[1] * scale))
                if b_ref_size == prev_b_ref_size:
                    continue
                prev_b_ref_size = b_ref_size

                if b_ref_size[0] < crop_size[0] or b_ref_size[1] < crop_size[1]:
                    break

                img_c_size = fit_size(img_b.size, b_ref_size)
                img_c = img_b.resize(img_c_size)

                for err, a_offset, c_offset in enumerate_matches(img_a, img_c, crop_size):
                    if err < best_err:
                        best_err = err
                        best_match = c_offset, img_c_size

    # img_a.save("temp/match_a.png")
    # b_off, b_size = best_match
    # img_b.resize(b_size).crop((b_off[0], b_off[1], b_off[0]+crop_size[0], b_off[1]+crop_size[1])).save("temp/match_b.png")

    dst_offset, dst_size = best_match

    print(dst_size, ref_size)

    scale_x = dst_size[0] / ref_size[0]
    scale_y = dst_size[1] / ref_size[1]
    offset_x = (dst_offset[0] - crop_amount) / ref_size[0]
    offset_y = (dst_offset[1] - crop_amount) / ref_size[1]

    return best_err / (ref_size[0]*ref_size[1]) / (255.0*255.0), ((scale_x, scale_y), (offset_x, offset_y))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert pages to a Mango-readable form")
    parser.add_argument("--base", metavar="dir/", help="Base directory")
    parser.add_argument("--jp", default="jp/*", metavar="jp/*.jpg", help="Japanese source pages")
    parser.add_argument("--en", default="en/*", metavar="en/*.jpg", help="English source pages")
    args = parser.parse_args(r"--base W:\Mango-Content\Source\Nagatoro\Vol-1".split())

    files_jp = glob.glob(os.path.join(args.base, args.jp))
    files_en = glob.glob(os.path.join(args.base, args.en))

    def rel(path):
        return os.path.relpath(path, args.base,)

    en_base = 0
    for jp_page in files_jp:
        best_err = 0.1
        best_index = -1
        best_transform = None

        deltas = [1,2,0,-1,-2,3,-3,4,-4,5,-5]

        for delta in deltas:
            index = en_base + delta
            if 0 <= index < len(files_en):
                en_page = files_en[en_base + delta]
                err, transform = compare_images(jp_page, en_page)
                print(f"{delta:+2}: {err:0.3f}")
                if err < best_err:
                    best_err = err
                    best_index = index
                    best_transform = transform
                    if err < 0.025: break

        print(best_transform)
        
        if best_index >= 0:
            en_page = files_en[best_index]
            print(rel(jp_page), rel(en_page), best_err)

            en_base = best_index
        else:
            print(rel(jp_page))
