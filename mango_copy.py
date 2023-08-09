import argparse
import os
import json
import copy
import re
import shutil

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
    args = parser.parse_args()

    os.makedirs(args.o, exist_ok=True)

    tasks = []

    desc_base = os.path.dirname(args.desc)
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

        path = args.o
        dst_path = os.path.join(path, f"page{index+1:03d}")
        jp_image = os.path.join(desc_base, page.get("jp", ""))
        _, jp_ext = os.path.splitext(jp_image)
        dst_image = dst_path + jp_ext
        shutil.copyfile(jp_image, dst_image)

        prog = index / len(pages) * 100
        print(f"Copied page {index+1}/{len(pages)} <{prog:.1f}%>")
