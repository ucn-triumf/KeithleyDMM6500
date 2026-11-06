# KeithleyDMM6500 to MIDAS

Goal: connect to the Keithley DMM6500 multimeter via ethernet and read a single measurement to the MIDAS history.

## Resources

* [DMM6500 reference manual](https://www.manualslib.com/manual/1440440/Keithley-Dmm6500.html)

## TCP Connection

* Raw SCPI socket on TCP port 5025. Commands and responses are terminated by line feed (`\n`).
* The instrument must use the SCPI command set: front panel Menu > System > Settings > Command Set = SCPI. In TSP mode the SCPI queries are not answered and the frontend fails at startup on `*IDN?`.
* `:MEASure:<function>?` selects the function, triggers, and returns one reading.

## MIDAS settings

`/Equipment/KeithleyDMM6500/Settings`:

* `ip_address`: instrument hostname or IP.
* `quantity`: one of
  * `voltage` — DC voltage (V)
  * `temperature` — unit and transducer (thermocouple/RTD/thermistor) as configured on the instrument
  * `resistance` — 2-wire resistance (Ohm)
  * `resistance_4wire` — 4-wire resistance (Ohm)

The reading is written to bank `DMM0` (one `TID_DOUBLE`).
