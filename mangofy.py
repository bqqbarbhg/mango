import io
import os

from jdict import JDict
import json
import itertools
from io import BytesIO
from PIL import Image
import re
import argparse
import shutil
import copy

jdict = JDict("data/jdict.json.gz")

def bounds_to_aabb(box):
    return {
        "min": (min(v.x for v in box.vertices), min(v.y for v in box.vertices)),
        "max": (max(v.x for v in box.vertices), max(v.y for v in box.vertices)),
    }

lang_hint = {
    "jp": "jp-Jpan",
    "en": "en-t-i0-handwrit",
}

def detect_page_ocr(path, language):
    """Detects document features in an image."""

    tmp_path = os.path.join("temp", path) + ".ocr01.json"
    try:
        with open(tmp_path, "rb") as f:
            return json.load(f)
    except FileNotFoundError:
        pass

    print(f".. Processing OCR: {path} ({language})")

    from google.cloud import vision
    client = vision.ImageAnnotatorClient()

    with io.open(path, 'rb') as image_file:
        content = image_file.read()

    image = vision.Image(content=content)

    with Image.open(BytesIO(content)) as img:
        resolution = img.size

    response = client.document_text_detection(
        image=image,
        image_context=dict(language_hints=[lang_hint[language]]),
    )

    paragraphs = []

    for page in response.full_text_annotation.pages:
        for block in page.blocks:
            for paragraph in block.paragraphs:
                p_text = ""
                p_para = {
                    "text": "",
                    "aabb": bounds_to_aabb(paragraph.bounding_box),
                    "words": [],
                    "symbols": [],
                }

                for word in paragraph.words:
                    if language == "en":
                        if p_text:
                            p_text += " "

                    p_word = {
                        "begin": len(p_text),
                        "end": len(p_text),
                        "aabb": bounds_to_aabb(word.bounding_box),
                    }

                    for symbol in word.symbols:
                        p_text += symbol.text
                        for ch in symbol.text:
                            p_symbol = {
                                "text": ch,
                                "aabb": bounds_to_aabb(symbol.bounding_box),
                            }
                            p_para["symbols"].append(p_symbol)

                    p_word["end"] = len(p_text)
                    p_para["words"].append(p_word)

                p_para["text"] = p_text
                paragraphs.append(p_para)

    if response.error.message:
        raise Exception(
            '{}\nFor more info on error messages, check: '
            'https://cloud.google.com/apis/design/errors'.format(
                response.error.message))

    result = {
        "paragraphs": paragraphs,
        "resolution": resolution,
    }

    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1, ensure_ascii=False)

    with open(tmp_path, "rb") as f:
        return json.load(f)

prio_score = {
    "news1": 3,
    "ichi1": 3,
    "spec1": 2,
    "gai1": 2,
    "nf01": 4,
    "nf02": 3,
    "nf03": 2,
}

def format_info(text, info, primary):
    return {
        "text": text,
        "primary": primary,
        "score": max((prio_score.get(p, 1) for p in info.priority), default=0),
        "info": info.info,
    }

def format_result(result):
    ks = list(format_info(k, v, result.kanji and i == result.index) for i,(k,v) in enumerate(result.word.kanji.items()))
    rs = list(format_info(k, v, not result.kanji and i == result.index) for i,(k,v) in enumerate(result.word.kana.items()))
    primary_score = next(v["score"] for v in itertools.chain(ks, rs) if v["primary"])
    conjugation = ""

    if result.conjugated:
        if result.negative:
            conjugation += "Negative "
        if result.formal:
            conjugation += "Formal "
        conjugation += result.conjugation

    return {
        "query": result.query,
        "kanji": sorted(ks, key=lambda x: x["score"], reverse=True),
        "kana": sorted(rs, key=lambda x: x["score"], reverse=True),
        "gloss": result.word.gloss,
        "score": primary_score,
        "conjugation": conjugation,
    }

def loose_intersects(a, b, factor):
    a_min = a["min"]
    a_max = a["max"]
    b_min = b["min"]
    b_max = b["max"]
    a_center_x = (a_min[0] + a_max[0]) * 0.5
    a_center_y = (a_min[1] + a_max[1]) * 0.5
    a_extent_x = (a_max[0] - a_min[0]) * 0.5
    a_extent_y = (a_max[1] - a_min[1]) * 0.5
    b_center_x = (b_min[0] + b_max[0]) * 0.5
    b_center_y = (b_min[1] + b_max[1]) * 0.5
    b_extent_x = (b_max[0] - b_min[0]) * 0.5
    b_extent_y = (b_max[1] - b_min[1]) * 0.5

    delta_x = abs(b_center_x - a_center_x)
    delta_y = abs(b_center_y - a_center_y)
    extent_x = a_extent_x + b_extent_x
    extent_y = a_extent_y + b_extent_y

    return delta_x < extent_x * factor and delta_y < extent_y * factor

def cluster_page_paragraphs(page):
    paragraphs = page["paragraphs"]
    unassigned = list(range(len(paragraphs)))
    clusters = []

    while unassigned:
        cluster = [unassigned.pop()]
        while True:
            for add_ix in unassigned:
                for self_ix in cluster:
                    add_aabb = paragraphs[add_ix]["aabb"]
                    self_aabb = paragraphs[self_ix]["aabb"]
                    if loose_intersects(add_aabb, self_aabb, 1.25):
                        cluster.append(add_ix)
                        unassigned.remove(add_ix)
                        break
            else:
                break
        clusters.append({ "paragraphs": cluster, "translation": "" })

    for cluster in clusters:
        c_para = [paragraphs[ix] for ix in cluster["paragraphs"]]
        cluster["aabb"] = {
            "min": (min(p["aabb"]["min"][0] for p in c_para), min(p["aabb"]["min"][1] for p in c_para)),
            "max": (max(p["aabb"]["max"][0] for p in c_para), max(p["aabb"]["max"][1] for p in c_para)),
        }

    page["clusters"] = clusters

