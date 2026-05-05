#!/bin/bash
echo "Quick test: Open text editor with unsaved changes, then run this"
echo "Press Ctrl+C to cancel, or Enter to continue..."
read

gnome-text-editor &
sleep 2
echo "Type some text in the editor, then press Ctrl+Q"
echo "When dialog appears, press Enter here"
read

python3 debug_dialog_buttons.py
