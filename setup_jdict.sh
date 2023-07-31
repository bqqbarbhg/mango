#!/usr/bin/env bash

set -x

if python3 --version ; then
    MANGO_PYTHON=python3
elif python --version ; then
    MANGO_PYTHON=python
else
    >&2 echo "Could not locate python!"
    exit 1
fi

mkdir -p data
curl http://ftp.edrdg.org/pub/Nihongo/JMdict_e.gz -o data/JMDict_e.gz
$MANGO_PYTHON jdict_gen/generate_jdict.py --jmdict-path data/JMDict_e.gz --conj-table-path jdict_gen/tables -o data/jdict.json.gz
