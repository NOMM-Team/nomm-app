import os
import yaml
import gi
import threading
import random
import requests

gi.require_version('Notify', '0.7')
from gi.repository import GdkPixbuf, GLib, Notify, Gtk


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

    # Handle the Icon
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
def download_with_progress(url, dest_folder):
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
        
        # --- ADD THIS BLOCK ---
        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
        stack.set_transition_duration(500) 
        stack.set_margin_top(10)

        # Labels for the animation swap
        tip_label_a = Gtk.Label(label=("Downloading mod"), wrap=True, use_markup=True)
        tip_label_b = Gtk.Label(label="", wrap=True, use_markup=True)
        
        for lbl in [tip_label_a, tip_label_b]:
            lbl.add_css_class("caption") # Assuming you have this in your CSS
            lbl.set_justify(Gtk.Justification.CENTER)

        stack.add_named(tip_label_a, "a")
        stack.add_named(tip_label_b, "b")
        # ----------------------

        box.append(lbl_name)
        # box.append(lbl_dest) # Keep if you want it
        box.append(progress_bar)
        box.append(stack) # Add the stack here

        # --- ADD THE ROTATION LOGIC ---
        def rotate_tips():
            if status["finished"]:
                return False
            
            current = stack.get_visible_child_name()
            next_name = "b" if current == "a" else "a"
            next_label = tip_label_b if next_name == "b" else tip_label_a
            
            next_label.set_label(f"<i>{random.choice(SHENANIGANS)}</i>")
            stack.set_visible_child_name(next_name)
            return True

        GLib.timeout_add(6000, rotate_tips) # Rotate every 6 seconds
        
        win.present()
        return win, progress_bar

    # Initialize UI on main thread
    window, pbar = create_ui()
    
    def run_download():
        try:
            response = requests.get(url, stream=True, timeout=15)
            total_size = int(response.headers.get('content-length', 0))

            downloaded = 0
            with open(dest_path, 'wb') as f:
                for data in response.iter_content(chunk_size=4096):
                    f.write(data)
                    downloaded += len(data)
                    if total_size > 0:
                        percent = downloaded / total_size
                        # Update UI Progress
                        GLib.idle_add(pbar.set_fraction, percent)

            status["success"] = True
        except Exception as e:
            print(f"Download error: {e}")
            status["success"] = False
        finally:
            status["finished"] = True
            GLib.idle_add(window.destroy) # Close window when done
            event.set() # Wake up the calling thread

    # Start download thread
    thread = threading.Thread(target=run_download)
    thread.start()

    # We use a nested main loop to make this method "block" 
    # until the download finishes without freezing the UI.
    while not status["finished"]:
        GLib.MainContext.default().iteration(True)

    return status["success"]