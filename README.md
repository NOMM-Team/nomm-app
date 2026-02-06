# NOMM (Native Open Mod Manager)

## The project

This may or may not eventually become a stupid simple, super clean native mod manager for linux.
The goal here is to keep the setup really simple for idiots like me who don't need multiple profiles and all that jazz.
Just a few clicks, a clean, modern interface, and you're done :)

[![Watch the video](https://i.imgur.com/1iGS3zd.png)](https://www.youtube.com/watch?v=3UWBQxQY9kk)
^ Click on the image above for a quick preview of current features ^

> [!WARNING]
> This project is made with the help of Gemini.
> 
> If you hate AI, that makes two of us 🙂
> _However_, I would never have been able to make something like this without it.

### My Guiding Principles

- No Ads
- No Telemetry
- No User Account Requirement
- Clean & Modern UI/UX
- Beginner-friendly
- Fully open

### How does it work?

One of the main ideas behind this project is that games are defined by easy to setup config yaml files.
This means that anyone can create a simple yaml for their game and submit it to the project with little to no coding knowledge and the tool will automate the rest.

For instance:

```yaml
name: 'Warhammer 40,000: Darktide'
steamappid: 1361210
mods_path: mods/

load_order_path: mods/mod_load_order.txt

essential-utilities:
  darktide-mod-loader:
    name: Darktide Mod Loader
    creator: Talon-d
    creator-link: https://github.com/talon-d
    source: "https://github.com/talon-d/darktideML-4linux/releases/download/1.5/darktideML-4linux1-5.zip"
    utility_path: ""
    enable_command: "sh handle_darktide_mods.sh --enable"
    disable_command: "sh handle_darktide_mods.sh --disable"
```

Let's go through these line by line.

##### Compulsory

- `name` : the name of the game
- `steamappid` : the steam ID of the game
- `mods_path` : the path where mods should be deployed for this game

##### Optional

- `load_order_path` : The path where a load order file would be, so that the tool can add a button to edit it directly
- `essential-utilities` : This section is used to define some special tools that are essential to mod the game.
    - `name` : the name of the tool
    - `creator` : the name of the creator
    - `creator-link` : a link tot he creator's github
    - `source` : a link to the actual file that needs to be downloaded
    - `utility_path` : where the utility files need to be extracted to (here it is in the root of the game directory)
    - `enable_command` : a command that will be run after extracting the files to the directory


## "Roadmap"

Phase 1 Development Progress:
- [x] Auto-detect Steam libraries
- [x] Auto-detect Steam library games
- [x] Obtain cool images for game tiles from Steam cache folder
- [x] Display results in a super clean library-style window
- [x] Let user choose a downloads folder location
- [x] Create a whole new window with a cool header from Steam cache folder
- [x] Associate app w/ nexusmods download links
- [x] Let user navigate downloaded mods and delete downloaded mods
- [x] Figure out how mod staging and symlinks and whatnot work because I have no idea
- [x] Let user enable/disable mods
- [x] Prepare "essential utilities" section in game config file that lets the community define some essential custom tools that are needed for a game to work, so that the process is easier for people who just want to mod the game (i.e. SKSE, Darktide mod loader, that kind of stuff)
- [x] Let user launch the game directly from the interface
- [x] Add a button to return to launcher from the main window

Phase 2 Development Progress:
- [ ] Handle simple FOMOD
- [ ] Let user skip launcher and go straight to game
- [ ] Figure out how to create a flatpak for the app
- [ ] Add language-specific strings
- [ ] Think about how to let user define load orders
- [ ] Let user define load orders
- [ ] Add support for GOG libraries / games
- [ ] ???

Phase 3 Development Progress:
- [ ] Manage conflicts (for sure this will be hard without an actually good developer)
- [ ] ???

Bonus (nice to have)
- [ ] Game profiles?
- [ ] ???

## "Building" / Executing

The app is built with:
- [Python](python.org) (3.14)
- [GTK](https://www.gtk.org/)
- [Libadwaita](https://gnome.pages.gitlab.gnome.org/libadwaita/)

This means you should be able to run it directly on most linux distros without too many problems via the console by typing:
`python3 ./launcher.py`
Whilst in the path where the code is.


