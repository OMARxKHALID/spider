import sys
import os

# Set TESSDATA_PREFIX for Flatpak and installed environments
tessdata = os.path.join(
    os.environ.get('FLATPAK_DEST', '/usr'),
    'share', 'tessdata'
)
if os.path.isdir(tessdata):
    os.environ.setdefault('TESSDATA_PREFIX', tessdata)
