import unittest
from time import time
from fMPS import fMPS
from ncon import ncon
from numpy.linalg import det, qr
from spin import N_body_spins, spins, comm, n_body
from numpy import array, linspace, real as re, reshape, sum, swapaxes as sw
from numpy import tensordot as td, squeeze, trace as tr, expand_dims as ed
from numpy import load, isclose, allclose, zeros_like as zl, prod, imag as im
from numpy import log, abs, diag, cumsum as cs, arange as ar, eye, kron as kr
from numpy import cross, dot, kron, split, concatenate as ct, isnan, isinf
from numpy import trace as tr, zeros, printoptions, tensordot, trace
from numpy.random import randn
from scipy.linalg import sqrtm, expm, norm, null_space as null, cholesky as ch
from scipy.sparse.linalg import expm_multiply, expm
from scipy.integrate import odeint, complex_ode as c_ode
from scipy.integrate import ode, solve_ivp
from numpy.linalg import inv, svd
import numpy as np
from tensor import get_null_space, H as cT, C as c
from matplotlib import pyplot as plt
from functools import reduce
from copy import copy, deepcopy
from tqdm import tqdm
from tdvp.tdvp_fast import tdvp, MPO_TFI
Sx, Sy, Sz = spins(0.5)
Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)

class Trajectory(object):
    """Trajectory"""

    def __init__(self, mps_0, H=None, W=None, fullH=False):
        """__init__

        :param mps_0: initial state
        :param H: hamiltonian
        :param T: time steps
        """
        self.H = H # hamiltonian as list of 4x4 mats or big matrix
        self.W = W # hamiltonian as mpo - required for invfreeint

        self.mps_0 = deepcopy(mps_0)
        self.mps = deepcopy(mps_0)
        self.fullH=fullH
        self.mps_history = []

    def euler(self, mps, dt, H=None, store=True):
        H = self.H if H is None else H
        if store:
            self.mps_history.append(mps.serialize(real=True))
        return (mps + mps.dA_dt(H, fullH=self.fullH)*dt).left_canonicalise()

    def rk4(self, mps, dt, H=None, store=True):
        H = self.H if H is None else H
        if store:
            self.mps_history.append(mps.serialize(real=True))
        k1 = mps.dA_dt(H, fullH=self.fullH)*dt
        k2 = (mps+k1/2).dA_dt(H, fullH=self.fullH)*dt
        k3 = (mps+k2/2).dA_dt(H, fullH=self.fullH)*dt
        k4 = (mps+k3).dA_dt(H, fullH=self.fullH)*dt

        return (mps+(k1+2*k2+2*k3+k4)/6).left_canonicalise()

    def invfree(self, mps, dt, W=None, store=True):
        if store:
            self.mps_history.append(mps.serialize(real=True))
        A = tdvp(mps.data, self.W, 1j*dt/2)
        return fMPS(A[0])

    def eulerint(self, T):
        """eulerint: integrate with euler time steps

        :param T:
        """
        mps, H = self.mps.left_canonicalise(), self.H
        L, d, D = mps.L, mps.d, mps.D

        for t in tqdm(T):
            mps = self.euler(mps, T[1]-T[0])

        self.mps = fMPS().deserialize(self.mps_history[-1], L, d, D, real=True)
        return self

    def rk4int(self, T):
        """rk4int: integrate with rk4 timesteps
        """
        mps, H = self.mps.left_canonicalise(), self.H
        L, d, D = mps.L, mps.d, mps.D

        for t in tqdm(T):
            mps = self.rk4(mps, T[1]-T[0])

        self.mps = fMPS().deserialize(self.mps_history[-1], L, d, D, real=True)
        return self

    def invfreeint(self, T, D=None):
        """invfreeint: inverse free (symmetric) integrator - wraps Frank code. 
                       requires a MPO - MPO_TFI/MPO_XXZ from tdvp 
                       remember my ed thing has Sx = 1/2 Sx etc. for some reason

        :param T:
        :param D:
        """
        assert hasattr(self, 'W')
        mps, H = self.mps, self.H
        L, d, D = mps.L, mps.d, mps.D

        for t in tqdm(T):
            mps = self.invfree(mps, T[1]-T[0])

        self.mps = fMPS().deserialize(self.mps_history[-1], L, d, D, real=True)
        return self

    def odeint(self, T):
        """odeint: integrate TDVP equations with scipy.odeint
           bar is upper bound - might do fewer iterations than it expects.
           Use another method for more predictable results

        :param T: timesteps
        :param D: bond dimension to truncate initial state to
        """
        mps, H = self.mps.left_canonicalise(), self.H
        L, d, D = mps.L, mps.d, mps.D
        bar = tqdm()
        m=0

        def f(t, v):
            """f_odeint: f acting on real vector

            :param v: Vector: [reals, imags]
            :param t: Time
            """
            bar.update()
            nonlocal m
            m+=1
            if m==4:
                return fMPS().deserialize(v, L, d, D, real=True)\
                            .left_canonicalise()\
                            .dA_dt(H, fullH=self.fullH)\
                            .serialize(real=True)
            else:
                return fMPS().deserialize(v, L, d, D, real=True)\
                            .dA_dt(H, fullH=self.fullH)\
                            .serialize(real=True)


        v = mps.serialize(real=True)
        Q = solve_ivp(f, (T[0], T[-1]), v, method='LSODA', t_eval=T,
                      max_step=T[1]-T[0], min_step=T[1]-T[0])
        traj = Q.y.T
        bar.close()

        self.mps_history = traj
        self.mps = fMPS().deserialize(traj[-1], L, d, D, real=True)
        return self

    def edint(self, T):
        """edint: exact diagonalisation 
        """
        H = self.H
        psi_0 = self.mps.recombine().reshape(-1)
        H = sum([n_body(a, i, len(H), d=2)
                 for i, a in enumerate(H)], axis=0) if not self.fullH else H
        self.ed_history = []
        psi_n = psi_0
        dt = T[1]-T[0]
        for t in tqdm(T):
            psi_n = expm(-1j *H*dt)@psi_n
            self.ed_history.append(psi_n)

        self.ed_history = array(self.ed_history)
        self.psi = self.ed_history[-1]
        return self

    def lyapunov(self, T, D=None, just_max=False):
        H = self.H
        if D is not None:
            print('growing: ')
            self.mps = self.mps.grow(self.H, 0.1, D).right_canonicalise()
        if hasattr(self, 'W') and self.mps.D!=1 and D!=1:
            self.invfreeint(linspace(0, 0.5, 50))
        else:
            self.rk4int(linspace(0, 0.5, 50))

        l, r = self.mps.get_envs()
        Q = kron(eye(2), self.mps.tangent_space_basis(type='eye'))
        if just_max:
            q = Q[0]
        dt = T[1]-T[0]
        e = []
        lys = []
        calc = False
        for t in tqdm(range(1, len(T)+1)):
            J = self.mps.jac(H)
            if just_max:
                q = expm_multiply(J*dt, Q)
                lys.append(log(abs(norm(q))))
                q /= norm(q)
            else:
                M = expm_multiply(J*dt, Q)
                if(sum(isnan(M))>0):
                    raise Exception
                Q, R = qr(M)
                lys.append(log(abs(diag(R))))

            self.mps = self.rk4(self.mps, dt, H).left_canonicalise()
            #self.mps = self.invfree(self.mps, dt, H)

        exps = (1/(dt))*cs(array(lys), axis=0)/ed(ar(1, len(lys)+1), 1)
        return exps, array(lys)

    def ed_OTOC(self, T, ops):
        V, W = ops
        psi_0 = self.mps.recombine().reshape(-1)
        H = self.H
        dt = T[1]-T[0]
        Ws = []
        for t in T:
            U = expm(-1j*H*t)
            Wt = cT(U)@W@U
            Ws.append(-re(c(psi_0)@comm(Wt, V)@comm(Wt, V)@psi_0))
        return Ws

    def mps_OTOC(self, T, ops):
        pass

    def mps_evs(self, ops, site):
        assert hasattr(self, "mps_history")
        L, d, D = self.mps.L, self.mps.d, self.mps.D
        return array([mps.Es(ops, site)
                    for mps in map(lambda x: fMPS().deserialize(x, L, d, D, real=True), self.mps_history)])

    def ed_evs(self, ops):
        assert hasattr(self, "ed_history")
        return array([[re(psi.conj()@op@psi) for op in ops] for psi in self.ed_history])

    def clear(self):
        self.mps_history = []
        self.mps = self.mps_0.copy()

