mango
=====

Augmented manga reader

## Initial Setup

```bash
# Setup Python dependencies
pip3 install -r requirements.txt

# Run this first to download JMDict and generate the jdict.py compatible table
./setup_jdict.sh

# Optional: If you want to enable WaniKani hints get an API key from
# https://www.wanikani.com/settings/personal_access_tokens
python3 wanikani/get_subjects.py --api-token aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
```

## Workflow

You need to have a directory of Japanese source page images in `${whatever}/jp`. Then you can either
write a `mango-desc.json` file by hand or use `mango_init.py` to generate one for you. This will assume
the Japanese source pages are in the correct order by filename.
If you want to have matched manual translations from an English source place them next to the `jp`
directory in a directory called `en`.

```bash
# Example of what the file setup should look like
tree content/my_source_data
+ my_source_data
+-- jp/
| +-- page_no1.jpg
| +-- page_no2.jpg
| +-- ...
+-- en/
| +-- first_page.jpg
| +-- second_page.jpg
| +-- ...

# Generate `my_source_data/mango-desc.json` by matching pages visually
# Hint: Use --sure-limit 0.06 or something if it's too slow
python3 mango_init.py --base content/my_source_data --threads 8

# Optional: You can improve the quality of the following part by gathering
# English language word list files at `data/english_dicts/`
mkdir -p data/english_dicts
cp /usr/share/dict/american-english data/english_dicts

# For this part you need to have a setup so you're capable of performing
# Google's document OCR.
# Follow the tutorial at https://cloud.google.com/vision/docs/ocr
# Now you should have something like `data/gcp_credentials.json`
GOOGLE_APPLICATION_CREDENTIALS=data/gcp_credentials.json \
    python3 mangofy.py content/my_source_data/mango-desc.json \
    -o content/my_result_data/ --threads 8

# Now you can run your preferred static web server to access
# the content. The web viewer should work on tablets as well!
python3 -m http.server

# Open http://localhost:8000/web_viewer/?doc=content/my_result_data
```

## Web viewer

The web viewer relies on "hardware" zoom so don't be afraid to use ctrl+scroll
or pinch to zoom. Double click on the edges of the page to move to previous/next.
Clicking text should give dictionary (and WaniKani) hints about the content, if
the intial parse is bad you can drag the endpoints of the selection to the area
you want. If you click a second time on a selected piece of text it'll focus on
a single kanji. Double clicking shows the English translation of the whole
paragraph.
