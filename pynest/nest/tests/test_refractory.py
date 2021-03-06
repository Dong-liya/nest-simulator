# -*- coding: utf-8 -*-
#
# test_refractory.py
#
# This file is part of NEST.
#
# Copyright (C) 2004 The NEST Initiative
#
# NEST is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# NEST is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with NEST.  If not, see <http://www.gnu.org/licenses/>.

import unittest

import numpy as np

import nest

"""
Assert that all neuronal models that have a refractory period implement it
correctly (except for Hodgkin-Huxley models which cannot be tested).

Details
-------
Submit the neuron to a constant excitatory current so that it spikes in the
[0, 50] ms.
A ``spike_detector`` is used to detect the time at which the neuron spikes and
a ``voltmeter`` is then used to make sure the voltage is clamped to ``V_reset``
during exactly ``t_ref``.

For neurons that do not clamp the potential, use a very large current to
trigger immediate spiking

Untested models
---------------
* ``aeif_cond_alpha_RK5``
* ``gif_pop_psc_exp``
* ``hh_cond_exp_traub``
* ``hh_psc_alpha``
* ``hh_psc_alpha_gap``
* ``iaf_psc_exp_ps_lossless``
* ``sli_neuron``
* ``siegert_neuron``
"""


# --------------------------------------------------------------------------- #
#  Models, specific parameters
# --------------------------------------------------------------------------- #

# Neurons that must be tested through a high current to spike immediately
# (t_ref = interspike)
neurons_interspike = [
    "amat2_psc_exp",
    "ht_neuron",
    "mat2_psc_exp",
]

neurons_interspike_ps = [
    "iaf_psc_alpha_canon",
    "iaf_psc_alpha_presc",
    "iaf_psc_delta_canon",
    "iaf_psc_exp_ps",
]

# Models that cannot be tested
ignore_model = [
     "aeif_cond_alpha_RK5",      # This one is faulty and will be removed
     "gif_pop_psc_exp",          # This one commits spikes at same time
     "hh_cond_exp_traub",        # This one does not support V_reset
     "hh_psc_alpha",             # This one does not support V_reset
     "hh_psc_alpha_gap",         # This one does not support V_reset
     "iaf_psc_exp_ps_lossless",  # This one use presice times
     "sli_neuron",               # This one is not optimal for PyNEST
     "siegert_neuron",           # This one does not connect to voltmeter
]

tested_models = [m for m in nest.Models("nodes") if (nest.GetDefaults(
                 m, "element_type") == "neuron" and m not in ignore_model)]

# Additional parameters for the connector
add_connect_param = {
    "iaf_cond_alpha_mc": {"receptor_type": 7},
}


# --------------------------------------------------------------------------- #
#  Simulation time and refractory time limits
# --------------------------------------------------------------------------- #

simtime = 100
resolution = 0.1


# --------------------------------------------------------------------------- #
#  Test class
# --------------------------------------------------------------------------- #


class TestRefractoryCase(unittest.TestCase):
    """
    Check the correct implementation of refractory time in all neuronal models.
    """

    def reset(self):
        nest.ResetKernel()

        msd = 123456
        N_vp = nest.GetKernelStatus(['total_num_virtual_procs'])[0]

        nest.SetKernelStatus({
            'resolution': resolution,
            'grng_seed': msd + N_vp,
            'rng_seeds': range(msd + N_vp + 1, msd + 2 * N_vp + 1)})

    def compute_reftime(self, model, sd, vm, neuron):
        '''
        Compute the refractory time of the neuron.

        Parameters
        ----------
        model : str
          Name of the neuronal model.
        sd : tuple
            GID of the spike detector.
        vm : tuple
            GID of the voltmeter.
        neuron : tuple
            GID of the recorded neuron.

        Returns
        -------
        t_ref_sim : double
            Value of the simulated refractory period.
        '''
        spike_times = nest.GetStatus(sd, "events")[0]["times"]

        if model in neurons_interspike:
            # Spike emitted at next timestep so substract resolution
            return spike_times[1]-spike_times[0]-resolution
        elif model in neurons_interspike_ps:
            return spike_times[1]-spike_times[0]
        else:
            Vr = nest.GetStatus(neuron, "V_reset")[0]
            times = nest.GetStatus(vm, "events")[0]["times"]

            # Index of the 2nd spike
            idx_max = np.argwhere(times == spike_times[1])[0][0]
            name_Vm = "V_m.s" if model == "iaf_cond_alpha_mc" else "V_m"
            Vs = nest.GetStatus(vm, "events")[0][name_Vm]

            # Get the index at which the spike occured
            idx_spike = np.argwhere(times == spike_times[0])[0][0]

            # Find end of refractory period between 1st and 2nd spike
            idx_end = np.where(
                np.isclose(Vs[idx_spike:idx_max], Vr, 1e-6))[0][-1]
            t_ref_sim = idx_end * resolution

            return t_ref_sim

    def test_refractory_time(self):
        '''
        Check that refractory time implementation is correct.
        '''
        for model in tested_models:
            self.reset()

            if "t_ref" not in nest.GetDefaults(model):
                continue

            # Randomly set a refractory period
            t_ref = 1.7
            # Create the neuron and devices
            nparams = {"t_ref": t_ref}
            neuron = nest.Create(model, params=nparams)

            name_Vm = "V_m.s" if model == "iaf_cond_alpha_mc" else "V_m"
            vm_params = {"interval": resolution, "record_from": [name_Vm]}
            vm = nest.Create("voltmeter", params=vm_params)
            sd = nest.Create("spike_detector", params={'precise_times': True})
            cg = nest.Create("dc_generator", params={"amplitude": 900.})

            # For models that do not clamp V_m, use very large current to
            # trigger almost immediate spiking => t_ref almost equals
            # interspike
            if model in neurons_interspike_ps:
                nest.SetStatus(cg, "amplitude", 10000000.)
            elif model == 'ht_neuron':
                # ht_neuron use too long time with a very large amplitude
                nest.SetStatus(cg, "amplitude", 2000.)
            elif model in neurons_interspike:
                nest.SetStatus(cg, "amplitude", 15000.)

            # Connect them and simulate
            nest.Connect(vm, neuron)
            nest.Connect(cg, neuron, syn_spec=add_connect_param.get(model, {}))
            nest.Connect(neuron, sd)

            nest.Simulate(simtime)

            # Get and compare t_ref
            t_ref_sim = self.compute_reftime(model, sd, vm, neuron)

            # Approximate result for precise spikes (interpolation error)
            if model in neurons_interspike_ps:
                self.assertAlmostEqual(t_ref, t_ref_sim, places=3,
                                       msg='''Error in model {}:
                                       {} != {}'''.format(
                                           model, t_ref, t_ref_sim))
            else:
                self.assertAlmostEqual(t_ref, t_ref_sim,
                                       msg='''Error in model {}:
                                       {} != {}'''.format(
                                           model, t_ref, t_ref_sim))


# --------------------------------------------------------------------------- #
#  Run the comparisons
# --------------------------------------------------------------------------- #

def suite():
    return unittest.makeSuite(TestRefractoryCase, "test")


def run():
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite())


if __name__ == '__main__':
    run()
