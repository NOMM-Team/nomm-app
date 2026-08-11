#!/usr/bin/env python3

import sys

from core.downloader import Downloader
from gui.application import Nomm

if __name__ == "__main__":
    # Downloader
    downloader = Downloader()

    app = Nomm(downloader=downloader)
    app.run(sys.argv)