def paragraph_mid_y(paragraph):
    aabb = paragraph["aabb"]
    return (aabb["min"][1] + aabb["max"][1]) * 0.5

def normalize_aabb(aabb, resolution):
    return {
        "min": (aabb["min"][0] / resolution[0], aabb["min"][1] / resolution[1]),
        "max": (aabb["max"][0] / resolution[0], aabb["max"][1] / resolution[1]),
    }

def cleanup_translation(text):
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([.,!?])", r"\1", text)
    text = re.sub(r"(^|[.,!?]\s*)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    return text

def add_cluster_translations(page_jp, page_en):
    for cluster_jp in page_jp["clusters"]:
        en_paragraphs = []

        for cluster_en in page_en["clusters"]:
            for jp_ix, en_ix in itertools.product(cluster_jp["paragraphs"], cluster_en["paragraphs"]):
                jp_aabb = normalize_aabb(page_jp["paragraphs"][jp_ix]["aabb"], page_jp["resolution"])
                en_aabb = normalize_aabb(page_en["paragraphs"][en_ix]["aabb"], page_en["resolution"])
                if loose_intersects(jp_aabb, en_aabb, 1.2):
                    break
            else:
                continue
            for en_ix in cluster_en["paragraphs"]:
                en_paragraphs.append(page_en["paragraphs"][en_ix])
        
        en_paragraphs = sorted(en_paragraphs, key=paragraph_mid_y)
        trans = " ".join(p["text"] for p in en_paragraphs)
        cluster_jp["translation"] = cleanup_translation(trans)


def add_hints_to_paragraph(paragraph):
    text = paragraph["text"]
    words = paragraph["words"]
    symbols = paragraph["symbols"]

    hints = []

    begin = 0
    word_ix = 0
    length = len(text)
    while begin < length:
        best_result = None
        best_end = begin + 1
        
        begin_aabb = symbols[begin]["aabb"]
        begin_y = (begin_aabb["min"][1] + begin_aabb["max"][1]) * 0.5

        for end in range(begin + 1, min(begin + 10, length + 1)):
            if end - 1 > begin:
                end_aabb = symbols[end - 1]["aabb"]
                end_y = end_aabb["min"][1]
                if end_y < begin_y: break

            segment = text[begin:end]
            result = list(jdict.lookup(segment))
            if result:
                best_result = result
                best_end = end

        if best_result:
            hint = {
                "begin": begin,
                "end": best_end,
                "results": sorted((format_result(r) for r in best_result), key=lambda x: x["score"], reverse=True),
            }
            hints.append(hint)
        begin = best_end


    paragraph["hints"] = hints

def add_hints_to_page(page):
    for paragraph in page["paragraphs"]:
        add_hints_to_paragraph(paragraph)

def process_page(jp_image, en_image, dst_path, opts):
    ocr = opts.get("ocr", True)

    if ocr:
        jp_page = detect_page_ocr(jp_image, "jp")
        add_hints_to_page(jp_page)

        if en_image:
            en_page = detect_page_ocr(en_image, "en")
            cluster_page_paragraphs(jp_page)
            cluster_page_paragraphs(en_page)
            add_cluster_translations(jp_page, en_page)
    else:
        with Image.open(jp_image) as img:
            resolution = img.size
        jp_page = {
            "paragraphs": [],
            "clusters": [],
            "resolution": resolution,
        }
    
    shutil.copyfile(jp_image, dst_path + ".jpg")

    with open(dst_path + ".json", "w", encoding="utf-8") as f:
        json.dump(jp_page, f, indent=1, ensure_ascii=False)

def replace_bracketed_number(text, offset):
    def inner(m):
        num_str = m.group(1)
        fmt = f"{{:0{len(num_str)}d}}"
        return fmt.format(offset + int(num_str))
    return re.sub(r"<([0-9]+)>", inner, text)

def expand_pages(desc):
    old_pages = desc["pages"]
    new_pages = []

    for page in old_pages:
        for offset in range(page.get("count", 1)):
            new_page = copy.deepcopy(page)
            if "count" in new_page:
                del new_page["count"]
            if "jp" in page:
                new_page["jp"] = replace_bracketed_number(page["jp"], offset)
            if "en" in page:
                new_page["en"] = replace_bracketed_number(page["en"], offset)
            new_pages.append(new_page)
    desc["pages"] = new_pages

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert pages to a Mango-readable form")
    parser.add_argument("desc", metavar="desc.json", help="Description file")
    parser.add_argument("-o", metavar="out-dir/", help="Output path")
    args = parser.parse_args()

    os.makedirs(args.o, exist_ok=True)

    desc_base = os.path.dirname(args.desc)

    with open(args.desc, "r", encoding="utf-8") as f:
        desc = json.load(f)
        expand_pages(desc)

        pages = desc["pages"]
        for index, page in enumerate(pages):
            print(f"Processing page {index+1}/{len(pages)}", flush=True)
            dst_path = os.path.join(args.o, f"page{index+1:03d}")
            jp_page = os.path.join(desc_base, page.get("jp", ""))
            en_page = os.path.join(desc_base, page.get("en", ""))
            process_page(jp_page, en_page, dst_path, page)
