from jdict import JDict

jdict = JDict("data/jdict.json.gz")

for result in jdict.lookup("してない"):
    print(", ".join(result.word.gloss))