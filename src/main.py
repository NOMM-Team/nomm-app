#!/usr/bin/env python3
# src/main.py

import sys
from gui.application import Nomm
from core.nxm_handler import handle_nexus_link

if __name__ == "__main__":
    # 1. Gestion du protocole NXM (Nexus Mods)
    if len(sys.argv) > 1 and sys.argv[1].startswith("nxm://"):
        nxm_link = sys.argv[1]
        print(f"nomm is processing: {nxm_link}")
        handle_nexus_link(nxm_link)
    
    # 2. Lancement normal de l'application
    else:
        print("Launching Nomm Application")
        app = Nomm()
        app.run(None)