axis_pkt_ring_buffer.sv : AXI Stream Packet Ring Buffer

# Files
axis_pkt_ring_buffer.sv     - the top of this design
axis_pkt_ring_buffer.core   - FuseSoC .core file with the necessary filelist etc.

# Overview
Reusable design for handling an AXI stream of 'packets' (as delimited by tlast being asserted)

The buffer will store incoming data in a ring buffer
When a packet completes (as indicated by tlast), this module:
- Adds an entry to a 'descriptor table' which contains a pointer to the START of the data in the main buffer
- Captures the pkt_metadata_i into the descriptor table

## Features
- Arbitrary input metadata to be captured when a packet completes
- Addressable data buffer and descriptor table
- 'pop' mechanism to free up space in the buffers
- Status flags:
    - empty_o               - asserted when no packets are waiting in the buffer
    - packet_lost_o         - pulses for one cycle when a packet is dropped due to full buffer/table
    - table_full_o          - asserted when the descriptor table is full
    - buf_almost_full_o     - asserted when the number of remaining slots is less than BufAlmostFullThreshold
    - table_almost_full_o   - asserted when the number of remaining table spaces is less than TableAlmostFullThreshold

- 'abandon' mechanism to indicate that a packet should be abandoned (even after capture has started; any already captured data will be overwritten by the next packet)

## Parameters:
- **PACKET_INDEX_W**            - width of packet indices. Constrains the maximum number of packets in the buffer to 2^n
- **DATA_W**                    - width of the incoming data on the AXI Stream. This is the same width that is read from the buffer
- **BUF_ADDR_W**                - width of buffer addresses. Constrains the buffer size to 2^n words

- **BufAlmostFullThreshold**    - number of free words in the buffer before buf_almost_full_o is asserted. Recommended to be a power of two for cheaper comparator logic
- **TableAlmostFullThreshold**  - number of free slots in the descriptor table befroe table_almost_full_o is asserted. Also recommended to be a power of two.

- **metadata_t**                - TYPE of the metadata input

Validity matrix:
    TODO show which input/output signals are valid at which others
