# Basic Operation

This lowRISC Ethernet interface provides separate TX and RX paths for full-duplex operation.

It has dedicated physical memory with one write-only buffer for TX, a read-only buffer for RX data, and a read-only metadata table for RX metadata.

The software must explicitly free packets in the RX buffer.

# Hardware Abstraction Layer
The HAL is available under `src/sw/ethernet.c` (and associated headers). It provides a large amount of low-level methods for accessing individual registers and buffers (with the appropriate 'volatile' keywords and such).

For writing a driver, you may find the following high-level methods useful:

* `ethernet_init(ethernet_t ethernet, uint64_t mac_address, bool promiscuous, ethernet_intr intr_mask)`
* `ethernet_pkt_metadata_t ethernet_read_and_pop_oldest_packet(ethernet_t ethernet, uint8_t *data)`
* `uint8_t ethernet_send_packet(ethernet_t ethernet, uint8_t *data, uint16_t len_bytes)`
* `void ethernet_disable(ethernet_t ethernet)`

Additionally, for MDIO communications you may need:
* `void ethernet_mdio_dir_set(ethernet_t ethernet, bool mdio_out_en)`
* `void ethernet_mdio_out_set(ethernet_t ethernet, bool mdio_out)`
* `bool ethernet_mdio_in_get(ethernet_t ethernet)`
* `bool ethernet_mdio_c_set(ethernet_t ethernet, bool mdio_clk)`

Depending on the needs of your driver, it may be necessary (and acceptable) to directly access lower-level methods instead.

See `src/sw/ethernet.c` for a full list of available functions.

See `ethernet.h` and `ethernet_autogen.h` for type definitions.

# Initialisation using `ethernet_init`
`ethernet_init` is provided to initialise the Ethernet interface. It takes the following arguments:

* `ethernet_t ethernet` - pointer to an `ethernet_t` struct. This should point to the base address of the ethernet device in your SoC's memory map.
* `uint64_t mac_address` - the MAC address to configure the Ethernet to listen for. The upper 16 bits will be ignored, as MAC addresses are 48 bits. If the 'promiscuous' mode is used, this does nothing, as all packets will be received regardless of their destination MAC address.
* `bool promiscuous` - enable/disable promiscuous mode. In promiscuous mode, all packets are received in the buffer and made available to the host, regardless of whether they are intended for this device. In non-promiscuous mode, only packets whose destination MAC address matches the one set above will be received.
* `ethernet_intr intr_mask` - provide a mask to configure interrupt conditions. The mask can be constructed from one-hot flags based as described by the `ethernet_intr` type in the header file.

For example, to configure Ethernet to listen only for MAC address `0xDEADBEEFCAFE` and to raise an interrupt when a transmission completes, or whenever there are any packets in the buffer:

```C
ethernet_t my_ethernet_struct = get_soc_ethernet();
uint64_t my_mac_addr = 0xDEADBEEFCAFE;
bool promiscuous_en = 0;
ethernet_intr intr_mask = ethernet_intr_rx_not_empty | ethernet_intr_tx_done;
ethernet_init(my_ethernet_struct, 0xDEADBEEFCAFE, promiscuous_en, intr_mask);
```

Additionally, on initialisation, any outstanding interrupt flags will be cleared, and any packets remaining in the RX buffer will be popped.

# TX
To transmit a packet, call:
```C
uint8_t ethernet_send_packet(ethernet_t ethernet, uint8_t *data, uint16_t len_bytes)
```
Your 'data' array should include the entire PACKET but not FRAME, i.e.:
- DO NOT include the preamble and SFD
- include the source MAC address
- include the destination MAC address
- include the 802.1Q tag (optionally)
- include the length/ethertype
- include the payload
- DO NOT include the frame check sequence
- DO NOT include an interpacket gap

This function will copy the provided array then return immediately. Transmission completes in the background and can be monitored by checking
```C
bool ethernet_tx_is_busy(ethernet_t ethernet)
```
When a TX completes, the `tx_done` flag in the `INTR_STATE` register will be set.

# RX
The Ethernet interface is always receiving.

The hardware will filter packets and will receive a packet for one of four reasons:
- The MAC address is a broadcast address
- The MAC address is a multicast address
- The MAC address matches the one set for this device
- The device is in promiscuous mode

Five flags may be set in the `INTR_STATE` register by RX packets:
- `rx_not_empty` - one or more packets are in the buffer
- `rx_table_almost_full` - six or more packets are in the buffer
- `rx_table_full` - eight packets in the buffer
- `rx_buf_almost_full` - remaining buffer capacity less than one maximum-sized packet
- `intr_packet_lost` - a packet was lost at some point (write to clear)

To receive a packet, call the following:
```C
ethernet_pkt_metadata_t ethernet_read_and_pop_oldest_packet(ethernet_t ethernet, uint8_t *data)
```

This will return a metadata struct which indicates:

* the length of the received packet, in bytes
* the reason it was captured
* a pointer to the ring buffer **which you should ignore**

It will also copy the packet data over the `*data` provided. Therefore, `data` should be an array with 1518 bytes allocated, to fit a maximum-sized Ethernet packet.

Calling this method will free up that packet's buffer space from the Ethernet interface.
This can be safely called if there are no packets buffered. If no packet exists in the buffer, the returned metadata will indicate a packet length of zero.

# Disabling
The method `ethernet_disable` instructs the device to stop listening for incoming packets.
Any packets transmitted while Ethernet is disabled will be looped back to the RX path, which can also be used for testing.
All interrupts will be disabled after calling `ethernet_disable`.
Any packets already present in the RX buffer will remain there until popped.
