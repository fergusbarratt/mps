import unittest
from time import time
from fMPS import fMPS
from ncon import ncon
from spin import N_body_spins, spins
from numpy import array, linspace, real as re, reshape, sum, swapaxes as sw
from numpy import tensordot as td, squeeze, trace as tr, expand_dims as ed
from numpy import load, isclose, allclose, zeros_like as zl, prod, imag as im
from numpy import log, abs, diag, cumsum as cs, arange as ar, eye, kron as kr
from numpy import cross, dot, kron
from numpy.random import randn
from scipy.linalg import sqrtm, expm, norm, null_space as null, cholesky as ch
from scipy.integrate import odeint, complex_ode as c_ode
from numpy import split, concatenate as ct
from numpy.linalg import inv, qr
import numpy as np
from tensor import get_null_space, H as cT, C as c
from matplotlib import pyplot as plt
from functools import reduce
from copy import copy, deepcopy
from tqdm import tqdm
Sx, Sy, Sz = spins(0.5)
Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)

class Trajectory(object):
    """Trajectory"""

    def __init__(self, mps_0, H, fullH=False):
        """__init__

        :param mps_0: initial state
        :param H: hamiltonian
        :param T: time steps
        """
        self.H = H
        self.mps = deepcopy(mps_0)
        self.fullH=fullH
        self.history = []

    def euler(self, dt, store=False):
        mps, H = self.mps, self.H
        self.mps =  self.mps + self.mps.dA_dt(H)*dt
        if store:
            self.history.append(mps.serialize())
        return self.mps

    def rk4(self, mps, dt):
        H = self.H
        k1 = mps.dA_dt(H, fullH=self.fullH)*dt
        k2 = (mps+k1/2).dA_dt(H, fullH=self.fullH)*dt
        k3 = (mps+k2/2).dA_dt(H, fullH=self.fullH)*dt
        k4 = (mps+k3).dA_dt(H, fullH=self.fullH)*dt
        #self.history.append(mps.serialize())

        mps = mps+(k1+2*k2+2*k3+k4)/6
        return mps

    def odeint(self, T, D=None, plot=False, timeit=False, lyapunovs=False):
        """odeint: pass to scipy odeint

        :param mps_0: initial 
        :param plot: plot the result
        :param timeit: time odeint
        """
        mps_0, H = self.mps.right_canonicalise(D), self.H
        L, d, D = mps_0.L, mps_0.d, mps_0.D
        v = mps_0.serialize(real=True)

        def f_odeint_r(v, t, L, d, D, H):
            """f_odeint: f acting on real vector

            :param v: Vector: [reals, imags]
            :param t: Time
            :param L: Length
            :param d: Local hilbert space dimension
            :param D: Bond dimension
            :param H: Hamiltonian
            """
            return fMPS().deserialize(v, L, d, D, real=True).dA_dt(H, fullH=self.fullH).serialize(real=True)

        t1 = time()
        traj = odeint(f_odeint_r, v, T, args=(L, d, D, H))
        t2 = time()
        if timeit:
            print(t2-t1)
        if plot:
            plt.plot(T, [mps.E(Sy, 0) for mps in map(lambda x: fMPS().deserialize(x, L, d, D, real=True), traj)])

