import os
import requests
from gui.notifications import send_download_notification

def download_mod(url, dest_folder):
    filename = url.split('/')[-1].split('?')[0] or "download"
    dest_path = os.path.join(dest_folder, filename)
    os.makedirs(dest_folder, exist_ok=True)

    # Envoyer une notification de démarrage
    send_download_notification("started", file_name=filename)

    success = False
    try:
        # Télécharger le fichier silencieusement
        response = requests.get(url, stream=True, timeout=15)
        response.raise_for_status() # Ajout d'une bonne pratique standard (lance une erreur si code HTTP n'est pas 200)
        with open(dest_path, 'wb') as f:
            for data in response.iter_content(chunk_size=4096):
                f.write(data)
        success = True
    except Exception as e:
        print(f"Download error: {e}")
        success = False

    return success