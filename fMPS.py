import unittest
from spin import n_body, N_body_spins, spins
from ncon import ncon
from numpy.random import rand, randint, randn
from numpy.linalg import svd, inv, norm#, cholesky as ch,
from scipy.linalg import null_space as null, sqrtm as ch
from numpy import array, concatenate, diag, dot, allclose, isclose, swapaxes as sw
from numpy import identity, swapaxes, trace, tensordot, sum, prod
from numpy import real as re, stack as st, concatenate as ct
from numpy import split as chop, zeros, ones, ones_like, empty
from numpy import save, load, zeros_like as zl, eye, cumsum as cs
from numpy import sqrt, expand_dims as ed, transpose as tra
from numpy import trace as tr, tensordot as td, kron, imag as im
from tests import is_right_canonical, is_right_env_canonical, is_full_rank
from tests import is_left_canonical, is_left_env_canonical, has_trace_1
from tensor import H as cT, truncate_A, truncate_B, diagonalise, rank, mps_pad
from tensor import C as c
from tensor import rdot, ldot, structure
from qmb import sigmaz, sigmax, sigmay
from copy import deepcopy
from functools import reduce
from itertools import product
Sx, Sy, Sz = spins(0.5)
Sx, Sy, Sz = 2*Sx, 2*Sy, 2*Sz

from time import time
from pathos.multiprocessing import ProcessingPool as Pool

