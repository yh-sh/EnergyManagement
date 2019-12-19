__author__ = 'Olivier Van Cutsem'

import numpy as np


class FaultForecast(object):
    """
    This class describes and manipulate a fault in the forecast of a Smart-Grid entity
    """

    TYPE_FORECAST_COEFF_LINEAR = "linear_coeff"
    TYPE_FORECAST_NEW_SIGNAL_FROM_FILE = "new_signal_from_file"

    def __init__(self, t_s, t_e, param):

        # Start and Ending time of the faults
        self.__t_start = t_s
        self.__t_end = t_e

        # Parameters describing the faults
        self.type_parameter = None
        if type(param) is float or type(param) is int:  # The parameter is a coefficient that modulates the forecast
            self.type_parameter = FaultForecast.TYPE_FORECAST_COEFF_LINEAR
            self.linear_coefficient = param
        elif type(param) is str:
            self.type_parameter = FaultForecast.TYPE_FORECAST_NEW_SIGNAL_FROM_FILE
            self.signal = None  # TODO: read from file

    @property
    def starting_time(self):
        return self.__t_start

    @property
    def ending_time(self):
        return self.__t_end

    def apply_fault(self, forecast_sig):
        """
        This method takes a forecast signal as a parameter and applies the fault on it
        :param forecast_sig: a triple (t_0, dt, sig) containing:
            - t_0: the starting time of the signal
            - dt: the sampling time of the signal
            - sig: the signal data vector
        :return: a signal vector of equal length as "sig", representing the faulted forecast
        """
        (t_0, dt, sig) = forecast_sig

        ret = sig

        if self.type_parameter == FaultForecast.TYPE_FORECAST_COEFF_LINEAR:
            faulted_vector = len(sig) * [1]  # fill with ones

            # Identify the indexes in faulted_vector whereto apply the coefficient
            idx_st = (self.starting_time - t_0)/dt
            idx_end = (self.ending_time - t_0)/dt
            faulted_vector[idx_st:idx_end] = (idx_end - idx_st) * [self.linear_coefficient]

            ret = np.multiply(faulted_vector, ret).tolist()
        else:
            pass  # TODO apply other type of fault

        return ret


# TEST
if __name__ == '__main__':

    test_fault = FaultForecast(12*3600, 18*3600, 0)
    test_forecast = range(0, 96, 1)
    print test_fault.apply_fault((0, 900, test_forecast))
