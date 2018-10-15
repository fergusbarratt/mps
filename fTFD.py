import unittest
from fMPS import fMPS
from ncon import ncon
from numpy.random import randint, randn
from numpy import kron, swapaxes as sw, eye, transpose as tra, sqrt
from scipy.linalg import norm, null_space as null, inv, cholesky as ch
from tensor import H as cT, C as c

class fTFD(fMPS):
    def __init__(self, data=None, d=None, D=None):
        """__init__"""
        super().__init__(data, d, D)

    def random(self, L, d, D, pure=True):
        if pure:
            data = super().random(L, d, D)
            self.data = [kron(a, b) for a, b in zip(data, data)]
            self.d = d**2
            self.D = D**2
        else:
            data = super().random(L, d**2, D)
        return self

    def symmetry(self):
        return fTFD([tra(X.reshape((int(sqrt(X.shape[0])), int(sqrt(X.shape[0])),
                                    int(sqrt(X.shape[1])), int(sqrt(X.shape[1])), 
                                    int(sqrt(X.shape[2])), int(sqrt(X.shape[2])))), 
                         [1, 0, 3, 2, 5, 4]).reshape(X.shape) for X in self])

    def flip_spin(self):
        return fTFD([X.reshape(int(sqrt(X.shape[0])), int(sqrt(X.shape[0])), *X.shape[1:]
                     ).transpose(1, 0, 2, 3
                     ).reshape(X.shape) 
                     for X in self])

    def M(self):
        D = self.D
        return kron(eye(D*(D+1)/2), -eye(D*(D-1)/2))

    def left_null_projector(self, n, l=None, get_vL=False, store_envs=False, vL=None):
        """left_null_projector:           |
                         - inv(sqrt(l)) - vL = vL- inv(sqrt(l))-
                                               |
        replaces A(n) in TDVP

        :param n: site
        """
        if l is None:
            l, _ = self.get_envs(store_envs)
        if vL is None:
            L_ = sw(cT(self[n])@ch(l(n-1)), 0, 1)
            L = L_.reshape(-1, self.d*L_.shape[-1])
            vL = null(L).reshape((self.d, L.shape[1]//self.d, -1))
        pr = ncon([inv(ch(l(n-1)))@vL, inv(ch(l(n-1)))@c(vL)], [[-1, -2, 1], [-3, -4, 1]])
        if get_vL:
            return pr, vL
        return pr

class testfTFD(unittest.TestCase):
    def setUp(self):
        """setUp"""
        self.N = N = 8  # Number of MPSs to test
        #  min and max params for randint
        L_min, L_max = 7, 8
        d_min, d_max = 2, 3 
        D_max = 16
        # N random MPSs
        self.pure_cases = [fTFD().random(randint(L_min, L_max),
                                         randint(d_min, d_max),
                                         D=4,
                                         pure=True)
                           for _ in range(N)]
        self.mixed_cases = [fTFD().random(randint(L_min, L_max),
                                          randint(d_min, d_max),
                                          D=16,
                                          pure=False)
                           for _ in range(N)]

    def test_symmetries(self):
        """test_symmetry"""
        for A, A_ in zip(self.pure_cases, self.mixed_cases):
            self.assertTrue(A==A.symmetry())
            self.assertFalse(A_==A_.symmetry())

if __name__=='__main__':
    unittest.main(verbosity=2)
