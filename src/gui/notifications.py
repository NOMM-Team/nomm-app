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

import os
import gi
gi.require_version('Notify', '0.7')
from gi.repository import Notify, GdkPixbuf, GLib


# This function handle notifications when downloading mods from Nexusmods
def send_download_notification(status, file_name="", game_name=None, icon_path=None):
    Notify.init("Yamm")
    
    if status == "success":
        title = "Download Successful"
        full_body = f"File {file_name} successfully downloaded for {game_name}"
    elif status == "failure-game-not-found":
        title = "Download Failed"
        full_body = f"Game {game_name} could not be found in game_configs, are you sure it is defined?"
    elif status == "started":
        title = "Downloading..."
        full_body = f"{file_name} download started as a background task"
    else:
        return

    notification = Notify.Notification.new(title, full_body)

    # Handle the Icon
    if icon_path and os.path.exists(icon_path):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, 64, 64, True)
            notification.set_icon_from_pixbuf(pixbuf)
        except Exception as e:
            print(f"Error loading notification pixbuf: {e}")
            notification.set_hint("desktop-entry", GLib.Variant.new_string("yamm"))
    else:
        notification.set_hint("desktop-entry", GLib.Variant.new_string("yamm"))

    try:
        notification.show()
    except Exception as e:
        print(f"libnotify failed: {e}")