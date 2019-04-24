import unittest
from pymps.iMPS import iMPS, ivMPS, TransferMatrix

from numpy.random import rand, randint, randn
from numpy import diag, dot, tensordot, transpose, allclose
from numpy import real as re, imag as im
from numpy import all, eye, isclose, reshape, swapaxes, trace as tr
from numpy import concatenate, array, stack, sum, identity, zeros, abs 
from numpy import sqrt, real_if_close, around, prod, sign, newaxis
from numpy import concatenate as ct, split as chop, save, load
from numpy.linalg import cholesky, eigvals, svd, inv, norm
from scipy.sparse.linalg import LinearOperator, eigs as arnoldi
from scipy.linalg import svd as svd_s, cholesky as cholesky_s

from copy import copy

from itertools import product
import matplotlib as mp
import matplotlib.pyplot as plt

from pymps.tensor import H, C, r_eigenmatrix, l_eigenmatrix, get_null_space, p
from pymps.tensor import basis_iterator, T, rotate_to_hermitian, eye_like
from pymps.spin import spins, N_body_spins
Sx, Sy, Sz = spins(0.5)

class TestTransferMatrix(unittest.TestCase):
    """TestTransferMatrix"""

    def setUp(self):
        N = 5
        D_min, D_max = 9, 10
        d_min, d_max = 2, 3
        p_min, p_max = 1, 2  # always 1 for now
        self.rand_cases = [iMPS().random(randint(d_min, d_max),
                                         randint(D_min, D_max),
                                         period=randint(p_min, p_max))
                           for _ in range(N)]
        self.transfer_matrices = [TransferMatrix(case.data[0])
                                  for case in self.rand_cases]

    def test_transfer_matrices(self):
        for tm in self.transfer_matrices:
            r = rand(tm.shape[1])
            full_tm = transpose(tensordot(tm.A, C(tm.A), [0, 0]), [0, 2, 1, 3]).reshape(tm.shape)
            self.assertTrue(allclose(full_tm @ r, tm.mv(r)))

    def test_aslinearoperator(self):
        for tm in self.transfer_matrices:
            r = rand(tm.shape[1])
            full_tm = transpose(tensordot(tm.A, C(tm.A), [0, 0]), [0, 2, 1, 3]).reshape(tm.shape)
            self.assertTrue(allclose(full_tm @ r, tm.aslinearoperator() @ (r)))

    def test_linear_operator_eigs(self):
        for tm in self.transfer_matrices:
            r = rotate_to_hermitian(arnoldi(tm.aslinearoperator(), k=1)[1].reshape(tm.A.shape[1:]))
            l = rotate_to_hermitian(arnoldi(tm.aslinearoperator().H, k=1)[1].reshape(tm.A.shape[1:]))
            r, l = r/sign(r[0, 0]), l/sign(l[0, 0])
            self.assertTrue(allclose(r, r.conj().T))
            self.assertTrue(allclose(l, l.conj().T))
            self.assertTrue(all(eigvals(r) > 0))
            self.assertTrue(all(eigvals(l) > 0))

