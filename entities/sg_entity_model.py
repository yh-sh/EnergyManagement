__author__ = 'Olivier Van Cutsem'

import os, inspect
from abc import abstractmethod
import pandas as pd
import logging
from sg_entity_param import *
import numpy as np
from sb_scheduler import OptiLoadScheduler, InteractiveLoadScheduler
from fault_management import FaultForecast
import json
#
### Generic model of a Smart Grid Entity
#

cmd_folder = os.path.realpath(os.path.abspath(os.path.split(inspect.getfile(inspect.currentframe()))[0]))
logger = logging.getLogger('sgEntityProcess.model')


class SmartGridEntityModel(object):

    CONFIG_FILENAME = "../config/entity_data_map.json"  # This file maps data to the entities IDs
    FAULTS_FILENAME = "../config/faults.json"

    def __init__(self, ent_id, time_data, simu_param):

        # The entity ID
        self.my_id = ent_id

        # The current time
        start_time, dt = time_data
        self.current_time = start_time
        self.dt = dt

        # Simulation param
        self.param = simu_param

        # Fault management
        self.list_faults = []
        self.current_fault = None

    def update_time(self):
        self.current_time += self.dt

    @abstractmethod
    def rt_phase(self, payload_msg):
        """
        Real-time phase
        :param payload_msg: a dictionary sent by the simu coord
        :return: TODO
        """
        pass

    @abstractmethod
    def planning_phase(self, payload_msg):
        """
        Planning phase
        :param payload_msg: a dictionary sent by the simu coord
        :return: TODO
        """
        pass

    @property
    def id(self):
        return self.my_id

    @property
    def timestamp(self):
        return self.current_time


# ----------- The Microgrid Manager

class MicroGridManagerEntityModel(SmartGridEntityModel):
    DR_CONFIG_FOLDER = "../config/type_dr_simu_config/"  # This file maps data to the entities IDs

    def __init__(self, ent_id, time_data, simu_param=None):
        super(MicroGridManagerEntityModel, self).__init__(ent_id, time_data, simu_param)

        # Read DR config file
        self.dr_simu_data = None
        try:
            self.dr_simu_data = json.load(open("{}/{}{}.json".format(cmd_folder, self.DR_CONFIG_FOLDER, SIMULATION_TYPE_DR)))
        except:
            print("WARNING: MGM cannot open DR simu config file")

    def rt_phase(self, payload_msg):
        """
        In real-time, the MGM can send:
         - The current Real-Time price
         - A DR event
        :param payload_msg: a dictionary sent by the simu coord
        :return:
        """
        idx_vector = int((self.current_time % (24 * 3600)) / ((24 * 3600)/len(self.dr_simu_data["energy_price"])))
        current_price_value = self.dr_simu_data["energy_price"][idx_vector]  # Online works with 1h data !
        return {ZMQ_RT_DATA_PRICE: current_price_value}

    def planning_phase(self, payload_msg):
        """
        Day Ahead logic. Depending on the DR config, various logic are possible
        :param payload_msg:
        :return:
        """
        nb_steps = int(24 * 3600 / self.dt)
        ret = {}
        type_msg = payload_msg[ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY]
        price_sig = resample_price_sig(self.dr_simu_data["energy_price"], 0, (0, 24 * 3600, self.dt))
        ret[ZMQ_PLANNING_PAYLOAD_TYPE_PRICE] = {"timestamps": range(0, 24*3600, self.dt), "forecast_data": list(price_sig)}

        # TEST:
        # Only one round: receiving START -> send prices -> receive DATA -> send END
        if type_msg == ZMQ_PLANNING_TYPE_SIG_START:
            ret[ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY] = ZMQ_PLANNING_TYPE_SIG_DATA
        elif type_msg == ZMQ_PLANNING_TYPE_SIG_DATA:
            ret[ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY] = ZMQ_PLANNING_TYPE_SIG_END

        return ret


# ----------- The Distributed Energy Resource

