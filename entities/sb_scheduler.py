"""
Author: David Ho Dac

- to install pulp, a simple pip install pulp should be enough
- Gurobi is used by pulp in the scheduling, to install it, if you have anaconda just do "sudo conda install gurobi"
"""

import os, inspect
from pulp import *
import json
import numpy as np
import logging
from gurobipy import *
import time

cmd_folder = os.path.realpath(os.path.abspath(os.path.split(inspect.getfile(inspect.currentframe()))[0]))
logger = logging.getLogger('sgEntityProcess.model.sbScheduler')


class Load(object):

    def __init__(self, id, power, st, et):
        self._id = id
        self._power = power
        self._st = st
        self._et = et

    @property
    def id(self):
        return self._id

    @property
    def power(self):
        return self._power

    @property
    def st(self):
        return self._st

    @property
    def et(self):
        return self._et


# Load Scheduler class
# the building_info file configuration is supposed to be known
# In it, the loads are defined with a 15min interval, and the electricity price signal with an 1h interval
# those two values are hardcoded inside the class
class OptiLoadScheduler(object):

    TIME_STEP_LOAD_PROFILE = 15*60

    def __init__(self, config_path):
        # list of Load objects
        self._list_shift_loads = []
        self._config_path = config_path

    # init the list of Load objects for the corresponding building
    # interpolates the value based on default 15min-load indexing (in config) (hardcoded)
    # assumption : one load can be used only once
    def init_loads(self, building_id, time_data, current_schedule):
        t_start, t_end, time_step = time_data
        building_info = json.load(open(cmd_folder+"/"+self._config_path))

        # if we are in day-ahead phase (loads are not scheduled yet)
        if t_start == 0:
            for (load, val) in building_info["loads"].items():
                if int(load) in building_info["buildings"][str(building_id)]:
                    pow = np.interp(np.linspace(time_step, len(val["power"])*time_step, (len(val["power"])*self.TIME_STEP_LOAD_PROFILE/time_step)), np.linspace(self.TIME_STEP_LOAD_PROFILE, len(val["power"])*self.TIME_STEP_LOAD_PROFILE, len(val["power"])), val["power"]).astype(int)
                    l = Load(int(load), pow, val["st"], val["et"])
                    self._list_shift_loads.append(l)

        # if day has started and microgrid is updating it's forecast
        else:
            for (load, val) in building_info["loads"].items():
                if int(load) in building_info["buildings"][str(building_id)]:
                    # takes loads that haven't been launched yet
                    if current_schedule.get(int(load)) >= t_start:
                        pow = np.interp(np.linspace(time_step, len(val["power"])*time_step, (len(val["power"])*self.TIME_STEP_LOAD_PROFILE/time_step)), np.linspace(self.TIME_STEP_LOAD_PROFILE, len(val["power"])*self.TIME_STEP_LOAD_PROFILE, len(val["power"])), val["power"]).astype(int)
                        l = Load(int(load), pow, max(val["st"] - t_start, 0), max(val["et"] - t_start, 0))
                        self._list_shift_loads.append(l)

    def schedule_loads(self, time_data, optimization_data):
        """
        This method select a starting time of the load to be scheduled, contained in self._list_shift_loads and store
        the information in self._scheduled_loads.
        :param time_data: a tuple (t_start, t_end, t_step) where:
                - t_0 is the instant corresponding to the first value of the returned vector (in seconds)
                - t_hor is the length of the time period of the returned vector of data
                - t_step is the time interval between two values of the returned vector of data
        :param optimization_data: a dict of data used for the optimization:
            - 'price_elec'
            - 'max_power'
        :return: /
        """

        t_start, t_end, dt = time_data
        hor = int((t_end-t_start)/dt)

        # Extract the parameters for the optimization
        elec_price = None
        max_power = None
        if 'price_elec' in optimization_data.keys():
            elec_price = optimization_data['price_elec']
        if 'max_power' in optimization_data.keys():
            max_power = optimization_data['max_power']

        R = 10.0**3 # Max power factor (indicative values : 10.0**-3 finds the optimal cost, 10.0**3 finds the optimal PAR)
        sampling_rate = self.TIME_STEP_LOAD_PROFILE # Sampling rate of the load power profile; corresponds to the t_step (and CONTROLLER_TIME_STEP) variable

        # Interval number
        interval_number = int(hor/dt)
        # Creation of useful lists for MILP variables
        intervals = range(0, interval_number)
        loads_range = range(0, len(self._list_shift_loads))
        # List with all possible load states
        states = [(j, i) for j in loads_range for i in intervals]
        # Creation of f cost function, vector (cost of electricity for each t.i for each load)
        en_cost = []
        for j in range(0, len(self._list_shift_loads)):  # foreach load j
            en_cost.append([self.energy_cost_turn_on(elec_price, j, i, dt / 3600.0, sampling_rate) for i in
                            range(0, interval_number)])  # append sublist of all intervals i

        # ------------- PuLP ------------------
        # Creation of PuLP variables containing the MILP problem data
        prob = LpProblem('Cost', LpMinimize)
        prob_2 = LpProblem('Power', LpMinimize)
        # Creation of x vector containing all the variables xji
        x = LpVariable.dicts('x', (loads_range, intervals), 0, None, LpBinary)
        # Creation of max power variable
        e_max_power = LpVariable.dicts('e_max_power',intervals, 0, 10 ** 3, LpContinuous)
        # Adding the objective function to the subproblem
        prob += lpSum([en_cost[j][i] * x[j][i] / R for (j, i) in states]), 'Total cost of energy of all loads'
        # Adding the epsilon max power to the subproblem
        prob_2 += lpSum([e_max_power[i] for i in intervals]), 'Maximum power'
        # Form a unique problem
        prob.extend(prob_2)

        # Definition of the constraints
        # Unique turn-on constraint (did also control the out of bound. have to put other time constraints)
        for j in loads_range:
            prob += lpSum([x[j][i] for i in intervals if (i + len(self._list_shift_loads[j].power) <= interval_number)]) == 1, ''

        # Max power constraint
        for i in intervals:
            tmp = []
            for j in loads_range:
                # Computes inequalities containing current power consumption of loads possibly turned on in a previons interval
                sampled_consumption = self._list_shift_loads[j].power
                tmp += [sampled_consumption[ia] * x[j][i - ia] for ia in range(0, len(sampled_consumption)) if ia <= i]
            prob += lpSum(tmp) <= max_power + e_max_power[i], ''

        # Time constraint
        for j in loads_range:
            sampled_consumption = self._list_shift_loads[j].power
            prob += lpSum([x[j][i] for i in intervals if (self._list_shift_loads[j].st <= i * dt<= (
                    self._list_shift_loads[j].et ))]) == 1, '' #- len(sampled_consumption) * dt

        # Solving the problem
        prob.solve(GUROBI())
        # Manipulating the loads : scheduling
        schedule = {}
        for j in loads_range:
            for i in intervals:
                x_val = x[j][i].varValue
                if x_val == 1:
                    #print("load num: {} or id: {} starts".format(j,self._list_shift_loads[j].id ))
                    load_start_time = x[j][i].varValue * i * dt     # calculates starting time
                    load_id = self._list_shift_loads[j].id     # gets load_id
                    schedule[load_id] = load_start_time     # adds to schedule
        print schedule
        return schedule

    def energy_cost_turn_on(self, elec_price, num_load, interval, dt, sampling_rate):
        """
        Auxiliary method that computes the cost in energy to turn on load num_load at interval interval

        :param elec_price: electricity price vector
        :param num_load: number of current load
        :param interval:    current interval
        :param dt:  time interval [hours]
        :param sampling_rate: sampling rate of the load power profile
        :return:    cost in energy to turn on load num_load at interval interval
        """

        # The price is given in dollar/kWh, and here we want cent/Wh, so need to divide by 10 (* 100 / 1000)
        adjust_factor = 1/10.0

        load_obj = self._list_shift_loads[num_load]
        load_profile = load_obj.power # list of interpolated power consumptions for the corresponding time points
        cost = 0
        for k in range(len(load_profile)): # k from 0 to number of samples of load l use getsampled
            if interval+k >= len(elec_price): # prevents looking at prices outside of area of interest
                return 10**6
            cost += load_profile[k] * (1*dt) * elec_price[interval+k] * adjust_factor # increments the cost for each interval when the load is on

        return cost

    # converts a load time start dict in a complete power profile
    def schedule_power_vector(self, schedule, time_data):

        # Extract the time info
        t_start, t_end, time_step = time_data

        p = np.array([0 for i in range(int((t_end-t_start)/time_step))])
        for l_id, sch_time in sorted(schedule.items()):
            rel_sch_time = (sch_time-t_start)  # sch_time is an absolute value in the day
            for load in self._list_shift_loads:
                if load.id == l_id:
                    p[int(rel_sch_time/time_step):int(rel_sch_time/time_step)+len(load.power)] += np.array(load.power)

        return p.tolist()


