# Frontend to readout the KeithleyDMM6500 as a MIDAS equipment
# Derek Fujimoto
# Nov 2026

import midas
import midas.frontend
import midas.event
from KeithleyDMM6500 import KeithleyDMM6500

class KeithleyFrontend(midas.frontend.FrontendBase):
    """
    A frontend contains a collection of equipment.
    You can access self.client to access the ODB etc (see `midas.client.MidasClient`).
    """
    def __init__(self):
        midas.frontend.FrontendBase.__init__(self, "KeithleyDMM6500FE")
        
        # one equipment per DMM
        self.add_equipment(KeithleyEquipment(self.client,
                                             equip_name="KeithleyDMM01",
                                             hostname="keithleydmm01.ucn.triumf.ca",
                                             bank_name="DMM1"))
        self.add_equipment(KeithleyEquipment(self.client,
                                             equip_name="KeithleyDMM02",
                                             hostname="keithleydmm02.ucn.triumf.ca",
                                             bank_name="DMM2"))

    def frontend_exit(self):
        """Close all connections to Keithley devices on the way out."""
        for equip in self.equipment.values():
            equip.dmm.close()

class KeithleyEquipment(midas.frontend.EquipmentBase):
    """Periodic equipment which reads one DMM6500 into one bank: a single
    measurement, or one measurement per 2000-SCAN channel if is_multiplex.

    Attributes:
        dmm (KeithleyDMM6500): open connection to the multimeter.
        read_failed (bool): whether the last readout raised, used to avoid
            rewriting the equipment status to the ODB on every cycle.
    """

    N_CHANNELS = 10 # for multiplexed devices

    def __init__(self, client,
                 equip_name="KeithleyDMM01",
                 hostname="keithleydmm01.ucn.triumf.ca",
                 bank_name="DMM0"):
        default_common = midas.frontend.InitialEquipmentCommon()
        default_common.equip_type = midas.EQ_PERIODIC
        default_common.read_when = midas.RO_ALWAYS
        default_common.buffer_name = "SYSTEM"
        default_common.trigger_mask = 0
        default_common.event_id = 1
        default_common.period_ms = 1000
        default_common.log_history = 10

        self.hostname = hostname
        self.bank_name = bank_name

        # Defaults for /Equipment/<name>/Settings. 
        # quantity: one of KeithleyDMM6500.MEASURE_CMD keys
        default_settings = {'ip_address': hostname,
                            'quantity': 'voltage',
                            'Options quantity': ['voltage',
                                                 'temperature',
                                                 'resistance'],
                            'is_multiplex': False,
                            f'Names {self.bank_name}': [""],
                            }

        midas.frontend.EquipmentBase.__init__(self, client, equip_name,
                                             default_common, default_settings)

        # must run before mlogger reads the equipment, else history is skipped
        self.resize_history_names()

        # validate once here so readout_func never sees a bad quantity
        quantity = self.settings['quantity']
        if quantity not in KeithleyDMM6500.MEASURE_CMD:
            self.client.msg(f'{equip_name}: invalid quantity "{quantity}", must be one of '
                            f'{list(KeithleyDMM6500.MEASURE_CMD)}', is_error=True)
            raise ValueError(f'Invalid quantity "{quantity}"')

        # connect to DMM - self.settings is populated by the base class. The
        # *IDN? query fails here if the instrument is not in SCPI mode
        try:
            self.dmm = KeithleyDMM6500(self.settings['ip_address'])
            self.client.msg(f'{equip_name}: connected to {self.dmm.idn()}')
        except Exception as err:
            self.client.msg(f'{equip_name}: unable to connect to KeithleyDMM6500', is_error=True)
            raise err from None

        # set up the scanner card, if used
        if self.settings['is_multiplex']:
            try:
                self.dmm.configure_scan(quantity, self.N_CHANNELS)
            except Exception as err:
                self.client.msg(f'{equip_name}: unable to configure scan: {err}', is_error=True)
                raise err from None
        self.read_failed = False

        # You can set the status of the equipment (appears in the midas status page)
        self.set_status("Initialized")

    def readout_func(self):
        """Take one reading and package it as a midas event.

        Returns:
            midas.event.Event|None: event with a single TID_DOUBLE bank holding
                the reading, or None if the read failed.
        """

        # read data: all scanner channels, or a single reading
        try:
            if self.settings['is_multiplex']:
                values = self.dmm.scan()
            else:
                values = [self.dmm.measure(self.settings['quantity'])]

        # OSError covers socket failures; ValueError covers an unparseable
        # response; AssertionError covers a scan with the wrong number of
        # readings. None may propagate: FrontendBase.run() has no error
        # handling, so an exception here kills the frontend.
        except (OSError, ValueError, ConnectionError, AssertionError) as err:
            if not self.read_failed:
                self.read_failed = True
                self.set_status(f"Read failed: {err}", "redLight")
            return None

        # recovered from an earlier failure
        if self.read_failed:
            self.read_failed = False
            self.set_status("Running")

        # bank names must be exactly 4 characters
        event = midas.event.Event()
        event.create_bank(self.bank_name, midas.TID_DOUBLE, values)

        return event

    def settings_changed_func(self):
        """Reconfigure the scan when the ODB settings change.

        Runs from an ODB callback, so errors are reported in the status rather
        than raised.
        """
        self.resize_history_names()

        if not self.settings['is_multiplex']:
            return

        try:
            self.dmm.configure_scan(self.settings['quantity'], self.N_CHANNELS)
        except (OSError, AssertionError) as err:
            self.client.msg(f'{self.name}: unable to configure scan: {err}', is_error=True)
            self.set_status(f"Scan config failed: {err}", "redLight")

    def resize_history_names(self):
        """Match the length of the history names array to the bank length."""
        names_key = f'Names {self.bank_name}'
        names = self.settings[names_key]

        # a length-1 ODB array may be returned as a scalar
        if not isinstance(names, list):
            names = [names]

        n_values = self.N_CHANNELS if self.settings['is_multiplex'] else 1
        if len(names) != n_values:
            names = (names + [""]*n_values)[:n_values]
            self.client.odb_set(f'{self.odb_settings_dir}/{names_key}', names)



if __name__ == "__main__":
    with KeithleyFrontend() as fe:
        fe.run()
