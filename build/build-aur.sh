#!/bin/bash
cd "$(dirname "$0")/aur"
makepkg -si