class DistributedEnergyResourceEntityModel(SmartGridEntityModel):
    def __init__(self, ent_id, time_data, simu_param=None):
        super(DistributedEnergyResourceEntityModel, self).__init__(ent_id, time_data, simu_param)

        # Loading data from Pandas DF
        self.forecast_data = None
        self.production_data = None
        self.init_data()

        # Faults list init
        self.init_fault()

    def init_data(self):
        """
        TODO
        :return:
        """
        map_data = json.load(open(cmd_folder+"/"+self.CONFIG_FILENAME))
        try:
            filename = map_data["DER"][str(self.id)]

            df = pd.read_csv(cmd_folder+"/"+filename)

            self.forecast_data = list(df["forecast"].values)
            self.production_data = list(df["production"].values)

        except:
            print("WARNING: DER #{} does not have data to read".format(self.id))

    def init_fault(self):
        """
        TODO
        :return:
        """

        json_data = open(cmd_folder + "/" + 'res_fault/res_fault.json').read()
        data = json.loads(json_data)

        for (fault_id, fault_data) in data.items():
            s_t = data[fault_id]['data'][0]
            e_t = data[fault_id]['data'][1]
            coef = data[fault_id]['data'][2]
            t_trigger = data[fault_id]['t_trigger']
            self.list_faults.append({"t_trigger": t_trigger, "data": FaultForecast(s_t, e_t, coef)})

    def rt_phase(self, payload_msg):
        """
        Describe TODO
        :param payload_msg:
        :return:
        """

        # get the hour in the day
        hour_in_day = int((self.current_time / self.dt)) % (24 * int(3600/self.dt))
        p_gen = self.production_data[hour_in_day]

        np.random.seed()
        p_noise = np.random.normal(0, max(self.production_data)/10.0)

        ret_msg = {ZMQ_RT_DATA_GENERATION: max(p_gen + p_noise, 0)}

        if self.update_current_fault() is True:  # Normal real-time phase
            logger.debug("DER #{} is requesting a Planning Phase @ t={}".format(self.id, self.current_time))
            ret_msg[ZMQ_RT_DATA_PLANNING_REQUEST] = True

        return ret_msg

    def planning_phase(self, payload_msg):
        """
        Describe TODO
        :param payload_msg:
        :return:
        """
        type_msg = payload_msg[ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY]
        ret = {}

        # generate the time and data vector
        t_0 = self.current_time % (24*3600)
        t_end = 24*3600
        sig_data = generate_forecast(self.forecast_data, (t_0, t_end, self.dt), self.current_fault)

        ret[ZMQ_PLANNING_PAYLOAD_TYPE_GEN] = {"timestamps": range(t_0, t_end, self.dt), "forecast_data": sig_data}

        if SIMULATION_ARCH_CENTRALIZED:
            if type_msg == ZMQ_PLANNING_TYPE_SIG_START:
                price_en = payload_msg[ZMQ_PLANNING_PAYLOAD_TYPE_PRICE]
                ret[ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY] = ZMQ_PLANNING_TYPE_SIG_DATA
            elif type_msg == ZMQ_PLANNING_TYPE_SIG_DATA:
                price_en = payload_msg[ZMQ_PLANNING_PAYLOAD_TYPE_PRICE]
                ret[ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY] = ZMQ_PLANNING_TYPE_SIG_DATA
            elif type_msg == ZMQ_PLANNING_TYPE_SIG_END:
                ret[ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY] = ZMQ_PLANNING_TYPE_SIG_END
        else:
            if type_msg == ZMQ_PLANNING_TYPE_SIG_START:
                ret[ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY] = ZMQ_PLANNING_TYPE_SIG_START

        return ret

    def update_current_fault(self):
        """
        This method compares the current time with the triggering time of the faults.
        In case of a new fault to trigger, it stores it in 'self.current_fault' and return True. Otherwise it returns False
        :return: boolean if a new fault is triggered
        """

        # New fault to trigger
        if len(self.list_faults) > 0:
            # Did we reach the time to trigger the new fault ?
            if self.current_time >= self.list_faults[0]["t_trigger"]:
                self.current_fault = self.list_faults.pop(0)["data"]  # remove and store the current fault
                return True

        # Is there a current fault to end?
        if self.current_fault is not None and self.current_time >= self.current_fault.ending_time:
            self.current_fault = None

        return False


# ----------- The Smart-Building

