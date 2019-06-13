import logging

from ctypes import cdll, byref, c_int, create_string_buffer, sizeof
LUCI = cdll.LoadLibrary('LUCI_10_x64.dll')

from qcodes.instrument.parameter import Parameter
from qcodes.instrument.base import Instrument
from qcodes.utils.validators import Enum

log = logging.getLogger(__name__)

LOW_NOISE_GAINS = (1e2, 1e3, 1e4, 1e5, 1e6, 1e7)
HIGH_SPEED_GAINS = (1e3, 1e4, 1e5, 1e6, 1e7, 1e8)
LP_SETTINGS = ('FBW', '10MHz', '1MHz') # ordered by corresponding binary coding 
COUPLING_MODES = ('DC', 'AC')
GAIN_SETTINGS = ('L', 'H')

ERROR_TABLE = {-1: "Invalid index: selected LUCI-10 not in list",
               -2: "Instrument error: LUCI-10 does not respond"}

class OE300Error(Exception):
    def __init__(self, error_code):
        super().__init__(ERROR_TABLE[error_code])


class OE300BaseParam(Parameter):
    def __init__(self, name, instrument, vals, nbits, **kwargs):
        super().__init__(name, instrument, vals, **kwargs)
        self._raw_value = 0
        self._nbits = nbits

    def get_raw(self):
        return self.raw_value_to_value(self.raw_value)

    def set_raw(self, value):
        old_raw_value = self.raw_value

        self._raw_value = self.value_to_raw_value(value)
        try:
            self._instrument.write_data()
        except OE300Error as e:
            self._raw_value = old_raw_value
            raise e
            
    def value_to_raw_value(self, value):
        return self.vals._valid_values.index(value)
        
    def raw_value_to_value(self, raw_value):
        return self.vals._valid_values[raw_value]

    def make_bits(self):
        return f'{self._raw_value:0{self._nbits}b}'


class OE300GainFactor(OE300BaseParam):    
    def set_raw(self, value):        
        old_gain_vals = self._instrument.gain.vals
        gains = LOW_NOISE_GAINS if value == 'L' else HIGH_SPEED_GAINS
        self._instrument.gain.vals = Enum(*gains)
        try:
            super().set_raw(value)
        except OE300Error as e:
            self._instrument.gain.vals = old_gain_vals
            raise e


class OE300(Instrument):
    """
    A driver for the FEMTO OE300 photodiode, controlled through the LUCI-10 interface. The LUCI-10 dll needs to be installed.
    """
    
    def __init__(self, name, index=None, idn=None, **kwargs):
        super().__init__(name, **kwargs)

        # connect to desired device
        idn_tmp = c_int()
        dev_idn_list = []
        for index in range(1, LUCI.EnumerateUsbDevices() + 1): #index starts at 1.
            LUCI.ReadAdapterID(index, byref(idn_tmp))
            dev_idn_list.append(idn_tmp)

        if index is None and idn is None:
            self._index=1
        elif index is None and idn is not None:
            self._index = dev_idn_list.index(idn) + 1 # index starts at 1.
        elif index is not None and idn is None:
            self._index = index
        else:
            if index == dev_idn_list.index(idn) + 1: # index starts at 1.
                self._index = index
            else:
                raise ValueError("index and idn do not match, it is best to only specify one")

        # reset device
        LUCI.WriteData(self._index, 0, 0)

        self.add_parameter('gain',
                           label='Gain',
                           vals=Enum(*LOW_NOISE_GAINS),
                           nbits=3)

        self.add_parameter('coupling',
                           label='Coupling',
                           vals=Enum(*COUPLING_MODES),
                           nbits=1)

        self.add_parameter('gain_mode',
                           label='Gain mode',
                           vals=Enum(*GAIN_SETTINGS),
                           nbits=1)

        self.add_parameter('lp_filter_bw',
                           label='Lowpass filter bandwidth',
                           vals=Enum(*LP_SETTINGS),
                           nbits=2)

    def write_data(self):        
        low_byte = int(self.lp_filter_bw.make_bits() +
                       self.gain_mode.make_bits() +
                       self.coupling.make_bits() +
                       self.gain.make_bits(), 2)
        error_code = LUCI.WriteData(self._index, low_byte, 0)
        if error_code:
            raise OE300Error(error_code)

    def get_idn(self):
        p = create_string_buffer(50)
        LUCI.GetProductString(self._index, p, sizeof(p))

        vendor = 'FEMTO'
        model = p.value.decode()
        serial = None
        firmware = None
        return {'vendor': vendor, 'model': model,
                'serial': serial, 'firmware': firmware}
