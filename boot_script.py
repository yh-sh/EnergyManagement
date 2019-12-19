__author__ = 'Olivier Van Cutsem'

import time, os
import subprocess
import json
import logging, inspect
import math

cmd_folder = os.path.realpath(os.path.abspath(os.path.split(inspect.getfile(inspect.currentframe()))[0]))
logger = logging.getLogger('communityGridSimulation')
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(message)s',
                    filename='./data/output/bootscript.log',
                    filemode='w')

def write_config_parameters(list_parameters_values):

    config = json.load(open('config/simulation_config.json', 'r'))

    for keys_config, v in list_parameters_values:

        data = config
        key_config = keys_config
        while type(key_config) is tuple:
            k0, key_config = key_config
            data = data[k0]

        data[key_config] = v



    json.dump(config, open('config/simulation_config.json', 'w'), indent=2)

def scale_quadratic_term(price_name, nb_build, mean_p, replace=False):
    """
    Scale the quadratic term to ensure a_q x^2 = a_l x
    :param gt_price:
    :param nb_build:
    :param max_p:
    :return:
    """

    price_sig = json.load(open('config/type_dr_simu_config/{}.json'.format(price_name), 'r'))

    coeff_n_build = nb_build
    coeff_scale = mean_p * coeff_n_build

    lin_p = price_sig['electricity_price']['energy_price']

    if 'quad_price_single_bldg' in price_sig['electricity_price'].keys():
        quad_p = price_sig['electricity_price']['quad_price_single_bldg']
    else:
        quad_p = price_sig['electricity_price']['quad_price']
        price_sig['electricity_price']['quad_price_single_bldg'] = quad_p

    if replace:
        price_sig['electricity_price']['quad_price'] = [p_l/coeff_scale for p_l in lin_p]
    else:
        price_sig['electricity_price']['quad_price'] = [p_q/coeff_n_build for p_q in quad_p]

    json.dump(price_sig, open('config/type_dr_simu_config/{}.json'.format(price_name), 'w'), indent=2)

def increasing_nb_simu_with_randomorder(list_nb_bldg, nb_test_stat_max, average_building_cons, output_filename, type_bldg='extern'):
    """"""
    main_directory = './data/output/{}/'.format(output_filename)
    if not os.path.exists(main_directory):
        os.makedirs(main_directory)
        logger.info("- Creating folder {}".format(main_directory))

    for n in list_nb_bldg:
        logger.info("--- Running statistical test with {} bldgs".format(n))

        current_directory = "{}simu_nb_sb_{}/".format(main_directory,n)
        if not os.path.exists(current_directory):
            os.makedirs(current_directory)
            logger.info("- Creating folder {}".format(current_directory))

        # Prepare the parameters
        nb_test_stat = nb_test_stat_max
        if math.factorial(n) <= nb_test_stat_max:
            nb_test_stat = math.factorial(n)

        comm_av_cons = average_building_cons * n

        output_filename_n = "{}_{}".format(output_filename, n)

        if type_bldg == 'intern':
            write_config_parameters([(('SB_CONFIG', 'NB'), n)])
            write_config_parameters([(('INSTANCES', ('BUILT_IN','SB')), n-1)])
            write_config_parameters([(('INSTANCES', ('EXTERNAL',(0, 'NB'))), 1)])
        else:
            write_config_parameters([(('SB_CONFIG', 'NB'), n)])
            write_config_parameters([(('INSTANCES', ('BUILT_IN', 'SB')), 0)])
            write_config_parameters([(('INSTANCES', ('EXTERNAL', (0, 'NB'))), n)])

        # Call the statistical test
        test_statistic(nb_test_stat, comm_av_cons, current_directory, output_filename_n, "price_{}".format(output_filename_n))

