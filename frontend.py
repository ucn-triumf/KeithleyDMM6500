# Frontend to readout the KeithleyDMM6500 as a MIDAS equipment
# Derek Fujimoto
# Nov 2026

import midas
import midas.frontend
import midas.event
from KeithleyDMM6500 import KeithleyDMM6500

class KeithleyEquipment(midas.frontend.EquipmentBase):
    """Periodic equipment which reads one DMM6500 measurement into one bank.

    Attributes:
        dmm (KeithleyDMM6500): open connection to the multimeter.
        read_failed (bool): whether the last readout raised, used to avoid
            rewriting the equipment status to the ODB on every cycle.
    """

    def __init__(self, client, hostname="keithley01.ucn.triumf.ca", bank_name="DMM0"):
        # The name of our equipment. This name will be used on the midas status
        # page, and our info will appear in /Equipment/<equip_name> in the ODB.
        equip_name = "KeithleyDMM6500"

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

        # Defaults for /Equipment/<name>/Settings. The base class applies these
        # with update_structure_only=True, so values edited in the ODB survive a
        # restart. mlogger labels the history tags of the variable <var> using
        # the key "Names <var>", hence the bank name below.
        # quantity: one of KeithleyDMM6500.MEASURE_CMD keys
        default_settings = {'ip_address': hostname,
                            'quantity': 'voltage',
                            'Options quantity': ['voltage', 
                                                 'temperature', 
                                                 'resistance', 
                                                 'resistance_4wire'],
                            f'Names {self.bank_name}': ['reading'],
                            }

        midas.frontend.EquipmentBase.__init__(self, client, equip_name,
                                             default_common, default_settings)

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
        self.read_failed = False

        # You can set the status of the equipment (appears in the midas status page)
        self.set_status("Initialized")

    def readout_func(self):
        """Take one reading and package it as a midas event.

        Returns:
            midas.event.Event|None: event with a single TID_DOUBLE bank holding
                the reading, or None if the read failed.
        """

        # read data
        try:
            value = self.dmm.measure(self.settings['quantity'])

        # OSError covers socket failures; ValueError covers an unparseable
        # response. Neither may propagate: FrontendBase.run() has no error
        # handling, so an exception here kills the frontend.
        except (OSError, ValueError, ConnectionError) as err:
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
        event.create_bank(self.bank_name, midas.TID_DOUBLE, [value])

        return event

class KeithleyFrontend(midas.frontend.FrontendBase):
    """
    A frontend contains a collection of equipment.
    You can access self.client to access the ODB etc (see `midas.client.MidasClient`).
    """
    def __init__(self):
        midas.frontend.FrontendBase.__init__(self, "KeithleyDMM6500FE")
        self.add_equipment(KeithleyEquipment(self.client, "keithley01.ucn.triumf.ca", "DMM0"))

    def frontend_exit(self):
        """Close all connections to Keithley devices on the way out."""
        for equip in self.equipment.values():
            equip.dmm.close()

if __name__ == "__main__":
    with KeithleyFrontend() as fe:
        fe.run()
