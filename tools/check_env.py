import sys
import importlib.util
import numpy
import pandas

print("python", sys.version.split()[0])
print("numpy", numpy.__version__)
print("pandas", pandas.__version__)
for m in ["pyarrow", "tables", "h5py", "scipy", "matplotlib", "sklearn", "pywin32"]:
    print(m, importlib.util.find_spec(m) is not None)