def test_statistic(nb_test, average_building_cons, output_folder=None, output_filename=None, copied_price_data_filename=None):
    """
    Run multiple simulations, with a constant amount of buildings
    :return:
    """

    # SCALE THE QUADRATIC FACTOR
    config = json.load(open('config/simulation_config.json', 'r'))
    scale_quadratic_term(config['SG_SIMULATION_CONFIG']['TYPE_DR_SIMU'], config['SB_CONFIG']['NB'], average_building_cons)

    # Configure the statistical test
    list_stattest_param = []
    list_stattest_param.append((('SIMULATION_PARAMETERS','ROUND_ROBIN_PLANNING'), 'ASC'))   # TODO: CHANGE THIS BACK !!
    list_stattest_param.append((('SIMULATION_PARAMETERS','SHUTDOWN_SERVER_UPON_SIMULATION_END'), True))
    list_stattest_param.append((('SIMULATION_PARAMETERS','DURATION'), 0))
    list_stattest_param.append((('SIMULATION_PARAMETERS','PLANNING_MAX_MSG_PER_BUILD'), 20))
    list_stattest_param.append((('SG_SIMULATION_CONFIG','AUTOMATED_SIMULATION'), False))  # TODO: CHANGE THIS BACK !!

    write_config_parameters(list_stattest_param)

    for i in range(nb_test):
        logger.info("- Launching simulation #{}".format(i))

        # Run the simulation
        start_time = time.time()
        command = ['npm start']
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
        print process.communicate()

        logger.info(" -> Simulation over (PROCESS OK={}), time elapsed = {} \n".format(process.returncode==0, time.time() - start_time))

        # When over, rename the ouput file
        if output_filename is None:
            output_filename = "planning_data"
        os.system("cp data/output/planning_data.csv {}{}_{}.csv".format(output_folder, output_filename, i))

    # Save price structure
    if copied_price_data_filename is None:
        copied_price_data_filename = "price_data_simu"

    os.system("cp config/type_dr_simu_config/{}.json {}{}.json".format(config['SG_SIMULATION_CONFIG']['TYPE_DR_SIMU'], output_folder, copied_price_data_filename))


def test_basic(average_building_cons):
    """
    Run a single simulation
    :return:
    """

    logger.info("--- Launching single simulation ")

    # Load the config file and modify it, if needed

    config = json.load(open('config/simulation_config.json', 'r'))

    scale_quadratic_term(config['SG_SIMULATION_CONFIG']['TYPE_DR_SIMU'], config['SB_CONFIG']['NB'], average_building_cons)

    config['SIMULATION_PARAMETERS']['ROUND_ROBIN_PLANNING'] = 'RAND'
    config['SIMULATION_PARAMETERS']['SHUTDOWN_SERVER_UPON_SIMULATION_END'] = True
    config['SIMULATION_PARAMETERS']['DURATION'] = 0
    config['SIMULATION_PARAMETERS']['PLANNING_MAX_MSG_PER_BUILD'] = 3  # TEST
    config['SG_SIMULATION_CONFIG']['AUTOMATED_SIMULATION'] = False

    json.dump(config, open('config/simulation_config.json', 'w'), indent=2)

    # Run the simulation
    start_time = time.time()
    command = ['npm start']
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE)
    process.communicate()
    logger.info(" -> Simulation over (CODE={}), time elapsed = {} \n".format(process.returncode, time.time() - start_time))

    # When over, rename the ouput file
    os.system("cp data/output/planning_data.csv data/output/planning_data.csv")

    # Don't forget to copy the price signal for this simulation !
    os.system("cp config/type_dr_simu_config/{}.json data/output/price_data_simu.json".format(config['SG_SIMULATION_CONFIG']['TYPE_DR_SIMU']))

if __name__ == '__main__':

    # Simulation setup
    setup_simu = 'noPV_noEV'

    # Same amount of buildings, random sequences
    average_building_cons = {'noPV_noEV': 1, '50PV_noEV': 1, '100PV_noEV': 1, '50PV_50EV': 1, 'def': 1}

    # Increasing number of buildings
    logger.info("==== LAUNCHING SIMULATION BATCH ====")

    test_statistic(nb_test=1,
                   average_building_cons=1,
                   output_folder="data/output/minergie_8bldg_comm/MarketRTP_only/50PV_50EV/",
                   output_filename="planning_data",
                   copied_price_data_filename="GT")

    logger.info("==== ENDING SIMULATION BATCH ====")
