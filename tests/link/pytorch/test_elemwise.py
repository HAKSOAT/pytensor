import numpy as np
import pytest

import pytensor.tensor as pt
from pytensor.configdefaults import config
from pytensor.graph.fg import FunctionGraph
from pytensor.tensor import elemwise as pt_elemwise
from pytensor.tensor.special import SoftmaxGrad, log_softmax, softmax
from pytensor.tensor.type import matrix, tensor, vector
from tests.link.pytorch.test_basic import compare_pytorch_and_py


def test_pytorch_Dimshuffle():
    a_pt = matrix("a")

    x = a_pt.T
    x_fg = FunctionGraph([a_pt], [x])
    compare_pytorch_and_py(x_fg, [np.c_[[1.0, 2.0], [3.0, 4.0]].astype(config.floatX)])

    x = a_pt.dimshuffle([0, 1, "x"])
    x_fg = FunctionGraph([a_pt], [x])
    compare_pytorch_and_py(x_fg, [np.c_[[1.0, 2.0], [3.0, 4.0]].astype(config.floatX)])

    a_pt = tensor(dtype=config.floatX, shape=(None, 1))
    x = a_pt.dimshuffle((0,))
    x_fg = FunctionGraph([a_pt], [x])
    compare_pytorch_and_py(x_fg, [np.c_[[1.0, 2.0, 3.0, 4.0]].astype(config.floatX)])

    a_pt = tensor(dtype=config.floatX, shape=(None, 1))
    x = pt_elemwise.DimShuffle([False, True], (0,))(a_pt)
    x_fg = FunctionGraph([a_pt], [x])
    compare_pytorch_and_py(x_fg, [np.c_[[1.0, 2.0, 3.0, 4.0]].astype(config.floatX)])


def test_multiple_input_output():
    x = vector("x")
    y = vector("y")
    out = pt.mul(x, y)

    fg = FunctionGraph(outputs=[out], clone=False)
    compare_pytorch_and_py(fg, [[1.5], [2.5]])

    x = vector("x")
    y = vector("y")
    div = pt.int_div(x, y)
    pt_sum = pt.add(y, x)

    fg = FunctionGraph(outputs=[div, pt_sum], clone=False)
    compare_pytorch_and_py(fg, [[1.5], [2.5]])


def test_pytorch_elemwise():
    x = pt.vector("x")
    out = pt.log(1 - x)

    fg = FunctionGraph([x], [out])
    compare_pytorch_and_py(fg, [[0.9, 0.9]])


@pytest.mark.parametrize("axis", [None, 0, 1])
def test_softmax(axis):
    x = matrix("x")
    out = softmax(x, axis=axis)
    fgraph = FunctionGraph([x], [out])
    test_input = np.arange(6, dtype=config.floatX).reshape(2, 3)

    compare_pytorch_and_py(fgraph, [test_input])


@pytest.mark.parametrize("axis", [None, 0, 1])
def test_logsoftmax(axis):
    x = matrix("x")
    out = log_softmax(x, axis=axis)
    fgraph = FunctionGraph([x], [out])
    test_input = np.arange(6, dtype=config.floatX).reshape(2, 3)

    compare_pytorch_and_py(fgraph, [test_input])


@pytest.mark.parametrize("axis", [None, 0, 1])
def test_softmax_grad(axis):
    dy = matrix("dy")
    dy_value = np.array([[1, 1, 1], [0, 0, 0]], dtype=config.floatX)
    sm = matrix("sm")
    sm_value = np.arange(6, dtype=config.floatX).reshape(2, 3)
    out = SoftmaxGrad(axis=axis)(dy, sm)
    fgraph = FunctionGraph([dy, sm], [out])
    compare_pytorch_and_py(fgraph, [dy_value, sm_value])
