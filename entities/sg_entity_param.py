__author__ = 'Olivier Van Cutsem'

import json
import os, inspect
# Load the param and config

cmd_folder = os.path.realpath(os.path.abspath(os.path.split(inspect.getfile(inspect.currentframe()))[0]))
data_param = json.load(open(cmd_folder+'/../config/messages_param.json'))
simu_config = json.load(open(cmd_folder+'/../config/simulation_config.json'))

# Simulation config

SIMULATION_TYPE_DR = simu_config["SG_SIMULATION_CONFIG"]["TYPE_DR_SIMU"]
SIMULATION_ARCH_CENTRALIZED = simu_config["SG_SIMULATION_CONFIG"]["ARCHITECTURE_CENTRALIZED"]
SIMULATION_USE_BLOCKCHAIN = simu_config["SG_SIMULATION_CONFIG"]["USE_BLOCKCHAIN"]

SIMULATION_DT = simu_config["SIMULATION_PARAMETERS"]["TIME_STEP"]  # The simulation period, in seconds
SIMULATION_STARTING_DATE = simu_config["SIMULATION_PARAMETERS"]["STARTING_DATE"]  # the beginning of simulation
SIMULATION_DURATION = simu_config["SIMULATION_PARAMETERS"]["DURATION"]  # the simulation duration, in seconds
SIMULATION_PLANNING_FREQ = simu_config["SIMULATION_PARAMETERS"]["PLANNING_FREQUENCY"]

NB_SB_SIMU = simu_config["SB_CONFIG"]["NB"]  # the total amount of smart-buildings
NB_DER_SIMU = simu_config["DER_CONFIG"]["NB"]  # the total amount of DERs

SG_ENTITIES_INSTANCES = simu_config["INSTANCES"]  # the type of model to use to instantiate each entity

###
# ZemoMQ parameters of PUB-SUB channels
###

ZMQ_SIMU_IP = simu_config["ZMQ_CONFIG"]["SIMU_IP"]  # Work in local
ZMQ_BROADCAST_ID = simu_config["ZMQ_CONFIG"]["BROADCAST_ID"]  # In the context of PUB-SUB communication, this special ID aims to communicate a msg to all of the SBs
ZMQ_SG_COORD_PUB = simu_config["ZMQ_CONFIG"]["SG_COORD_PUB"]   # The Smart-Grid coordinator sends to this port
ZMQ_ENTITIES_PUB = simu_config["ZMQ_CONFIG"]["SG_ENTITY_PUB"]   # The Smart-Buildings send to this port

ZMQ_GROUP_SB_ID = simu_config["ZMQ_CONFIG"]["GROUP_SB_ID"]   # The Smart-Buildings send to this port
ZMQ_GROUP_DER_ID = simu_config["ZMQ_CONFIG"]["GROUP_DER_ID"]   # The Smart-Buildings send to this port
ZMQ_GROUP_MGM_ID = simu_config["ZMQ_CONFIG"]["GROUP_MGM_ID"]   # The Smart-Buildings send to this port

SB_FIRST_ID = simu_config["ZMQ_CONFIG"]["SB_FIRST_ID"]  # the ID of the first SB
DER_FIRST_ID = simu_config["ZMQ_CONFIG"]["DER_FIRST_ID"]  # the ID of the first SB
MICROGRID_MANAGER_ID = simu_config["ZMQ_CONFIG"]["MICROGRID_MANAGER_ID"]

###
# Types of message exchanged between the simu-coordinator and the SG entities
###

ZMQ_SG_COORD_NEXT_SIMU_STEP = data_param["SG_COORD_SIGNAL"]["SIMU_STEP"]  # Online simulation progression igniter signal
ZMQ_SG_COORD_PLANNING_SIGNAL = data_param["SG_COORD_SIGNAL"]["PLANNING_SIGNAL"]  # Planning signal
ZMQ_SG_COORD_STOP = data_param["SG_COORD_SIGNAL"]["STOP"]  # Stopping signal
ZMQ_SG_COORD_NEW_CONNECTION = data_param["SG_COORD_SIGNAL"]["NEW_CONNECTION"]  # Planning signal

###
# Real-time type of data exchanged
###

ZMQ_RT_DATA_PRICE = data_param["NEXT_SIMU_STEP_PAYLOAD_KEYS"]["PRICE_DATA"]  # Online data sent to the the SG coordinator as simulation goes on
ZMQ_RT_DATA_CONSUMPTION = data_param["NEXT_SIMU_STEP_PAYLOAD_KEYS"]["CONSUMPTION_DATA"]  # Register to the SG coordinator
ZMQ_RT_DATA_GENERATION = data_param["NEXT_SIMU_STEP_PAYLOAD_KEYS"]["GENERATION_DATA"]  # Register to the SG coordinator
ZMQ_RT_DATA_PLANNING_REQUEST = data_param["NEXT_SIMU_STEP_PAYLOAD_KEYS"]["PLANNING_PHASE_REQUEST"]  # offline data sent to the the SG coordinator as day-ahead logic goes on


###
# Types of message sent by both sides during Day-Ahead exchange
###

ZMQ_PLANNING_TYPE_SIG_START = data_param["PLANNING_SIGNAL_TYPE_SIGNAL"]["START_TYPE"]
ZMQ_PLANNING_TYPE_SIG_DATA = data_param["PLANNING_SIGNAL_TYPE_SIGNAL"]["DATA_TYPE"]
ZMQ_PLANNING_TYPE_SIG_END = data_param["PLANNING_SIGNAL_TYPE_SIGNAL"]["END_PHASE"]

# KEYS IN PAYLOAD

ZMQ_PLANNING_PAYLOAD_TYPE_SIG_KEY = data_param["PLANNING_SIGNAL_PAYLOAD_KEYS"]["TYPE_SIGNAL"]
ZMQ_PLANNING_PAYLOAD_TYPE_PRICE = data_param["PLANNING_SIGNAL_PAYLOAD_KEYS"]["PRICE_FORECAST"]
ZMQ_PLANNING_PAYLOAD_TYPE_GEN = data_param["PLANNING_SIGNAL_PAYLOAD_KEYS"]["GENERATION_FORECAST"]
ZMQ_PLANNING_PAYLOAD_TYPE_CONS = data_param["PLANNING_SIGNAL_PAYLOAD_KEYS"]["CONSUMPTION_FORECAST"]
ZMQ_PLANNING_PAYLOAD_TYPE_MODEL = data_param["PLANNING_SIGNAL_PAYLOAD_KEYS"]["MODEL_DATA"]
ZMQ_PLANNING_PAYLOAD_TYPE_BLOCKCHAIN = data_param["PLANNING_SIGNAL_PAYLOAD_KEYS"]["BLOCKCHAIN_DATA"]