# Load scheduler that takes into accout the power profiles of the other buildings/local generation
class InteractiveLoadScheduler(OptiLoadScheduler):

    def schedule_loads(self, time_data, optimization_data):
        """
        This method select a starting time of the load to be scheduled, contained in self._list_shift_loads and store
        the information in self._scheduled_loads.
        :param time_data: a tuple (t_0, t_hor, t_step) where:
                - t_0 is the instant corresponding to the first value of the returned vector (in seconds)
                - t_hor is the length of the time period of the returned vector of data
                - t_step is the time interval between two values of the returned vector of data
        :param optimization_data: a dict of data used for the optimization:
            - 'price_elec': a dictionary containing the keys: "energy_price", "quad_price", and "local_price"
            - 'external_consumption'
            - 'external_gen'
            - 'max_power'
        :return: /
        """

        # Extract the parameters for the optimization
        t_start, t_end, dt = time_data

        # Interval number
        interval_number = int((t_end - t_start) / dt)
        # Creation of useful lists for MILP variables
        intervals = range(interval_number)
        loads_range = range(0, len(self._list_shift_loads))
        # List with all possible load states
        states = [(j, i) for j in loads_range for i in intervals]

        elec_price = {}
        max_power = None

        external_consumption = interval_number * [0]
        external_gen = interval_number * [0]

        if 'price_elec' in optimization_data.keys():
            elec_price = optimization_data['price_elec']
        if 'external_consumption' in optimization_data.keys():
            external_consumption = optimization_data['external_consumption']
        if 'external_gen' in optimization_data.keys():
            external_gen = optimization_data['external_gen']
        if 'max_power' in optimization_data.keys():
            max_power = optimization_data['max_power']

        logger.debug("Horizon is %s steps, loads to schedule: %s", interval_number, len(self._list_shift_loads))

        elec_balance = np.add(external_consumption, np.negative(external_gen))
        external_grid_con = elec_balance.clip(min=0)
        elec_balance = np.negative(elec_balance)
        remaining_gen = elec_balance.clip(min=0)

        logger.debug("Data coming from the rest of the microgrid: total demand: %s [W] | local gen: %s [W]", external_grid_con, remaining_gen)

        # ==============================================
        # GUROBIPY  (needs installation of gurobi + pip install gurobipy)
        # ==============================================

        # Creation of a new model
        m = Model("interactive")

        # Definition of variables and Objective ==========================

        x = m.addVars(states, vtype=GRB.BINARY, name="x")  #tupledict object
        y = m.addVars(intervals, lb=0, vtype=GRB.CONTINUOUS, name="y")  #total consumption from grid
        y_i_m = m.addVars(intervals, lb=0, vtype=GRB.CONTINUOUS, name="y_i_m")  #individual consumption from grid
        y_i_res = m.addVars(intervals, lb=0, vtype=GRB.CONTINUOUS, name="y_i_res")  #individual consumption from RES
        init_loads_weight = m.addVars(intervals, lb=0, name="init_loads_weight")  #tupledict object

        m.update()

        obj = 0.0
        # Creation of a linear expression that will benefit loads that are launched first in time

        logger.debug("--> Gurobi variables have been initialized")

        weight_early_load = 1  # This coefficient to ensure that sum(weight_early_load * init_loads_weight) << rest of the objective

        # THE OBJECTIVE FUNCTION
        if "quad_price" in elec_price.keys() and sum(external_grid_con) > 0:
            for i in intervals:
                obj += (y_i_m[i]/1000.0 * y_i_m[i]/1000.0 + 2 * y_i_m[i]/1000.0 * external_grid_con[i]/1000.0) * elec_price["quad_price"][i]

        if "energy_price" in elec_price.keys():
            for i in intervals:
                obj += y[i]/1000.0 * elec_price["energy_price"][i]

        if "local_price" in elec_price.keys():
            for i in intervals:
                obj += y_i_res[i]/1000.0 * elec_price["local_price"][i]

        # Linear expression to prioritize loads scheduled earlier in time
        # for i in intervals:
        #     obj += init_loads_weight[i] * weight_early_load

        m.setObjective(obj, GRB.MINIMIZE)

        logger.debug("--> Gurobi problem has been set (minimize e + l_res)")

        # Unique turn-on constraint (did also control the out of bound. have to put other time constraints)
        for j in loads_range:
            sum_local = quicksum([x[j, i] for i in intervals if ((i + len(self._list_shift_loads[j].power)) <= interval_number)])
            m.addConstr(sum_local, "=", 1, name='load_boundary')

        # Max power constraint
        if max_power != None:
            for i in intervals:
                tmp = []
                for j in loads_range:
                    sampled_consumption = self._list_shift_loads[j].power
                    tmp += [sampled_consumption[ia] * x[j, (i - ia)] for ia in range(0, len(sampled_consumption)) if ia <= i]
                m.addConstr(quicksum(tmp), "<=", max_power, name='max_power')

        # Time constraint
        for j in loads_range:
            s = quicksum([x[j, i] for i in intervals if (self._list_shift_loads[j].st <= (i * dt) <= (self._list_shift_loads[j].et - len(self._list_shift_loads[j].power)))])
            m.addConstr(s, "=", 1, name='only_one_starting_time')

        # Linear expression added to model to benefit loads scheduled earlier in time
        init_weight=[0] * interval_number
        for i in intervals:
            for j in loads_range:
                init_weight[i] += x[j, i]*i
            m.addConstr(init_loads_weight[i], "=", init_weight[i], name='init_load_weight')

        # Definition of y and y_i_res through constraints
        for i in intervals:
            tmp = []
            total_m_con = []
            for j in loads_range:
                sampled_consumption = self._list_shift_loads[j].power
                tmp += [sampled_consumption[ia] * x[j, (i - ia)] for ia in range(0, len(sampled_consumption)) if ia <= i]
            # total individual consumption = y from grid + y from res
            m.addConstr(quicksum(tmp), "=", y_i_m[i]+y_i_res[i], name='grid_demand_breakdown_def')
            # consumption from RES smaller than remaining RES generation
            m.addConstr(y_i_res[i], "<=", remaining_gen[i], name='local_gen_limit')
            # adding the external consumption from grid
            total_m_con = [y_i_m[i] + external_grid_con[i]]
            m.addConstr(quicksum(total_m_con), "=", y[i], name='macrogrid_consumption_def')
            # intrinsic boundaries
            m.addConstr(y_i_res[i], ">=", 0, name='positive_local_cons')
            m.addConstr(y_i_m[i], ">=", 0, name='positive_macrogrid_cons')
            m.addConstr(y[i], ">=", 0, name='positive_cons')

        # Solving ========================================
        m.update()
        m.setParam('OutputFlag', False)
        m.optimize()

        e_y, e_y_l, l_y, l_weight = 0, 0, 0, 0

        if "energy_price" in elec_price.keys():
            for i in intervals:
                e_y_l += y[i].X/1000.0 * elec_price["energy_price"][i]

        if "quad_price" in elec_price.keys():
            for i in intervals:
                e_y += y[i].X/1000.0 * y[i].X/1000.0 * elec_price["quad_price"][i]

        if "local_price" in elec_price.keys():
            for i in intervals:
                l_y += y_i_res[i].X/1000.0 * elec_price["local_price"][i]

        for i in intervals:
            l_weight += init_loads_weight[i].X * weight_early_load

        logger.debug("Guroby has solved the problem")
        logger.debug(" - Total Objective function sol: %s", m.ObjVal)
        logger.debug(" --- Objective function macrogrid quad term: %s", e_y)
        logger.debug(" --- Objective function macrogrid lin term: %s", e_y_l)
        logger.debug(" --- Objective function RES term: %s", l_y)
        logger.debug(" --- Objective function init_load_weight term: %s ", l_weight)

        # Manipulating the loads : scheduling
        schedule = {}
        for j in loads_range:
            for i in intervals:
                x_val = round(x[j, i].X)
                if x_val == 1:
                    load_start_time = t_start + x[j, i].X * i * dt  # calculates starting time
                    load_id = self._list_shift_loads[j].id  # gets load_id
                    schedule[load_id] = load_start_time  # adds to schedule

        logger.debug("New schedule: %s", schedule)

        return schedule
