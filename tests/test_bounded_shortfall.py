import sys
from pathlib import Path
import numpy as np
import importlib.util
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('v2_21_test',ROOT/'src/v2_21_frozen_model.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
assert list(mod.bounded_shortfall(np.array([0.0, 1.0, 2.0]), np.log1p([1.0,1.0,1.0])))==[1.0,0.0,0.0]
assert float(mod.bounded_shortfall([0],[float('-inf')])[0])==0.0
assert float(mod.bounded_shortfall([1],[np.log1p(0)])[0])==0.0
assert np.isfinite(mod.bounded_shortfall([np.nan],[0.0])).all()
print('SYNTHETIC_BOUNDED_SHORTFALL_TESTS=PASS')
