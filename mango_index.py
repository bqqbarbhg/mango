import argparse
import os
import json
from open_ex import open_ex

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aggregate info.json files into an index")
    parser.add_argument("path", metavar="path/", help="Path to search recursively and write the index.json into")
    args = parser.parse_args()

    volumes = []
    for root, dirs, files in os.walk(args.path):
        if "mango-info.json" in files:
            path = os.path.join(root, "mango-info.json")
            with open_ex(path, "rb") as f:
                info = json.load(f)
            rel_path = os.path.relpath(root, args.path).replace("\\", "/")
            volumes.append({
                "path": rel_path,
                "info": info,
            })

    index = {
        "volumes": volumes
    }
    index_path = os.path.join(args.path, "index.json")
    with open_ex(index_path, "wt") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

