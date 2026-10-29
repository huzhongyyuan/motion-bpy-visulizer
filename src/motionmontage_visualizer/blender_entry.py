"""Executed by Blender's Python, not the host interpreter."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motionmontage_visualizer.renderer import run
run(Path(sys.argv[sys.argv.index('--')+1]))
