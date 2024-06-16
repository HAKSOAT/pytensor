from collections.abc import Callable, Iterable
from functools import partial

import numpy as np
import pytest

from pytensor.compile.function import function
from pytensor.compile.mode import get_mode
from pytensor.compile.sharedvalue import SharedVariable, shared
from pytensor.configdefaults import config
from pytensor.graph.basic import Apply
from pytensor.graph.fg import FunctionGraph
from pytensor.graph.op import Op
from pytensor.raise_op import CheckAndRaise
from pytensor.tensor.type import scalar, vector


torch = pytest.importorskip("torch")


pytorch_mode = get_mode("PYTORCH")
py_mode = get_mode("FAST_COMPILE")


def compare_pytorch_and_py(
    fgraph: FunctionGraph,
    test_inputs: Iterable,
    assert_fn: Callable | None = None,
    must_be_device_array: bool = True,
    pytorch_mode=pytorch_mode,
    py_mode=py_mode,
):
    """Function to compare python graph output and pytorch compiled output for testing equality

    Parameters
    ----------
    fgraph: FunctionGraph
        PyTensor function Graph object
    test_inputs: iter
        Numerical inputs for testing the function graph
    assert_fn: func, opt
        Assert function used to check for equality between python and pytorch. If not
        provided uses np.testing.assert_allclose
    must_be_device_array: Bool
        Checks if torch.device.type is cuda


    """
    if assert_fn is None:
        assert_fn = partial(np.testing.assert_allclose)

    fn_inputs = [i for i in fgraph.inputs if not isinstance(i, SharedVariable)]

    pytensor_torch_fn = function(fn_inputs, fgraph.outputs, mode=pytorch_mode)
    pytorch_res = pytensor_torch_fn(*test_inputs)

    if must_be_device_array:
        if isinstance(pytorch_res, list):
            assert all(isinstance(res, torch.Tensor) for res in pytorch_res)
        else:
            assert pytorch_res.device.type == "cuda"

    pytensor_py_fn = function(fn_inputs, fgraph.outputs, mode=py_mode)
    py_res = pytensor_py_fn(*test_inputs)

    if len(fgraph.outputs) > 1:
        for j, p in zip(pytorch_res, py_res):
            assert_fn(j.cpu(), p)
    else:
        assert_fn([pytorch_res[0].cpu()], py_res)

    return pytensor_torch_fn, pytorch_res


def test_pytorch_FunctionGraph_once():
    """Make sure that an output is only computed once when it's referenced multiple times."""
    from pytensor.link.pytorch.dispatch import pytorch_funcify

    x = vector("x")
    y = vector("y")

    class TestOp(Op):
        def __init__(self):
            self.called = 0

        def make_node(self, *args):
            return Apply(self, list(args), [x.type() for x in args])

        def perform(self, inputs, outputs):
            for i, inp in enumerate(inputs):
                outputs[i][0] = inp[0]

    @pytorch_funcify.register(TestOp)
    def pytorch_funcify_TestOp(op, **kwargs):
        def func(*args, op=op):
            op.called += 1
            return list(args)

        return func

    op1 = TestOp()
    op2 = TestOp()

    q, r = op1(x, y)
    outs = op2(q + r, q + r)

    out_fg = FunctionGraph([x, y], outs, clone=False)
    assert len(out_fg.outputs) == 2

    out_torch = pytorch_funcify(out_fg)

    x_val = torch.tensor([1, 2]).to(getattr(torch, config.floatX))
    y_val = torch.tensor([2, 3]).to(getattr(torch, config.floatX))

    res = out_torch(x_val, y_val)
    assert len(res) == 2
    assert op1.called == 1
    assert op2.called == 1

    res = out_torch(x_val, y_val)
    assert len(res) == 2
    assert op1.called == 2
    assert op2.called == 2


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_shared(device):
    with torch.device(device):
        a = shared(np.array([1, 2, 3], dtype=config.floatX))
        pytensor_torch_fn = function([], a, mode="PYTORCH")
        pytorch_res = pytensor_torch_fn()

        assert isinstance(pytorch_res, torch.Tensor)
        assert isinstance(a.get_value(), np.ndarray)
        np.testing.assert_allclose(pytorch_res.cpu(), a.get_value())

        pytensor_torch_fn = function([], a * 2, mode="PYTORCH")
        pytorch_res = pytensor_torch_fn()

        assert isinstance(pytorch_res, torch.Tensor)
        assert isinstance(a.get_value(), np.ndarray)
        np.testing.assert_allclose(pytorch_res.cpu(), a.get_value() * 2)

        new_a_value = np.array([3, 4, 5], dtype=config.floatX)
        a.set_value(new_a_value)

        pytorch_res = pytensor_torch_fn()
        assert isinstance(pytorch_res, torch.Tensor)
        np.testing.assert_allclose(pytorch_res.cpu(), new_a_value * 2)


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_shared_updates(device):
    with torch.device(device):
        a = shared(0)

        pytensor_torch_fn = function([], a, updates={a: a + 1}, mode="PYTORCH")
        res1, res2 = pytensor_torch_fn(), pytensor_torch_fn()
        assert res1 == 0
        assert res2 == 1
        assert a.get_value() == 2
        assert isinstance(a.get_value(), np.ndarray)

        a.set_value(5)
        res1, res2 = pytensor_torch_fn(), pytensor_torch_fn()
        assert res1 == 5
        assert res2 == 6
        assert a.get_value() == 7
        assert isinstance(a.get_value(), np.ndarray)


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_pytorch_checkandraise(device):
    with torch.device(device):
        check_and_raise = CheckAndRaise(AssertionError, "testing")

        x = scalar("x")
        conds = (x > 0, x > 3)
        y = check_and_raise(x, *conds)

        y_fn = function([x], y, mode="PYTORCH")

        with pytest.raises(AssertionError, match="testing"):
            y_fn(0.0)
        assert y_fn(4).item() == 4