#        self.history = traj
        self.mps = fMPS().deserialize(traj.T[-1, :], L, d, D, real=True)
        return self

    def lyapunov_old(self, T, D=None, ops=[]):
        self.mps.left_canonicalise(D)
        print(self.mps.structure())
        H = self.H
        Q = self.mps.tangent_space_basis()
        dt = T[1]-T[0]
        e = []
        lys = []
        evs = []
        for t in tqdm(range(1, len(T)+1)):
            for m, v in enumerate(Q):
                q = v+dt*self.mps.ddA_dt(v, H) # unitary to order dt^2: inst. lyapunov exponents should be off by O(dt^2)
                Q[m] = q
            Q, R = qr(Q)
            lys.append(log(abs(diag(R))))
            evs.append([self.mps.E(*opsite) for opsite in ops])
            self.euler(dt).left_canonicalise()
        exps = (1/(dt))*cs(array(lys), axis=0)/ed(ar(1, len(lys)+1), 1)
        return exps, array(lys), array(evs)

    def lyapunov(self, T, D=None, ops=[], bar=True):
        H = self.H
        self.mps = self.mps.left_canonicalise(D)
        Q = kron(eye(2), self.mps.tangent_space_basis())
        dt = T[1]-T[0]
        e = []
        lys = []
        evs = []
        def tqdm_(x): return tqdm(x) if bar else x
        for t in tqdm_(range(1, len(T)+1)):
            J = self.mps.jac(H, True, True)
            Q = expm(J*dt)@Q
            Q, R = qr(Q)
            lys.append(log(abs(diag(R))))
            evs.append([self.mps.E(*opsite) for opsite in ops])
            self.mps = self.rk4(self.mps, dt)
            self.mps = self.mps.left_canonicalise(D)
        exps = (1/(dt))*cs(array(lys), axis=0)/ed(ar(1, len(lys)+1), 1)
        return exps, array(lys), array(evs)

    def time_reverse(self, T):
        es = []
        Ψ = self.mps.copy()
        dt = T[1]-T[0]
        for t in tqdm(range(len(T))):
            Ψ = self.rk4(Ψ, dt).left_canonicalise()
            es.append(Ψ.E(Sx, 0))
        for t in tqdm(range(len(T))):
            Ψ = self.rk4(Ψ, -dt).left_canonicalise()
            es.append(Ψ.E(Sx, 0))
        plt.plot(es)
        print(norm(es[-1]-es[0]))
        plt.show()

    def OTOC(self, T, op):
        psi_0 = self.mps.recombine().reshape(-1)
        H = self.H
        dt = T[1]-T[0]
        Ws = []
        for t in T:
            U = expm(-1j*H*t)
            W_0 = op
            W_t = cT(U)@op@U
            x1 = W_0@W_t@psi_0 # W(0)W(t)|Ψ>
            x2 = W_t@W_0@psi_0 # W(t)W(0)|Ψ>
            Ws.append(1-re(c(x1)@x2))
        return Ws

