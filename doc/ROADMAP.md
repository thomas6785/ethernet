# Table
TODO attach a table of roadmap features organised by type and priority

# Notes and explanations (where necessary)

## Clean up registers for TX/RX control
Put the following into a register together called `TX_ctrl`:
* TX packet length
* Loopback enable - this should be considered a configuration field for TX, not RX
* Loopback error inject - this should also be reworked to behave as a self-clearing flag or a countdown timer rather than a pulse, allowing the host to more easily inject errors into the middle of a packet without precisely timing the register write
* (read-only) current position of the TX pointer (maybe - see below)
* pointer to packet head in memory for DMA engine (maybe - see below)

This more cleanly separates the RX and TX control registers:
* promiscuous is an RX option
* pop is an RX option
* loopback is a TX option

## Allow TX buffer writes during TX
Currently the host cannot begin writing the next packet until the current one is done - this is a major bottleneck!
One possible solution is to expose the TX pointer to the host through a status register.
Another option is to implement a DMA engine for TX (as outlined below). Note that implementing an RX DMA engine is quite a complex challenge, but it may be suitable to use a DMA engine for TX, and continue to use internal buffers for RX.

## SoC for test
- Create a minimal SoC with a simple core, memory, and bus
- Connect the Ethernet IP to this SoC and set up a linker script/Makefile for Ethernet firmware
- This will enable:
    - integration testing with a broader range
    - automated testing of the HAL

## Alternative buses for top level
Currently the ethernet top uses a simple memory interface, and an adapter to AXI supports AXI4.

It may be beneficial to support other protocols:
    - AHB
    - TileLink
    - Wishbone
    - APB (for CSRs only)

Each will require an adapter layer and testbench

## AXI crossbar
Currently the AXI top converts the entire AXI interface into a single memory interface which is shared by all four memory regions (TX data, RX data, RX metadata, CSRs). This causes a bottleneck and there is no reason why we can't support simultaneous reads/writes from different memory regions.

To address this, create an AXI crossbar that splits the incomign AXI into four AXI ports. Then convert each AXI port into a memory interface.

This warrants an analysis of the tradeoffs it offers. There could be considerable hardware overhead depending on the complexity of the AXI-memory adapter. Equally, there could be considerable payoff if periods of heavy traffic are being bottlenecked by movement of TX/RX data.

## Decouple TX/RX memories from the design
- Memory is highly technology dependent and carefully managed, so having it tightly coupled with the design is not ideal
- Move the TX/RX memory buffers to nearer the surface of the design instead of being several layers deep into their respective ```*_framing``` modules
- This will also be the first step to allowing the Ethernet IP to perform a DMA by accessing memory via a bus

## Support DMA
- Separate the RX/TX control logic entirely from the data buffers, placing the data buffers in a module that WRAPS the core
- Create an alternate version of this wrapper which transforms the memory interfaces for TX/RX into an AXI master port

In this case, addressing is not trivial:
- The TX framer can have a ```TX_BASE_ADDRESS``` config register which it will read from
- The RX framer will need an ```RX_BASE_ADDRESS``` and ```RX_BUFFER_SIZE``` to write packets to. The developer will be responsible for ensuring these memory regions are appropriately allocated to the Ethernet.
    - Each packet would store an offset relative to the base address in the descriptor table
    - This can get very tricky if the user switches base address - old packets will still be at the old memory location.
        - One option is to include a bit on each packet that is set when the RX base address changes, as an indicator that the packet was received before the change.
        - Another option is simply to specify that any packets in the buffer are invalidated when the RX buffer moves.
        - Finally, we could redesign the RX framing entirely, abandon the 'descriptor table' and simply rely on inline metadata in the memory buffer. A typical flow then might be to allocate a chunk of memory and let the RX run until it is full, then allocate a new chunk of memory while the software is consuming the old one. Not including a descriptor table makes it difficult for software to peek ahead at arbitrary packets, which they are unlikely to do anyway. It also makes it difficult to know if there is another packet next in the buffer or not, but we can work around that. Finally, not using a ring buffer introduces complications where a packet may begin in one buffer, run out of space, and switch to a second buffer.
