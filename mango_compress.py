import argparse
import os
import subprocess
import shlex
import sys

mango_enc_exes = [
    "data/mango-enc.exe",
    "data/mango-enc",
]

def args_to_cmd(args):
    if sys.platform == "win32":
        return subprocess.list2cmdline(args)
    else:
        return shlex.join(args)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", help="Root path to convert files in")
    parser.add_argument("--exe", help="Encoder executable")
    args = parser.parse_args()

    exe = args.exe
    if not exe:
        for exe_name in mango_enc_exes:
            if os.path.exists(exe_name):
                exe = exe_name
                print(f"Autodetected: --exe {exe_name}")
                break
    if not exe:
        raise RuntimeError("Could not find encoder exe by default name, use --exe to specify manually")

    for file in os.listdir(args.path):
        _, ext = os.path.splitext(file)
        if ext.lower() in (".png", ".jpg", ".jpeg"):
            path = os.path.join(args.path, file)
            exe_args = [exe_name, path]
            print(f"$ {args_to_cmd(exe_args)}")
            subprocess.check_call(exe_args)