class TestTrajectory(unittest.TestCase):
    """TestF"""
    def setUp(self):
        """setUp"""
        self.tens_0_2 = load('mat2x2.npy')
        self.tens_0_3 = load('mat3x3.npy')
        self.tens_0_4 = load('mat4x4.npy')
        self.tens_0_5 = load('mat5x5.npy')

        self.mps_0_1 = fMPS().left_from_state(self.tens_0_2).right_canonicalise(1)

        self.mps_0_2 = fMPS().left_from_state(self.tens_0_2)
        self.psi_0_2 = self.mps_0_2.recombine().reshape(-1)

        self.mps_0_3 = fMPS().left_from_state(self.tens_0_3)
        self.psi_0_3 = self.mps_0_3.recombine().reshape(-1)

        self.mps_0_4 = fMPS().left_from_state(self.tens_0_4)
        self.psi_0_4 = self.mps_0_4.recombine().reshape(-1)

        self.mps_0_5 = fMPS().left_from_state(self.tens_0_5)
        self.psi_0_5 = self.mps_0_5.recombine().reshape(-1)

    def test_lyapunov_2_identity(self):
        """test_lyapunov_2_identity lyapunov exponents are exactly half the timestep? when H=eye(4)"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_2
        H = [eye(4)]
        T = linspace(0, 0.1, 100)
        exps, lys, _ = Trajectory(mps, H).lyapunov_old(T, D=2)
        self.assertTrue(allclose(exps[-1], (T[1]-T[0])/2))

    def test_lyapunov_matrices_local_hamiltonian_2(self):
        """zero lyapunov exponents with local hamiltonian"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_2
        H = [Sx1-Sx2]
        T = linspace(0, 1, 100)
        exps, lys, _ = Trajectory(mps, H).lyapunov(T, D=1, bar=True)
        self.assertTrue(allclose(exps[-1], 0))

    def test_lyapunov_matrices_no_truncate_2(self):
        """zero lyapunov exponents with no projection"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_2
        H = [Sz1@Sz2+Sx1+Sx2]
        T = linspace(0, 1, 100)
        exps, lys, _ = Trajectory(mps, H).lyapunov(T, D=None, bar=True)
        self.assertTrue(allclose(exps[-1], 0))

    def test_lyapunov_matrices_truncate_3(self):
        """Chaotic and non chaotic systems"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        T = linspace(0, 20, 100)

        mps = self.mps_0_4
        H = [Sx1@Sx2+Sy1@Sy2+Sz1@Sz2, Sx1@Sx2+Sy1@Sy2+Sz1@Sz2, Sx1@Sx2+Sy1@Sy2+Sz1@Sz2]
        exps1, lys1, _ = Trajectory(mps, H).lyapunov(T, D=2, bar=True)

        #mps = self.mps_0_3
        #H = [Sx1@Sx2+Sy1@Sy2+Sz1@Sz2, Sx1@Sx2+Sy1@Sy2+Sz1@Sz2]
        #exps2, lys2, _ = Trajectory(mps, H).lyapunov(T, D=2, bar=True)

        fig, ax = plt.subplots(2, 1, sharex=True, sharey=True)
        #ax[0][0].plot(exps1)
        #ax[0][0].set_title('no chaos')
        #ax[0][1].plot(lys1)

        ax[0].plot(exps1)
        ax[0].set_title('chaos')
        ax[1].plot(lys1)
        fig.tight_layout()
        plt.show()

    def test_lyapunov_matrices_local_hamiltonian_3(self):
        """zero lyapunov exponents with local hamiltonian"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_3
        H = [Sx1+Sx2, Sx2]
        T = linspace(0, 1, 100)
        exps, lys, _ = Trajectory(mps, H).lyapunov(T, D=1, bar=True)
        self.assertTrue(allclose(exps[-1], 0))

    def test_lyapunov_matrices_no_truncate_3(self):
        """zero lyapunov exponents with no truncation"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_3
        H = [Sz1@Sz2+Sx1+Sx2, Sz1@Sz2+Sx2]
        T = linspace(0, 0.1, 100)
        exps, lys, _ = Trajectory(mps, H).lyapunov(T, D=None, bar=True)
        self.assertTrue(allclose(exps[-1], 0))

    def test_lyapunov_2(self):
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_2
        H = [Sx1@Sx2+Sy1@Sy2+Sz1@Sz2+Sx1-Sz2]
        T = linspace(0, 20, 2000)
        exps1, lys1, evs1 = Trajectory(mps, H).lyapunov(T, D=1, ops=[(Sx, 0), (Sy, 0), (Sz, 0)])
        exps2, lys2, evs2 = Trajectory(mps, H).lyapunov(T, D=2, ops=[(Sx, 0), (Sy, 0), (Sz, 0)])
        print(exps1[-1], exps2[-2])

        fig, ax = plt.subplots(3, 2, sharex=True)
        ax[0][0].plot(T, exps1)
        ax[1][0].plot(T, lys1)
        ax[2][0].plot(T, evs1)
        ax[0][1].plot(T, exps2)
        ax[1][1].plot(T, lys2)
        ax[2][1].plot(T, evs2)

        ax[0][0].set_ylim([-1, 1])
        ax[1][0].set_ylim([-1, 1])
        ax[2][0].set_ylim([-1, 1])
        ax[0][1].set_ylim([-1, 1])
        ax[1][1].set_ylim([-1, 1])
        ax[2][1].set_ylim([-1, 1])
        plt.show()

    def test_lyapunov_3(self):
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_3
        H = [Sz1@Sz2+Sx1, Sz1@Sz2+Sx2]
        T = linspace(0, 3, 300)
        exps, lys, evs = Trajectory(mps, H).lyapunov(T, ops=[(Sx, 0), (Sy, 0), (Sz, 0)])
        print(exps[-1])

        fig, ax = plt.subplots(3, 1, sharex=True)
        ax[0].plot(T, exps)
        ax[1].plot(T, lys)
        ax[2].plot(T, evs)

        #ax[0].set_ylim([-1, 1])
        #ax[1].set_ylim([-1, 1])
        ax[2].set_ylim([-1, 1])
        plt.show()

    def test_lyapunov_4(self):
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_4
        H = [Sz1@Sz2+Sx1, Sz1@Sz2+Sx1+Sx2, Sz1@Sz2+Sx2]
        T = linspace(0, 1, 100)
        exps, lys, evs = Trajectory(mps, H).lyapunov(T, ops=[(Sx, 0), (Sy, 0), (Sz, 0)])
        print(exps[-1])

        fig, ax = plt.subplots(3, 1, sharex=True)
        ax[0].plot(T, exps)
        ax[1].plot(T, lys)
        ax[2].plot(T, evs)

        ax[2].set_ylim([-1, 1])
        plt.show()

    def test_lyapunov_5(self):
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps = self.mps_0_5
        H = [Sz1@Sz2+Sx1, Sz1@Sz2+Sx1+Sx2, Sz1@Sz2+Sx1+Sx2, Sz1@Sz2+Sx2]
        T = linspace(0, 1, 100)
        exps, lys, evs = Trajectory(mps, H).lyapunov(T, ops=[(Sx, 0), (Sy, 0), (Sz, 0)])
        print(exps[-1])

        fig, ax = plt.subplots(3, 1, sharex=True)
        ax[0].plot(T, exps)
        ax[1].plot(T, lys)
        ax[2].plot(T, evs)

        ax[2].set_ylim([-1, 1])
        plt.show()

    def test_exps_2(self):
        """test_exps_2: 2 spins: 100 timesteps, expectation values within tol=1e-2 of ed results"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        H = Sz1@Sz2 + Sx1+Sx2
        mps_0 = self.mps_0_2.right_canonicalise()
        psi_0 = self.psi_0_2
        dt = 1e-2
        N = 100 
        tol = 1e-2
        mps_n = mps_0
        psi_n = psi_0
        for _ in range(N):
            self.assertTrue(isclose(psi_n.conj()@Sx1@psi_n, mps_n.E(Sx, 0), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sy1@psi_n, mps_n.E(Sy, 0), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sz1@psi_n, mps_n.E(Sz, 0), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sx2@psi_n, mps_n.E(Sx, 1), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sy2@psi_n, mps_n.E(Sy, 1), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sz2@psi_n, mps_n.E(Sz, 1), atol=tol))

            mps_n = mps_n + mps_n.dA_dt(H, fullH=True)*dt
            psi_n = expm(-1j*H*dt)@psi_n

    def test_exps_3(self):
        """test_exps_3: 3 spins: 100 timesteps, expectation values within tol=1e-2 of ed results"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 3)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 3)
        Sx3, Sy3, Sz3 = N_body_spins(0.5, 3, 3)
        H = Sz1@Sz2 + Sz2@Sz3 + Sx1+Sx2+Sx3
        mps_0 = self.mps_0_3
        psi_0 = self.psi_0_3
        dt = 1e-2
        N = 100 
        tol = 1e-2
        mps_n = mps_0
        psi_n = psi_0
        for _ in range(N):
            self.assertTrue(isclose(psi_n.conj()@Sx1@psi_n, mps_n.E(Sx, 0), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sy1@psi_n, mps_n.E(Sy, 0), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sz1@psi_n, mps_n.E(Sz, 0), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sx2@psi_n, mps_n.E(Sx, 1), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sy2@psi_n, mps_n.E(Sy, 1), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sz2@psi_n, mps_n.E(Sz, 1), atol=tol))

            mps_n = mps_n + mps_n.dA_dt(H, fullH=True)*dt
            psi_n = expm(-1j*H*dt)@psi_n

    def test_exps_4(self):
        """test_exps_4: 4 spins: 100 timesteps, expectation values within tol=1e-2 of ed results"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 4)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 4)
        Sx3, Sy3, Sz3 = N_body_spins(0.5, 3, 4)
        Sx4, Sy4, Sz4 = N_body_spins(0.5, 4, 4)
        H = Sz1@Sz2 +Sz2@Sz3 + Sz3@Sz4 + Sx1+Sx2+Sx3+Sx4
        mps_0 = self.mps_0_4
        psi_0 = self.psi_0_4
        dt = 1e-2
        N = 100 
        tol = 1e-2
        mps_n = mps_0
        psi_n = psi_0
        for _ in range(N):
            self.assertTrue(isclose(psi_n.conj()@Sx1@psi_n, mps_n.E(Sx, 0), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sy1@psi_n, mps_n.E(Sy, 0), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sz1@psi_n, mps_n.E(Sz, 0), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sx2@psi_n, mps_n.E(Sx, 1), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sy2@psi_n, mps_n.E(Sy, 1), atol=tol))
            self.assertTrue(isclose(psi_n.conj()@Sz2@psi_n, mps_n.E(Sz, 1), atol=tol))

            mps_n = mps_n + mps_n.dA_dt(H, fullH=True)*dt
            psi_n = expm(-1j*H*dt)@psi_n

    def test_trajectory_2_D_1(self):
        """test_trajectory_2: 2 spins, lyapunov trajectory, initial state has bond dimension 1"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps_0 = self.mps_0_1
        H = 4*(Sz1@Sz2 +Sy1@Sy2+Sx1@Sx2) + (Sx1-Sz2)
        N, dt = 50, 1e-2
        Trajectory(mps_0, H).odeint(linspace(0, N*dt, N), plot=False, timeit=True)

    def test_trajectory_2_no_truncate(self):
        """test_trajectory_2: 2 spins, lyapunov trajectory"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps_0 = self.mps_0_2
        H = Sz1@Sz2 + Sx1+Sx2
        N = 100
        dt = 1e-1
        Trajectory(mps_0, H).odeint(linspace(0, N*dt, N), plot=False, timeit=True)
        # odeint up to 3x faster!

    def test_trajectory_3_no_truncate(self):
        """test_trajectory_3: 3 spins, lyapunov trajectory"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 3)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 3)
        Sx3, Sy3, Sz3 = N_body_spins(0.5, 3, 3)
        mps_0 = self.mps_0_3
        H = Sz1@Sz2+Sz2@Sz3 + Sx1+Sx2+Sx3
        dt, N = 1e-1, 100
        Trajectory(mps_0, H).odeint(linspace(0, N*dt, N), plot=False, timeit=True)

    def test_trajectory_4_no_truncate(self):
        """test_trajectory_4: 4 spins, lyapunov trajectory"""
        Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
        Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)
        mps_0 = self.mps_0_4
        #H = Sz1@Sz2+Sz2@Sz3+Sz3@Sz4 + Sx1+Sx2+Sx3+Sx4
        H = [Sz1@Sz2+Sx1, Sz1@Sz2+Sx1+Sx2, Sz1@Sz2+Sx2]
        dt, N = 1e-1, 300
        T = linspace(0, N*dt, N)
        Trajectory(mps_0, H).odeint(T, plot=True)
        plt.show()

    def test_OTOC(self):
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
        Ws = Trajectory(mps, H).OTOC(T, op)
        self.assertTrue(allclose(Ws, 0))


if __name__ == '__main__':
    unittest.main(verbosity=2)
