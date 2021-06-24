import gzip
import json
from collections import namedtuple

Result = namedtuple("Result", "query word kanji info conjugated negative formal conjugation")
Word = namedtuple("Word", "kanji kana pos gloss")
Info = namedtuple("Info", "priority info")

class JDict:
    def __init__(self, path):
        fn = gzip.open if path.endswith(".gz") else open
        with fn(path, "rb") as f:
            self.data = json.load(f)
            self.words = self.data["words"]
            self.conjugations = self.data["conj"]
            self.positions = self.data["pos"]
            self.infos = [Info(i["priority"], i["info"]) for i in self.data["infos"]]
            self.str_to_word = self.data["str_to_word"]

    def get_word(self, index):
        word = self.words[index]
        return Word(
            { k: self.infos[v] for k,v in word["kanji"] },
            { k: self.infos[v] for k,v in word["kana"] },
            self.positions[word["pos"]],
            word["gloss"])

    def lookup_precise(self, query):
        result = self.str_to_word.get(query, [])
        if not isinstance(result, list):
            result = [result]
        for cdata in result:
            id = (cdata >> 0) & ((1 << 18) - 1)
            kanji = bool((cdata >> 18) & 1)
            index = bool((cdata >> 19) & ((1 << 5) - 1))
            cj = (cdata >> 24) & ((1 << 4) - 1)
            fml = bool((cdata >> 28) & 1)
            neg = bool((cdata >> 29) & 1)

            kind = ["kana", "kanji"][kanji]
            word = self.get_word(id)
            info = self.infos[self.words[id][kind][index][1]]
            conjugation = self.conjugations[cj]
            conjugated = cj != 0
            yield Result(query, word, kanji, info, conjugated, neg, fml, conjugation)

    def lookup(self, query):
        yield from self.lookup_precise(query)
        if query.endswith("ている"):
            for q in self.lookup_precise(query[:-2]):
                yield q._replace(formal=False, conjugation="Progressive")
        elif query.endswith("てる"):
            for q in self.lookup_precise(query[:-1]):
                yield q._replace(formal=False, conjugation="Progressive")
        elif query.endswith("ています"):
            for q in self.lookup_precise(query[:-3]):
                yield q._replace(formal=True, conjugation="Progressive")
        elif query.endswith("ておく"):
            for q in self.lookup_precise(query[:-2]):
                yield q._replace(formal=False, conjugation="Future")
        elif query.endswith("ておきます"):
            for q in self.lookup_precise(query[:-4]):
                yield q._replace(formal=True, conjugation="Future")
        elif query.endswith("てある"):
            for q in self.lookup_precise(query[:-2]):
                yield q._replace(formal=False, conjugation="Finished")
        elif query.endswith("てあります"):
            for q in self.lookup_precise(query[:-4]):
                yield q._replace(formal=True, conjugation="Finished")
        
        if query.endswith("ー"):
            yield from self.lookup(query[:-1])
        if query.endswith("〜"):
            yield from self.lookup(query[:-1])
