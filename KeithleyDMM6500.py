"""
Connect to KeithleyDMM6500 over TCP Ethernet (raw SCPI socket). Basic readout queries

The instrument must be set to the SCPI command set (front panel:
Menu > System > Settings > Command Set = SCPI), otherwise SCPI queries are not answered.

To read through a 2000-SCAN scanner card, the front-panel TERMINALS switch must be set to REAR.

Manual:
https://www.manualslib.com/manual/1440440/Keithley-Dmm6500.html

Derek Fujimoto
Nov 2026
"""
import socket
import time

class KeithleyDMM6500(object):
    """Raw-socket SCPI connection to a Keithley DMM6500.

    Attributes:
        socket (socket.socket): open TCP connection to the instrument.
        n_channels (int): number of scanner channels, set by configure_scan().
    """

    # default number of bytes to read out at once
    RECV_BYTES = 1024

    # termination character
    TERM = '\n'

    # max time to wait for a full response (s). :MEAS? at high NPLC or with
    # autorange can take longer than 1 s
    TIMEOUT_S = 5

    # SCPI query for each supported measurement. :MEASure selects the function,
    # triggers, and returns a single reading
    MEASURE_CMD = {'voltage':          ':MEAS:VOLT:DC?',
                   'temperature':      ':MEAS:TEMP?',
                   'resistance':       ':MEAS:RES?',
                   }

    # SCPI function name for each supported measurement, used to configure scanner channels
    FUNCTION_NAME = {'voltage':          'VOLT:DC',
                     'temperature':      'TEMP',
                     'resistance':       'RES',
                     }

    # 2000-SCAN channel count
    SCAN_MAX_CHANNELS = 10

    # reading buffer used for scans
    SCAN_BUFFER = 'defbuffer1'

    def __init__(self, ip, port=5025):
        """Open the connection.

        Args:
            ip (str): hostname or IP address of the instrument.
            port (int): raw SCPI socket port (5025 on the DMM6500).
        """

        # create connection
        self.socket = socket.create_connection((ip, port), timeout=10)

        # set timeout on send/recv
        self.socket.settimeout(self.TIMEOUT_S) # seconds

    def close(self):
        """terminate the connection"""
        self.socket.close()

    def write(self, cmd:str):
        """Send a command which does not return a response.

        Args:
            cmd (str): SCPI command, without terminator.

        Raises:
            ConnectionError: if the socket connection is broken.
        """

        # format cmd
        cmd += self.TERM

        # send cmd - ensure full command is sent
        sent = 0
        while sent < len(cmd):
            s = self.socket.send(cmd[sent:].encode('ascii'))
            sent += s
            if s == 0:
                raise ConnectionError("KeithleyDMM6500 socket connection broken")

    def query(self, cmd:str):
        """Send a query and return the response.

        Args:
            cmd (str): SCPI query, without terminator.

        Returns:
            str: response with whitespace and terminator stripped.

        Raises:
            ConnectionError: if the socket is closed by the instrument.
            TimeoutError: if no complete response arrives within TIMEOUT_S.
        """

        self.write(cmd)

        # read response until terminator character is recorded
        msg = ""
        resp = ""
        t0 = time.monotonic() # timeout on response time
        while self.TERM not in resp:
            resp = self.socket.recv(self.RECV_BYTES).decode()

            # empty read means the instrument closed the connection
            if not resp:
                raise ConnectionError("KeithleyDMM6500 socket closed by instrument")
            msg += resp

            if time.monotonic()-t0 > self.TIMEOUT_S:
                raise TimeoutError("KeithleyDMM6500 timeout on recv")

        return msg.strip()

    def idn(self):
        """Get the instrument identification string.

        Returns:
            str: manufacturer, model, serial number, firmware version.
        """
        return self.query('*IDN?')

    def measure(self, quantity:str):
        """Take a single reading.

        Args:
            quantity (str): one of
                'voltage'          (DC voltage, V),
                'temperature'      (unit and transducer as configured on the instrument),
                'resistance'       (2-wire, Ohm).

        Returns:
            float: measured value.
        """
        assert quantity in self.MEASURE_CMD, \
            f"Unknown quantity '{quantity}', must be one of {list(self.MEASURE_CMD)}"

        return float(self.query(self.MEASURE_CMD[quantity]))

    def configure_scan(self, quantity:str, n_channels:int):
        """Configure a single scan over scanner card channels 1 to n_channels.

        All channels measure the same quantity. Must be called before scan().

        Args:
            quantity (str): one of the MEASURE_CMD keys (see measure()).
            n_channels (int): number of channels to scan, starting at channel 1.
        """
        assert quantity in self.FUNCTION_NAME, \
            f"Unknown quantity '{quantity}', must be one of {list(self.FUNCTION_NAME)}"

        assert 1 <= n_channels <= self.SCAN_MAX_CHANNELS, \
            f"n_channels={n_channels} out of range, must be 1 to {self.SCAN_MAX_CHANNELS}"

        channel_list = f'(@1:{n_channels})'
        self.write(f':SENS:FUNC "{self.FUNCTION_NAME[quantity]}", {channel_list}')
        self.write(f':ROUT:SCAN:CRE {channel_list}')
        self.write(':ROUT:SCAN:COUN:SCAN 1')
        self.n_channels = n_channels

    def scan(self):
        """Run one scan as set by configure_scan() and return the readings.

        Returns:
            list[float]: one reading per channel, in channel order.
        """
        assert hasattr(self, 'n_channels'), "configure_scan() must be called before scan()"

        # the instrument refuses to scan with the front terminals selected. The
        # TERMINALS switch is a physical button and cannot be set over SCPI
        terminals = self.query(':ROUT:TERM?')
        assert terminals == 'REAR', \
            f"Scan needs the rear terminals, but the TERMINALS switch is set to '{terminals}'. " \
            "Press TERMINALS on the instrument front panel to select REAR"

        # clear buffer, run the scan, wait for completion, then fetch the readings
        response = self.query(f':TRAC:CLE "{self.SCAN_BUFFER}";:INIT;*WAI;'
                              f':TRAC:DATA? 1, {self.n_channels}, "{self.SCAN_BUFFER}", READ')
        readings = [float(value) for value in response.split(',')]

        assert len(readings) == self.n_channels, \
            f"Expected {self.n_channels} scan readings, got {len(readings)}: '{response}'"
        return readings
