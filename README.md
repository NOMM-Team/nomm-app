# NOMM (Native Open Mod Manager)

## The project

This may or may not eventually become a stupid simple, super clean native mod manager for linux.
The goal here is to keep the setup really simple for idiots like me who don't need multiple profiles and all that jazz.
Just a few clicks, a clean, modern interface, and you're done :)

> [!WARNING]
> A big chunk of this project is made by vibe coding with Gemini.
> I take no responsibility for any kind of impact this early in development app may have on your system.
> 
> If you hate AI, that makes two of us 🙂
> 
> _However_, I would never have been able to make something like this without it.

### My Guiding Principles

- No Ads
- No Telemetry
- No User Account Requirement
- Clean & Modern UI/UX
- Beginner-friendly
- Fully open

## "Roadmap"

Phase 1 Development Progress:
- [x] Auto-detect Steam libraries
- [x] Auto-detect Steam library games
- [x] Obtain cool images from Steam cache folder
- [x] Display results in a super clean library-style window
- [x] Let user choose a downloads folder location
- [ ] Create a whole new window with a cool header from Steam cache folder
- [ ] Associate app w/ nexusmods download links
- [ ] Let user navigate downloaded mods and delete downloaded mods
- [ ] Figure out how mod staging and symlinks and whatnot work because I have no idea
- [ ] Let user enable/disable mods
- [ ] Prepare "special tools" section in game config file that lets the community define some essential custom tools that are needed for a game to work, so that the process is easier for people who just want to mod the game (i.e. SKSE, Darktide mod loader, that kind of stuff)
- [ ] Let user launch the game directly from the interface
- [ ] Make app differentiate between first time setup and re-launch (and also think about the consequences of this from a UX standpoint - shoudl launcher be relaunched on 2nd+ startup? If not, add a button to return to launcher from the main window)
- [ ] Figure out how to create a flatpak for the app

Phase 2 Development Progress:
- [ ] Add language-specific strings
- [ ] Think about how to let user define load orders
- [ ] Let user define load orders
- [ ] Add support for GOG libraries / games
- [ ] ???

Phase 3 Development Progress:
- [ ] Manage conflicts (for sure this will be hard without an actual developer)
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
`python3 ./main.py`
Whilst in the path where the code is.


