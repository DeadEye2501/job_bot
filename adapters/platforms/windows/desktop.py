"""Открытие адресов и выделение файлов средствами Windows."""

import os
import subprocess


def open_target(target: str) -> None:
    os.startfile(target)


def show_in_folder(target) -> None:
    subprocess.Popen(["explorer", f"/select,{target}"])
