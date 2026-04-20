# Ce fichier fait partie de Yamm (Yet Another Mod Manager).
# Yamm est un fork de Nomm, développé initialement par Allexio.
#
# Copyright (C) 2026 Emetros
# Copyright (C) 2024 Allexio
#
# Ce programme est un logiciel libre : vous pouvez le redistribuer et/ou le modifier
# selon les termes de la Licence Publique Générale GNU telle que publiée par la
# Free Software Foundation, soit la version 3 de la Licence, soit (à votre
# discrétion) toute version ultérieure.
#
# Ce programme est distribué dans l'espoir qu'il sera utile, mais SANS AUCUNE
# GARANTIE ; sans même la garantie implicite de COMMERCIALISATION ou
# d'ADÉQUATION À UN USAGE PARTICULIER. Voir la Licence Publique Générale GNU
# pour plus de détails.
#
# Vous devriez avoir reçu une copie de la Licence Publique Générale GNU
# avec ce programme. Sinon, voir <https://www.gnu.org/licenses/>.

import sys
from gui.application import Yamm
from core.nexus_api import handle_nexus_link

if __name__ == "__main__":
    # 1. Gestion du protocole NXM (Nexus Mods)
    if len(sys.argv) > 1 and sys.argv[1].startswith("nxm://"):
        nxm_link = sys.argv[1]
        print(f"yamm is processing: {nxm_link}")
        handle_nexus_link(nxm_link)
    
    # 2. Lancement normal de l'application
    else:
        print("Launching Yamm Application")
        app = Yamm()
        app.run(None)