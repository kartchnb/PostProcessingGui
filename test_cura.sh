#!/usr/bin/bash

# Delete Cura's log to start with a fresh new one
rm ~/.local/share/cura/5.3/cura.log 2> /dev/null

rm settings.json 2> /dev/null

#rm ~/untitled.gcode 2> /dev/null

# Launch Cura
cura cube.stl&