class TestiMPS(unittest.TestCase):
    """TestiMPS"""

    def setUp(self):
        N = 5
        D_min, D_max = 2, 3 
        d_min, d_max = 2, 3
        p_min, p_max = 1, 2  # always 1 for now
        self.rand_cases = [iMPS().random(randint(d_min, d_max),
                                         randint(D_min, D_max),
                                         period=randint(p_min, p_max))
                           for _ in range(N)]
        self.rand_v_cases = [ivMPS().random(randint(d_min, d_max),
                                            randint(D_min, D_max),
                                            period=randint(p_min, p_max))
                             for _ in range(N)]

    def test_tangent_space(self):
        from numpy import real, imag, trace as tr, array
        import matplotlib.pyplot as plt
        A = self.rand_cases[0]
        pr, vL = A.left_null_projector(True)
        V = vL.reshape(-1, vL.shape[-1])
        self.assertTrue(allclose(eye_like(V.T), V.conj().T@V))

        Sx12, Sy12, Sz12 = N_body_spins(0.5, 1, 2)
        Sx22, Sy22, Sz22 = N_body_spins(0.5, 2, 2)
        def H(λ): return [-4*Sz12@Sz22+2*λ*(Sx12+Sx22)]
        λ = 5
        def H(λ): return [Sz12@Sz22+Sx12@Sx22+Sy12@Sy12]

        O, l, r, K = A.I_EP(H(λ), testing=True)
        fun = norm(O(concatenate([real(K.reshape(-1)), imag(K.reshape(-1))])))
        print(fun)
        self.assertTrue(abs(norm(O(concatenate([real(K.reshape(-1)), imag(K.reshape(-1))]))))<1e-5)
        self.assertTrue(allclose(tr(K@r), 0))
        
        dt = 0.1
        rs = []
        for _ in range(500):
            A = (A+dt*A.dA_dt(H(λ))).left_canonicalise()
            rs.append(A.Es([2*Sx, 2*Sy, 2*Sz]))
            print(A.energy(H(λ)))

        plt.plot(array(rs))
        plt.show()

    def test_canonicalise_conditions(self):
        for case in self.rand_cases:
            v_case = copy(case).canonicalise(to_vidal=True)  # v returns a vidal form MPS, reuse tests from v_canon
            G, L = v_case.data[0]
            LG = L @ G
            GL = G @ L

            L_ = transpose(tensordot(LG, C(LG), [0, 0]), [0, 2, 1, 3])
            R_ = transpose(tensordot(GL, C(GL), [0, 0]), [0, 2, 1, 3])

            # Normalisation, eigenvalue condition
            self.assertTrue(allclose(tensordot(identity(case.D), L_, [[0, 1], [0, 1]]), identity(case.D)))
            self.assertTrue(allclose(tensordot(R_, identity(case.D), [[2, 3], [0, 1]]), identity(case.D)))

            # L scaled right
            self.assertTrue(isclose(sum(L*L), 1))

            # right canonicalisation
            r_case = copy(case).canonicalise('r')
            A = r_case.data[0]
            self.assertTrue(allclose(tensordot(A, H(A), [[0, -1], [0, 1]]), identity(case.D)))

            # left canonicalisation
            l_case = copy(case).canonicalise('l')
            A = l_case.data[0]
            self.assertTrue(allclose(tensordot(H(A), A, [[0, -1], [0, 1]]), identity(case.D)))

    def test_canonicalisation_unique(self):
        for case in self.rand_cases:
            l_mps = case.copy().canonicalise('l')
            A = l_mps.copy()
            A_ = l_mps.canonicalise('l')
            for _ in range(10):
                A_= A_.canonicalise('l')
            _, l, r = A.eigs()
            _, l_, r_ = A_.eigs()
            self.assertTrue(allclose(l, l_))
            self.assertTrue(allclose(r, r_))
            
    def test_iMPS_eigs(self):
        for case in self.rand_cases:
            eta, l, r = case.transfer_matrix().eigs()
            self.assertTrue(allclose(tr(l @ r), 1))

    def test_canonicalise_EVs(self):
        for case in self.rand_cases:
            ops = [Sx, Sy, Sz]
            case.canonicalise()
            I_ = case.E(identity(2))
            Ss_ = array([case.E(op) for op in ops])

            # Norm is 1
            self.assertTrue(allclose(I_, 1))

            for _ in range(10):
                hands = ['l', 'm', 'r', None]
                for hand in hands:
                    if hand is not None:
                        case.canonicalise(hand)

            I__ = case.E(identity(2))
            Ss__ = array([case.E(op) for op in ops])

            # Norm conserved, operator expectations don't change
            # After applying 10 canonicalisations
            self.assertTrue(allclose(I__, 1))
            self.assertTrue(allclose(Ss__, Ss_))

    def test_EVs(self):
        for case in self.rand_cases:
            hands = ['l', 'm', 'r', None]
            for hand in hands:
                if hand is not None:
                    case.canonicalise(hand)
                self.assertTrue(isclose(case.E(identity(2), hand), 1))


    def test_v_canonicalise_conditions(self):
        for case in self.rand_v_cases:
            case.canonicalise()
            G, L = case.data[0]
            LG = swapaxes(dot(L, G), 0, 1)
            GL = dot(G, L)

            L_ = transpose(tensordot(LG, C(LG), [0, 0]), [0, 2, 1, 3])
            R_ = transpose(tensordot(GL, C(GL), [0, 0]), [0, 2, 1, 3])

            # Normalisation, eigenvalue condition
            self.assertTrue(allclose(tensordot(identity(case.D), L_, [[0, 1], [0, 1]]), identity(case.D)))
            self.assertTrue(allclose(tensordot(R_, identity(case.D), [[2, 3], [0, 1]]), identity(case.D)))
            # L scaled right
            self.assertTrue(isclose(sum(L*L), 1))

    def test_v_canonicalise_EVs(self):
        for case in self.rand_v_cases:
            ops = [Sx, Sy, Sz]
            case.canonicalise()
            I_ = case.E(identity(2))
            Ss_ = array([case.E(op) for op in ops])

            # Norm is 1
            self.assertTrue(allclose(I_, 1))

            for _ in range(10):
                case.canonicalise()

            I__ = case.E(identity(2))
            Ss__ = array([case.E(op) for op in ops])

            # Norm conserved, operator expectations don't change
            # After applying 10 canonicalisations
            self.assertTrue(allclose(I__, 1))
            self.assertTrue(allclose(Ss__, Ss_))

if __name__ == '__main__':
    unittest.main(verbosity=2)
