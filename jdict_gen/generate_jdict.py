#!/usr/bin/env python3

import xml.etree.ElementTree as ET
import conj
from collections import namedtuple
import json
import time
import argparse
import gzip

parser = argparse.ArgumentParser(description="Generate jdict.json")
parser.add_argument("--jmdict-path", help="Path to the JMDict to use")
parser.add_argument("--conj-table-path", help="Path for directory containing conjugation csv files")
parser.add_argument("-o", help="Output filename")
args = parser.parse_args()

start = time.time()

print(f"Parsing JMDict {args.jmdict_path}...", flush=True)
if args.jmdict_path.endswith(".gz"):
    with gzip.open(args.jmdict_path, "rb") as f:
        root = ET.parse(f)
else:
    root = ET.parse(args.jmdict_path)

print(f"Loading conjugation tables from {args.conj_table_path}...", flush=True)
ct = conj.read_conj_tables(args.conj_table_path)

def encode_base(id, kanji, index):
    assert 0 <= id < (1 << 18)
    assert 0 <= kanji <= 1
    assert 0 <= index < (1 << 5)
    return id | kanji << 18 | index << 19

def encode_conjugation(id, kanji, index, neg, fml, cj):
    assert 0 <= id < (1 << 18)
    assert 0 <= kanji <= 1
    assert 0 <= index < (1 << 5)
    assert 1 <= cj < (1 << 4)
    assert 0 <= fml <= 1
    assert 0 <= neg <= 1
    return id | kanji << 18 | index << 19 | cj << 24 | fml << 28 | neg << 29

def conjugate(txt, position, id, kanji, index):
    try: pos = ct['kwpos'][position][0]
    except KeyError:
        raise ValueError("unknown part-of-speech: %s\n'conj.py --list' will "
            "print a list of conjugatable parts-of-speech" % position)
    if pos not in [x[0] for x in ct['conjo']]:
        return

    # Get pos number from kw:
    for conj2,conjnm in sorted (ct['conj'].values(), key=lambda x:x[0]):
        for neg, fml in (0,0),(0,1),(1,0),(1,1):
            neg, fml = bool (neg), bool (fml)
            for onum in range(1,10):  # onum values start at 1, not 0.
                try: _,_,_,_,_, stem, okuri, euphr, euphk, _ \
                    = ct['conjo'][pos,conj2,neg,fml,onum]
                except KeyError: break

                kt = conj.construct (txt, stem, okuri, euphr, euphk) \
                        if len(txt) >= 2 else ''

                if kt:
                    yield kt, encode_conjugation(id, kanji, index, neg, fml, conj2)

words = [ ]
infos = { }

word_to_cdata = { }
def add_word_to_cdata(word, cdata):
    global word_to_cdata

    prev = word_to_cdata.get(word)
    if not prev:
        word_to_cdata[word] = cdata
    elif isinstance(prev, list):
        if cdata not in prev:
            prev.append(cdata)
    elif prev != cdata:
        word_to_cdata[word] = [prev, cdata]

pos_descs = { c[0]: c[2] for c in ct['kwpos'].values() }
inv_pos_descs = { v: k for k,v in pos_descs.items() }

counter = 0

max_kr = 0

print("Processing words, this will take a while (printing one '.' per 10k words)", flush=True)

for id, entry in enumerate(root.iter("entry")):
    pos = entry.findtext("sense/pos") or "unclassified"
    gloss = entry.findall("sense/gloss")

    counter += 1
    if counter % 10000 == 0:
        print(".", end="", flush=True)

    if pos not in inv_pos_descs:
        pos_id = max(pos_descs.keys()) + 1
        pos_descs[pos_id] = pos
        inv_pos_descs[pos] = pos_id

    eles = [[], []]

    for kanji, ele_name in enumerate(("r_ele", "k_ele")):
        for index, ele in enumerate(entry.findall(ele_name)):
            conjugated = False
            eb = ele.findtext("keb" if kanji else "reb")

            pris = frozenset(e.text for e in ele.findall("ke_pri" if kanji else "re_pri"))
            inf = frozenset(e.text for e in ele.findall("ke_inf" if kanji else "re_inf"))
            info = (pris, inf)

            info_id = infos.get(info, 0)
            if info_id == 0:
                info_id = len(infos)
                infos[info] = info_id

            eles[kanji].append((eb, info_id))
            if eb:
                for word, cdata in conjugate(eb, pos, id, kanji, index):
                    if len(word) > 1:
                        add_word_to_cdata(word, cdata)
                        conjugated = True
            if not conjugated:
                cdata = encode_base(id, kanji, index)
                add_word_to_cdata(eb, cdata)

        max_kr = max(max_kr, len(eles[kanji]))

    word = {
        "kanji": eles[1],
        "kana": eles[0],
        "pos": inv_pos_descs[pos],
        "gloss": [g.text for g in gloss],
    }
    words.append(word)

conj_descs = { str(c[0]): c[1] for c in ct['conj'].values() }
info_list = [{
    "priority": sorted(list(pri)),
    "info": list(inf)
} for pri, inf in infos]

conj_list = ["Unconjugated"] * (len(ct["conj"]) + 1)
pos_list = [""] * (max(pos_descs.keys()) + 1)

for c in ct["conj"].values():
    conj_list[c[0]] = c[1]

for ix, pos in pos_descs.items():
    pos_list[ix] = pos

result = {
    "conj": conj_list,
    "pos": pos_list,
    "infos": info_list,
    "words": words,
    "str_to_word": word_to_cdata,
}

print(" Done!", flush=True)

print(f"Writing the output JSON file at {args.o}...", flush=True)
if args.o.endswith(".gz"):
    with gzip.open(args.o, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
else:
    with open(args.o, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

end = time.time()

print(f"Finished in {end - start:.1f} seconds!", flush=True)
