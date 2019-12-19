__author__ = 'Olivier Van Cutsem'

import sys, os, inspect
import time
import numpy as np
from multiprocessing import Process
import logging

from sg_entity_param import *
from sg_entity_model import MicroGridManagerEntityModel, DistributedEnergyResourceEntityModel, SmartBuildingEntityModel
import zmq.green as zmq

# --- Logger INIT
# Set level of logger (ERROR > INFO > DEBUG)
# Logging messages which are less severe than level will be ignored
cmd_folder = os.path.realpath(os.path.abspath(os.path.split(inspect.getfile(inspect.currentframe()))[0]))
logging.basicConfig(filename=cmd_folder+'/../data/log/sg_entity_processes.log', level=logging.DEBUG)
logger = logging.getLogger('sgEntityProcess')

# ----------------------------------------------------------------------------- #
# --------- The generic process that emulates any smart grid entity ----------- #
# - It is supposed that external coordinator has created the PUB-SUB channels - #
# ----------------------------------------------------------------------------- #


def sg_entity_process(my_id_txt, instance_class, simu_parameters):
    """
    This function enters a main loop that is quited only when a STOP signal is received
    :param my_id_txt: a string, containing the ID of the Smart-Grid entity
    :param instance_class: the class that implements the core logic
    :param simu_parameters: set of parameters
    :return: /
    """
    my_id = int(my_id_txt[2:])

    # Create the Smart-Grid object that contains current time, scheduling energy data and useful methods
    time_data = (SIMULATION_STARTING_DATE, SIMULATION_DT)  # (init time, time step)

    # Create the Smart-Grid entity object
    sg_entity_obj = instance_class(ent_id=my_id, time_data=time_data, simu_param=None)  # TODO: give param

    # Create the PUB-SUB pair and connect a data POLLER
    (sg_coord_sub, ent_pub) = connect_pub_sub_sockets(my_id)
    socket_poller = zmq.Poller()
    socket_poller.register(sg_coord_sub, zmq.POLLIN)

    time.sleep(0.5)  # Wait for socket to have settle, just in case

    logger.info("SG entity#{0} has been created ".format(my_id))

    # Notify the NodeJS that I'm here
    register_to_coordinator(ent_pub, sg_entity_obj)

    # ----------------- #
    # --- MAIN LOOP --- #
    # ----------------- #

    logger.info("SG entity#{0} enters its main loop -- Ready to work !".format(my_id))

    while True:

        # ---
        # Wait for a signal from the SIMU COORD
        # ---

        type_msg, payload_msg = listen_for_sg_coord_signal(sg_coord_sub, socket_poller)

        if type_msg == ZMQ_SG_COORD_NEXT_SIMU_STEP:  # Next simu step ?

            # ---
            # ONLINE logic
            # ---

            rt_msg = sg_entity_obj.rt_phase(payload_msg)
            logger.debug("[@%s] SG entity %s receives a RealTime msg: %s", sg_entity_obj.current_time, my_id, rt_msg)

            # --- Send it to the Coordinator
            send_sg_coord_rt_data(ent_pub, sg_entity_obj, rt_msg)

            # --- UPDATE SIMULATION TIME
            sg_entity_obj.update_time()

            time.sleep(0.2)

        elif type_msg == ZMQ_SG_COORD_PLANNING_SIGNAL:  # Planning phase message

            # ---
            # PLANNING logic
            # ---

            time.sleep(np.random.rand(1)[0])
            planning_msg = sg_entity_obj.planning_phase(payload_msg)
            logger.debug("[@%s] SG entity %s receives a Planning msg: %s", sg_entity_obj.current_time, my_id, planning_msg)

            # --- Send it to the Coordinator
            # Exeception: In Planning mode, we could for example receive data without sending back an answer
            if planning_msg != None:
                send_sg_coord_planning_data(ent_pub, sg_entity_obj, planning_msg)

        elif type_msg == ZMQ_SG_COORD_STOP:  # Stop the process !
            break


