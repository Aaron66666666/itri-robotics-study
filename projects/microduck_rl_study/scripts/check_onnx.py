"""Check an exported policy: input/output shapes and no NaN on zero and random input."""
import sys

import numpy as np
import onnxruntime as ort

s = ort.InferenceSession(sys.argv[1])
inp = s.get_inputs()[0]
for name, x in [("zeros", np.zeros(inp.shape, np.float32)),
                ("random", np.random.default_rng(0).normal(size=inp.shape).astype(np.float32))]:
    y = s.run(None, {inp.name: x})[0]
    print(name, inp.shape, "->", y.shape, "nan:", bool(np.isnan(y).any()), "max|a|:", float(np.abs(y).max()))
