import os
import random
import threading

import gi
import requests
import yaml

gi.require_version('Notify', '0.7')
from gi.repository import GdkPixbuf, GLib, Gtk, Notify

# This function handle notifications when downloading mods from Nexusmods
def send_download_notification(status, file_name="", game_name=None, icon_path=None):
    Notify.init("NOMM")
    
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

    # Icon
    if icon_path and os.path.exists(icon_path):
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_path, 64, 64, True)
            notification.set_icon_from_pixbuf(pixbuf)
        except Exception as e:
            print(f"Error loading notification pixbuf: {e}")
            notification.set_hint("desktop-entry", GLib.Variant.new_string("nomm"))
    else:
        notification.set_hint("desktop-entry", GLib.Variant.new_string("nomm"))

    try:
        notification.show()
    except Exception as e:
        print(f"libnotify failed: {e}")

# Check import before uncommenting the method
def download_popup(url, dest_folder, downloader):

    filename = url.split('/')[-1].split('?')[0] or "download"
    dest_path = os.path.join(dest_folder, filename)
    os.makedirs(dest_folder, exist_ok=True)

    shenanigans_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shenanigans.yaml")
    with open(shenanigans_path) as f:
        SHENANIGANS = yaml.safe_load(f)["shenanigans"]

    # State tracking
    status = {"success": False, "finished": False}
    event = threading.Event()

    def create_ui():
        win = Gtk.Window(title="Downloader", modal=True, deletable=False, decorated=False)
        win.set_default_size(400, 150)

        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, 
            spacing=12, 
            margin_top=20, 
            margin_bottom=20, 
            margin_start=20, 
            margin_end=20
        )

        win.set_child(box)

        lbl_name = Gtk.Label(label=f"Downloading File: <b>{filename}</b>", use_markup=True, xalign=0)
        progress_bar = Gtk.ProgressBar(show_text=True)
        
        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
        stack.set_transition_duration(500) 
        stack.set_margin_top(10)

        # Labels for the animation swap
        tip_label_a = Gtk.Label(label=("Downloading mod"), wrap=True, use_markup=True)
        tip_label_b = Gtk.Label(label="", wrap=True, use_markup=True)
        
        for lbl in [tip_label_a, tip_label_b]:
            lbl.add_css_class("caption")
            lbl.set_justify(Gtk.Justification.CENTER)

        stack.add_named(tip_label_a, "a")
        stack.add_named(tip_label_b, "b")

        box.append(lbl_name)
        box.append(progress_bar)
        box.append(stack)

        def rotate_tips():
            if status["finished"]:
                return False
            
            current = stack.get_visible_child_name()
            next_name = "b" if current == "a" else "a"
            next_label = tip_label_b if next_name == "b" else tip_label_a
            
            next_label.set_label(f"<i>{random.choice(SHENANIGANS)}</i>")
            stack.set_visible_child_name(next_name)
            return True

        GLib.timeout_add(6000, rotate_tips)
        
        win.present()
        return win, progress_bar

    # Initialize UI on main thread
    window, pbar = create_ui()

    def on_download_progress(downloader_inst, download_data):
        pbar.set_fraction(download_data['progress'])

    def on_download_done(downloader_inst, success):
        print('finished')
        status['finished'] = True
        status['success'] = success
        window.destroy()
        return False
            
    def on_download_fail(downloader_inst, e):
        status['finished'] = True
        status['success'] = False
        print(f'Error downloading the mod: {e}')
        window.destroy()
        return False
    
    downloader.connect('progress-changed', on_download_progress)
    downloader.connect('download-complete', on_download_done)
    downloader.connect('download-error', on_download_fail)

    event.set()
    threading.Thread(target=downloader.download_mod, args=(url, dest_folder), daemon=True).start()

    # We use a nested main loop to make this method "block" 
    # until the download finishes without freezing the UI.
    while not status["finished"]:
        GLib.MainContext.default().iteration(True)

    return status["success"]