from numpy import load
import matplotlib.pyplot as plt
import matplotlib as mpl
mpl.style.use('ggplot')

A = load('data/spectra/lyapunovs_L8_D1_N20400.npy')[-1000:]
B = load('data/spectra/lyapunovs_L8_D2_N20400.npy')[-1000:]
C = load('data/spectra/lyapunovs_L8_D3_N20400.npy')[-1000:]
D = load('data/spectra/lyapunovs_L8_D4_N20400.npy')[-1000:]
E = load('data/spectra/lyapunovs_L8_D5_N20400.npy')[-1000:]
F = load('data/spectra/lyapunovs_L8_D6_N20400.npy')[-1000:]
G = load('data/spectra/lyapunovs_L8_D7_N20400.npy')[-1000:]
#H = load('data/spectra/lyapunovs_L8_D8_N20400.npy')[-1000:]

data = [A, B, C, D, E, F, G]
Ds = [1, 2, 3, 4, 5, 6, 7]
fig, ax = plt.subplots(7, 1, sharex=True, sharey=True, figsize=(4, 10))
for m, x in enumerate(data):
    ax[m].plot(x)
    ax[m].set_title('D='+str(Ds[m]), loc='right')
fig.tight_layout()
#plt.savefig('images/spectra/conv.pdf', bbox_inches='tight')
plt.show()

