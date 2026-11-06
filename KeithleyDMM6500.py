"""
Connect to KeithleyDMM6500 over TCP Ethernet (raw SCPI socket). Basic readout queries

The instrument must be set to the SCPI command set (front panel:
Menu > System > Settings > Command Set = SCPI), otherwise SCPI queries are not answered.

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
                   'resistance_4wire': ':MEAS:FRES?',
                   }

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

        # format cmd
        cmd += self.TERM

        # send cmd - ensure full command is sent
        sent = 0
        while sent < len(cmd):
            s = self.socket.send(cmd[sent:].encode('ascii'))
            sent += s
            if s == 0:
                raise ConnectionError("KeithleyDMM6500 socket connection broken")

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
                'resistance'       (2-wire, Ohm),
                'resistance_4wire' (4-wire, Ohm).

        Returns:
            float: measured value.
        """
        assert quantity in self.MEASURE_CMD, \
            f"Unknown quantity '{quantity}', must be one of {list(self.MEASURE_CMD)}"

        return float(self.query(self.MEASURE_CMD[quantity]))
