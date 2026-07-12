import os, sys
# make the plugin-root modules (waypoints_core) importable from tests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