def getTypeOfClassFromID(ent_id):
    if ent_id == MICROGRID_MANAGER_ID:
        return "mgm"
    elif SB_FIRST_ID <= ent_id < DER_FIRST_ID:
        return "sb"
    else:
        return "der"

# -------------------------------------------------------- #
# ------ SG-coordinator communication with PUB-SUB ------- #
# -------------------------------------------------------- #


def connect_pub_sub_sockets(sg_entity_id):
    """
    Connect to the existing PUB-SUB sockets
    :param sb_id: the ID of the Smart-Building
    :return: a tuple (s_sub, sb_pub) of SUB-PUB pair
    """
    zmq_context = zmq.Context()

    sb_pub = zmq_context.socket(zmq.PUB)
    sb_pub.connect('tcp://' + ZMQ_SIMU_IP + ':' + ZMQ_ENTITIES_PUB)

    server_sub = zmq_context.socket(zmq.SUB)
    server_sub.connect('tcp://' + ZMQ_SIMU_IP + ':' + ZMQ_SG_COORD_PUB)
    server_sub.setsockopt(zmq.SUBSCRIBE, str(sg_entity_id) + "e")  # Listen only to my messages (suffix e to prevent
    server_sub.setsockopt(zmq.SUBSCRIBE, str(ZMQ_BROADCAST_ID))  # and broadcast ones

    if getTypeOfClassFromID(sg_entity_id) == "mgm":
        server_sub.setsockopt(zmq.SUBSCRIBE, str(ZMQ_GROUP_MGM_ID))  # and group ones
    elif getTypeOfClassFromID(sg_entity_id) == "der":
        server_sub.setsockopt(zmq.SUBSCRIBE, str(ZMQ_GROUP_DER_ID))  # and broadcast ones
    elif getTypeOfClassFromID(sg_entity_id) == "sb":
        server_sub.setsockopt(zmq.SUBSCRIBE, str(ZMQ_GROUP_SB_ID))  # and broadcast ones

    return server_sub, sb_pub


def listen_for_sg_coord_signal(sg_coord_sub, socket_poller, max_attempt=100):
    """
    TODO
    :param sg_coord_sub:
    :param socket_poller:
    :param max_attempt: set it to 0 for a non-blocking listen
    :return: a tuple:
     - A string representing the type of message
     - A dictionary, representing the core of the message
    """

    msg = None
    attempt = 0
    while msg is None:

        socks = dict(socket_poller.poll(timeout=100))  # wait for 100 ms

        if socks.get(sg_coord_sub) == zmq.POLLIN:
            m = sg_coord_sub.recv_multipart()

            (rec, msg_raw) = m  # rec = receiver, msg_raw = message as a dictionary
            try:
                msg = json.loads(msg_raw)

                return msg["TYPE"], msg["DATA"]
            except ValueError:
                return None, None
        else:
            attempt += 1

        if attempt >= max_attempt:
            break

    return None, None


#  --------- Register to the coordinator

def register_to_coordinator(ent_pub, ent_obj):
    """
    Notifying the NodeJS server that I'm connected
    :param ent_pub: the SG-coordinator PUB socket to send a msg to
    :param ent_obj: a SmartBuildingModel object, representing the SB model
    :return: /
    """

    # Publish to the SUB of the nodeJS server
    send_zmq_message(ent_pub, ZMQ_SG_COORD_NEW_CONNECTION, ent_obj, {})


#  --------- Messages to the coordinator

def send_sg_coord_rt_data(ent_pub, ent_obj, rt_data):
    """
    Send RT data to the Simulation Coordinator
    :return: /
    """

    # Publish to the SUB of the nodeJS server
    send_zmq_message(ent_pub, ZMQ_SG_COORD_NEXT_SIMU_STEP, ent_obj, rt_data)


def send_sg_coord_planning_data(ent_pub, ent_obj, plan_data):
    """
    Send Planning data to the Simulation Coordinator
    :return: /
    """

    # Publish to the SUB of the nodeJS server
    send_zmq_message(ent_pub, ZMQ_SG_COORD_PLANNING_SIGNAL, ent_obj, plan_data)


