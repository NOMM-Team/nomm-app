#!/usr/bin/env python3

import sys

from nomm.core.downloader import Downloader
from nomm.gui.application import Nomm

def main():
    downloader = Downloader()
    app = Nomm(downloader=downloader)
    return app.run(sys.argv)

if __name__ == "__main__":
    sys.exit(main())