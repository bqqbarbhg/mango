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
import string
import glob
import gzip
import requests
import base64

jdict = JDict("data/jdict.json.gz")

def open_gz(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rb")
    else:
        return open(path, "rb")

HIRAGANA = (
    "ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすず"
    "せぜそぞただちぢっつづてでとどなにぬねのはばぱひびぴ"
    "ふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろわ"
    "をんーゎゐゑゕゖゔゝゞ・「」。、")
KATAKANA = (
    "ァアィイゥウェエォオカガキギクグケゲコゴサザシジスズセゼソ"
    "ゾタダチヂッツヅテデトドナニヌネノハバパヒビピフブプヘベペ"
    "ホボポマミムメモャヤュユョヨラリルレロワヲンーヮヰヱヵヶヴ"
    "ヽヾ・「」。、")

KATAKANA_TO_HIRAGANA = { ord(k): ord(h) for k,h in zip(KATAKANA, HIRAGANA) }

wk_subjects = { }
wk_kanjis = { }

en_words = set()

def bounds_to_aabb(box):
    return {
        "min": (min(v.x for v in box.vertices), min(v.y for v in box.vertices)),
        "max": (max(v.x for v in box.vertices), max(v.y for v in box.vertices)),
    }

lang_hint = {
    "jp": "ja-Jpan",
    "en": "en-t-i0-handwrit",
}

def format_break(line_break, BreakType):
    if not line_break: return None
    btype = line_break.type_
    prefix = line_break.is_prefix
    return {
        "space": btype in (BreakType.SPACE, BreakType.SURE_SPACE, BreakType.EOL_SURE_SPACE),
        "newline": btype in (BreakType.EOL_SURE_SPACE, BreakType.LINE_BREAK),
        "hyphen": btype in (BreakType.HYPHEN,),
        "sure": btype in (BreakType.SURE_SPACE, BreakType.EOL_SURE_SPACE),
        "prefix": prefix,
    }

def detect_page_ocr(path, language):
    """Detects document features in an image."""

    tmp_path = os.path.join("temp", "ocr02", path) + ".json"
    try:
        with open(tmp_path, "rb") as f:
            return json.load(f)
    except FileNotFoundError:
        pass

    print(f".. Processing OCR: {path} ({language})", flush=True)

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

    BreakType = vision.TextAnnotation.DetectedBreak.BreakType

    for page in response.full_text_annotation.pages:
        for block in page.blocks:
            for paragraph in block.paragraphs:
                p_text = ""
                p_para = {
                    "text": "",
                    "aabb": bounds_to_aabb(paragraph.bounding_box),
                    "words": [],
                    "symbols": [],
                    "break": format_break(paragraph.property.detected_break, BreakType),
                }

                for word in paragraph.words:
                    p_word = {
                        "begin": len(p_text),
                        "end": len(p_text),
                        "aabb": bounds_to_aabb(word.bounding_box),
                        "break": format_break(word.property.detected_break, BreakType),
                    }

                    for symbol in word.symbols:
                        p_text += symbol.text
                        for ch in symbol.text:
                            p_symbol = {
                                "text": ch,
                                "begin": len(p_text) - len(symbol.text),
                                "end": len(p_text),
                                "aabb": bounds_to_aabb(symbol.bounding_box),
                                "break": format_break(symbol.property.detected_break, BreakType),
                            }
                            p_para["symbols"].append(p_symbol)

                            br = p_symbol["break"]
                            if br:
                                if br["newline"]:
                                    p_text += "\n"
                                elif br["space"]:
                                    p_text += " "

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

def capitalize_nonword(m):
    text = m.group(1)
    if text not in en_words:
        return text.capitalize()
    else:
        return text

def cleanup_translation(text):
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+([.,!?])", r"\1", text)
    text = re.sub(r"(^|[.!?]\s*)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    text = re.sub(r"\bi\b", "I", text)
    text = re.sub(r"\b([a-z]+)\b", capitalize_nonword, text)
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

svg_cache = { }
def download_svg(url):
    cached = svg_cache.get(url)
    if cached: return cached

    path = re.sub(r"[^a-zA-Z0-9]", "_", url) + ".svg"
    path = os.path.join("temp", "download", path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        pass

    print(f"Downloading {url}", flush=True)
    r = requests.get(url)
    result = r.text
    svg_cache[url] = result

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(result)

    return result

def get_extra_hints(text):
    hints = []

    def wk_kana(reading):
        return {
            "text": reading["reading"],
            "primary": reading["primary"],
            "score": 1,
            "info": [],
        }

    def wk_radical(id):
        radical = wk_subjects[id]

        image_url = ""
        for image in radical["character_images"]:
            content_type = image["content_type"]
            inline_styles = image["metadata"].get("inline_styles", False)
            if content_type == "image/svg+xml" and inline_styles:
                image_url = image["url"]
        
        if image_url:
            svg = download_svg(image_url)
        else:
            ch = radical["characters"]
            svg = (
                "<svg xmlns=\"http://www.w3.org/2000/svg\" xmlns:xlink=\"http://www.w3.org/1999/xlink\" viewBox=\"0 0 1000 1000\">"
                "<defs><style>.c{font: 950px sans-serif; text-anchor: middle; dominant-baseline: ideographic;}</style></defs>"
                f"<text x=\"500\" y=\"1000\" class=\"c\">{ch}</text></svg>")

        return {
            "name": radical["meanings"][0]["meaning"],
            "image": "data:image/svg+xml;base64," + base64.standard_b64encode(svg.encode("utf-8")).decode("ascii"),
        }

    wk_kanji = wk_kanjis.get(text, "")
    if wk_kanji:
        hint = {
            "query": text,
            "kanji": [{ "text": text, "primary": True, "score": 1, "info": [] }],
            "kana": [wk_kana(r) for r in wk_kanji["readings"]],
            "gloss": [m["meaning"].lower() for m in wk_kanji["meanings"]],
            "score": 1,
            "conjugation": "",
            "radicals": [wk_radical(id) for id in wk_kanji["component_subject_ids"]],
        }
        hints.append(hint)
    
    return hints

def add_hints_to_paragraph(paragraph):
    text = paragraph["text"]
    symbols = paragraph["symbols"]

    hints = []

    sym_begin = 0
    length = len(symbols)
    while sym_begin < length:
        best_result = None
        best_sym_end = sym_begin + 1
        best_segment = None

        begin_aabb = symbols[sym_begin]["aabb"]

        for sym_end in range(sym_begin + 1, min(sym_begin + 10, length + 1)):
            text_begin = symbols[sym_begin]["begin"]
            text_end = symbols[sym_end - 1]["end"]

            segment = text[text_begin:text_end]
            result = list(jdict.lookup(segment))
            if result:
                best_result = result
                best_sym_end = sym_end
                best_segment = segment

        if best_result:
            extra = get_extra_hints(best_segment)
            hint = {
                "begin": sym_begin,
                "end": best_sym_end,
                "results": extra + sorted((format_result(r) for r in best_result), key=lambda x: x["score"], reverse=True),
            }
            hints.append(hint)
        sym_begin = best_sym_end

    alt_hints = []
    for sym_begin in range(length):
        for sym_end in range(sym_begin, length):
            text_begin = symbols[sym_begin]["begin"]
            text_end = symbols[sym_end - 1]["end"]
            segment = text[text_begin:text_end]
            segment = re.sub(r"\s+", "", segment)
            segment = segment.translate(KATAKANA_TO_HIRAGANA)
            if len(segment) > 1 or (len(segment) == 1 and segment[0] not in HIRAGANA):
                result = list(jdict.lookup(segment))
                extra = get_extra_hints(segment)
                if result:
                    hint = {
                        "begin": sym_begin,
                        "end": sym_end,
                        "results": extra + sorted((format_result(r) for r in result), key=lambda x: x["score"], reverse=True),
                    }
                    alt_hints.append(hint)
                elif extra:
                    hint = {
                        "begin": sym_begin,
                        "end": sym_end,
                        "results": extra,
                    }
                    alt_hints.append(hint)

    paragraph["hints"] = hints
    paragraph["alt_hints"] = alt_hints

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
    parser.add_argument("--range", metavar="begin:end", help="Process a range of pages")
    parser.add_argument("--en-dicts", nargs="+", action="append", help="English word list files")
    parser.add_argument("--wanikani", help="Wanikani subject file")

    args = parser.parse_args()

    os.makedirs(args.o, exist_ok=True)

    desc_base = os.path.dirname(args.desc)

    uppercase = set(string.ascii_uppercase)
    for pat in itertools.chain(*args.en_dicts):
        for path in glob.glob(pat):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    if line[0] in uppercase: continue
                    en_words.add(line)

    print(f"Loaded {len(jdict.words)} Japanese words", flush=True)

    if en_words:
        print(f"Loaded {len(en_words)} English words", flush=True)
    
    if args.wanikani:
        with open_gz(args.wanikani) as f:
            wanikani_subjects = json.load(f)["subjects"]
            print(f"Loaded {len(wanikani_subjects)} WaniKani subjects", flush=True)
            for subject in wanikani_subjects:
                data = subject["data"]
                wk_subjects[subject["id"]] = data
                if subject["object"] == "kanji":
                    wk_kanjis[data["characters"]] = data

    with open(args.desc, "r", encoding="utf-8") as f:
        desc = json.load(f)
        expand_pages(desc)

        pages = desc["pages"]
        begin = 0
        end = len(pages)

        if args.range:
            if ":" in args.range:
                s_begin, s_end = args.range.split(":")
                if s_begin:
                    begin = int(s_begin) - 1
                if s_end:
                    end = int(s_end) - 1
            else:
                end = begin = int(args.range) - 1

        for index, page in enumerate(pages):
            if not (begin <= index <= end): continue

            print(f"Processing page {index+1}/{len(pages)}", flush=True)
            dst_path = os.path.join(args.o, f"page{index+1:03d}")
            jp_page = os.path.join(desc_base, page.get("jp", ""))
            en_page = os.path.join(desc_base, page.get("en", ""))
            process_page(jp_page, en_page, dst_path, page)