class SmartBuildingEntityModel(SmartGridEntityModel):

    def __init__(self, ent_id, time_data, simu_param=None):
        super(SmartBuildingEntityModel, self).__init__(ent_id, time_data, simu_param)

        # The current planning of this SB
        self.__energy_planning = dict()
        self.__load_schedule = dict()

        # State used this GT phase
        self.pp_state = dict()

    def rt_phase(self, payload_msg):
        """
        Describe TODO
        :param payload_msg:
        :return:
        """
        hour_in_day = int(self.current_time / self.dt) % (24 * int(3600/self.dt))
        p = self.__energy_planning['forecast_data'][hour_in_day]

        np.random.seed()
        p_noise = np.random.normal(0, max(self.__energy_planning['forecast_data'])/10.0)
        return {ZMQ_RT_DATA_CONSUMPTION: max(p + p_noise, 0)}

    def planning_phase(self, payload_msg):
        """
        Centralized of Decentralized
        :param payload_msg:
        :return:
        """

        type_msg = payload_msg[ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY]

        if SIMULATION_ARCH_CENTRALIZED:

            data_msg = payload_msg
            return self.run_centralized_planning(type_msg, data_msg)
        else:
            data_msg = payload_msg
            return self.run_gt_planning(type_msg, data_msg)

    def run_centralized_planning(self, type_msg, payload_msg):
        """
        Centralized planning
        :param type_msg:
        :param payload_msg:
        :return:
        """
        ret = {}

        if type_msg == ZMQ_PLANNING_TYPE_SIG_START or type_msg == ZMQ_PLANNING_TYPE_SIG_DATA:

            # Read the price data
            self.pp_state["electricity_price"] = payload_msg[ZMQ_PLANNING_PAYLOAD_TYPE_PRICE]
            ret[ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY] = ZMQ_PLANNING_TYPE_SIG_DATA

            # Updates energy plannings (solve opti problem)
            self.update_energy_planning()
            ret[ZMQ_PLANNING_PAYLOAD_TYPE_CONS] = self.__energy_planning

        elif type_msg == ZMQ_PLANNING_TYPE_SIG_END:
            ret[ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY] = ZMQ_PLANNING_TYPE_SIG_END

        return ret

    def run_gt_planning(self, type_msg, data_msg):

        """
        This method implements the day-ahead energy planning logic.

        :param sb_obj: a SmartBuildingModel object, representing the SB model
        :param type_msg:
        :param payload_msg:
        :return: /

        Algorithm
        ---------
        INPUTS :
        - (C(h), electricity price functions for each hour)
        - (l-n, vector containing scheduled daily energy consumption for all other users)
        COMPUTATION :
        0. randomly init ln and l-n
        1. loop:
        2.  at random time do :
        3.      solve opti problem () ok
        4.      if xn changes (threshold) : ok
        5.          update xn ok
        6.          broadcast message to announce ln to other users ok
        6'.        else break ok
        7.      if a control message is received:
        8.          update l-n
        9. until timeout (no more message received from other users)
        OUTPUT :
        modified xn (resp. ln)
        """

        # ---
        # FINITE STATE MACHINE LOGIC:
        # TODO: describe
        # ---

        if type_msg == ZMQ_PLANNING_TYPE_SIG_START:

            logger.info("==== GT INIT PHASE ====")
            return self.init_gt_phase(data_msg)

        elif type_msg == ZMQ_PLANNING_TYPE_SIG_DATA:

            # This could be a pre-info containing BC data
            if SIMULATION_USE_BLOCKCHAIN and ZMQ_PLANNING_PAYLOAD_TYPE_BLOCKCHAIN in data_msg.keys():
                logger.debug("Receives a Blockchain info")
                self.pp_state["bc_info"] = data_msg[ZMQ_PLANNING_PAYLOAD_TYPE_BLOCKCHAIN]
            else:
                logger.info("==== GT DATA PHASE ====")
                return self.run_gt_logic(data_msg)

        elif type_msg == ZMQ_PLANNING_TYPE_SIG_END:

            logger.info("==== GT END PHASE ====")
            return self.end_gt_phase(data_msg)

    def init_gt_phase(self, data_msg):
        """
        Initialise the smart-building with received data and send back information
        :param data_msg:
        :return:
        """
        t_0 = self.current_time % (24*3600)
        t_end = 24*3600
        idx_start = t_0 / self.dt
        idx_end = t_end / self.dt

        # --- Data from the grid
        # Elec price: this is a dictionary containing price components
        self.pp_state["electricity_price"] = data_msg[ZMQ_PLANNING_PAYLOAD_TYPE_PRICE]

        if ZMQ_PLANNING_PAYLOAD_TYPE_GEN in data_msg.keys():
            self.pp_state["ext_generation_forecast"] = {}
            for der_id, der_data in data_msg[ZMQ_PLANNING_PAYLOAD_TYPE_GEN].items():
                self.pp_state["ext_generation_forecast"][der_id] = der_data['forecast_data']
        else:
            self.pp_state["ext_generation_forecast"] = None

        # Internal data
        self.pp_state["ext_consumption_forecast"] = {}  # a map ID_sb -> FORECAST

        if SIMULATION_USE_BLOCKCHAIN:
            self.pp_state["bc_info"] = {}

        ret = {ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY: ZMQ_PLANNING_TYPE_SIG_START}

        # Give a first consumption
        self.update_energy_planning()
        sig_data = self.__energy_planning['forecast_data'][idx_start:idx_end]

        # Generate the message to send back
        data_cons_forecast = {"timestamps": range(t_0, t_end, self.dt), "forecast_data": sig_data}
        ret[ZMQ_PLANNING_PAYLOAD_TYPE_CONS] = data_cons_forecast

        return ret

    def end_gt_phase(self, data_msg):
        """
        END the Game Theory phase
        :param data_msg:
        :return:
        """

        ret = {ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY: ZMQ_PLANNING_TYPE_SIG_END}
        logger.debug("SB %s size of optimal power: %s. Optimal power vector: %s", self.id, len(self.__energy_planning['forecast_data']), self.__energy_planning)
        return ret

    def run_gt_logic(self, data_msg):
        """
        Initialise the smart-building with received data and send back information
        :param data_msg:
        :return:
        """

        ret = {ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY: ZMQ_PLANNING_TYPE_SIG_DATA}

        # Extract the time data and init the return message
        t_0 = self.current_time % (24*3600)
        t_end = 24*3600
        idx_start = t_0/self.dt
        idx_end = t_end/self.dt
        data_cons_forecast = {"timestamps": range(t_0, t_end, self.dt), "forecast_data": None}

        # Analysis of data_msg:
        for sb_id, data_sb in data_msg[ZMQ_PLANNING_PAYLOAD_TYPE_CONS].items():
            self.pp_state["ext_consumption_forecast"][sb_id] = data_sb["forecast_data"]

        # Do the local optimization

        # -- Optimization
        logger.debug("SB%s is going to run a planning phase", self.id)

        # gets the current energy planning
        former_state = self.__energy_planning.get('forecast_data', None)
        logger.debug("Its current planning: %s", former_state)

        # updates energy plannings (solve opti problem)
        self.update_energy_planning()

        if not (self.__energy_planning['forecast_data'] == former_state):  # if sb has modified his forecasted data
            # broadcast the change to the blockchain
            data_cons_forecast["forecast_data"] = self.__energy_planning['forecast_data'][idx_start:idx_end]
            logger.debug("Forecast modified: %s", self.__energy_planning['forecast_data'])
        else:
            logger.debug('The planning of SB%s has not changed !', self.id)

        ret[ZMQ_PLANNING_PAYLOAD_TYPE_CONS] = data_cons_forecast

        return ret

    def update_energy_planning(self):
        """
        Solve the LP opti that produce the planning for the day. Store it into EnergyPlanning
        :return: /
        """

        # Optimization parameters: TODO remove it
        max_power = 5000

        # Parameters
        horizon = 24 * 3600  # The daily horizon
        t_end = 24 * 3600  # The end time of the forecast
        current_time = (self.current_time % horizon)  # The current time in the day
        time_data = (current_time, t_end, self.dt)

        # LOGGER INFO
        logger.debug("Optimization from t_0=%s to t_end=%s (dt=%s)", current_time, t_end, self.dt)

        # The planning will be modified: prepare the timestamp
        self.__energy_planning['timestamps'] = [(self.dt * t) for t in range(horizon / self.dt)]

        # Data from the grid: resample the prices
        price_sig = None
        if type(self.pp_state["electricity_price"]) is not dict:
            price_sig = resample_price_sig(self.pp_state["electricity_price"], 0, time_data)  # the second parameter means that the price info is directly a vecotr
        else:
            price_sig = {}
            for k, v in self.pp_state["electricity_price"].items():
                price_sig[k] = resample_price_sig(v, 0, time_data)

        # In decentralized mode, the other buildings and DERs send their forecast
        if not SIMULATION_ARCH_CENTRALIZED:
            pred_cons = self.pp_state["ext_consumption_forecast"]
            pred_gens = self.pp_state["ext_generation_forecast"]

            # Computing the total external power at each interval
            external_generation = [0] * int((t_end - current_time) / self.dt)
            external_consumption = [0] * int((t_end - current_time) / self.dt)
            for (sb_id, forecast_profile) in pred_cons.iteritems():
                if int(sb_id) != int(self.id):
                    if type(forecast_profile) is list and len(forecast_profile) == len(external_generation):
                        external_consumption = [x + max(y_sb, 0) for (x, y_sb) in zip(external_consumption, forecast_profile)]
                        external_generation = [x - min(y_sb, 0) for (x, y_sb) in zip(external_generation, forecast_profile)]  # y_sb is negative

            # Computing total generation of sum of RES and SBs that produce
            if pred_gens is not None:
                for der_id, der_data in pred_gens.items():
                    external_generation = [x + y_der for (x, y_der) in zip(external_generation, der_data)]  # y_der is positive

            # Launch the scheduling
            data_opti = {'price_elec': price_sig, 'external_consumption': external_consumption, 'external_gen': external_generation}
            interactive_scheduler = InteractiveLoadScheduler(self.CONFIG_FILENAME)
            interactive_scheduler.init_loads(self.id, time_data, self.__load_schedule)
            en_sched = interactive_scheduler.schedule_loads(time_data, data_opti)
            opti_power = interactive_scheduler.schedule_power_vector(en_sched, time_data)

        else:  # CENTRALIZED MODE
            opti_scheduler = InteractiveLoadScheduler(self.CONFIG_FILENAME)
            opti_scheduler.init_loads(self.id, time_data, self.__load_schedule)
            # price_sig is sent by the MGM: take the "forecast_data
            # TODO: allow demand cost ? bof bof pour residential ..
            data_opti = {'price_elec': {'energy_price': price_sig["forecast_data"]}}
            en_sched = opti_scheduler.schedule_loads(time_data, data_opti)
            opti_power = opti_scheduler.schedule_power_vector(en_sched, time_data)

        self.update_en_sched(en_sched)
        self.update_power_vector(time_data, opti_power)
        logger.debug("The SB has updated its schedule: %s", self.__load_schedule)

    def update_power_vector(self, time_data, opti_power):
        """
        This method updates the SB power vector after scheduling optimization is done
        :param opti_power:
        :return: updated_opti_power
        """
        t_start, t_end, dt = time_data
        if t_start:
            former_power = self.__energy_planning['forecast_data']
            updated_opti_power = [former_power[i] for i in range(t_start/dt)] + opti_power
            self.__energy_planning['forecast_data'] = updated_opti_power

        else:
            self.__energy_planning['forecast_data'] = opti_power

    def update_en_sched(self, new_en_sched):
        """
        This method updates schedule of building
        :param new_en_sched:
        """
        for load_id in new_en_sched.keys():
            self.__load_schedule[load_id] = new_en_sched[load_id]

