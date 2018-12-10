import os, sys, inspect
currentdir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))
parentdir = os.path.dirname(os.path.dirname(currentdir))
sys.path.insert(0,parentdir)

from fMPS import fMPS
from tdvp.tdvp_fast import MPO_TFI
from fTDVP import Trajectory
from spin import N_body_spins, spins, n_body
from numpy import load, linspace, save, sum, log, array, cumsum as cs
from numpy import arange as ar, mean
from numpy.linalg import eigvalsh
import matplotlib.pyplot as plt
import matplotlib as mpl
from tensor import H as cT, C as c
from tqdm import tqdm
mpl.style.use('ggplot')
L = 6
S_list = [N_body_spins(0.5, n, L) for n in range(1, L+1)]
i = 3
j = 3
Sxi, Syi, Szi = S_list[i]
Sxj, Syj, Szj = S_list[j]

Sx1, Sy1, Sz1 = N_body_spins(0.5, 1, 2)
Sx2, Sy2, Sz2 = N_body_spins(0.5, 2, 2)

ent = Sz1@Sz2
loc = Sx1+Sz1, Sx2+Sz2

listH = [ent+loc[0]+loc[1]] + [ent+loc[1] for _ in range(L-2)]
fullH = sum([n_body(a, i, len(listH), d=2) for i, a in enumerate(listH)], axis=0)
D = 8
L = 6
v = eigvalsh(fullH)
E = (max(v)-min(v))/2.5
N = 10

# generate a list of product states with the same energy
mpss = [fMPS().random_with_energy_E(E, listH, L, 2, 1) 
        for _ in tqdm(range(500))]

extras = []
for mps in tqdm(mpss):
    extras += Trajectory(fMPS().load('fixtures/product{}.npy'.format(L)),
                       H=listH,
                       W=L*[MPO_TFI(0, 0.25, 0.5, 0.)]).invfreeint(
                       linspace(0, 10, 50), 'high').mps_list()

mpss += extras

otocss = []
for mps in mpss:
    T = linspace(0, 100, 1000)
    ops = Szi, Szj 
    otocs = array(Trajectory(mps, fullH, fullH=True).ed_OTOC(T, ops))
    otocss.append(otocs)

fig, ax = plt.subplots(1, 1, sharex=True)
ax.plot(T, array(otocss).T)
ax.plot(T,  mean(array(otocss), axis=0), c='black', label='$\\overline{C(t)}$')
ax.set_ylabel('$C(t)$')
ax.set_xlabel('t')
plt.legend()
#plt.savefig('images/sat/C.pdf')
#save('data/otocs', mean(array(otocss), axis=0))

#ma = mean(otocss, axis=0)
#plt.plot(log(ma)-log(ma)[1])
plt.show()
#save('data/otocs', log(ma)-log(ma)[1])

#fig, ax = plt.subplots(1, 1, sharex=True)
#ax.set_title('$Sz{}, Sz{}$'.format(i+1, j+1))
##ax.plot(T, log(otocs)-log(otocs)[1])
#fig.tight_layout()
##fig.savefig('images/spectra/otoc.pdf')
#plt.show()
