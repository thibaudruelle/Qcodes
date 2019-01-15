try:
    import nidaqmx
    from nidaqmx import constants
    from nidaqmx.constants import Edge, AcquisitionType, TerminalConfiguration
except ImportError:
    raise ImportError('Could not find nidaqmx module.')

from qcodes.instrument.base import Instrument
from qcodes.instrument.channel import InstrumentChannel
from qcodes import ArrayParameter, MultiParameter
from qcodes.utils import validators as vals

from functools import partial
import numpy as np


class AIRead(MultiParameter):
    def __init__(self, name, instrument, **kwargs):
        super().__init__(name, names=('',), shapes=((1,),), **kwargs)

        self._task = instrument

    def prepare_AIRead(self):
        clock = self._task.clock

        N_chans = self._task.number_of_channels.get()

        # setpoints
        N_samp = clock.samp_quant_samp_per_chan.get()
        samp_rate = clock.samp_clk_rate.get()
        setpointlist = tuple(np.linspace(0, (N_samp-1)/samp_rate, N_samp))
        spname = 'Time'
        spunit = 's'

        self.setpoints = ((setpointlist,),)*N_chans
        self.setpoint_names = ((spname,),)*N_chans
        self.setpoint_units = ((spunit,),)*N_chans
        self.setpoint_labels = ((spname,),)*N_chans
        self.names = tuple(self._task._task.channel_names)
        self.units = ('V',)*N_chans
        self.labels = self.names
        self.shapes = ((N_samp,),)*N_chans

    def get_raw(self):
        res = self._task._task.read(constants.READ_ALL_AVAILABLE)
        return tuple(np.array(res))


class NIDAQ_StartTrigger(InstrumentChannel):
    def __init__(self, parent: InstrumentChannel, name):
        super().__init__(parent, name)

        trigger = self.parent._task.triggers.start_trigger

        self.add_parameter(name='trig_type',
                           label=' type',
                           set_cmd=lambda x: setattr(trigger, "trig_type", x),
                           get_cmd=lambda: getattr(trigger, "trig_type"),
                           vals=vals.Enum(*constants.TriggerType)
                           )
        
        self.add_parameter(name='dig_edge_src',
                           label='start trigger digital edge source',
                           set_cmd=lambda x: setattr(trigger, "dig_edge_src", x),
                           get_cmd=lambda: getattr(trigger, "dig_edge_src"),
                           vals=vals.Strings()
                           )


class NIDAQ_SampleClock(InstrumentChannel):
    def __init__(self, parent: InstrumentChannel, name, rate, source="",
                 active_edge=Edge.RISING,
                 sample_mode=AcquisitionType.FINITE,
                 samps_per_chan=1000):
        super().__init__(parent, name)

        timing = self.parent._task.timing

        timing.cfg_samp_clk_timing(rate, source, active_edge, sample_mode, samps_per_chan)

        # self.add_parameter(name='type',
        #                    label='sample timing type',
        #                    set_cmd=lambda x: setattr(timing, "samp_timing_type", x),
        #                    get_cmd=lambda: getattr(timing, "samp_timing_type"),
        #                    vals=vals.Enum(*SampleTimingType)
        #                    )

        self.add_parameter(name='samp_clk_rate',
                           label='sampling rate',
                           unit='samples/s',
                           set_cmd=lambda x: setattr(timing, "samp_clk_rate", x),
                           get_cmd=lambda: getattr(timing, "samp_clk_rate"),
                           vals=vals.Numbers(min_value=0, max_value=timing.samp_clk_max_rate)
                           )
        
        self.add_parameter(name='samp_quant_samp_mode',
                           label='acquisition type',
                           set_cmd=lambda x: setattr(timing, "samp_quant_samp_mode", x),
                           get_cmd=lambda: getattr(timing, "samp_quant_samp_mode"),
                           vals=vals.Enum(*AcquisitionType)
                           )
        
        self.add_parameter(name='samp_quant_samp_per_chan',
                           label='N samples',
                           unit='',
                           set_cmd=lambda x: setattr(timing, "samp_quant_samp_per_chan", x),
                           get_cmd=lambda: getattr(timing, "samp_quant_samp_per_chan"),
                           vals=vals.Ints(min_value=0)
                           )
        
        self.add_parameter(name='samp_clk_src',
                           label='sample clock source',
                           set_cmd=lambda x: setattr(timing, "samp_clk_src", x),
                           get_cmd=lambda: getattr(timing, "samp_clk_src"),
                           vals=vals.Strings()
                           )


