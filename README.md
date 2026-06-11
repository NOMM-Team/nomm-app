[![Watch the video](https://i.imgur.com/Qdn83As.png)](https://www.youtube.com/watch?v=3UWBQxQY9kk)
<div align="center">
  <a href="https://discord.gg/WFRePSjEQY"><img src="https://img.shields.io/discord/1472479817512521772?color=0098DB&label=Discord&logo=discord&logoColor=0098DB"></a>
</div>

# NOMM (Native Open Mod Manager)

## The project

NOMM is a stupid simple, super clean "native" (as in it runs on Linux without having to use translation tools...) mod manager for Linux.
The goal here is to keep the setup really simple for idiots like me who don't need complex features and all that jazz.
Just a few clicks, a clean, modern interface, and you're done :)

Don't come here expecting it to manage mods for something like Skyrim. There are specific tools for that (see [NaK](https://github.com/SulfurNitride/NaK) or [Jackify](https://github.com/Omni-guides/Jackify)).

Instead, think of NOMM as more of a general purpose tool for most games that just need you to point to a directory and extract some zip files.

> [!WARNING]
> This project is partially made with the help of Gemini (especially on the GUI side of things).
> 
> If you hate AI, that makes two of us, _however_, I would never have been able to make something like this without it (simply because of the amount of work and research it would have required).
> <br>I want to be clear that even if coding is not my job, I _do_ have a computer science background and understand all of the code that Gemini has created. 

### My Guiding Principles

- No Ads
- No Telemetry
- No User Account Requirement
- Clean & Modern UI/UX
- Beginner-friendly
- Fully open

## How can you add support for a game?

One of the main ideas behind this project is that games are defined by easy to create config `.yaml` files.
This means that anyone can create a simple yaml for their game and submit it to the project with little to no coding knowledge and the tool will automate the rest.

You can find out more info on how to add support for your game [here](https://nomm.moe/docs/adding-your-game).

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
- [x] Add mod update checker
- [x] Let user skip launcher and go straight to game
- [x] Figure out how to create a flatpak for the app
- [x] Add language-specific strings
- [X] Let user define load orders
- [x] Add support for GOG libraries / games (through Heroic)
- [x] Add support for Epic libraries / games (through Heroic)
- [x] Detect conflicts

Phase 3 Development Progress:
- [x] Manage conflicts (for sure this will be hard without an actually good developer)
- [x] Review access rights to be more restrictive
- [ ] Make a Flathub build
- [x] Handle more complex FOMOD, and handle them cleanly

Bonus (nice to have)
- [ ] Game profiles?
- [ ] ???

## Installing/Running

The easiest way to run the app is with flatpak!

To do so :

1. Go to the [releases](https://github.com/Allexio/nomm/releases) tab.
2. Expand the `Assets` box of the latest version
3. Click on the `nomm.flatpak` file to download it
4. Once downloaded, if you have KDE/GNOME you may simply double click the file. This should boot up `KDE Discover` or `Gnome Software`.
5. Once there you should have a button to install the app, click it.
6. Once installed, you will see a `Launch` or `Run` button appear, click it.

And you're done!

For more advanced users (those who prefer the console or may not have a standard distro)

You may install and run the flatpak via command line:
4. `flatpak install nomm.flatpak`
5. `flatpak run flatpak run com.nomm.Nomm`

From now on when you want to launch it you can just look for it in your start menu (by typing "nomm")

## Building

### Dependencies

The app is built with:
- [Python](python.org) (3.14) -> ...Python...
- [GTK](https://www.gtk.org/) (>4.0) -> UI framework
- [Libadwaita](https://gnome.pages.gitlab.gnome.org/libadwaita/) -> UI framework
- [Requests](https://pypi.org/project/requests/) -> requests to nexusmods, gog, epic, etc.
- [Unrar](https://pypi.org/project/unrar/) -> extraction of mods in rar format
- [vdf](https://github.com/ValvePython/vdf) -> read steam config files
- [PyYAML](https://pyyaml.org/) -> read and write yaml files

### Prerequisites

- Obviously to build a flatpak you need to have a distro with flatpak support (most of them do) -> this should normally include the `flatpak-builder` utility
- You need to download the [flatpak-pip-generator](https://github.com/flatpak/flatpak-builder-tools/blob/master/pip/flatpak-pip-generator) tool

### Building the app

#### Flatpak

1. Make the `build.sh` file executable (if you don't know how to do this see [here](https://stackoverflow.com/questions/817060/creating-executable-files-in-linux))
2. Place your `flatpak-pip-generator.py` file at the root of the app's directory
3. Run `./build.sh`
4. Wait for flatpak to be built
5. You should now have a `nomm.flatpak` file in the directory
6. To install your newly obtained flatpak, follow the steps in the "[Installing/Running](https://github.com/Allexio/nomm?tab=readme-ov-file#installingrunning)" section above

#### AUR

1. Clone the repository
```
git clone https://github.com/Allexio/nomm.git
```
2. Make the `build-aur.sh` file executable. from the downloaded folder use this command:
```
chmod +x ./build/build-aur.sh
```
3. Confirm the installation