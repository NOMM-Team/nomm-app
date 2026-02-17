# NOMM (Native Open Mod Manager)

## The project

This may or may not eventually become a stupid simple, super clean native mod manager for linux.
The goal here is to keep the setup really simple for idiots like me who don't need multiple profiles and all that jazz.
Just a few clicks, a clean, modern interface, and you're done :)

[![Watch the video](https://i.imgur.com/1iGS3zd.png)](https://www.youtube.com/watch?v=3UWBQxQY9kk)
^ Click on the image above for a quick preview of current features ^

> [!WARNING]
> This project is partially made with the help of Gemini.
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

## How can I add support for a game?

One of the main ideas behind this project is that games are defined by easy to create config `.yaml` files.
This means that anyone can create a simple yaml for their game and submit it to the project with little to no coding knowledge and the tool will automate the rest.

This yaml file will need to be placed in `[nomm root folder]/default_game_configs`
For instance, if you would want to add support for Stadew Valley, you would create a `[nomm root folder]/default_game_configs/stardew_valley.yaml` file.

In that yaml you will need to define some basic information for it to be recognised:

```yaml
name: 'Warhammer 40,000: Darktide' # the name of the game, with any symbols, spaces and whatnot kept intact
steamappid: 0000000 # the steam app id, you can find this on: https://steamdb.info/
mods_path: mods/ # the path where the mods need to be installed when they are enabled
gogstoreid: 1207666893 # the gog store id, you can find this on: https://gogapidocs.readthedocs.io/en/latest/gameslist.html
```
> [!NOTE]
> Obviously you should only add `gogstoreid` if the game is actually on the GOG store.

You can additionally define some extra stuff for added features:
```yaml
load_order_path: mods/mod_load_order.txt # for games with a text-editable load order, you can specify a path and a button will appear in the app to edit it directly.

essential-utilities: # this lets you define things such as mod loaders or essential utilities
  darktide-mod-loader: # you can have multiple ones, each one needs its own key
    name: Darktide Mod Loader # the name of the tool
    creator: Talon-d # the creator of the tool
    creator-link: https://github.com/talon-d # a link to the creator's page, portal, social, whatever
    source: "https://github.com/talon-d/darktideML-4linux/releases/download/1.5/darktideML-4linux1-5.zip" #the actual thing we'll need to download
    utility_path: "" # where the utility needs to be extracted to
    enable_command: "sh handle_darktide_mods.sh --enable" # any command that needs to be run (from the root of the game folder) to enable the mod loader
```

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
- [x] Rudimentary FOMOD support
- [ ] Handle more complex FOMOD, and handle them cleanly
- [ ] Let user skip launcher and go straight to game
- [ ] Figure out how to create a flatpak for the app
- [ ] Add language-specific strings
- [ ] Think about how to let user define load orders
- [ ] Let user define load orders
- [x] Add support for GOG libraries / games (through Heroic)
- [x] Add support for Epic libraries / games (through Heroic)
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


