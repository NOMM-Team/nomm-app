#!/usr/bin/env python3

import sys

from core.downloader import Downloader
from core.nexus_api import handle_nexus_link
from gui.application import Nomm

if __name__ == "__main__":
    # Downloader
    downloader = Downloader()
    
    # Nexusmod API
    if len(sys.argv) > 1 and sys.argv[1].startswith("nxm://"):
        nxm_link = sys.argv[1]
        print(f"NOMM is processing: {nxm_link}")
        handle_nexus_link(nxm_link, downloader)
    
    # App launch
    else:
        print("Launching NOMM Application")
        app = Nomm(downloader=downloader)
        app.run(None)