def resample_price_sig(price_signal, _type, time_data):
    """
    TODO: describe
    """

    (t_s, t_e, time_step) = time_data

    if type(price_signal) == dict:
        price_signal = price_signal["forecast_data"]

    signal = []
    if _type == 1:  # price signal as a compound vector
        signal = [s[0] for s in price_signal]

    elif _type == 0:  # price signal as a simple vector
        signal = price_signal

    # Price signal is hourly -> repeat the values
    ratio_time = int((24*3600/time_step) / len(price_signal))
    interpolated_signal = np.repeat(signal, ratio_time)

    # Take the right indexes
    idx_start = int(t_s/time_step)
    idx_stop = int(t_e/time_step)

    resized_sig = interpolated_signal[idx_start:idx_stop]

    return resized_sig


def generate_forecast(signal_data, time_data, fault=None):
    """
    Reframe a signal according to time_data and apply a fault, if specified
    """
    # Extract time data
    (current_time, t_e, dt) = time_data
    t_s = current_time % (24*3600)
    logger.debug(" === Fault triggered ===")

    # forecast_data ranges from 0 -> 24*3600 with a step of dt
    idx_st = int(t_s/dt)
    idx_end = int(t_e/dt)

    # select the forecast from t_s to t_e, in term of indexes
    ret = signal_data[idx_st:idx_end]

    # If there is a fault forecast, apply it
    if fault is not None:
        ret = fault.apply_fault((t_s, dt, ret))

    return ret


# TEST
if __name__ == '__main__':

    test_fault = FaultForecast(12*3600, 18*3600, 0)
    test_forecast = range(0, 96, 1)
    print generate_forecast(test_forecast, (8*3600, 24*3600, 900), test_fault)
