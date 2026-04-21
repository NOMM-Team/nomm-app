#!/usr/bin/env python3

import sys
from gui.application import Nomm
from core.nexus_api import handle_nexus_link

if __name__ == "__main__":
    #  Nexusmod API
    if len(sys.argv) > 1 and sys.argv[1].startswith("nxm://"):
        nxm_link = sys.argv[1]
        print(f"NOMM is processing: {nxm_link}")
        handle_nexus_link(nxm_link)
    
    # APP LAUNCH
    else:
        print("Launching NOMM Application")
        app = Nomm()
        app.run(None)