class fMPS(object):
    """finite MPS:
    lists of numpy arrays (1d) of numpy arrays (2d). Finite"""

    def __init__(self, data=None, d=None, D=None):
        """__init__

        :param data: data for internal fMPS
        :param d: local state space dimension - can be inferred if d is None
        :param D: Bond dimension: if not none, will truncate with right 
        canonicalisation
        """

        if data is not None:
            self.L = len(data)
            if d is not None:
                self.d = d
            else:
                self.d = data[0].shape[0]
            if D is not None:
                self.right_canonicalise(D)
            else:
                self.D = max([max(x.shape[1:]) for x in data])
            self.data = data

    def __call__(self, k):
        """__call__: 1-based indexing

        :param k: item to get
        """
        return self.data[k+1]

    def __getitem__(self, k):
        """__getitem__: 0-based indexing

        :param k: item to get
        """
        return self.data[k]

    def __eq__(self, other):
        """__eq__

        :param other:
        """
        return array(
            [allclose(a, b) for a, b in zip(self.data, other.data)]).all()

    def __ne__(self, other):
        """__ne__

        :param other:
        """
        return not self.__eq__(other)

    def __len__(self):
        """__len__"""
        return len(self.data)

    def __add__(self, other):
        """__add__: This is not how to add two MPS: it's itemwise addition.
                    A hack for time evolution.

        :param other: MPS with arrays to add
        """
        return fMPS([a+b for a, b in zip(self.data, other.data)]) 

    def __mul__(self, other):
        """__mul__: This is not multiplying an MPS by a scalar: it's itemwise:
                    Hack for time evolution.
                    Multiplication by other**L

        :param other: scalar to multiply
        """
        return fMPS([other*a for a in self.data], self.d)

    def __rmul__(self, other):
        """__rmul__: right scalar multiplication

        :param other: scalar to multiply
        """
        return self.__mul__(other)

    def __truediv__(self, other):
        """__mul__: This is not multiplying an MPS by a scalar: it's itemwise:
                    Hack for time evolution.
                    Multiplication by other**L

        :param other: scalar to multiply
        """
        return self.__mul__(1/other)

    def left_from_state(self, state):
        """left_from_state: generate left canonical mps from state tensor

        :param state:
        """
        self.L = len(state.shape)
        self.d = state.shape[0]
        Psi = state
        Ls = []

        def split(Psi, n):
            Psi = Psi.reshape(-1, self.d**(self.L-(n+1)), order='F')
            (U, S, V) = svd(Psi, full_matrices=False)
            Ls.append(diag(S))
            return (array(chop(U, self.d)), dot(diag(S), V))

        As = [None]*self.L
        for n in range(self.L):
            (As[n], Psi) = split(Psi, n)
        assert len(As) == self.L

        self.data = As
        self.Ls = Ls

        self.D = max([max(shape[1:]) for shape in self.structure()])

        return self

    def right_from_state(self, state):
        """right_from_state: generate right canonical mps from state tensor

        :param state:
        """
        self.L = len(state.shape)
        self.d = state.shape[0]
        Psi = state
        Ls = []

        def split(Psi, n):
            Psi = Psi.reshape(self.d**(n-1), -1, order='C')
            (U, S, V) = svd(Psi, full_matrices=False)
            Ls.append(diag(S))
            return (dot(U, diag(S)), array(chop(V, self.d, axis=1)))

        Bs = [None]*(self.L+1)
        for n in reversed(range(1, self.L+1)):
            # Exclusive of up_to, generate up_to matrices
            (Psi, Bs[n]) = split(Psi, n)
        Bs = Bs[1:]

        self.data = Bs
        self.Ls = Ls[::-1]
        
        self.D = max([max(shape[1:]) for shape in self.structure()])

        return self

    def recombine(self):
        state = empty([self.d]*self.L) + 1j*empty([self.d]*self.L)

        for ij in product(*[range(self.d)]*self.L):
            #warnings.simplefilter('ignore')
            state[ij] = reduce(dot, map(lambda k_x: k_x[1][ij[k_x[0]]],
                                        enumerate(self.data)))[0][0]
        return state

    def random(self, L, d, D):
        """__init__

        :param L: Length
        :param d: local state space dimension
        :param D: bond dimension
        generate a random fMPS
        """

        self.L = L
        self.d = d
        fMPS = [rand(*((d,) + shape)) + 1j*rand(*((d,) + shape))
                for shape in self.create_structure(L, d, D)]
        self.D = max([max(shape[1:]) for shape in self.create_structure(L, d, D)])
        self.data = fMPS
        return self

    def create_structure(self, L, d, D):
        """create_structure: generate the structure of a OBC fMPS

        :param L: Length
        :param d: local state space dimension
        :param D: bond dimension
        """

        if D is None:
            D = d**L
        left = [(min(d**n, D), min(d**(n+1), D)) for n in range(L//2)]

        def transpose(ltups):
            l = []
            for tup in ltups:
                l.append((tup[1], tup[0]))
            return l
        if L % 2 == 0:
            structure = left + transpose(left[::-1])
        else:
            structure = left + [(left[-1][-1], transpose(left[::-1])[0][0])] +\
                        transpose(left[::-1])
        return structure

    def right_canonicalise(self, D=None, testing=False):
        """right_canonicalise: bring internal fMPS to right canonical form,
        potentially with a truncation

        :param D: bond dimension to truncate to during right sweep
        :param testing: test canonicalness
        """
        if D is not None:
            self.D = min(D, self.D)

        self.ok = True

        def split(M):
            """split: Do SVD, and reshape B matrix

            :param M: matrices
            """
            (U, S, B) = svd(M, full_matrices=False)
            return (U, diag(S), array(chop(B, self.d, axis=1)))

        # left sweep
        for m in range(len(self.data))[::-1]:
            U, S, B = split(concatenate(self.data[m], axis=1))
            U, S, self.data[m] = truncate_B(U, S, B, D)
            if m-1 >= 0:
                self.data[m-1] = tensordot(self.data[m-1], dot(U, S), (-1, 0))

        # right sweep
        Vs = [None]*self.L
        Ls = [None]*self.L

        V = S = identity(1)
        for m in range(len(self.data)):
            M = trace(dot(dot(dot(dot(cT(self.data[m]),
                                  V),
                              S),
                          cT(V)),
                      self.data[m]), 0, 0, 2)

            Vs[m], Ls[m] = diagonalise(M)

            self.data[m] = swapaxes(dot(dot(cT(V), self.data[m]), Vs[m]),
                                    0, 1)

            V, S = Vs[m], Ls[m]

        Ls = [ones_like(Ls[-1])] + Ls  # Ones on each end

        for m in range(len(self.data)):
            # sort out the rank (tDj is tilde)
            Dj = Ls[m].shape[0]
            tDj = rank(Ls[m])
            P = concatenate([identity(tDj), zeros((tDj, Dj-tDj))], axis=1)
            self.data[m-1] = self.data[m-1] @ cT(P)
            self.data[m] = P @ self.data[m]
            Ls[m] = P @ Ls[m] @ cT(P)

        self.Ls = Ls  # store all the singular values

        if testing:
            self.update_properties()
            self.ok = self.ok \
                and self.is_right_canonical\
                and self.is_right_env_canonical\
                and self.is_full_rank\
                and self.has_trace_1

        return self

    def left_canonicalise(self, D=None, testing=False):
        """left_canonicalise: bring internal fMPS to left canonical form,
        potentially with a truncation

        :param D: bond dimension to truncate to during right sweep
        :param testing: test canonicalness
        """
        if D is not None:
            self.D = min(D, self.D)

        self.ok = True

        def split(M):
            """split: Do SVD and reshape A matrix

            :param M: matrix
            """
            (A, S, V) = svd(M, full_matrices=False)
            return (array(chop(A, self.d, axis=0)), diag(S), V)

        for m in range(len(self.data)):
            # sort out canonicalisation
            A, S, V = split(concatenate(self.data[m], axis=0))
            self.data[m], S, V = truncate_A(A, S, V, D)
            if m+1 < len(self.data):
                self.data[m+1] = swapaxes(tensordot(dot(S, V),
                                          self.data[m+1], (-1, 1)), 0, 1)

        Ls = [None]*self.L
        Vs = [None]*self.L
        V = S = identity(1)

        for m in range(len(self.data))[::-1]:
            # sort out env canonicalisation
            M = trace(dot(dot(dot(dot(self.data[m],
                                  V),
                              S),
                          cT(V)),
                      cT(self.data[m])), 0, 0, 2)

            Vs[m], Ls[m] = diagonalise(M)

            self.data[m] = swapaxes(dot(dot(cT(Vs[m]), self.data[m]), V),
                                    0, 1)

            V, S = Vs[m], Ls[m]

        Ls.append(ones_like(Ls[0]))  # Ones on each end

        for m in range(len(self.data)):
            # sort out the rank (tDj is tilde)
            Dj = Ls[m].shape[0]
            tDj = rank(Ls[m])
            P = concatenate([identity(tDj), zeros((tDj, Dj-tDj))], axis=1)
            self.data[m-1] = self.data[m-1] @ cT(P)
            self.data[m] = P @ self.data[m]
            Ls[m] = P @ Ls[m] @ cT(P)

        self.Ls = Ls  # store all the singular values

        if testing:
            self.update_properties()
            self.ok = self.ok\
                and self.is_left_canonical\
                and self.is_left_env_canonical\
                and self.is_full_rank\
                and self.has_trace_1

        return self

    def mixed_canonicalise(self, oc, D=None, testing=False):
        """mixed_canonicalise: bring internal fMPS to mixed canonical form with
        orthogonality center oc, potentially with a truncation

        :param oc: orthogonality center
        :param D: bond dimension
        :param testing: test canonicalness
        """
        self.ok = True
        self.oc = oc
        self.right_canonicalise(D)

        def split(M):
            """split: Do SVD and reshape A matrix

            :param M: matrix
            """
            (A, S, V) = svd(M, full_matrices=False)
            return (array(chop(A, self.d, axis=0)), diag(S), V)

        for m in range(len(self.data))[:oc]:
            # sort out canonicalisation
            A, S, V = split(concatenate(self.data[m], axis=0))
            self.data[m], S, V = truncate_A(A, S, V, D)
            if m+1 < len(self.data):
                self.data[m+1] = swapaxes(tensordot(dot(S, V),
                                                    self.data[m+1],
                                                    (-1, 1)), 0, 1)

        if testing:
            self.ok = self.ok and is_left_canonical(self.data[:oc])\
                              and is_right_canonical(self.data[oc+1:])

        return self

    def update_properties(self):
        """update_properties: Could be slow"""
        self.is_left_canonical = is_left_canonical(self.data)
        self.is_right_canonical = is_right_canonical(self.data)
        self.has_norm_1 = isclose(self.norm(), 1)
        try:
            self.is_left_env_canonical = is_left_env_canonical(self.data,
                                                               self.Ls)
            self.is_right_env_canonical = is_right_env_canonical(self.data,
                                                                 self.Ls)
            self.is_full_rank = is_full_rank(self.Ls)
            self.has_trace_1 = has_trace_1(self.Ls)
        except AttributeError:
            self.is_left_env_canonical = False
            self.is_right_env_canonical = False
            self.is_full_rank = False
            self.has_trace_1 = False

    def structure(self):
        """structure"""
        return [x[0].shape for x in self.data]

    def overlap(self, other):
        """overlap

        :param other: other with which to calculate overlap
        """
        assert len(self) == len(other)

        padded_self, padded_other = mps_pad(self, other)

        F = ones((1, 1))
        for L, R in zip(padded_self, padded_other):
            F = tensordot(tensordot(cT(L), F, (-1, 1)), R, ([0, -1], [0, 1]))
        return F[0][0]

    def norm(self):
        """norm: not efficient - computes full overlap. 
        use self.E(identity(self.d), site) for mixed 
        canonicalising version"""
        return self.overlap(self)

    def get_envs(self, store_envs=False):
        """get_envs: return all envs (slow). indexing is a bit weird: l(-1) is |=
           returns: fns tuple of functions l, r"""
        def get_l(mps):
            ls = [array([[1]])]
            for n in range(len(mps)):
                ls.append(sum(cT(mps[n]) @ ls[-1] @ mps[n], axis=0))
            return lambda n: ls[n+1]

        def get_r(mps):
            rs = [array([[1]])]
            for n in range(len(mps))[::-1]:
                rs.append(sum(mps[n] @ rs[-1] @ cT(mps[n]), axis=0))
            return lambda n: rs[::-1][n+1]
        if store_envs:
            self.l, self.r = get_l(self), get_r(self)
            return self.l, self.r

        return get_l(self), get_r(self)

    def left_transfer(self, op, j, i, ret_all=True):
        """transfer an operator (u, d, ...) on aux indices at i to site(s) j
        Returns a function such that R(j) == op at j. No bounds checking.
        """
        Ls = [op]
        oplinks = [2, 3]+list(range(-3, -len(op.shape)-1, -1))
        for m in reversed(range(j, i)):
            Ls.insert(0, ncon([self[m].conj(), self[m], Ls[0]], [[1, -2, 3], [1, -1, 2], oplinks]))
        return (lambda n: Ls[n-j]) if ret_all else Ls[0]

    def right_transfer(self, op, i, j, ret_all=True):
        """transfer an operator (..., u, d) on aux indices at i to site(s) j
        Returns a function such that R(j) == op at j. No bounds checking.
        """
        Rs = [op]
        oplinks = list(range(-1, -len(op.shape)+1, -1))+[2, 3]
        for m in range(i+1, j+1):
            Rs.append(ncon([self[m].conj(), self[m], Rs[-1]], [[1, 3, -len(op.shape)+1], [1, 2, -len(op.shape)], oplinks]))
        return (lambda n: Rs[n-i-1]) if ret_all else Rs[0]

    def links(self, op=True):
        """links: op True: return the links for ncon for full contraction of this 
        mps with operator shape of [d,d]*L
                  op False: return links for full contraction of this mps 
        """
        if op:
            L = self.L
            links = [[n, 2*L+n, 2*L+n+1] for n in range(1, L+1)]+[list(range(1, 2*L+1))]+\
                    [[L+n, 3*L+n if n!=1 else 2*L+n , 3*L+n+1 if n!=L else 2*L+n+1] for n in range(1, L+1)]
            return links
        else:
            L = self.L
            links = [[n, L+n, L+n+1] for n in range(1, L+1)]+[[n, (1+int(n!=1))*L+n, (1+int(n!=L))*L+n+1] for n in range(1, L+1)]
            return links

    def E(self, op, site):
        """E: one site expectation value

        :param op: 1 site operator
        :param site: site
        """
        M = self.mixed_canonicalise(site)[site]
        return re(tensordot(op, trace(dot(cT(M),  M), axis1=1, axis2=3), [[0, 1], [0, 1]]))

    def E_L(self, op):
        """E_L: expectation of a full size operator

        :param op: operator
        """
        op = op.reshape([self.d, self.d]*self.L)
        return re(ncon([a.conj() for a in self]+[op]+self.data, self.links()))

    def energy(self, H, fullH=False):
        """energy: if fullH: alias for E_L, else does nn stuff

        :param H: hamiltonian
        """
        if not fullH:
            l, r = self.get_envs()
            e = []
            for m, h in enumerate(H):
                h = h.reshape(2, 2, 2, 2)
                C = ncon([h]+self.data[m:m+2], [[-1, -2, 1, 2], [1, -3, 3], [2, 3, -4]])
                e.append(ncon([c(l(m-1))@self.data[m].conj(), self.data[m+1].conj()@c(r(m+1))]+[C], [[1, 3, 4], [2, 4, 5], [1, 2, 3, 5]]))
            return re(sum(e))
        else:
            return self.E_L(H)

    def dA_dt(self, H, store_energy=False, fullH=False, par=False, store_envs=False):
        """dA_dt: Finds A_dot (from TDVP) [B(n) for n in range(n)], energy. Uses inverses. 
        Indexing is A[0], A[1]...A[L-1]

        :param self: matrix product states @ current time
        :param H: Hamiltonian
        :param energy: store list of 2 site energies as self.e: sum(self.e) = E
        :param par: whether to calculate the update in parallel. 
                    almost never faster
        :param store envs: whether to store the environments as self.l, self.r
        """
        L, d, A = self.L, self.d, self.data
        l, r = self.get_envs(store_envs)
        pr = lambda n: self.left_null_projector(n, l)

        if not fullH:
            def B(n, H=H):  
                e = []
                B = -1j*zl(A[n])
                _, Dn, Dn_1 = A[n].shape

                if d*Dn==Dn_1:
                    # Projector is full of zeros
                    return -1j*B

                R = ncon([pr(n), A[n]], [[-3, -4, 1, -2], [1, -1, -5]])
                Rs = self.left_transfer(R, 0, n) # list of E**k @ R - see left_transfer docs

                for m, h in reversed(list(enumerate(H))):
                    if m > n:
                        # from gauge symmetry
                        continue

                    h = h.reshape(2,2,2,2)
                    Am, Am_1 = self.data[m:m+2]
                    C = ncon([h]+[Am, Am_1], [[-1, -2, 1, 2], [1, -3, 3], [2, 3, -4]]) # HAA
                    K = ncon([c(l(m-1))@Am.conj(), Am_1.conj()]+[C], [[1, 3, 4], [2, 4, -2], [1, 2, 3, -1]]) #AAHAA
                    e.append(trace(K@c(r(m+1))))

                    if m==n:
                        B += -1j*ncon([pr(m)@l(m-1), c(inv(r(m)))@c(Am_1)@c(r(m+1))]+[C], [[-1, -2, 1, 3], [2, -3, 4], [1, 2, 3, 4]])
                    if m==n-1:
                        B += -1j*ncon([c(l(m-1))@c(Am), pr(m+1)]+[C], [[1, 3, 4], [-1, -2, 2, 4], [1, 2, 3, -3]])
                    if m < n-1:
                        B += -1j*ncon([K, Rs(m+2)], [[1, 2], [1, 2, -1, -2, -3]])
                self.e = e
                return B
        else:
            def B(n, H=H):
                H = H.reshape([self.d, self.d]*self.L)
                links = self.links()
                # open up links for projector 
                links[n] = [-1, -2]+links[n][:2]
                if n == L-1:
                    links[-1] = links[-1][:2]+[-3]
                else:
                    links[n+1] = [links[n+1][0], -3, links[n+1][2]]
                return -1j*ncon([pr(m) if m==n else c(inv(r(n)))@a.conj() if m==n+1 else a.conj() for m, a in enumerate(A)]+[H]+A, links)

        if par:
            with Pool(2) as p:
                return fMPS(list(p.map(B, range(L))))
        else:
            return fMPS([B(n) for n in range(L)])
    
    def ddA_dt(self, v, H, fullH=False):
        """d(dA)_dt: find ddA_dt - in 2nd tangent space: 
           for time evolution of v in tangent space

        :param H: hamiltonian
        :param fullH: is the hamiltonian full
        """
        L, d, A = self.L, self.d, self.data
        dA = self.import_tangent_vector(v)
        dA_dt = self.dA_dt(H, store_energy=True, fullH=fullH, store_envs=True)
        l, r, e = self.l, self.r, self.e
        # down are the tensors acting on c(Aj), up act on Aj
        down, up = self.jac(H, fullH)

        ddA = [sum([td(down(i, j), c(dA[j]), [[3, 4, 5], [0, 1, 2]]) + 
                    td(up(i, j),     dA[j],  [[3, 4, 5], [0, 1, 2]]) for j in range(L)], axis=0)
               for i in range(L)]

        return self.extract_tangent_vector(ddA)

    def jac(self, H, matrix=False, real=False, fullH=False, testing=False):
        """jac: calculate the jacobian of the current mps
        """
        L, d, A = self.L, self.d, self.data
        dA_dt = self.dA_dt(H, fullH=fullH, store_envs=True)
        l, r = self.l, self.r

        # Get tensors
        ## unitary rotations: -<d_iψ|(d_t |d_kψ> +iH|d_kψ>) (dA_k)
        #-<d_iψ|d_kd_jψ> dA_j/dt (dA_k) (range(k+1, L))
        def Γ1(i, k): return sum([td(c(self.christoffel(k, j, i, envs=(l, r))), dA_dt[j], [[3, 4, 5], [0, 1, 2]]) for j in range(max(k, i), L)])
        #-i<d_iψ|H|d_kψ> (dA_k)
        def F1(i, k): return  -1j*self.F1(i, k, H, envs=(l, r), fullH=fullH)

        ## non unitary (from projection): -<d_id_kψ|(d_t |ψ> +iH|ψ>) (dA_k*) (should be zero for no projection)
        #-<d_id_kψ|d_jψ> dA_j/dt (dA_k*)
        def Γ2(i, k): return td(self.christoffel(i, k, min(i, k), envs=(l, r)), dA_dt[min(i, k)], [[6, 7, 8], [0, 1, 2]])
        #-i<d_id_k ψ|H|ψ> (dA_k*)
        def F2(i, k): return -1j*self.F2(i, k, H, envs=(l, r), fullH=fullH)

        print('\n', im(F2(1, 2)).reshape(-1), im(Γ2(1, 2)).reshape(-1), sep='\n')
        raise Exception

        def F1t(i, j): return F1(i, j) + Γ1(i, j)
        def F2t(i, j): return F2(i, j) + Γ2(i, j) #F2, Γ2 act on dA*j

        if matrix == False:
            return F1t, F2t 

        vL, sh = self.tangent_space_dims(l, True)
        shapes = list(cs([prod([a, b]) for (a, b) in sh if a!=0 and a!=0]))
        DD = shapes[-1]

        def index(i, j):
            slices = [slice(a[0], a[1], 1) for a in [([0]+shapes)[i:i+2] for i in range(len(shapes))]]
            return (slices[i], slices[j])

        nulls = len([1 for (a, b) in sh if a==0 or b==0])

        def ungauge_i(tens, i, conj=False): 
            vL_ = vL[i] if not conj else c(vL[i])
            k = len(tens.shape[3:])
            links = [1, 2, -2]+list(range(-3, -3-k, -1))
            return ncon([ch(l(i-1))@vL_, 
                        ncon([tens, ch(r(i))], [[-1, -2, 1, -4, -5, -6], [1, -3]])], 
                        [[1, 2, -1], links])

        def ungauge_j(tens, i, conj=False): 
            vL_ = vL[i] if not conj else c(vL[i])
            k = len(tens.shape[:-3])
            links = list(range(-1, -k-1, -1))+[1, 2, -k-2]
            return ncon([ch(l(i-1))@vL_, tens@ch(r(i))], 
                    [[1, 2, -k-1], links])

        def ungauge(tens, i, j, conj=(True, False)):
            return ungauge_j(ungauge_i(tens, i, conj[0]), j, conj[1])

        J1 = -1j*zeros((DD, DD))
        J2 = -1j*zeros((DD, DD))

        for i_ in range(len(shapes)):
            for j_ in range(len(shapes)):
                i, j = i_+nulls, j_+nulls
                J1_ij = ungauge(F1t(i, j), i, j, (True, False))
                J2_ij = ungauge(F2t(i, j), i, j, (True, True ))
                J1[index(i_, j_)] = J1_ij.reshape(prod(J1_ij.shape[:2]), -1)
                J2[index(i_, j_)] = J2_ij.reshape(prod(J2_ij.shape[:2]), -1)

        if not real:
            return J1, J2
        else:
            J = kron(Sz, re(J2))+kron(eye(2), re(J1)) + kron(Sx, im(J2)) + kron(-1j*Sy, im(J1))
            J[abs(J)<1e-15]=0
            return J

    def F1(self, i_, j_, H, envs=None, fullH=False, testing=False):
            '''<d_iψ|H|d_jψ>'''
            L, d, A = self.L, self.d, self.data
            l, r = self.get_envs() if envs is None else envs
            pr = lambda n: self.left_null_projector(n, l)
            if not fullH:
                i, j = (j_, i_) if j_<i_ else (i_, j_)
                G = 1j*zeros((*A[i].shape, *A[j].shape))
                _, Din_1, Di = self[i].shape
                d, Djn_1, Dj = self[j].shape 

                if not (d*Djn_1==Dj or d*Din_1==Di):
                    Ru = ncon([pr(j), c(A[j])], [[1, -2, -3, -4], [1, -1, -5]])
                    Rus = self.left_transfer(Ru, 0, j)

                    Rd = ncon([pr(i), A[i]], [[-3, -4, 1, -2], [1, -1, -5]])
                    Rds = self.left_transfer(Rd, 0, i)

                    Rb = ncon([pr(j), pr(j), inv(r(j))], [[-3, -4, 1, -1], [1, -2, -6, -7], [-5, -8]])
                    Rbs = self.left_transfer(Rb, 0, j)

                    Lb = ncon([l(i-1)]+[pr(i), pr(i), inv(r(i)), inv(r(i))], [[2, 3], [-1, -2, 1, 2], [1, 3, -4, -5], [-3, -7], [-6, -8]])
                    Lbs = self.right_transfer(Lb, i, L-1)

                    for m, h in reversed(list(enumerate(H))):
                        if m > i:
                            # from gauge symmetry
                            if not i==j:
                                continue
                            else:
                                #AAHAA
                                h = h.reshape(2,2,2,2)
                                Am, Am_1 = self.data[m:m+2]
                                C = ncon([h]+[Am, Am_1], [[-1, -2, 1, 2], [1, -3, 3], [2, 3, -4]]) # HAA
                                Kr = ncon([c(Am), c(Am_1)@r(m+1)]+[C], 
                                         [[1, -2, 4], [2, 4, 3], [1, 2, -1, 3]])
                                G+=tr(Lbs(m)@Kr, 0, -1, -2)

                        h = h.reshape(2,2,2,2)
                        Am, Am_1 = self.data[m:m+2]

                        if m==i:
                            if j==i:
                                # BAHBA
                                G += ncon([l(m-1)]+[pr(m), inv(r(m))@Am_1]+[h]+[pr(m), inv(r(m))@c(Am_1)]+[r(m+1)], 
                                          [[5, 6], [1, 5, -4, -5], [2, -6, 7], [1, 2, 3, 4], [-1, -2, 3, 6], [4, -3, 8], [7, 8]])

                            elif j==i+1:
                                # ABHBA
                                G += ncon([l(m-1)]+[Am, pr(m+1)]+[h]+[pr(m), r(m)@c(Am_1)],
                                         [[5, 6], [1, 6, 7], [2, 7, -4, -5], [1, 2, 3, 4], [-1, -2, 3, 5], [4, -3, -6]])
                            else:
                                # AAHBA
                                O = ncon([l(m-1)@Am, Am_1]+[h]+[pr(m), inv(r(m))@c(Am_1)], 
                                         [[3, 6, 5], [4, 5, -4], [1, 2, 3, 4], [-1, -2, 1, 6], [2, -3, -5]]) #(A)ud
                                G += tensordot(O, Rus(m+2), [[-1, -2], [0, 1]])
                        elif m==i-1:
                            if j==i:
                                # ABHAB
                                x = ncon([l(m-1)@Am, pr(m+1)]+[h]+[c(Am), pr(m+1)]+[inv(r(m+1))],
                                           [[3, 5, 6], [4, 6, -4, -5], [1, 2, 3, 4], [1, 5, 7], [-1, -2, 2, 7], [-3, -6]]) #AA
                                G += x
                            else:
                                # AAHAB
                                Q = ncon([l(m-1)@Am, Am_1]+[h]+[c(Am), pr(m+1)], 
                                         [[3, 6, 5], [4, 5, -3], [1, 2, 3, 4], [1, 6, 7], [-1, -2, 2, 7]]) #(A)
                                G += tensordot(Q, Rus(m+2), [-1, 0])
                        elif m<i:
                            #AAHAA
                            C = ncon([h]+[Am, Am_1], [[-1, -2, 1, 2], [1, -3, 3], [2, 3, -4]]) # HAA
                            K = ncon([l(m-1)@c(Am), c(Am_1)]+[C], 
                                     [[1, 3, 4], [2, 4, -2], [1, 2, 3, -1]])
                            if i==j:
                                x = tensordot(K, Rbs(m+2), [[0, 1], [0, 1]])
                                G += x
                            else:
                                G += tensordot(K, tensordot(Rds(m+2)@inv(r(i)), Rus(i+1), [-1, 0]), 
                                               [[0, 1], [0, 1]])
                        if testing:
                            #AAHAA
                            K = ncon([c(l(m-1))@Am.conj(), Am_1.conj()]+[C], 
                                     [[1, 3, 4], [2, 4, -2], [1, 2, 3, -1]])
                            # BAHBA
                            M = ncon([l(m-1)]+[pr(m), inv(r(m))@Am_1]+[h]+[pr(m), inv(r(m))@c(Am_1)]+[r(m+1)], 
                                      [[5, 6], [1, 5, -4, -5], [2, -6, 7], [1, 2, 3, 4], [-1, -2, 3, 6], [4, -3, 8], [7, 8]])
                            # ABHBA
                            N = ncon([l(m-1)]+[Am, pr(m+1)]+[h]+[pr(m), r(m)@c(Am_1)],
                                     [[5, 6], [1, 6, 7], [2, 7, -4, -5], [1, 2, 3, 4], [-1, -2, 3, 5], [4, -3, -6]])
                            # AAHBA
                            O = ncon([l(m-1)@Am, Am_1]+[h]+[pr(m), inv(r(m))@c(Am_1)], 
                                     [[3, 6, 5], [4, 5, -4], [1, 2, 3, 4], [-1, -2, 1, 6], [2, -3, -5]]) #(A)ud
                            # ABHAB
                            P = ncon([l(m-1)@Am, pr(m+1)]+[h]+[c(Am), pr(m+1)]+[r(m+1)],
                                     [[3, 5, 6], [4, 6, -4, -5], [1, 2, 3, 4], [1, 5, 7], [-1, -2, 2, 7], [-3, -6]]) #AA
                            # AAHAB
                            Q = ncon([l(m-1)@Am, Am_1]+[h]+[c(Am), pr(m+1)], 
                                     [[3, 6, 5], [4, 5, -3], [1, 2, 3, 4], [1, 6, 7], [-1, -2, 2, 7]]) #(A)
                            assert allclose(norm(td(M, l(m-1)@c(Am), [[0, 1, 2], [0, 1, 2]])), 0)
                            assert allclose(norm(td(M, l(m-1)@Am, [[3, 4, 5], [0, 1, 2]])), 0)
                            assert allclose(norm(td(N, l(m-1)@c(Am), [[0, 1, 2], [0, 1, 2]])), 0)
                            assert allclose(norm(td(N, l(m)@Am_1, [[3, 4, 5], [0, 1, 2]])), 0)
                            assert allclose(norm(td(O, l(m-1)@c(Am), [[0, 1, 2], [0, 1, 2]])), 0)
                            assert allclose(norm(td(P, l(m)@c(Am_1), [[0, 1, 2], [0, 1, 2]])), 0)
                            assert allclose(norm(td(P, l(m)@Am_1, [[3, 4, 5], [0, 1, 2]])), 0)
                            assert allclose(norm(td(Q, l(m)@c(Am_1), [[0, 1, 2], [0, 1, 2]])), 0)
            elif fullH:
                i, j = (i_, j_)
                H = H.reshape([self.d, self.d]*self.L)
                links = self.links(True)
                bottom = [pr(m) if m==i else c(inv(r(m-1)))@a.conj() if m==i+1 else a.conj() for m, a in enumerate(A)]
                top = [c(pr(m)) if m==j else c(inv(r(m-1)))@a.conj() if m==j+1 else a.conj() for m, a in enumerate(A)]
                if i!=L-1 and j!=L-1:
                    links[i] = links[i][:2] + [-1, -2]
                    links[i+1][1] = -3
                    links[L+1+j] = links[L+1+j][:2] + [-4, -5]
                    links[L+1+j+1][1] = -6
                elif i!=L-1:
                    links[i] = links[i][:2] + [-1, -2]
                    links[i+1][1] = -3
                    links[L+1+j] = links[L+1+j][:2] + [-4, -5]
                    links[L-1][-1] = -6
                elif j!=L-1:
                    links[i] = links[i][:2] + [-1, -2]
                    links[2*L][-1] = -3
                    links[L+1+j] = links[L+1+j][:2] + [-4, -5]
                    links[L+1+j+1][1] = -6
                else:
                    links[i] = links[i][:2] + [-1, -2]
                    links[L+1+j] = links[L+1+j][:2] + [-4, -5]
                G = ncon(bottom+[H]+top, links)
                if i==L-1 and j==L-1:
                    G = ed(ed(G, -1), 2)
                return G

            if j_<i_:
                return c(tra(G, [3, 4, 5, 0, 1, 2]))
            else:
                return G

    def F2(self, i_, j_, H, envs=None, fullH=False):
        '''<d_id_j ψ|H|ψ>'''
        L, d, A = self.L, self.d, self.data
        l, r = self.get_envs() if envs is None else envs
        pr = lambda n: self.left_null_projector(n, l)

        i, j = (j_, i_) if j_<i_ else (i_, j_)
        if i==j:
            G = 1j*zeros((*A[i].shape, *A[j].shape))
        elif not fullH:
            G = 1j*zeros((*A[i].shape, *A[j].shape))
            _, Din_1, Di = self[i].shape
            if not d*Din_1==Di:
                Rj = ncon([pr(j), A[j]], [[-3, -4, 1, -2], [1, -1, -5]])
                Rjs = self.left_transfer(Rj, i, j)

                Ri = ncon([pr(i), A[i]], [[-3, -4, 1, -2], [1, -1, -5]])
                Ris = self.left_transfer(Ri, 0, i)

                for m, h in reversed(list(enumerate(H))):
                    if m > i:
                        # from gauge symmetry
                        continue
                    h = h.reshape(2,2,2,2)
                    Am, Am_1 = self.data[m:m+2]
                    C = ncon([h]+[Am, Am_1], [[-1, -2, 1, 2], [1, -3, 3], [2, 3, -4]]) # HAA
                    K = ncon([c(l(m-1))@Am.conj(), Am_1.conj()]+[C], [[1, 3, 4], [2, 4, -2], [1, 2, 3, -1]]) #AAHAA
                    e = tr(K@r(m+1))

                    if m==i:
                        if j==i+1:
                            G += ncon([l(m-1)@C, pr(i), dot(pr(j), inv(r(i)))],   [[1, 2, 3, -6], [-1, -2, 1, 3], [-4, -5, 2, -3]])
                        else:
                            L =  ncon([l(m-1)@C, pr(i), inv(r(i))@c(Am_1)], [[1, 2, 3, -4], [-1, -2, 1, 3], [2, -3, -5]]) # ud
                            G1 = deepcopy(G)
                            G += ncon([L, Rjs(m+2)], [[-1, -2, -3, 1, 2], [1, 2, -4, -5, -6]])
                    elif m==i-1:
                        L = ncon([l(m-1)@C, c(Am), pr(i)], [[1, 2, 3, -3], [1, 3, 4], [-1, -2, 2, 4]])
                        G1 = deepcopy(G)
                        G += ncon([L, ncon([Rjs(m+2), inv(r(i))], [[-1, 2, -3, -4, -5], [2, -2]])], [[-1, -2, 1], [1, -3, -4, -5, -6]])
                    else:
                        L = ncon([K, Ris(m+2)], [[1, 2], [1, 2, -1, -2, -3]])
                        G1 = deepcopy(G)
                        G += ncon([ncon([L@inv(r(i)), Rjs(i+1)], [[-1, -2, 1], [1, -3, -4, -5, -6]]), 
                                   r(i)], 
                                   [[-1, -2, 1, -4, -5, -6], [1, -3]])
        elif fullH:
            H = H.reshape([self.d, self.d]*self.L)
            if i==j:
                G = zeros((*A[i].shape, *A[j].shape))
            else:
                links = self.links(True)
                if i==j-1:
                    bottom = [pr(i) if m==i else ncon([c(r(j-1)), pr(j)], [[-2, 1], [-1, 1, -3, -4]]) if m==j else a.conj() for m, a in enumerate(A)]
                else:
                    bottom = [pr(m) if (m==i or m==j) else a.conj() for m, a in enumerate(A)]
                    bottom = [c(inv(r(m-1)))@a.conj() if m==i+1 or m==j+1 else a for m, a in enumerate(bottom)]
                top = A
                links[i] = links[i][:2]+[-1, -2] 
                links[i+1][1] = -3
                links[j] = links[j][:2]+[-4, -5] 
                if j == L-1:
                    links[-1][-1] = -6
                else:
                    links[j+1][1] = -6
                G = ncon(bottom+[H]+top, links)

        if j_<i_:
            return tra(G, [3, 4, 5, 0, 1, 2])
        else:
            return G

    def christoffel(self, i, j, k, envs=None, closed=(None, None, None)):
        """christoffel: return the christoffel symbol in basis c(A_i), c(A_j), A_k. 
           Close indices i, j, k, with elements of closed tuple: i.e. (B_i, B_j, B_k).
           Will leave any indices marked none open :-<d_id_jψ|d_kψ>"""
        L, d, A = self.L, self.d, self.data
        l, r = self.get_envs() if envs is None else envs
        pr = lambda n: self.left_null_projector(n, l)

        def Γ(i_, j_, k):
                """Γ: Christoffel symbol: does take advantage of gauge"""
                #j always greater than i (Γ symmetric in i, j)
                i, j = (j_, i_) if j_<i_ else (i_, j_)

                _, Din_1, Di = self[i].shape

                if j==i or i!=k or (d*Din_1==Di):
                    G = 1j*zeros((*A[i].shape, *A[j].shape, *A[k].shape))
                else:
                    R = ncon([pr(j), A[j]], [[-3, -4, 1, -2], [1, -1, -5]])
                    Rs = self.left_transfer(R, i, j)
                    G = ncon([pr(i), Rs(i+1), inv(r(i)), inv(r(i))], [[-1, -2, -7, -8], [1, 2, -4, -5, -6], [1, -9], [2, -3]])
                if j_<i_:
                    return -tra(G, [3, 4, 5, 0, 1, 2, 6, 7, 8])
                else:
                    return -G

        if any([c is not None for c in closed]):
            c_ind = [m for m, A in enumerate(closed) if A is not None]
            o_ind = [m for m, A in enumerate(closed) if A is None]
            links = [reduce(lambda x, y: x+y,
                           [list(array([-1, -2, -3])-3*(o_ind.index(n))) if n in o_ind else 
                           [c_ind.index(n), c_ind.index(n)+3, c_ind.index(n)+6] for n in range(3)])]+\
                    [[n, n+3, n+6] for n in range(len(c_ind))]
            Γ_c = ncon([Γ(i, j, k)]+[closed[j] for j in c_ind], links)
        else:
            Γ_c = Γ(i, j, k)

        return -Γ_c

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
            L_ = cT(self[n])@ch(l(n-1))
            L = sw(L_, 0, 1).reshape(-1, self.d*L_.shape[-1])
            vL = null(L).reshape((self.d, int(L.shape[1]/self.d), -1))
        pr = ncon([inv(ch(l(n-1))), vL, c(vL), c(inv(ch(l(n-1))))], [[-2, 2], [-1, 2, 1], [-3, 4, 1], [-4, 4]])
        if get_vL:
            return pr, vL
        return pr

    def tangent_state(self, x, n, envs=None, vL=None):
        l , r = self.get_envs() if envs is None else envs
        _, vL = self.left_null_projector(n, l, get_vL=True) if vL is None else 1, vL
        return fMPS([inv(ch(l(n-1)))@vL@x if m==n else inv(ch(r(n)))@A if m==n+1 else A for m, A in enumerate(self.data)])

    def tangent_space_dims(self, l=None, get_vLs=False):
        l, _ = self.get_envs() if l is None else (l, None)
        vLs = [self.left_null_projector(n, l=l, get_vL=True)[1] for n in range(self.L)]
        shapes = [(vL.shape[-1], self.data[n+1].shape[1] if n+1<self.L else 1)
                  for vL, n in zip(vLs, range(self.L))]
        if get_vLs:
            return vLs, shapes
        else:
            return shapes

    def tangent_space_basis(self, full=False):
        """ return a tangent space basis
        """
        Qs = [eye(d1*d2)+1j*0 for d1, d2 in self.tangent_space_dims() if d1*d2 != 0]
        def direct_sum(basis1, basis2):
            d1 = len(basis1[0])
            d2 = len(basis2[0])
            return [ct([b1, zeros(d2)]) for b1 in basis1]+\
                   [ct([zeros(d1), b2]) for b2 in basis2]
        return array(reduce(direct_sum, Qs))

    def extract_tangent_vector(self, dA):
        """extract_tangent_vector from dA: 
           assume mps represents element of tangent space i.e.
           [B1...BN] <=> A1...Bn...AN + A1...Bn+1...AN+...
           return x1++x2++x3...++xN (concatenate + flatten)"""
        xs = []
        for n, shape in enumerate(self.tangent_space_dims()):
            if prod(shape) == 0:
                continue
            _, vL = self.left_null_projector(n, get_vL=True, store_envs=True)
            l, r = self.l, self.r
            x = ncon([c(vL), ch(l(n-1))@dA[n]@ch(r(n))], [[1, 2, -1], [1, 2, -2]])
            xs.append(x.reshape(-1))
        return ct(xs)

    def import_tangent_vector(self, v, xs=False):
        l, r = self.get_envs()
        vLs, shapes = self.tangent_space_dims(l, get_vLs=True)
        vLs = [vL for vL in vLs if prod(vL.shape)!=0]
        S = [shape for shape in shapes if prod(shape)!=0]
        nulls = len([shape for shape in shapes if prod(shape)==0])
        vs = chop(v, cs([prod(s) for s in S]))
        xs = [x.reshape(*shape) for x, shape in zip(vs, S)]
        l_, r_ = lambda n: l(n+nulls), lambda n: r(n+nulls)
        Bs = [zl(A) for A in self.data[:nulls]] + \
             [inv(ch(l_(n-1)))@vL@x@inv(ch(r_(n))) for n, (vL, x) in enumerate(zip(vLs, xs))]
        return fMPS(Bs)
    
    def serialize(self, real=False):
        """serialize: return a vector with mps data in it"""
        vec = concatenate([a.reshape(-1) for a in self])
        if real:
            return ct([vec.real, vec.imag])
        else:
            return vec

    def deserialize(self, vec, L, d, D, real=False):
        """deserialize: take a vector with mps data (from serialize), 
                        make MPS

        :param vec: vector to deserialize
        :param L: length of mps to make
        :param d: local hilbert space dimension
        :param D: bond dimension
        """
        if real:
            vec = reduce(lambda x, y: x+1j*y, chop(vec, 2))
        self.L, self.d, self.D = L, d, D
        structure = [(d, *x) for x in self.create_structure(L, d, D)]
        self.data = []
        for shape in structure:
            self.data.append(vec[:prod(shape)].reshape(shape))
            _, vec = chop(vec, [prod(shape)])
        return self

    def store(self, filename):
        """store in file 
        :param filename: filename to store in 
        """
        save(filename, ct([array([self.L, self.d, self.D]), self.serialize()]))

    def load(self, filename):
        """load from file

        :param filename: filename to load from
        """
        params, arr = chop(load(filename), [3])
        self.L, self.d, self.D = map(lambda x: int(re(x)), params)
        return self.deserialize(arr, self.L, self.d, self.D)
         
class vfMPS(object):
    """vidal finite MPS
    lists of tuples (\Gamma, \Lambda) of numpy arrays"""
    def __init__(self,  data=None, d=None):
        """__init__

        :param data: matrices in form [(\Gamma, \Lambda)]
        :param d: local state space dimension
        """
        if data is not None and d is not None:
            self.L = len(data)
            self.d = d
            self.D = max([datum[0][0].shape for datum in data])

    def from_fMPS(self, fMPS):
        """from_fMPS: convert a normal form fMPS to vidal form

        :param fMPS: fMPS to convert
        """
        self.d = fMPS.d
        fMPS.right_canonicalise()
        data = []
        for L, A in zip(fMPS.Ls, fMPS.data):
            G = swapaxes(dot(inv(L), A), 0, 1)
            data.append((L, G))
        self.data = data
        return self

    def to_fMPS(self):
        """to_fMPS: return from vidal form to normal form"""
        return fMPS([swapaxes(dot(*x), 0, 1) for x in self.data], self.d)

class TestfMPS(unittest.TestCase):
    """TestfMPS"""

    def setUp(self):
        """setUp"""
        self.N = N = 5  # Number of MPSs to test
        #  min and max params for randint
        L_min, L_max = 6, 8 
        d_min, d_max = 2, 4
        D_min, D_max = 5, 10
        ut_min, ut_max = 3, 7
        # N random MPSs
        self.rand_cases = [fMPS().random(randint(L_min, L_max),
                                         randint(d_min, D_min),
                                         randint(D_min, D_max))
                           for _ in range(N)]
        # N random MPSs, right canonicalised and truncated to random D
        self.right_cases = [fMPS().random(
                            randint(L_min, L_max),
                            randint(d_min, D_min),
                            randint(D_min, D_max)).right_canonicalise(
                            randint(D_min, D_max))
                            for _ in range(N)]
        # N random MPSs, left canonicalised and truncated to random D
        self.left_cases = [fMPS().random(
                            randint(L_min, L_max),
                            randint(d_min, D_min),
                            randint(D_min, D_max)).left_canonicalise(
                            randint(D_min, D_max))
                           for _ in range(N)]
        self.mixed_cases = [fMPS().random(
                            randint(L_min, L_max),
                            randint(d_min, D_min),
                            randint(D_min, D_max)).mixed_canonicalise(
                            randint(ut_min, ut_max),
                            randint(D_min, D_max))
                            for _ in range(N)]

        # finite fixtures
        self.tens_0_2 = load('mat2x2.npy')
        self.tens_0_3 = load('mat3x3.npy')
        self.tens_0_4 = load('mat4x4.npy')
        self.tens_0_5 = load('mat5x5.npy')
        self.tens_0_6 = load('mat6x6.npy')
        self.tens_0_7 = load('mat7x7.npy')

        self.mps_0_2 = fMPS().left_from_state(self.tens_0_2)
        self.psi_0_2 = self.mps_0_2.recombine().reshape(-1)

        self.mps_0_3 = fMPS().left_from_state(self.tens_0_3)
        self.psi_0_3 = self.mps_0_3.recombine().reshape(-1)

        self.mps_0_4 = fMPS().left_from_state(self.tens_0_4)
        self.psi_0_4 = self.mps_0_4.recombine().reshape(-1)

        self.mps_0_5 = fMPS().left_from_state(self.tens_0_5)
        self.psi_0_5 = self.mps_0_5.recombine().reshape(-1)

        self.mps_0_6 = fMPS().left_from_state(self.tens_0_6)
        self.psi_0_6 = self.mps_0_6.recombine().reshape(-1)

        self.mps_0_7 = fMPS().left_from_state(self.tens_0_7)
        self.psi_0_7 = self.mps_0_7.recombine().reshape(-1)

    def test_energy_2(self):
        """test_energy_2: 2 spins: energy of random hamiltonian matches full H"""
        H2 = randn(4, 4)+1j*randn(4, 4)
        H2 = (H2+H2.conj().T)/2
        e_ed = self.psi_0_2.conj()@H2@self.psi_0_2
        e_mps = self.mps_0_2.energy(H2, fullH=True)
        self.assertTrue(isclose(e_ed, e_mps))

    def test_energy_3(self):
        """test_energy_3: 3 spins: energy of random hamiltonian matches full H"""
        H3 = randn(8, 8)+1j*randn(8, 8)
        H3 = (H3+H3.conj().T)/2
        e_ed = self.psi_0_3.conj()@H3@self.psi_0_3
        e_mps = self.mps_0_3.energy(H3, fullH=True)
        self.assertTrue(isclose(e_ed, e_mps))

    def test_energy_4(self):
        """test_energy_4: 4 spins: energy of random hamiltonian matches full H"""
        H4 = randn(16, 16)+1j*randn(16, 16)
        H4 = (H4+H4.conj().T)/2
        e_ed = self.psi_0_4.conj()@H4@self.psi_0_4
        e_mps = self.mps_0_4.energy(H4, fullH=True)
        self.assertTrue(isclose(e_ed, e_mps))

    def test_left_from_state(self):
        for _ in range(self.N):
            d = randint(2, 4)
            L = randint(4, 6)
            full = randn(*[d]*L) + 1j*randn(*[d]*L)
            full /= norm(full)
            case = fMPS().left_from_state(full)
            self.assertTrue(allclose(case.recombine(), full))

    def test_right_from_state(self):
        for _ in range(self.N):
            d = randint(2, 4)
            L = randint(4, 6)
            full = randn(*[d]*L) + 1j*randn(*[d]*L)
            full /= norm(full)
            case = fMPS().right_from_state(full)
            self.assertTrue(allclose(case.recombine(), -full) or
                            allclose(case.recombine(), full))

    def test_right_canonicalise(self):
        """test_right_canonicalise"""
        for case in self.right_cases:
            if not case.ok:
                print('\n')
                print('d: ', case.d, 'L: ', case.L, 'D: ', case.D)
                print('irc: ',
                      is_right_canonical(case.data, error=True),
                      case.is_right_canonical)
                print('irec: ', case.is_right_env_canonical)
                print('ifr: ', case.is_full_rank)
                print('tr1: ', case.has_trace_1)
                print('norm: ', case.norm())
                print('\n')
            self.assertTrue(case.ok)

    def test_left_canonicalise(self):
        """test_left_canonicalise"""
        for case in self.left_cases:
            if not case.ok:
                print('\n')
                print('d: ', case.d, 'L: ', case.L, 'D: ', case.D)
                print('ilc: ',
                      is_left_canonical(case.data, error=True),
                      case.is_left_canonical)
                print('ilec: ', case.is_left_env_canonical)
                print('fr: ', case.is_full_rank)
                print('tr1: ', case.has_trace_1)
                print('norm: ', case.norm())
                print('\n')
            self.assertTrue(case.ok)

    def test_left_canonicalise_norm(self):
        for case in self.rand_cases:
            I = []
            for _ in range(10):
                case.left_canonicalise()
                I.append(case.E(identity(case.d), 1))
            self.assertTrue(allclose(I, 1))

    def test_left_canonicalise_expectation_values(self):
        """EVs of spin operators on 3 random sites don't change after canonicalising 10 times"""
        for case in self.rand_cases:
            if case.d == 2:
                site1, site2, site3 = randint(0, case.L-1), randint(0, case.L-1), randint(0, case.L-1)
                S = [(sigmax().full(), site1), (sigmay().full(), site2), (sigmaz().full(), site3)]
                I0 = [case.E(*opsite) for opsite in S]
                I = []
                for _ in range(10):
                    case.left_canonicalise()
                    I.append([case.E(*opsite) for opsite in S])
                for In in I:
                    self.assertTrue(allclose(I0, In))

    def test_right_canonicalise_expectation_values(self):
        """EVs of spin operators on 3 random sites don't change after canonicalising 10 times"""
        for case in self.rand_cases:
            if case.d == 2:
                site1, site2, site3 = randint(0, case.L-1), randint(0, case.L-1), randint(0, case.L-1)
                S = [(sigmax().full(), site1), (sigmay().full(), site2), (sigmaz().full(), site3)]
                I0 = [case.E(*opsite) for opsite in S]
                I = []
                for _ in range(10):
                    case.right_canonicalise()
                    I.append([case.E(*opsite) for opsite in S])
                for In in I:
                    self.assertTrue(allclose(I0, In))

    def test_right_canonicalise_norm(self):
        """Norm doesn't change after canonicalising ten times"""
        for case in self.rand_cases:
            I = []
            for _ in range(10):
                case.right_canonicalise()
                I.append(case.E(identity(case.d), 1))
            self.assertTrue(allclose(I, 1))

    def test_mixed_canonicalise(self):
        """test_mixed_canonicalise"""
        for case in self.mixed_cases:
            if not case.ok:
                print('\n')
                print('d: ', case.d, 'L: ', case.L, 'D: ', case.D)
                print('irc: ', is_right_canonical(case.data[case.oc+1:],
                                                  error=True))
                print('ilc: ', is_left_canonical(case.data[:case.oc],
                                                 error=True))
                print('irec: ', case.is_right_env_canonical)
                print('ifr: ', case.is_full_rank)
                print('tr1: ', case.has_trace_1)
                print('norm: ', case.norm())
                print('\n')
            self.assertTrue(case.ok)

    def test_self_D_is_correct(self):
        for case in self.left_cases + self.right_cases:
            self.assertTrue(case.D >= max([max(x[0].shape) for x in case.data]))

    def test_left_norms(self):
        """test_left_norms"""
        for case in self.left_cases:
            if not isclose(case.norm(), 1):
                case.update_properties()
                print('left')
                print(case.norm())
                print('L: ', case.L)
                print('D: ', case.D)
                print('d: ', case.d)
                print(case.structure())
                print(case.is_left_canonical)
                try:
                    print('oc: ', case.oc)
                except:
                    print('no oc')
            self.assertTrue(isclose(case.norm(), 1))

    def test_right_norms(self):
        """test_right_norms"""
        for case in self.right_cases:
            if not isclose(case.norm(), 1):
                print('right')
                print(case.norm())
                print('L: ', case.L)
                print('D: ', case.D)
                print('d: ', case.d)
                print(case.structure())
                try:
                    print('oc: ', case.oc)
                except:
                    print('no oc')
            self.assertTrue(isclose(case.norm(), 1))

    def test_serialize_deserialize(self):
        mps = self.mps_0_4
        mps_ = fMPS().deserialize(mps.serialize(), mps.L, mps.d, mps.D)
        self.assertTrue(mps==mps_)

    def test_store_load(self):
        mps = self.mps_0_2
        mps.store('x')
        mps_ = fMPS().load('x.npy')
        self.assertTrue(mps==mps_)

        mps = self.mps_0_3
        mps.store('x')
        mps_ = fMPS().load('x.npy')
        self.assertTrue(mps==mps_)

        mps = self.mps_0_4
        mps.store('x')
        mps_ = fMPS().load('x.npy')
        self.assertTrue(mps==mps_)

    def test_serialize_deserialize_real(self):
        mps = self.mps_0_4
        mps_ = fMPS().deserialize(mps.serialize(True), mps.L, mps.d, mps.D, True)
        self.assertTrue(mps==mps_)

    def test_import_extract_tangent_vector(self):
        Sx12, Sy12, Sz12 = N_body_spins(0.5, 1, 2)
        Sx22, Sy22, Sz22 = N_body_spins(0.5, 2, 2)

        mps = self.mps_0_4
        H = [Sz12@Sz22+Sx12, Sz12@Sz22+Sx12+Sx22, Sz12@Sz22+Sx22]
        dA = mps.dA_dt(H)
        dA_ = mps.import_tangent_vector(mps.extract_tangent_vector(dA))
        self.assertTrue(dA==dA_)

    def test_local_hamiltonians_2(self):
        Sx12, Sy12, Sz12 = N_body_spins(0.5, 1, 2)
        Sx22, Sy22, Sz22 = N_body_spins(0.5, 2, 2)

        mps = self.mps_0_2
        listH = [Sz12@Sz22+Sx12+Sx22]
        fullH = listH[0]
        self.assertTrue(mps.dA_dt(listH, fullH=False)==mps.dA_dt(fullH, fullH=True))

    def test_local_hamiltonians_3(self):
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 3)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 3)
        Sx3, Sy3, Sz3 = N_body_spins(0.5, 3, 3)

        Sx12, Sy12, Sz12 = N_body_spins(0.5, 1, 2)
        Sx22, Sy22, Sz22 = N_body_spins(0.5, 2, 2)

        mps = self.mps_0_3
        listH = [Sz12@Sz22+Sx12, Sz12@Sz22+Sx12+Sx22]
        fullH = sum([n_body(a, i, len(listH), d=2) for i, a in enumerate(listH)], axis=0)
        self.assertTrue(mps.dA_dt(listH, fullH=False)==mps.dA_dt(fullH, fullH=True))

    def test_local_hamiltonians_4(self):
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 4)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 4)
        Sx3, Sy3, Sz3 = N_body_spins(0.5, 3, 4)
        Sx4, Sy4, Sz4 = N_body_spins(0.5, 4, 4)

        Sx12, Sy12, Sz12 = N_body_spins(0.5, 1, 2)
        Sx22, Sy22, Sz22 = N_body_spins(0.5, 2, 2)

        mps = self.mps_0_4
        listH = [Sz12@Sz22+Sx12, Sz12@Sz22+Sx12+Sx22, Sz12@Sz22+Sx22]
        fullH = sum([n_body(a, i, len(listH), d=2) for i, a in enumerate(listH)], axis=0)
        self.assertTrue(mps.dA_dt(listH, fullH=False)==mps.dA_dt(fullH, fullH=True))

    def test_local_hamiltonians_5(self):
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 5)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 5)
        Sx3, Sy3, Sz3 = N_body_spins(0.5, 3, 5)
        Sx4, Sy4, Sz4 = N_body_spins(0.5, 4, 5)
        Sx5, Sy5, Sz5 = N_body_spins(0.5, 5, 5)

        Sx12, Sy12, Sz12 = N_body_spins(0.5, 1, 2)
        Sx22, Sy22, Sz22 = N_body_spins(0.5, 2, 2)

        mps = self.mps_0_5
        listH = [Sz12@Sz22+Sx12, Sz12@Sz22+Sx12+Sx22, Sz12@Sz22+Sx12+Sx22, Sz12@Sz12+Sx22]
        fullH = sum([n_body(a, i, len(listH), d=2) for i, a in enumerate(listH)], axis=0)
        self.assertTrue(mps.dA_dt(listH, fullH=False)==mps.dA_dt(fullH, fullH=True))

    def test_local_hamiltonians_6(self):
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 6)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 6)
        Sx3, Sy3, Sz3 = N_body_spins(0.5, 3, 6)
        Sx4, Sy4, Sz4 = N_body_spins(0.5, 4, 6)
        Sx5, Sy5, Sz5 = N_body_spins(0.5, 5, 6)
        Sx6, Sy6, Sz6 = N_body_spins(0.5, 6, 6)

        Sx12, Sy12, Sz12 = N_body_spins(0.5, 1, 2)
        Sx22, Sy22, Sz22 = N_body_spins(0.5, 2, 2)

        mps = self.mps_0_6
        listH = [Sz12@Sz22+Sx12, Sz12@Sz22+Sx12+Sx22, Sz12@Sz22+Sx12+Sx22, Sz12@Sz12+Sx12+Sx22, Sz12@Sz12+Sx22]
        fullH = sum([n_body(a, i, len(listH), d=2) for i, a in enumerate(listH)], axis=0)
        self.assertTrue(mps.dA_dt(listH, fullH=False)==mps.dA_dt(fullH, fullH=True))

    def test_local_hamiltonians_7(self):
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 7)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 7)
        Sx3, Sy3, Sz3 = N_body_spins(0.5, 3, 7)
        Sx4, Sy4, Sz4 = N_body_spins(0.5, 4, 7)
        Sx5, Sy5, Sz5 = N_body_spins(0.5, 5, 7)
        Sx6, Sy6, Sz6 = N_body_spins(0.5, 6, 7)
        Sx7, Sy7, Sz7 = N_body_spins(0.5, 7, 7)

        Sx12, Sy12, Sz12 = N_body_spins(0.5, 1, 2)
        Sx22, Sy22, Sz22 = N_body_spins(0.5, 2, 2)

        mps = self.mps_0_7
        listH = [Sz12@Sz22+Sx12, Sz12@Sz22+Sx12+Sx22, Sz12@Sz22+Sx12+Sx22, Sz12@Sz22+Sx12+Sx22, Sz12@Sz22+Sx12+Sx22, Sz12@Sz22+Sx22]
        fullH = sum([n_body(a, i, len(listH), d=2) for i, a in enumerate(listH)], axis=0)
        self.assertTrue(mps.dA_dt(listH, fullH=False)==mps.dA_dt(fullH, fullH=True))

    def test_christoffel(self):
        mps = self.mps_0_6.left_canonicalise()
        ijks = ((4, 5, 4), (3, 5, 3), (3, 4, 3)) # all non zero indexes (for full rank)
        for i, j, k in ijks:
            # Gauge projectors are in the right place
            mps.left_canonicalise()
            l, r = mps.get_envs()
            self.assertTrue(not allclose(mps.christoffel(i, j, k), 0))
            i_true=allclose(mps.christoffel(i, j, k, closed=(l(i-1)@c(mps[i]), None, None)), 0)
            i_false=allclose(mps.christoffel(i, j, k, closed=(l(i-1)@mps[i], None, None)), 0)
            j_true=allclose(mps.christoffel(i, j, k, closed=(None, l(j-1)@c(mps[j]), None)), 0)
            j_false=allclose(mps.christoffel(i, j, k, closed=(None, l(j-1)@mps[j], None)), 0)
            k_true=allclose(mps.christoffel(i, j, k, closed=(None, None, l(k-1)@mps[k])), 0)
            k_false=allclose(mps.christoffel(i, j, k, closed=(None, None, l(k-1)@c(mps[k]))), 0)
            self.assertTrue(i_true)
            self.assertTrue(j_true)
            self.assertTrue(k_true)
            self.assertTrue(not i_false)
            self.assertTrue(not j_false)
            self.assertTrue(not k_false)

            mps.right_canonicalise()
            l, r = mps.get_envs()
            self.assertTrue(not allclose(mps.christoffel(i, j, k), 0))
            i_true=allclose(mps.christoffel(i, j, k, closed=(l(i-1)@c(mps[i]), None, None)), 0)
            i_false=allclose(mps.christoffel(i, j, k, closed=(l(i-1)@mps[i], None, None)), 0)
            j_true=allclose(mps.christoffel(i, j, k, closed=(None, l(j-1)@c(mps[j]), None)), 0)
            j_false=allclose(mps.christoffel(i, j, k, closed=(None, l(j-1)@mps[j], None)), 0)
            k_true=allclose(mps.christoffel(i, j, k, closed=(None, None, l(k-1)@mps[k])), 0)
            k_false=allclose(mps.christoffel(i, j, k, closed=(None, None, l(k-1)@c(mps[k]))), 0)
            self.assertTrue(i_true)
            self.assertTrue(j_true)
            self.assertTrue(k_true)
            self.assertTrue(not i_false)
            self.assertTrue(not j_false)
            self.assertTrue(not k_false)

            # symmetric in i, j
            self.assertTrue(allclose(mps.christoffel(i, j, k, closed=(c(mps[i]), c(mps[j]), mps[k])), 
                                     mps.christoffel(j, i, k, closed=(c(mps[j]), c(mps[i]), mps[k]))  ))
            
            self.assertTrue(allclose(tra(mps.christoffel(i, j, k), [3, 4, 5, 0, 1, 2, 6, 7, 8]), mps.christoffel(j, i, k)))


        ijks = ((1, 2, 1),)
        for i, j, k in ijks:
            # Christoffel symbols that are zero for untruncated become not zero after truncation
            self.assertTrue(allclose(mps.christoffel(i, j, k), 0))
            mps.left_canonicalise(2)
            self.assertTrue(not allclose(mps.christoffel(i, j, k), 0))

    def test_F2_F1(self):
        '''<d_id_j ψ|H|ψ>, <d_iψ|H|d_jψ>'''
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 6)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 6)
        Sx3, Sy3, Sz3 = N_body_spins(0.5, 3, 6)
        Sx4, Sy4, Sz4 = N_body_spins(0.5, 4, 6)
        Sx5, Sy5, Sz5 = N_body_spins(0.5, 5, 6)
        Sx6, Sy6, Sz6 = N_body_spins(0.5, 6, 6)

        Sx12, Sy12, Sz12 = N_body_spins(0.5, 1, 2)
        Sx22, Sy22, Sz22 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_6.left_canonicalise()
        listH = [Sz12@Sz22+Sx12, Sz12@Sz22+Sx12+Sx22, Sz12@Sz22+Sx22+Sx12+Sx22, Sz12@Sz22+Sz12+Sx22, Sz12@Sz22+Sx22]
        eyeH = [(1/(mps.L-1))*eye(4) for _ in range(5)]
        fullH = Sz1@Sz2+Sz2@Sz3+Sz3@Sz4+Sz4@Sz5+Sz5@Sz6+Sx1+Sx2+Sx3+Sx4+Sx5+Sx6

        for i, j in product(range(mps.L), range(mps.L)):
            ## F2 = <d_id_j ψ|H|ψ>
            # zero for H = I
            self.assertTrue(allclose(mps.F2(i, j, eyeH, fullH=False), 0))

            # Test gauge projectors are in the right place
            mps.right_canonicalise()
            l, r = mps.get_envs()
            z1 = ncon([mps.F2(i, j, listH), l(i-1)@c(mps[i])], [[1, 2, 3, -1, -2, -3], [1, 2, 3]])
            z2 = ncon([mps.F2(i, j, listH), l(j-1)@c(mps[j])], [[-1, -2, -3, 1, 2, 3], [1, 2, 3]])
            self.assertTrue(allclose(z1, 0))
            self.assertTrue(allclose(z2, 0))

            mps.left_canonicalise()
            l, r = mps.get_envs()
            z1 = ncon([mps.F2(i, j, listH), l(i-1)@c(mps[i])], [[1, 2, 3, -1, -2, -3], [1, 2, 3]])
            z2 = ncon([mps.F2(i, j, listH), l(j-1)@c(mps[j])], [[-1, -2, -3, 1, 2, 3], [1, 2, 3]])
            self.assertTrue(allclose(z1, 0))
            self.assertTrue(allclose(z2, 0))

            ## F1 = <d_iψ|H|d_jψ>
            # For H = I: should be equal to δ_{ij} pr(i)
            if i!=j:
                self.assertTrue(allclose(mps.F1(i, j, eyeH), 0))
            if i==j:
                b = mps.F1(i, j, eyeH)
                a = ncon([mps.left_null_projector(i), inv(r(i))], [[-1, -2, -4, -5], [-3, -6]])
                self.assertTrue(allclose(a, b)) 
                # should just be L-1

            # Test gauge projectors are in the right place
            mps.left_canonicalise()
            l, r = mps.get_envs()
            z1 = td(mps.F1(i, j, listH), l(i-1)@c(mps[i]), [[0, 1, 2], [0, 1, 2]])
            z1 = td(mps.F1(i, j, listH), l(j-1)@mps[j], [[3, 4, 5], [0, 1, 2]])
            self.assertTrue(allclose(z1, 0))
            self.assertTrue(allclose(z2, 0))

            mps.right_canonicalise()
            l, r = mps.get_envs()
            z1 = td(mps.F1(i, j, listH), l(i-1)@c(mps[i]), [[0, 1, 2], [0, 1, 2]])
            z1 = td(mps.F1(i, j, listH), l(j-1)@mps[j], [[3, 4, 5], [0, 1, 2]])
            self.assertTrue(allclose(z1, 0))
            self.assertTrue(allclose(z2, 0))

            # TODO: fullH fails gauge projectors test (listH doesn't): 
            # TODO: fullH different from listH:

    def test_F2_F1_christoffel(self):
        '''<d_id_j ψ|H|ψ>, <d_iψ|H|d_jψ>'''
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_3
        H = [eye(4), Sz1+Sz2]
        dA_dt = mps.dA_dt(H, store_envs=True)
        i, j = 1, 2

        F2 = -1j*mps.F2(i, j, H)
        Γ2 = -td(mps.christoffel(i, j, i), dA_dt[i], [[-3, -2, -1], [0, 1, 2]])
        print(norm(F2-Γ2))
        #print(F2.shape)
        #print('\n', F2.reshape(-1), Γ2.reshape(-1), sep='\n', end='\n')
        #print('\n', F2.reshape(-1)/Γ2.reshape(-1), sep='\n', end='\n')
        print('\n', ncon([F2, inv(mps.r(i))], [[-1, -2, 1, -4, -5, -6], [1, -3]]).reshape(-1)/Γ2.reshape(-1), sep='\n', end='\n')



    def test_ddA_dt(self):
        Sx12, Sy12, Sz12 = N_body_spins(0.5, 1, 2)
        Sx22, Sy22, Sz22 = N_body_spins(0.5, 2, 2)

        mps = self.mps_0_2
        eyeH = [eye(4)]
        dt = 0.1
        Z = [randn(3)+1j*randn(3) for _ in range(10)]

        for z in Z:
            self.assertTrue(allclose(mps.ddA_dt(z, eyeH), -1j*z))

    def test_left_transfer(self):
        mps = self.mps_0_4.left_canonicalise()
        l, r = mps.get_envs()
        L = mps.L
        rs = mps.left_transfer(r(L-1), 1, L)
        for i in range(L):
            self.assertTrue(allclose(rs(i+1), r(i)))
            self.assertTrue(allclose(mps.left_transfer(r(L-1), i+1, L, False), r(i)))

    def test_right_transfer(self):
        mps = self.mps_0_4.right_canonicalise()
        l, r = mps.get_envs()
        L = mps.L
        ls = mps.right_transfer(l(0), 0, L-1)
        for i in range(L):
            self.assertTrue(allclose(ls(i+1), l(i)))

    def test_local_recombine(self):
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 4)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 4)
        Sx3, Sy3, Sz3 = N_body_spins(0.5, 3, 4)
        Sx4, Sy4, Sz4 = N_body_spins(0.5, 4, 4)

        Sx12, Sy12, Sz12 = N_body_spins(0.5, 1, 2)
        Sx22, Sy22, Sz22 = N_body_spins(0.5, 2, 2)

        listH4 = [Sz12@Sz22+Sx12, Sz12@Sz22+Sx12+Sx22, Sz12@Sz22+Sx22]
        comH4 = sum([n_body(a, i, len(listH4), d=2) for i, a in enumerate(listH4)], axis=0)
        fullH4 = Sz1@Sz2+Sz2@Sz3+Sz3@Sz4+Sx1+Sx2+Sx3+Sx4
        self.assertTrue(allclose(fullH4, comH4))

    def test_local_energy(self):
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 4)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 4)
        Sx3, Sy3, Sz3 = N_body_spins(0.5, 3, 4)
        Sx4, Sy4, Sz4 = N_body_spins(0.5, 4, 4)

        Sx12, Sy12, Sz12 = N_body_spins(0.5, 1, 2)
        Sx22, Sy22, Sz22 = N_body_spins(0.5, 2, 2)

        mps = self.mps_0_4
        listH = [Sz12@Sz22+Sx12, Sz12@Sz22+Sx12+Sx22, Sz12@Sz22+Sx22]
        fullH = Sz1@Sz2+Sz2@Sz3+Sz3@Sz4+Sx1+Sx2+Sx3+Sx4
        self.assertTrue(isclose(mps.energy(listH, fullH=False), mps.energy(fullH, fullH=True)))

    def test_profile_dA_dt(self):
        """test_profile_dA_dt: profile dA_dt: """
        #list hamiltonian slower until L~6
        # ~10s for 100 sites D=10
        d, L = 2, 10 
        mps = fMPS().random(L, d, 10)
        listH = [randn(4, 4)+1j*randn(4, 4) for _ in range(L-1)]
        listH = [h+h.conj().T for h in listH]
        #print('')
        t1 = time()
        B = mps.dA_dt(listH, fullH=False)
        t2 = time()
        #print('ser, list: ', t2-t1)
        if L<9:
            H = randn(d**L, d**L)+1j*randn(d**L, d**L)
            fullH = H+H.conj().T
            t1 = time()
            B = mps.dA_dt(listH, fullH=False, par=True)
            t2 = time()
           # print('par, list: ', t2-t1)
            t1 = time()
            B = mps.dA_dt(fullH, fullH=True)
            t2 = time()
            #print('ser, full: ', t2-t1)
            t1 = time()
            B = mps.dA_dt(fullH, fullH=True, par=True)
            t2 = time()
            #print('par, full: ', t2-t1)

    def test_profile_F2_F1(self):
        Sx12, Sy12, Sz12 = N_body_spins(0.5, 1, 2)
        Sx22, Sy22, Sz22 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_6.left_canonicalise(1)
        H = [Sz12@Sz22+Sx12, Sz12@Sz22+Sx12+Sx22, Sz12@Sz22+Sx22+Sx12+Sx22, Sz12@Sz22+Sz12+Sx22, Sz12@Sz22+Sx22]
        l, r = mps.get_envs()
        L = mps.L
        t1 = time()
        for i, j in product(range(L), range(L)):
            mps.F2(i, j, H, envs=(l, r))
        t2 = time()
        #print('\nF2: ', t2-t1)
        t1 = time()
        for i, j in product(range(L), range(L)):
            mps.F1(i, j, H, envs=(l, r))
        t2 = time()
        #print('F1: ', t2-t1)

    def test_jac_eye(self):
        mps = self.mps_0_2
        H = [eye(4)]
        J1, J2 = mps.jac(H, True)
        self.assertTrue(allclose(J1, -1j*eye(3)))
        self.assertTrue(allclose(J2, 0))
        J = mps.jac(H, True, True)
        self.assertTrue(allclose(J, kron(1j*Sy, eye(3))))

        mps = self.mps_0_3
        H = [eye(4)/2, eye(4)/2]
        J1, J2 = mps.jac(H, True)
        J = mps.jac(H, True, True)
        self.assertTrue(allclose(J1, -1j*eye(7)))
        self.assertTrue(allclose(J2, 0))
        self.assertTrue(allclose(J, kron(1j*Sy, eye(7))))

        mps = self.mps_0_4
        H = [eye(4)/3, eye(4)/3, eye(4)/3]
        J1, J2 = mps.jac(H, True)
        J = mps.jac(H, True, True)
        self.assertTrue(allclose(J1, -1j*eye(15)))
        self.assertTrue(allclose(J2, 0))
        self.assertTrue(allclose(J, kron(1j*Sy, eye(15))))

    def test_jac_no_projection(self):
        """No projection: J2=0"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)

        mps = self.mps_0_3
        H = [Sz1@Sz2+Sx1+Sx2, Sz1@Sz2+Sx2]
        J1, J2 = mps.jac(H, False)
        #print(allclose(J2(1, 2), 0))

class TestvfMPS(unittest.TestCase):
    """TestvfMPS"""

    def setUp(self):
        """setUp"""
        N = 20  # Number of MPSs to test
        #  min and max params for randint
        L_min, L_max = 9, 20
        d_min, d_max = 2, 5
        D_min, D_max = 5, 40
        # N random MPSs
        self.cases = [fMPS().random(randint(L_min, L_max),
                                    randint(d_min, d_max),
                                    randint(D_min, D_max))
                      for _ in range(N)]
        # N random MPSs right canonicalised with truncation
        self.right_cases = [fMPS().random(
                                randint(L_min, L_max),
                                randint(d_min, d_max),
                                randint(D_min, D_max)).right_canonicalise(
                                randint(D_min, D_max))
                            for _ in range(N)]

    def test_vidal_to_and_from_fMPS(self):
        """test_to_from_fMPS"""
        other_cases = [vfMPS().from_fMPS(case).to_fMPS() for case in self.cases]
        self.assertTrue(array([fMPS1 == fMPS2
                               for fMPS1, fMPS2 in zip(self.cases,
                                                       other_cases)]).all())

if __name__ == '__main__':
    unittest.main(verbosity=2)
