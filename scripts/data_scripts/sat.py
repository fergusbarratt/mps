from numpy import load, cumsum as cs, arange as ar, expand_dims as ed
from numpy import array, log, save, exp, vectorize, linspace, log
from numpy import exp, unique, linspace
from scipy.optimize import curve_fit
from scipy.interpolate import interp1d, InterpolatedUnivariateSpline
from functools import reduce
import matplotlib as mpl
mpl.rc('text', usetex=True)

import matplotlib.pyplot as plt
plt.style.use('ggplot')

dt = 0.1

# rolling time average (divided by dt)
def av(lys, dt=1):
    return (1/dt)*cs(array(lys), axis=0)/ar(1, len(lys)+1)
# simple numerical integration
def inte(lys, dt=1):
    return dt*cs(array(lys), axis=0)
# simple numerical differentiation
def numdiff(F, T=None):
    if T is None:
        T = linspace(0, len(F), len(F)//dt+1)
    return array([(F[n+1]-F[n])/(T[n+1]-T[n]) for n in range(len(F)-1)])
# rolling max - make function monotonic
def rm(lys):
    a = [lys[0]]
    for i in lys[1:]:
        a.append(i if i>a[-1] else a[-1])
    return array(a)

Y = []
# load all the entanglement entropies - time average, and add last element to Y
Ds = array([2, 3, 4, 5, 6, 7])
for D in Ds:
    X = load('../../data/S_{}.npy'.format(D))
    T = linspace(0, 300, len(X))
    plt.plot(T, X, label=str(D))
    Y.append(av(X)[-1])
plt.ylabel('$S_E(t)$')
plt.xlabel('$t$')
plt.legend()
plt.savefig('../../images/sat/entanglement.pdf')
plt.show()

dat = array(Y)

# g_ is a linear interpolation of D from saturation entanglement entropy
g_ = interp1d(dat, Ds)

# make a D function that takes an entropy and gives a bond dimension
def D(s):
    if s<min(dat):
        return 2
    if s>max(dat):
        return 8
    else:
        return g_(s)

D = vectorize(D)

plt.scatter(D(dat), dat)
plt.xlabel('$D$')
plt.ylabel('Saturation $S_E$')
plt.savefig('../../images/sat/sat_SE_vs_D.pdf')
plt.show()

# Functions for maximum lyapunov exponent and kolmogorov sinai entropy
Ds_ = array([1, 2, 3, 4, 5, 6, 7, 8])
lamb = load('../../data/exps.npy')
max_l = array(list(map(max, map(abs, lamb))))
ks = array(list(map(sum, map(abs, lamb))))/2

# lambda(D) and KS(D) - data is v. poor for these atm 
max_l = interp1d(Ds_, max_l)
ks = interp1d(Ds_, ks)

fig, ax = plt.subplots(1, 1, figsize=(7, 4))
ax.scatter(Ds_, max_l(Ds_), label='$\lambda_{max}(D)$', marker='x')
ax.scatter(Ds_, ks(Ds_), label='$S_{KS}(D)$', marker='x')
ax.legend()
ax.set_xlabel('$D$')
fig.savefig('../../images/sat/lambda_max_ks.pdf')
plt.show()

fig, ax = plt.subplots(2, 2, sharex=True)
C = load('../../data/otocs.npy')
S = load('../../data/S.npy')
factor = (rm(D(S)))**2
ax[0][0].plot(numdiff(C))
ax[0][0].set_title('$\partial_t C(t)$')
ax[1][0].plot(max_l(rm(D(S))))
ax[1][0].set_title('$\lambda_{max}(D(t))$')
ax[1][1].plot(ks(rm(D(S)))/factor)
ax[1][1].set_title('$S_{KS}(D(t))/D(t)^2$')
ax[0][1].plot(numdiff(S))
ax[0][1].set_title('$\partial_t S_E(t)$')
ax[0][1].set_xlabel('$t$')
ax[1][1].set_xlabel('$t$')
plt.tight_layout()
plt.savefig('../../images/sat/diffC_otoc_lambda_S_ks.pdf')
plt.show()

#########################################################################
#########################################################################
#########################################################################
fig, ax = plt.subplots(1, 1)
T = linspace(0, 100, 1001)
ax.plot(T[:998], numdiff(S), label ='$\partial_t S_E(t)$')
ax.plot(T[:999], ks(rm(D(S)))/factor, label='$S_{KS}(D(t))/(D(t)^2)$')
ax.set_xlabel('$t$', fontsize=15)
plt.xticks(fontsize=15)
plt.yticks(fontsize=15)
plt.legend(prop={'size': 16})
plt.savefig('/Users/fergusbarratt/Desktop/dS_Ks.pdf')
plt.show()
#########################################################################
#########################################################################
#########################################################################

ts = [0]
for Di in Ds:
    if len(rm(D(S))[rm(D(S))==Di]!=0):
        ts.append(ts[-1]+len(rm(D(S))[rm(D(S))==Di]))
ts.append(len(rm(D(S))))
ts = ts[1:]

xs = array(list(unique(rm(D(S))))[1:]+[8])

dS = InterpolatedUnivariateSpline(ts, ks(xs)/array(xs)**2, k=2)

plt.scatter([0]+ts, dS(array([0]+ts)))
T = linspace(0, 100, 1001)
plt.plot(ks(rm(D(S)))/factor)
plt.show()
T_ = range(len(rm(D(S))))
#plt.plot(dS(T)*1.7)
#plt.plot(ks(D(S))/factor)
#plt.show()

fig, ax = plt.subplots(1, 1)
ax.plot(numdiff(S), label ='$\partial_t S_E(t)$')
ax.plot(T_, dS(T_), label='$S_{KS}(D(t))/(D(t)^2)$ (smoothed)')
ax.set_xlabel('$t$')
plt.legend(prop={'size': 17})
plt.savefig('/Users/fergusbarratt/Desktop/dS_Ks_smooth.pdf')
plt.show()

raise Exception
fig, ax = plt.subplots(1, 1)
ax.plot(numdiff(log(C[1:])[10:]), label='$\partial_t ln(C(t)$')
#ax.plot(ks(rm(D(S)))/factor, label='$S_{KS}(D(t))/(D(t)^2)$')
#ax.plot(fl(2*av(fl(max_l(rm(D(S)))[:(len(C)+1)], 0)), 0), label='$2\lambda_{max}(D(t))$')
ax.plot(2*max_l(rm(D(S)))[:(len(C)+1)][10:], label='$2\lambda_{max}(D(t))$')
plt.legend()
#ax.set_ylim([-2, 5])
#plt.savefig('images/sat/dlnC_lmax.pdf')
plt.show()

