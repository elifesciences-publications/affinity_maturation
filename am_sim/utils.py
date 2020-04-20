'''
This file containst utilities to be used in the other libraries.
'''
import numpy as np
import scipy.stats as sps


# --- meta-dictionary

def metadict_append(meta_dict, el):
    '''
    Appends the elements of a results dictionary to corresponding lists in the
    meta-dictionary. If the meta_dict is empty then it also creates the lists.
    '''
    if len(meta_dict) == 0:
        for k in el.keys():
            meta_dict[k] = [el[k]]
    else:
        for k in el.keys():
            meta_dict[k].append(el[k])


# --- distributions


def gaussian_pdf(x, mu, sigma):
    '''
    return a gaussian distribution pdf given mean and standard deviation
    '''
    dx = x[1] - x[0]
    rho_i = sps.norm.pdf(x=x, loc=mu, scale=sigma)
    return rho_i / (np.sum(rho_i) * dx)


def lognorm_pdf(x, dx, mu, sigma, offset):
    '''
    return a lognormal distribution pdf given mu, sigma and offset
    '''
    lognorm = sps.lognorm.pdf(x, s=sigma, loc=offset, scale=np.exp(mu))
    lognorm /= np.sum(lognorm) * dx
    return lognorm


# --- selection functions

def sigmoid_psurv(en, en_thr, a, b, C):
    '''
    Utility function implementing the sigmoid survival probability function.

    Parameters:
    - en (array): energies for which the survival probability must be evaluated
    - en_thr (float): threshold selection energy
    - a,b (float): stochasticity selection parameters
    - C (float): Ag concentration
    '''
    return a + (1. - a - b) / (1. + np.exp(en - en_thr) / C)


def Bsel_psurv(en, C, par):
    '''
    Ag-binding selection survival probability.

    Parameters:
    - en (array): energies for which the survival probability must be evaluated
    - C (float): Ag concentration
    - par: model parameters array
    '''
    if par['B_sel']:
        return sigmoid_psurv(en, en_thr=par['eps_B'], a=0, b=0, C=C)
    else:
        return np.ones_like(en)


def Tsel_psurv(en, bareps, C, par):
    '''
    T-cell help selection survival probability.

    Parameters:
    - en (array): energies for which the survival probability must be evaluated
    - bareps (float): population's bar-epsilon.
    - C (float): Ag concentration
    - par: model parameters array
    '''
    if par['T_sel']:
        a, b = par['a_selection'], par['b_selection']
        return sigmoid_psurv(en, en_thr=bareps, a=a, b=b, C=C)
    else:
        return np.ones_like(en)


# --- concentration evolution


def next_ag_concentration(C_av, C_res, k_minus, k_plus):
    '''
    Perform one evolution step for the available and reservoir concentrations.
    Notice that k_minus and k_plus must be in units of turns, not of days.
    '''
    nrc = C_res * np.exp(-k_plus)
    nac = C_av * np.exp(-k_minus)
    nac += C_res * (k_plus / (k_plus - k_minus)) * \
        (np.exp(-k_minus) - np.exp(-k_plus))
    return nac, nrc


# --- differentiation


def prob_mc_pc_differentiation(par, t_rounds):
    '''
    Given the set of parameters and the evolution time in rounds returns the
    probability of mc and pc differentiation.

    Parameters:
    - par: parameters dictionary
    - t_rounds (int): evolution time in rounds

    Returns:
    - p_mc, p_pc (float): probabilities of MC and PC differentiation.
    '''
    p_diff = par['diff_prob']
    days_per_round = par['days_per_turn']
    sw_t = par['diff_switch_time'] / days_per_round
    sigma_t = par['diff_switch_sigma'] / days_per_round
    residual_f = par['diff_residual_fraction']
    # if no switch time then same probability of MC/PC fate
    if sw_t is None:
        return p_diff / 2., p_diff / 2.
    # if switch time but no sigma then hard switch
    elif sigma_t is None:
        p_main, p_res = p_diff * (1. - residual_f), p_diff * residual_f
        return (p_main, p_res) if t <= sw_t else (p_res, p_main)
    # else sigmoid switch
    else:
        fr_mc = residual_f + (1. - 2. * residual_f) / \
            (1. + np.exp((t - sw_t) / sigma_t))
        return p_diff * fr_mc, p_diff * (1. - fr_mc)

# --- GC seeding (stochastic GC)


def pick_founders_en(par, mc_seed_energies):
    '''
    Utility function for determining the founder clones population of a GC.
    It takes as argument the parameter dictionary and the list of MCs
    previously collected during evolution.

    It returns the list of founder clones, randomly picked between memory and
    naive cells according to the model specifications.

    Parameters:
    - par: model parameters dictionary
    - mc_seed_energies (array): list of energies for the MCs collected so far
        in evolution.
    '''
    par_mc_reinit = par['f_mem_reinit']
    Ni = par['N_i']
    Nf = par['N_founders']
    Nmc = mc_seed_energies.size
    # evaluate probability that a clone comes from the memory pool
    if par_mc_reinit == 'pop':
        # proportional to the size of the MC population
        pr_mc = Nmc / (Ni + Nmc)
    else:
        # constant
        pr_mc = par_mc_reinit

    # pick founders among MC + Naive cells
    N_mem_founders = np.random.binomial(n=Nf, p=pr_mc)
    en_founders = np.zeros(Nf)
    # add memory founders
    en_founders[:N_mem_founders] = np.random.choice(
        mc_seed_energies, N_mem_founders, replace=Nmc < N_mem_founders)
    # add naive founders
    en_founders[N_mem_founders:] = np.random.normal(
        loc=par['mu_i'], scale=par['sigma_i'], size=Nf - N_mem_founders)

    return en_founders


# --- mutations

def generate_stoch_mutations(par, N_mut):
    '''
    Generates log-normal distributed random mutations.

    Parameters:
    - par: model parameters dictionary
    - N_mut (int): number of mutations to be generated

    Returns:
    - delta_en (array): list of energy differences caused by mutation.
    '''
    delta_en = np.random.lognormal(
        mean=par['ker_ln_mu'], sigma=par['ker_ln_sigma'],
        size=N_mut) + par['ker_ln_offset']
    return delta_en


def mutation_kernel(par):
    '''
    Builds the total mutation kernel...
    '''
    # build x-bins
    dx = par['dx']
    ker_x = np.arange(0., par['ker_xlim'], dx)
    ker_x = np.concatenate((-ker_x[:0:-1], ker_x))

    # build affinity-affecting mutations kernel (lognormal distribution)
    ker_aa = lognorm_pdf(x=ker_x, dx=dx,
                         mu=par['ker_ln_mu'],
                         sigma=par['ker_ln_sigma'],
                         offset=par['ker_ln_offset'])

    # build kernel for silent mutations (delta on zero)
    nxk = len(ker_x)
    delta = np.zeros(nxk)
    delta[nxk // 2] = 1. / dx

    # building total kernel for a single mutation
    ker_one = par['p_aa_eff'] * ker_aa + par['p_sil_eff'] * delta

    # include the effect of duplication
    ker_one *= 2

    # build total kernel for n mutations and duplication (kernel self-convolution)
    ker_tot = np.copy(ker_one)
    for m in range(par['n_duplications'] - 1):
        ker_tot = np.convolve(ker_tot, ker_one, 'same') * dx

    return ker_x, ker_tot
