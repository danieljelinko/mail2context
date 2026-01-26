from fastcore.test import *
from fastcore.test import test_close as test_is_close
from fastcore.imports import equals

def test_eq(a, b, cname="=="):
    test(a, b, equals, cname=cname)

def test_ne(a, b, cname="!="):
    test(a, b, nequals, cname=cname)

def test_close(a, b, eps=1e-5, cname="~="):
    test_is_close(a, b, eps=eps)
