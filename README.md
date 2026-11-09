# KeithleyDMM6500 to MIDAS

Goal: connect to the Keithley DMM6500 multimeter via ethernet and read a single measurement to the MIDAS history.

## Resources

* [DMM6500 reference manual](https://www.manualslib.com/manual/1440440/Keithley-Dmm6500.html)
* [SCAN multiplex card manual](https://download.tek.com/manual/2000SCAN-901-01_F-Jan-2014.pdf)

## TCP Connection

* Raw SCPI socket on TCP port 5025. Commands and responses are terminated by line feed (`\n`).
* The instrument must use the SCPI command set: front panel Menu > System > Settings > Command Set = SCPI. In TSP mode the SCPI queries are not answered and the frontend fails at startup on `*IDN?`.
* `:MEASure:<function>?` selects the function, triggers, and returns one reading.

## MIDAS settings

One frontend (`KeithleyDMM6500FE`) runs one equipment per DMM

`/Equipment/<equipment>/Settings`:

* `ip_address`: instrument hostname or IP.
* `quantity`: one of
  * `voltage` — DC voltage (V)
  * `temperature` — unit and transducer (thermocouple/RTD/thermistor) as configured on the instrument
  * `resistance` — 2-wire resistance (Ohm)
* `is_multiplex`: `n` (default) for a single reading from the front/rear inputs, `y` to scan all 10 2000-SCAN channels. Must be set to `y` by hand on the DMM with the scanner card.
* `Names <bank>`: history labels. Resized automatically to the bank length; empty entries are labelled `<bank>_<index>` by mlogger.

Each equipment writes its bank as `TID_DOUBLE`: one value, or 10 values in channel order when multiplexed.

## Multiplexer Board

One DMM has a 2000-SCAN card (10 channels, 2-wire measurements only).

* Set the front-panel TERMINALS switch to REAR.
* All channels use the same `quantity`. The scan is configured at startup and again whenever the settings change, so `quantity` and `is_multiplex` can be edited live.
* Each cycle: `:TRAC:CLE`, `:INIT`, `*WAI`, `:TRAC:DATA? 1, 10, "defbuffer1", READ`.
* The 2000-SCAN switches channels with mechanical relays, and each switch makes a click. A scan of all 10 channels clicks at least 10 times. Watch for relay wear. Every channel's relay operates once per scan, which at a 1000 ms period is about 86,000 operations per channel per day, or roughly 30 million a year. Relays have a finite life, and switching a live signal wears them faster than switching with no load.