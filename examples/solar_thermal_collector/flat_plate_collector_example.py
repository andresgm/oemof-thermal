# -*- coding: utf-8 -*-

"""
Example to show the functionality of the solar thermal collector
with a fixed collector size (aperture area).

authors: Franziska Pleissner, Caroline Möller

SPDX-License-Identifier: GPL-3.0-or-later
"""
import os

import pandas as pd

from oemof import solph
from oemof.tools import economics
from oemof.thermal.solar_thermal_collector import flat_plate_precalc
import oemof.outputlib as outputlib
from plots import plot_collector_heat


# set paths
base_path = os.path.dirname(os.path.abspath(os.path.join(__file__)))
data_path = os.path.join(base_path, 'data/')
results_path = os.path.join(base_path, 'results/')
if not os.path.exists(results_path):
    os.mkdir(results_path)

# parameters for the precalculation
periods = 48
latitude = 52.2443
longitude = 10.5594
collector_tilt = 10
collector_azimuth = 20
a_1 = 1.7
a_2 = 0.016
eta_0 = 0.73
temp_collector_inlet = 20
delta_temp_n = 10

# input data
input_data = pd.read_csv(data_path + 'data_flat_collector.csv').head(periods)
input_data['Datum'] = pd.to_datetime(input_data['Datum'])
input_data.set_index('Datum', inplace=True)
input_data.index = input_data.index.tz_localize(tz='Europe/Berlin')
input_data = input_data.asfreq('H')

demand_df = pd.read_csv(
    os.path.join(base_path, 'data', 'heat_demand.csv'),
    sep=','
)
demand = list(demand_df['heat_demand'].iloc[:periods])

# precalculation
# - calculate global irradiance on the collector area
# and collector efficiency depending on the
# temperature difference -
precalc_data = flat_plate_precalc(
    latitude,
    longitude,
    collector_tilt,
    collector_azimuth,
    eta_0,
    a_1,
    a_2,
    temp_collector_inlet,
    delta_temp_n,
    irradiance_global=input_data['global_horizontal_W_m2'],
    irradiance_diffuse=input_data['diffuse_horizontal_W_m2'],
    temp_amb=input_data['temp_amb'],
)

precalc_data.to_csv(
    os.path.join(results_path, 'flat_plate_precalcs.csv'),
    sep=';'
)


# regular oemof system #

# parameters for the energy system
peripheral_losses = 0.05
elec_consumption = 0.02
backup_costs = 40
costs_storage = economics.annuity(20, 20, 0.06)
costs_electricity = 1000
storage_loss_rate = 0.001
conversion_storage = 0.98
size_collector = 10  # m2

# busses
bth = solph.Bus(label='thermal')
bel = solph.Bus(label='electricity')
bcol = solph.Bus(label='solar')

# source for collector heat.
# - actual_value is the precalculated collector heat -
collector_heat = solph.Source(
    label='collector_heat',
    outputs={
        bcol: solph.Flow(
            fixed=True,
            actual_value=precalc_data['collectors_heat'],
            nominal_value=size_collector,
        )
    },
)

# sources and sinks
el_grid = solph.Source(
    label='grid', outputs={bel: solph.Flow(variable_costs=costs_electricity)}
)

backup = solph.Source(
    label='backup', outputs={bth: solph.Flow(variable_costs=backup_costs)}
)

consumer = solph.Sink(
    label='demand',
    inputs={bth: solph.Flow(fixed=True, actual_value=demand, nominal_value=1)},
)

collector_excess_heat = solph.Sink(
    label='collector_excess_heat', inputs={bcol: solph.Flow()}
)

# transformer and storage
collector = solph.Transformer(
    label='collector',
    inputs={bcol: solph.Flow(), bel: solph.Flow()},
    outputs={bth: solph.Flow()},
    conversion_factors={
        bcol: 1,
        bel: elec_consumption * (1 - peripheral_losses),
        bth: 1 - peripheral_losses
    },
)

storage = solph.components.GenericStorage(
    label='storage',
    inputs={bth: solph.Flow()},
    outputs={bth: solph.Flow()},
    loss_rate=storage_loss_rate,
    inflow_conversion_factor=conversion_storage,
    outflow_conversion_factor=conversion_storage,
    investment=solph.Investment(ep_costs=costs_storage),
)

# build the system and solve the problem
date_time_index = input_data.index
energysystem = solph.EnergySystem(timeindex=date_time_index)

energysystem.add(
    bth,
    bcol,
    bel,
    collector_heat,
    el_grid,
    backup,
    consumer,
    collector_excess_heat,
    storage,
    collector,
)

model = solph.Model(energysystem)
model.solve(solver='cbc', solve_kwargs={'tee': True})

# save model results to csv
results = outputlib.processing.results(model)

electricity_bus = outputlib.views.node(results, 'electricity')['sequences']
thermal_bus = outputlib.views.node(results, 'thermal')['sequences']
solar_bus = outputlib.views.node(results, 'solar')['sequences']
df = pd.merge(
    pd.merge(electricity_bus, thermal_bus, left_index=True, right_index=True),
    solar_bus, left_index=True, right_index=True)
df.to_csv(results_path + 'flat_plate_results.csv')

# Example plot
plot_collector_heat(precalc_data, periods, eta_0)
