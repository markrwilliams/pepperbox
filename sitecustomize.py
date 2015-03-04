import sys
from pepperbox.restrict import restrict
restrict()
del restrict
del sys.modules['pepperbox.restrict']
del sys.modules['sys']
