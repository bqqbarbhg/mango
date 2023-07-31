import requests
import argparse
import json

parser = argparse.ArgumentParser(description="Download WaniKani subjects")
parser.add_argument("--api-token", metavar="aaa-bbb-ccc", help="Authorization token for the API")
parser.add_argument("-o", default="data/wanikani_subjects.json", metavar="wanikani_subjects.json", help="Output path")
args = parser.parse_args()

subjects = []

url = "https://api.wanikani.com/v2/subjects"
while url:
    r = requests.get(url, headers={
        "Wanikani-Revision": "20170710",
        "Authorization": f"Bearer {args.api_token}",
    })
    data = r.json()
    url = data["pages"]["next_url"]
    subjects += data["data"]

with open(args.o, "w", encoding="utf-8") as f:
    json.dump({ "subjects": subjects }, f)
