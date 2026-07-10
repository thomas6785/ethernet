This is a port of the Alex Forencich GHz RGMII Ethernet MAC.

It was forked in Jan 2019 and subsequently modified for lowRISC.

# Overview
- exposes two AXI Stream interfaces and an RGMII interface.
- has loopback mode, and a signal to artificially inject errors into the loopback path for testing CRC.
- TX data automatically has a CRC appended to it.
- RX data automatically has the CRC checked and the AXIS 'tuser' signal indicates an error.

TODO improve these docs with a detailed port list, module hierarchy, etc.