class NIDAQ_AIChannel(InstrumentChannel):
    def __init__(self, parent: InstrumentChannel, name, chanid,
                 terminal_config=TerminalConfiguration.RSE,
                 min_val=-10, max_val=10):
        super().__init__(parent, name)

        chan = self.parent._task.ai_channels.add_ai_voltage_chan(
            chanid, name, terminal_config=terminal_config, min_val=min_val, max_val=max_val)
             
        self._chan = chan

        self.add_parameter(name='ai_term_cfg',
                           label='ai terminal configuration',
                           set_cmd=lambda x: setattr(chan, "ai_term_cfg", x),
                           get_cmd=lambda: getattr(chan, "ai_term_cfg"),
                           vals=vals.Enum(*constants.TerminalConfiguration)
                           )

        self.add_parameter(name='ai_min',
                           label='ai min value',
                           unit='V',
                           set_cmd=lambda x: setattr(chan, "ai_min", x),
                           get_cmd=lambda: getattr(chan, "ai_min"),
                           vals=vals.Numbers()
                           )

        self.add_parameter(name='ai_max',
                           label='ai max value',
                           unit='V',
                           set_cmd=lambda x: setattr(chan, "ai_max", x),
                           get_cmd=lambda: getattr(chan, "ai_max"),
                           vals=vals.Numbers()
                           )


class NIDAQ_Task(InstrumentChannel):
    def __init__(self, parent: Instrument, name):
        super().__init__(parent, name)

        self._task = task =  nidaqmx.Task(name)

        self.add_submodule("start_trigger",
                           NIDAQ_StartTrigger(self, "start_trigger"))

        self.add_parameter(name='number_of_channels',
                           label='number of channels',
                           get_cmd=lambda: getattr(task, "number_of_channels")
                           )

        self.add_parameter('AIRead',
                           parameter_class=AIRead,
                           )

    def add_ai_channel(self, channame, chanid,
                       terminal_config=TerminalConfiguration.RSE,
                       min_val=-10, max_val=10):
        chan = NIDAQ_AIChannel(self, channame, chanid, terminal_config, min_val, max_val)
        self.add_submodule(channame, chan)

    def add_sample_clock(self, rate, source="",
                         active_edge=Edge.RISING,
                         sample_mode=AcquisitionType.FINITE,
                         samps_per_chan=1000):
        clockname = "clock"
        clock = NIDAQ_SampleClock(self, clockname, rate, source,
                                  active_edge, sample_mode, samps_per_chan)
        self.add_submodule(clockname, clock)

    def read(self):
        self._task.read()

    def start(self):
        self._task.start()

    def stop(self):
        self._task.stop()

    def close(self):
        self._task.close()


class PXI_6251(Instrument):
    """
    QCoDeS driver for NI PXI 6251 DAQ card.

    Requires nidaqmx module to be installed (pip install nidaqmx).
    """

    def __init__(self, name: str, device_name: str = 'PXI-6251', **kwargs):
        """
        Create an instance of the instrument.

        Args:
            name (str): The internal QCoDeS name of the instrument
            device_name (str): The device name from the list
                system = nidaqmx.system.System.local()
                [device.name for device in system.devices]
        """

        super().__init__(name, **kwargs)

        self._device = nidaqmx.system.device.Device(device_name)
        self._device_name = self._device.name
        self._ai_channels = self._device.ai_physical_chans.channel_names
        self._ao_channels = self._device.ao_physical_chans.channel_names
        self._ci_channels = self._device.ci_physical_chans.channel_names
        self._co_channels = self._device.ci_physical_chans.channel_names
        self._di_lines = self._device.di_lines.channel_names
        self._di_ports = self._device.di_ports.channel_names
        self._do_lines = self._device.do_lines.channel_names
        self._do_ports = self._device.do_ports.channel_names
        self._terminals = self._device.terminals
            
    def get_idn(self):
        """
        Returns:
            A dict containing vendor, model, serial, and firmware.
        """

        idn_dict ={
            'vendor': 'NI',
            'model': self._device.product_type,
            'serial': str(self._device.product_num),
            'firmware': ''
        }

        return idn_dict

    def add_task(self, taskname):
        task = NIDAQ_Task(self, taskname)
        self.add_submodule(taskname, task)