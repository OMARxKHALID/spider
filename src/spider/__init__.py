import sys
import os

# Add the vendor directory to sys.path so we can import bundled libraries
vendor_dir = os.path.join(os.path.dirname(__file__), 'vendor')
if vendor_dir not in sys.path:
    sys.path.insert(0, vendor_dir)
