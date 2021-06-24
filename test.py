from jdict import JDict

jdict = JDict("data/jdict.json.gz")

for result in jdict.lookup("誤解してない"):
    print(", ".join(result.word.gloss))