class TestTrajectory(unittest.TestCase):
    """TestF"""
    def setUp(self):
        """setUp"""
        self.tens_0_2 = load('fixtures/mat2x2.npy')
        self.tens_0_3 = load('fixtures/mat3x3.npy')
        self.tens_0_4 = load('fixtures/mat4x4.npy')
        self.tens_0_5 = load('fixtures/mat5x5.npy')

        self.mps_0_1 = fMPS().left_from_state(self.tens_0_2).right_canonicalise(1)

        self.mps_0_2 = fMPS().left_from_state(self.tens_0_2)
        self.psi_0_2 = self.mps_0_2.recombine().reshape(-1)

        self.mps_0_3 = fMPS().left_from_state(self.tens_0_3)
        self.psi_0_3 = self.mps_0_3.recombine().reshape(-1)

        self.mps_0_4 = fMPS().left_from_state(self.tens_0_4)
        self.psi_0_4 = self.mps_0_4.recombine().reshape(-1)

        self.mps_0_5 = fMPS().left_from_state(self.tens_0_5)
        self.psi_0_5 = self.mps_0_5.recombine().reshape(-1)

    def test_integrators(self):
        test_2 = True
        if test_2:
            Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
            Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)

            dt, t_fin = 2e-2, 10
            T = linspace(0, t_fin, int(t_fin//dt)+1)

            mps_0 = self.mps_0_2
            H = [Sz1@Sz2+Sx1+Sx2]
            W = mps_0.L*[MPO_TFI(0, 0.25, 0.5, 0)]
            F = Trajectory(mps_0, H=H, W=W)

            A = F.edint(T).ed_evs([Sx1, Sy1, Sz1])
            F.clear()
            B = F.eulerint(T).mps_evs([Sx, Sy, Sz], 0)
            F.clear()
            C = F.invfreeint(T).mps_evs([Sx, Sy, Sz], 0)
            F.clear()
            self.assertTrue(norm(B-A)/prod(A.shape)<dt**2)
            self.assertTrue(norm(C-A)/prod(A.shape)<dt**2)

            plot=False
            if plot:
                fig, ax = plt.subplots(1, 1, sharex=True, sharey=True)
                ax.set_ylim([-1, 1])
                ax.plot(T, A)
                ax.plot(T, B)
                ax.plot(T, C)
                plt.show()

        test_3 = True
        if test_3:
            Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
            Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)

            dt, t_fin = 2e-2, 10 
            T = linspace(0, t_fin, int(t_fin//dt)+1)

            mps_0 = self.mps_0_3.right_canonicalise()
            H = [Sz1@Sz2+Sx1+Sx2] + [Sz1@Sz2+Sx2]
            W = mps_0.L*[MPO_TFI(0, 0.25, 0.5, 0)]
            F = Trajectory(mps_0, H=H, W=W)

            Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 3)
            Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 3)
            Sx3, Sy3, Sz3 = N_body_spins(0.5, 3, 3)


            A = F.edint(T).ed_evs([Sx3, Sy3, Sz3])
            F.clear()
            B = F.eulerint(T).mps_evs([Sx, Sy, Sz], 2)
            F.clear()
            C = F.invfreeint(T).mps_evs([Sx, Sy, Sz], 2)
            self.assertTrue(norm(B-A)/prod(A.shape)<dt**2)
            self.assertTrue(norm(C-A)/prod(A.shape)<dt**2)

            plot=False
            if plot:
                fig, ax = plt.subplots(1, 1, sharey=True, sharex=True)
                ax.set_ylim([-1, 1])
                ax.plot(T, A)
                ax.plot(T, B)
                ax.plot(T, C)
                plt.show()

        test_4 = True
        if test_4:
            Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
            Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)

            dt, t_fin = 2e-2, 10 
            T = linspace(0, t_fin, int(t_fin//dt)+1)

            mps_0 = self.mps_0_4.right_canonicalise()
            H = [Sz1@Sz2+Sx1+Sx2] + [Sz1@Sz2+Sx2] + [Sz1@Sz2+Sx2]
            W = mps_0.L*[MPO_TFI(0, 0.25, 0.5, 0)]
            F = Trajectory(mps_0, H=H, W=W)

            Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 4)
            Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 4)
            Sx3, Sy3, Sz3 = N_body_spins(0.5, 3, 4)
            Sx4, Sy4, Sz4 = N_body_spins(0.5, 4, 4)

            A = F.edint(T).ed_evs([Sx3, Sy3, Sz3])
            F.clear()
            B = F.eulerint(T).mps_evs([Sx, Sy, Sz], 2)
            F.clear()
            C = F.invfreeint(T).mps_evs([Sx, Sy, Sz], 2)
            self.assertTrue(norm(B-A)/prod(A.shape)<dt)
            self.assertTrue(norm(C-A)/prod(A.shape)<dt**2)

            plot=False
            if plot:
                fig, ax = plt.subplots(1, 1, sharey=True, sharex=True)
                ax.set_ylim([-1, 1])
                ax.plot(T, A)
                #ax.plot(T, B)
                ax.plot(T, C)
                plt.show()

        test_5 = True
        if test_5:
            Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
            Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)

            dt, t_fin = 2e-2, 10 
            T = linspace(0, t_fin, int(t_fin//dt)+1)

            mps_0 = self.mps_0_5.right_canonicalise()
            H = [Sz1@Sz2+Sx1+Sx2] + [Sz1@Sz2+Sx2] + [Sz1@Sz2+Sx2] + [Sz1@Sz2+Sx2]
            W = mps_0.L*[MPO_TFI(0, 0.25, 0.5, 0)]
            F = Trajectory(mps_0, H=H, W=W)

            Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 5)
            Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 5)
            Sx3, Sy3, Sz3 = N_body_spins(0.5, 3, 5)
            Sx4, Sy4, Sz4 = N_body_spins(0.5, 4, 5)
            Sx5, Sy5, Sz5 = N_body_spins(0.5, 5, 5)


            A = F.edint(T).ed_evs([Sx3, Sy3, Sz3])
            F.clear()
            B = F.eulerint(T).mps_evs([Sx, Sy, Sz], 2)
            F.clear()
            C = F.invfreeint(T).mps_evs([Sx, Sy, Sz], 2)
            self.assertTrue(norm(B-A)/prod(A.shape)<dt)
            self.assertTrue(norm(C-A)/prod(A.shape)<dt**2)

            plot=False
            if plot:
                fig, ax = plt.subplots(1, 1, sharey=True, sharex=True)
                ax.set_ylim([-1, 1])
                ax.plot(T, A)
                #ax.plot(T, B)
                ax.plot(T, C)
                plt.show()

    def test_OTOC(self):
        """OTOC zero for W=eye"""
        Sx1,  Sy1,  Sz1 =  N_body_spins(0.5, 1,  5)
        Sx2,  Sy2,  Sz2 =  N_body_spins(0.5, 2,  5)
        Sx3,  Sy3,  Sz3 =  N_body_spins(0.5, 3,  5)
        Sx4,  Sy4,  Sz4 =  N_body_spins(0.5, 4,  5)
        Sx5,  Sy5,  Sz5 =  N_body_spins(0.5, 5,  5)

        mps = fMPS().random(5, 2, None).left_canonicalise()
        H = Sz1@Sz2+Sz2@Sz3+Sz3@Sz4+Sz4@Sz5+\
                Sx1+Sx2+Sx3+Sx4+Sx5+\
                Sz1+Sz2+Sz3+Sz4+Sz5
        op = eye(2**5)
        T = linspace(0, 10, 100)
        Ws = Trajectory(mps, H).ed_OTOC(T, op)
        self.assertTrue(allclose(Ws, 0))

    def test_lyapunov_local_hamiltonian_2(self):
        """zero lyapunov exponents with local hamiltonian"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_2
        H = [Sx1-Sx2]
        T = linspace(0, 1, 100)
        exps, lys, _ = Trajectory(mps, H).lyapunov(T, D=1, bar=True)
        self.assertTrue(allclose(exps[-1], 0))

    def test_lyapunov_local_hamiltonian_3(self):
        """zero lyapunov exponents with local hamiltonian"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_3
        H = [Sx1+Sx2, Sx2]
        T = linspace(0, 1, 100)
        exps, lys, _ = Trajectory(mps, H).lyapunov(T, D=1, bar=True)
        self.assertTrue(allclose(exps[-1], 0))

    def test_lyapunov_no_truncate_2(self):
        """zero lyapunov exponents with no projection"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_2
        H = [Sz1@Sz2+Sx1+Sx2]
        T = linspace(0, 1, 100)
        exps, lys, _ = Trajectory(mps, H).lyapunov(T, D=None, bar=True)
        self.assertTrue(allclose(exps[-1], 0))

    def test_lyapunov_no_truncate_3(self):
        """zero lyapunov exponents with no truncation"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_3
        H = [Sz1@Sz2+Sx1+Sx2, Sz1@Sz2+Sx2]
        T = linspace(0, 0.1, 100)
        exps, lys, _ = Trajectory(mps, H).lyapunov(T, D=None, bar=True)
        self.assertTrue(allclose(exps[-1], 0))

if __name__ == '__main__':
    unittest.main(verbosity=2)