def send_zmq_message(ent_pub, msg_type, ent_obj, msg):
    """
    Send a formatted multipart message over ZMQ
    :param ent_pub: a PUB ZMQ
    :param msg_type: a string, representing the type of message
    :param ent_id: an int, representing the ID of the entity
    :param msg: a dictionary containing the message
    :return: /
    """
    msg_formatted = {"data": msg, "timestamp": ent_obj.timestamp}

    logger.debug("[@%s] SG entity %s sends a msg to the SG coordinator: %s", ent_obj.timestamp, ent_obj.id, msg)
    ent_pub.send_multipart([str(msg_type), str("i{}".format(ent_obj.id)), json.dumps(msg_formatted)])

# --------------------------- #
# --- Processes launching --- #
# --------------------------- #


if __name__ == '__main__':

    # TODO: read parameter when this file is called

    param_script = []
    if len(sys.argv) > 1:
        param_script = sys.argv

    # -
    # ---- Instantiate and start the processes
    # -

    entity_list = []

    builtin_entities = SG_ENTITIES_INSTANCES["BUILT_IN"]
    list_sb_builtin = range(SB_FIRST_ID, SB_FIRST_ID+builtin_entities["SB"])

    # --- BUILT-IN entities

    # - DERs
    for i in range(DER_FIRST_ID, DER_FIRST_ID+NB_DER_SIMU):
        der_class = DistributedEnergyResourceEntityModel
        der = Process(target=sg_entity_process, args=("id{}".format(i), der_class, None))
        der.start()
        entity_list.append(der)

    # - MGM
    if SIMULATION_ARCH_CENTRALIZED:
        for i in [MICROGRID_MANAGER_ID]:
            mgm_class = MicroGridManagerEntityModel
            mgm = Process(target=sg_entity_process, args=("id{}".format(i), mgm_class, None))
            mgm.start()
            entity_list.append(mgm)

    # - Smart-Buildings
    for i in list_sb_builtin:
        sb_class = SmartBuildingEntityModel
        sb = Process(target=sg_entity_process, args=("id{}".format(i), sb_class, None))
        sb.start()
        entity_list.append(sb)

    # --- External entities
    list_external_entities = SG_ENTITIES_INSTANCES["EXTERNAL"]

    id_sb_last = 1
    if len(list_sb_builtin) > 0:
        id_sb_last = SB_FIRST_ID+builtin_entities["SB"]

    for instance_data in list_external_entities:  # Loop over all the external modules
        nb_instances = instance_data["NB"]
        for i in range(nb_instances):  # For each module, instanciate X entities

            # Path, module and process name
            path_to_process_function = instance_data["path"]
            module_to_process_function = instance_data["module"]
            process_name = instance_data["function_process"]

            # Import the module where the process to instance lays

            folder = path_to_process_function
            if folder not in sys.path:
                sys.path.append(os.path.abspath(path_to_process_function))
            ventity_class_module = __import__(module_to_process_function)  # filename MUST be the same with class name
            process_function = getattr(ventity_class_module, process_name)

            # Parameters
            sb_param = None
            if "param" in instance_data.keys():
                sb_param = instance_data["param"]

            # Instanciate and start the process
            simu_param = simu_config["SIMULATION_PARAMETERS"]
            p_ext = Process(target=process_function, args=(id_sb_last, sb_param, simu_param))


            p_ext.start()
            entity_list.append(p_ext)

            id_sb_last += 1  # Increment the building ID

    # ---- Wait for the process to end
    for ent in entity_list:
        ent.join()

    # Notify the NodeJS server that the processes are finished
    zmq_context = zmq.Context()

    sb_pub_close = zmq_context.socket(zmq.PUB)
    sb_pub_close.connect('tcp://' + ZMQ_SIMU_IP + ':' + ZMQ_ENTITIES_PUB)
    sb_pub_close.send_multipart([str(ZMQ_BROADCAST_ID), str(ZMQ_SG_COORD_STOP)])
    sb_pub_close.close()
