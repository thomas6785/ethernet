"""
Testbench for the ethernet_top
"""

import random
import logging

from functools import wraps

import cocotb
from cocotb.simtime import get_sim_time
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge,Combine,Timer

from models import AxiEthernetDutWithMirror,AxiEthernetWrapper
from models import TX_BUFFER_BASE,RX_BUFFER_BASE,RX_TABLE_BASE
from test_utils import create_test

from logging.handlers import RotatingFileHandler
from cocotb.logging import SimLogFormatter

#####################
# Configure logging #
#####################
logging.getLogger("cocotb.ethernet_top_axi_tb.axi").setLevel(logging.WARNING)
logging.getLogger("cocotb.ethernet_top_axi_tb.eth_rgmii_tx_data").setLevel(logging.WARNING)
logging.getLogger("cocotb.ethernet_top_axi_tb.eth_rgmii_rx_data").setLevel(logging.WARNING)
# The AXI library prints an INFO() for every single transaction... it's very noisy. Long-term it would be best to submit a PR to demote these to debug()

root_logger = logging.getLogger()
meta_logger = logging.getLogger("cocotb.meta")

# undo the setup cocotb did
for handler in root_logger.handlers:
    root_logger.removeHandler(handler)
    handler.close()

# Add a log file handler with rotation
file_handler = RotatingFileHandler("coco.log", backupCount=2)
file_handler.doRollover() # rollover the log file to start fresh each time
file_handler.setFormatter(SimLogFormatter(strip_ansi=True))
file_handler.setLevel(logging.INFO)  # Adjust the level as needed
root_logger.addHandler(file_handler)

# Add a console handler for real-time output
console_handler = logging.StreamHandler()
console_handler.setFormatter(SimLogFormatter())
console_handler.setLevel(logging.INFO)  # Adjust the level as needed
root_logger.addHandler(console_handler)

##############
# Reset test #
##############
@create_test()
async def reset_state_test(dut_wrapped):
    # Check all registers/state is reset to expected values
    await dut_wrapped.intr_state_get()
    await dut_wrapped.intr_mask_get()
    await dut_wrapped.status_get()
    await dut_wrapped.mode_get()
    await dut_wrapped.mac_address_get()
    await dut_wrapped.rx_packet_pending()
    await dut_wrapped.irq_pending()

#############################
# Register read/write tests #
#############################
@create_test(with_mirror=True)
async def reg_mac_addr_test(dut_wrapper):
    # Check value after reset matches
    await dut_wrapper.mac_address_get()

    # Check recognisable value
    await dut_wrapper.mac_address_set([0x12,0x34,0x56,0x78,0x9a,0xbc][::-1])
    await dut_wrapper.mac_address_get()

    # Check min and max
    await dut_wrapper.mac_address_set([0]*6)
    await dut_wrapper.mac_address_get()
    await dut_wrapper.mac_address_set([255]*6)
    await dut_wrapper.mac_address_get()

    # Random values
    for _ in range(5):
        await dut_wrapper.mac_address_set([random.randint(0,255) for _ in range(6)])
        await dut_wrapper.mac_address_get()

@create_test(with_mirror=True)
async def reg_intr_mask_test(dut_wrapped):
    await dut_wrapped.intr_mask_set(0)
    await dut_wrapped.intr_mask_get()
    await dut_wrapped.intr_mask_set(127)
    await dut_wrapped.intr_mask_get()
    for _ in range(5):
        randval = random.randint(0, 127)
        await dut_wrapped.intr_mask_set(randval)
        await dut_wrapped.intr_mask_get()

@create_test(with_mirror=True)
async def reg_intr_test_test(dut_wrapped):
    await dut_wrapped.intr_mask_set(127)
    await dut_wrapped.test_intr()
    await dut_wrapped.irq_pending()
    await dut_wrapped.intr_mask_set(0)
    await dut_wrapped.irq_pending()
    for i in range(8):
        await dut_wrapped.intr_mask_set(1<<i)
        irq_pending = await dut_wrapped.irq_pending() # get IRQ pending state for the model and DUT to check they match
        assert irq_pending == (i==6), f"IRQ pending should be {i==6} when INTR_TEST is fired and INTR_MASK is {1<<i}"

@create_test(with_mirror=True)
async def reg_ctrl_test(dut_wrapped):
    await dut_wrapped.mode_set(0,0)
    await dut_wrapped.mode_get()
    await dut_wrapped.mode_set(1,0)
    await dut_wrapped.mode_get()
    await dut_wrapped.mode_set(0,1)
    await dut_wrapped.mode_get()
    await dut_wrapped.mode_set(1,1)
    await dut_wrapped.mode_get()

@create_test(with_mirror=True)
async def reg_status_test(dut_wrapped):
    await dut_wrapped.status_get()
    # TODO tests covering status and INTR_STATE flags

#################
# Loopback test #
#################
@create_test(
    with_mirror=True,
    loopback=True,
    promiscuous=True,
    prep_tx_buffer=True
)
async def loopback_basic_test(dut_wrapped):
    await dut_wrapped.tx_packet_send(64)
    await dut_wrapped.wait_for_tx_done()

    # Check packet was received
    await dut_wrapped.rx_packet_pending()
    await dut_wrapped.rx_buffer_metadata_get(0)
    await dut_wrapped.read_packet(0) # read the data and check it matches between the model and the DUT

@create_test(
        with_mirror=True,
        loopback=True,
        promiscuous=True,
        prep_tx_buffer=True
)
async def loopback_b2b_transmissions(dut_wrapped):
    for i in range(8):
        # kick off the transmission of a random-length packet
        await dut_wrapped.tx_packet_send(random.randint(56,1518)) # send a random-length packet between 60 and 1518 bytes

        for _ in range(10):
            await RisingEdge(dut_wrapped.dut.clk_125M_i) # wait a bit for the RX path of the previous packet to finish
        # while that's running check some status bits
        assert (await dut_wrapped.wrapper.status_get())>>8 == i # check the number of packets pending in the RX table

        # wait for that to complete
        await dut_wrapped.wait_for_tx_done(tail_after_done=random.randint(0,8)) # wait for TX to finish

    for _ in range(10):
        await RisingEdge(dut_wrapped.dut.clk_125M_i) # wait a bit for the RX path of the final packet to finish
    assert await dut_wrapped.status_get() # check the final status matches the model

    # The timing of this test case is a bit tricky to grasp:
    # To test the IPG enforcement, we have to make sure we immediately start the next transmission after one ends
    # so checking any statuses etc. is done inbetween
    # The wait_for_tx_done() function waits to the TX path to finish but it may still be propagating through the RX path

    # So the loop, repeated 8 times, is:
    # - Kick off a packet
    # - Wait a few cycles for the PREVIOUS packet to finish propagating the the RX path
    # - Verify that the PREVIOUS packet was received by checking the status register (not entirely necessary but doesn't hurt)
    # - Wait for this packet's TX to finish
    # - Wait a SMALL NUMBER OF CYCLES
    # - Restart the loop

    # one last bit of trickery: the DUT takes sim time for the packet to be received, so if we call tx_packet_send() then status_get() immediately, the new packet won't be reflected yet
    # the MODEL doesn't have this - the new packet arrives instantly. For this reason, when we call status_get we call it directly on the DUT wrapper, skipping the comparison with the model
    # this is a known and deliberate limitation of the model and does not compromise the usefulness of this test as there are others checks in place:
    #   - the final state is compared with the model
    #   - assertions in the SystemVerilog check the IPG is enforced

    # The polling to check if a packet has finished TX yet takes 4 cycles here, so in the worst case we might not proceed with the test until 4 cycles after the TX finished
    # the IPG is 12 bytes = 12 cycles
    # so to make sure we are always testing that we should wait no more than 8 cycles after the previous TX finished
    # otherwise we are just sending two packets and there is no way to know if the IPG was enforced or not

@create_test(
    loopback = True,
    promiscuous = True
)
async def loopback_b2b_edge_case_test(dut_wrapped):
    # Test case covering the possibility that the instruction to TX a new packet arrives JUST as the previous one finishes
    pass
    # TODO write this test

#######################
# MAC Filtering Tests #
#######################
@create_test(
    with_mirror=True,
    loopback=True,
    promiscuous=False,
    mac_addr=[0xDE,0xAD,0xBE,0xEF,0xCA,0xFE][::-1],
    prep_tx_buffer=True
)
async def mac_non_match_test(dut_wrapped):
    # Send a packet
    await dut_wrapped.tx_packet_send(64)
    await dut_wrapped.wait_for_tx_done()

    # Check packet was NOT received due to MAC mismatch
    assert not (await dut_wrapped.rx_packet_pending()), "Expected no packet after mismatching MAC without promiscuous mode"

@create_test(
    with_mirror=True,
    loopback=True,
    promiscuous=random.choice([False,True]), # can be promiscuous or not, shouldn't matter
    mac_addr=[0xDE,0xAD,0xBE,0xEF,0xCA,0xFE][::-1],
    prep_tx_buffer=True
)
async def mac_match_test(dut_wrapped):
    # Send a packet with matching MAC
    await dut_wrapped.tx_buffer_write64(0,0xBEBAFECAEFBEADDE)
    await dut_wrapped.tx_packet_send(64)
    await dut_wrapped.wait_for_tx_done()

    # Check packet was received due to MAC match
    assert (await dut_wrapped.rx_packet_pending()), "Expected packet after sending with matching MAC without promiscuous mode"
    await dut_wrapped.rx_buffer_metadata_get(0)
    await dut_wrapped.read_packet(0) # read the data and check it matches between the model and the DUT

@create_test(
    with_mirror=True,
    loopback=True,
    promiscuous=True,
    mac_addr=[0xDE,0xAD,0xBE,0xEF,0xCA,0xFE][::-1],
    prep_tx_buffer=True
)
async def mac_promiscuous_test(dut_wrapped):
    # Send a packet
    await dut_wrapped.tx_packet_send(64)
    await dut_wrapped.wait_for_tx_done()

    # Check packet was received due to promiscuous mode
    assert (await dut_wrapped.rx_packet_pending()), "Expected packet after sending in promiscuous mode"
    await dut_wrapped.rx_buffer_metadata_get(0)
    await dut_wrapped.read_packet(0)

@create_test(
    with_mirror=True,
    loopback=True,
    promiscuous=random.choice([True,False]), # for broadcast, promiscuity shouldn't matter
    mac_addr=[0xDE,0xAD,0xBE,0xEF,0xCA,0xFE][::-1],
    prep_tx_buffer=True
)
async def mac_broadcast_test(dut_wrapped):
    # Send a broadcast packet
    await dut_wrapped.tx_buffer_write64(0,0x0000FFFFFFFFFFFF)
    await dut_wrapped.tx_packet_send(64)
    await dut_wrapped.wait_for_tx_done()

    # Check packet was received due to broadcast address
    assert (await dut_wrapped.rx_packet_pending()), "Expected packet after sending broadcast address"
    await dut_wrapped.rx_buffer_metadata_get(0)
    await dut_wrapped.read_packet(0)

@create_test(
    with_mirror=True,
    loopback=True,
    promiscuous=random.choice([True,False]), # for multicast, promiscuity shouldn't matter
    mac_addr=[0xDE,0xAD,0xBE,0xEF,0xCA,0xFE][::-1],
    prep_tx_buffer=True
)
async def mac_multicast_test(dut_wrapped):
    # Send a multicast packet
    await dut_wrapped.tx_buffer_write64(0,0x00000000_005E0001) # multicast address
    await dut_wrapped.tx_packet_send(64)
    await dut_wrapped.wait_for_tx_done()

    # Check packet was received due to multicast address
    assert (await dut_wrapped.rx_packet_pending()), "Expected packet after sending multicast address"
    await dut_wrapped.rx_buffer_metadata_get(0)
    await dut_wrapped.read_packet(0)

##################################
# Test packet queueing behaviour #
##################################
@create_test(
    with_mirror=True,
    loopback=True,
    promiscuous=True,
    mac_addr=[0xDE,0xAD,0xBE,0xEF,0xCA,0xFE][::-1]
)
async def packet_queue_test(dut_wrapped):
    # Send 5 packets
    for pkt_num in range(5):
        for i in range(64//8):
            await dut_wrapped.tx_buffer_write64(i,pkt_num*0x100+i)
        await dut_wrapped.tx_packet_send(64)
        await dut_wrapped.wait_for_tx_done()

    # Check 5 packets were received
    await dut_wrapped.status_get()
    await dut_wrapped.rx_packet_pending()
    for pkt_num in range(5):
        await dut_wrapped.rx_buffer_metadata_get(pkt_num)
        await dut_wrapped.read_packet(pkt_num) # read the data and check it matches between the model and the DUT

@create_test(
    with_mirror=True,
    promiscuous=True,
    loopback=True,
    mac_addr=[0xDE,0xAD,0xBE,0xEF,0xCA,0xFE][::-1]
)
async def packet_pop_test(dut_wrapped):
    # Send 5 packets
    for pkt_num in range(5):
        for i in range(64//8):
            await dut_wrapped.tx_buffer_write64(i,pkt_num*0x100+i)
        await dut_wrapped.tx_packet_send(64)
        await dut_wrapped.wait_for_tx_done()

    # Pop two packets
    for _ in range(5):
        await dut_wrapped.status_get()
        await dut_wrapped.rx_buffer_metadata_get(0)
        await dut_wrapped.rx_pop_packet()

@create_test(
    with_mirror=True,
    loopback=True,
    promiscuous=True
)
async def packet_peek_test(dut_wrapped):
    # load up 8 packets into the DUT
    for _ in range(8):
        for i in range(64//8):
            await dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF))
        await dut_wrapped.tx_packet_send(64)
        await dut_wrapped.wait_for_tx_done()

    # peek at all 8 packets out-of-order
    assert await dut_wrapped.rx_packet_pending(), "Expected packets to be pending after sending 8 packets"
    while (await dut_wrapped.rx_packet_pending()):
        n_packets_pending = (await dut_wrapped.status_get())>>8
        peek_order = list(range(n_packets_pending))
        random.shuffle(peek_order)

        for pkt_idx in peek_order:
            await dut_wrapped.rx_buffer_metadata_get(pkt_idx)
            await dut_wrapped.read_packet(pkt_idx)

        await dut_wrapped.rx_pop_packet()

#################################
# Memory interface stress tests #
#################################
@create_test(
    with_mirror=True,
    loopback=True,
    promiscuous=True
)
async def back_to_back_tx_buffer_test(dut_wrapped):
    # Create writes to 8 different words back-to-back
    writes = [
        dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF))
        for i in range(8)
    ]
    # Shuffle their order
    random.shuffle(writes)
    # Start them all simultaneously and wait for them all to finish
    await Combine(
        *[cocotb.start_soon(i) for i in writes]
    )
    # Send that packet and check it was received with the same data
    await dut_wrapped.tx_packet_send(64)
    await dut_wrapped.wait_for_tx_done()
    await dut_wrapped.status_get()
    await dut_wrapped.rx_buffer_metadata_get(0)
    await dut_wrapped.read_packet(0)

@create_test(
    with_mirror=True,
    loopback=True,
    promiscuous=True,
    prep_tx_buffer=True
)
async def back_to_back_rx_buffer_test(dut_wrapped):
    await dut_wrapped.tx_packet_send(64)
    await dut_wrapped.wait_for_tx_done()

    await dut_wrapped.status_get()
    await dut_wrapped.rx_buffer_metadata_get(0)

    await Combine(
        *[cocotb.start_soon(dut_wrapped.rx_buffer_read64(i)) for i in range(8)]
    ) # cool use of list comprehension and the * operator!

@create_test(
    loopback=True,
    promiscuous=True
)
async def back_to_back_metadata_test(dut_wrapped):
    # load up 5 packets into the DUT
    for pkt_num in range(5):
        for i in range(64//8):
            await dut_wrapped.tx_buffer_write64(i,pkt_num*0x100+i)
        await dut_wrapped.tx_packet_send(64)
        await dut_wrapped.wait_for_tx_done()

    await Combine(
        *[cocotb.start_soon(dut_wrapped.rx_buffer_metadata_get(i)) for i in range(5)]
    ) # cool use of list comprehension and the * operator!

@create_test(with_mirror=True)
async def back_to_back_csr_test(dut_wrapped):
    # define a series of CSR accesses
    # remember how 'async/await' works! None of these will actually start until they are awaited, or (in this case) passed into cocotb.start_soon
    processes = [
        dut_wrapped.intr_mask_set(0x55),
        dut_wrapped.intr_mask_get(),
        dut_wrapped.intr_state_get(),
        dut_wrapped.status_get(),
        dut_wrapped.mode_set(random.choice([0,1]),random.choice([0,1])),
        dut_wrapped.mode_get(),
        dut_wrapped.mac_address_set([random.randint(0,255) for _ in range(6)]),
    ]

    random.shuffle(processes)
    await Combine(
        *[cocotb.start_soon(proc) for proc in processes]
    ) # they will all start simultaneously according to the Python, but then CocoTB has a locking mechanism that will ensure they each wait their turn for bus access

    await dut_wrapped.status_get()
    await dut_wrapped.mac_address_get()

@create_test(
    loopback=True,
    promiscuous=True
)
async def back_to_back_mixed_test(dut_wrapped):
    # load up 8 packets into the DUT
    for pkt_num in range(8):
        for i in range(64//8):
            await dut_wrapped.tx_buffer_write64(i,pkt_num*0x100+i)
        await dut_wrapped.tx_packet_send(64)
        await dut_wrapped.wait_for_tx_done()

    # define a series of CSR reads, CSR writes, RX reads, and TX writes
    processes = [
        dut_wrapped.intr_mask_set(0x55),
        dut_wrapped.intr_mask_get(),
        dut_wrapped.intr_state_get(),
        dut_wrapped.status_get(),
        dut_wrapped.mode_set(random.choice([0,1]),random.choice([0,1])),
        dut_wrapped.mode_get(),
        dut_wrapped.mac_address_set([random.randint(0,255) for _ in range(6)])
    ]

    for i in range(8):
        processes.append(dut_wrapped.rx_buffer_metadata_get(i))
        processes.append(dut_wrapped.rx_buffer_read64(i))
        processes.append(dut_wrapped.tx_buffer_write64(i,i))

    # Randomly order those accesses to stress the bus arbitration and locking mechanisms
    random.shuffle(processes)

    # Start them all simultaneously and wait for them to finish
    await Combine(
        *[cocotb.start_soon(proc) for proc in processes]
    ) # they will all start simultaneously according to the Python, but then CocoTB has a locking mechanism that will ensure they each wait their turn for bus access

    # Check status is as expected by the model
    await dut_wrapped.status_get()

    # Let's check the MAC address wrote correctly (can't include this in the processes because of atomicity issues - the MAC read/writes are each two transactions but the model treats it as one action)
    # this isn't really a problem as that's not the purpose of this test
    await dut_wrapped.mac_address_get()

    # Let's also send off that last packet we wrote so we can read it back and make sure it got written correctly
    # First pop existing packets
    for _ in range(8):
        await dut_wrapped.status_get()
        await dut_wrapped.rx_buffer_metadata_get(0)
        await dut_wrapped.read_packet(0)
        await dut_wrapped.rx_pop_packet()

    # Now send the last packet we wrote and check it
    await dut_wrapped.mode_set(1,1)
    await dut_wrapped.tx_packet_send(64)
    await dut_wrapped.wait_for_tx_done()
    await dut_wrapped.status_get()
    await dut_wrapped.rx_buffer_metadata_get(0)
    await dut_wrapped.read_packet(0)

########################
# Fullness flags tests #
########################
@create_test(
    loopback=True,
    promiscuous=True
)
async def table_full_test(dut_wrapped):
    # Fill the table with 8 packets
    for _ in range(8):
        for i in range(64//8):
            await dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF)) # TODO I have to write this exact line a lot, it would be helpful if the wrapper provided a method to write random TX data
        await dut_wrapped.tx_packet_send(64)
        await dut_wrapped.wait_for_tx_done()
        await dut_wrapped.status_get()

    # Check that the table is full (model does this too, but this is a sense check)
    status = await dut_wrapped.status_get()
    assert (status>>8) == 8, f"Expected 8 packets pending, got {status>>8}"
    assert (status>>1) & 3==3, f"Expected table full and almost full flags to be set"

    # Pop packets back out
    for _ in range(8):
        await dut_wrapped.rx_pop_packet()
        await dut_wrapped.status_get()

@create_test(
    loopback=True,
    promiscuous=True
)
async def buffer_full_test(dut_wrapped):
    # Send 5 long packets to fill the buffer
    for _ in range(5):
        pkt_len = random.randint(1350,1518)
        for i in range((pkt_len+7)//8):
            await dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF))
        await dut_wrapped.tx_packet_send(pkt_len)
        await dut_wrapped.wait_for_tx_done()
        await dut_wrapped.status_get()

    status = await dut_wrapped.status_get()
    assert status & 0x8, f"Expected buffer full flag"
    assert (status>>8) == 5, f"Expected 5 packets pending, got {status>>8}"

    # Pop packets back out
    for _ in range(5):
        await dut_wrapped.rx_pop_packet()
        await dut_wrapped.status_get()

@create_test(
    loopback=True,
    promiscuous=True
)
async def buffer_full_edge_test(dut_wrapped):
    # test an edge case where the buffer is almost full and we send a packet that should JUST fit

    # send 5 packets that almost fill the buffer
    space_used = 0
    for _ in range(5):
        pkt_len = random.randint(1330,1518)
        space_used += pkt_len
        for i in range((pkt_len+7)//8):
            await dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF))
        await dut_wrapped.tx_packet_send(pkt_len)
        await dut_wrapped.wait_for_tx_done()
        await dut_wrapped.status_get()

    # calculate the remaining space and send a packet of exactly that size
    remaining_space = 8192 - space_used

    for i in range(remaining_space//8):
        await dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF))
    await dut_wrapped.tx_packet_send(remaining_space)
    await dut_wrapped.wait_for_tx_done()
    await dut_wrapped.status_get()
    await dut_wrapped.intr_state_get()

@create_test(
    loopback=True,
    promiscuous=True
)
async def buffer_almost_full_edge_test(dut_wrapped):
    # send 4 packets that almost reach the buffer_almost_full threshold
    space_used = 0
    first_pkt_len = None
    for _ in range(4):
        pkt_len = random.randint(1330,1518)
        if first_pkt_len is None:
            first_pkt_len = pkt_len
        space_used += pkt_len
        for i in range((pkt_len+7)//8):
            await dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF))
        await dut_wrapped.tx_packet_send(pkt_len)
        await dut_wrapped.wait_for_tx_done()
        await dut_wrapped.status_get()

    # min = 4*(1330) = 5320 -> 1347 spaces until the threshold
    # max = 4*(1518) = 6072 -> 595 spaces until the threshold

    space_until_threshold = 6667 - space_used # this should put us just shy of the threshold

    await dut_wrapped.tx_packet_send(space_until_threshold)
    await dut_wrapped.wait_for_tx_done()
    assert (await dut_wrapped.status_get()) & 0x8 == 0, "Expected buffer_almost_full flag to be clear"

    # now pop the first packet out and send a new one that should push us over the threshold
    await dut_wrapped.rx_pop_packet()
    await dut_wrapped.status_get()
    await dut_wrapped.tx_packet_send(first_pkt_len+1)
    await dut_wrapped.wait_for_tx_done()
    assert (await dut_wrapped.status_get() & 0x8), "Expected buffer_almost_full flag to be set"

@create_test(
    loopback=True,
    promiscuous=True
)
async def buffer_full_packet_lost_test(dut_wrapped):
    # Send 5 long packets to fill the buffer
    for _ in range(5):
        pkt_len = random.randint(1350,1518)
        for i in range((pkt_len+7)//8):
            await dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF))
        await dut_wrapped.tx_packet_send(pkt_len)
        await dut_wrapped.wait_for_tx_done()
        await dut_wrapped.status_get()

    # Send one more packet which should be lost
    pkt_len = random.randint(1350,1518)
    for i in range((pkt_len+7)//8):
        await dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF))
    await dut_wrapped.tx_packet_send(pkt_len)

    for _ in range(pkt_len-10):
        await RisingEdge(dut_wrapped.dut.clk_125M_i)
    await dut_wrapped.status_get() # check that status midway
    await dut_wrapped.wait_for_tx_done()

    # Check the packet lost flag was set
    intr_state = await dut_wrapped.intr_state_get()
    assert intr_state & 0x10, "Expected packet lost flag"
    await dut_wrapped.status_get()

    # Pop some packets out - the flag should stay
    for _ in range(3):
        await dut_wrapped.rx_pop_packet()
        intr_state = await dut_wrapped.intr_state_get()
        assert intr_state & 0x10, "Expected packet lost flag to stay set after popping packets"
    await dut_wrapped.status_get()

    # Clear the flag explicitly
    await dut_wrapped.clear_packet_lost_flag()
    intr_state = await dut_wrapped.intr_state_get()
    assert not (intr_state & 0x10), "Expected packet lost flag to be cleared after explicit clear"
    await dut_wrapped.status_get()

@create_test(
    loopback=True,
    promiscuous=True
)
async def table_full_packet_lost_test(dut_wrapped):
    # Send 8 packets to fill the table
    for _ in range(8):
        pkt_len = random.randint(64,100)
        for i in range((pkt_len+7)//8):
            await dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF))
        await dut_wrapped.tx_packet_send(pkt_len)
        await dut_wrapped.wait_for_tx_done()
        await dut_wrapped.status_get()

    # Send one more packet which should be lost
    pkt_len = random.randint(64,1518)
    for i in range((pkt_len+7)//8):
        await dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF))
    await dut_wrapped.tx_packet_send(pkt_len)
    await dut_wrapped.wait_for_tx_done()

    # Check the packet lost flag was set
    intr_state = await dut_wrapped.intr_state_get()
    assert intr_state & 0x10, "Expected packet lost flag"
    await dut_wrapped.status_get()

    # Pop some packets out - the flag should stay
    for _ in range(3):
        await dut_wrapped.rx_pop_packet()
        intr_state = await dut_wrapped.intr_state_get()
        assert intr_state & 0x10, "Expected packet lost flag to stay set after popping packets"
    await dut_wrapped.status_get()

    # Clear the flag explicitly
    await dut_wrapped.clear_packet_lost_flag()
    intr_state = await dut_wrapped.intr_state_get()
    assert not (intr_state & 0x10), "Expected packet lost flag to be cleared after explicit clear"
    await dut_wrapped.status_get()

@create_test(
    loopback=True,
    promiscuous=True
)
async def packet_lost_recovery_test(dut_wrapped):
    # Send 9 packets to fill the table and cause a packet lost
    for _ in range(9):
        pkt_len = random.randint(64,100)
        for i in range((pkt_len+7)//8):
            await dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF))
        await dut_wrapped.tx_packet_send(pkt_len)
        await dut_wrapped.wait_for_tx_done()

    # Check status vs. model
    await dut_wrapped.status_get()

    # Pop a packet out
    await dut_wrapped.rx_pop_packet()

    # Send a new packet
    pkt_len = random.randint(64,100)
    for i in range((pkt_len+7)//8):
        await dut_wrapped.tx_buffer_write64(i,0xa5a5)
    await dut_wrapped.tx_packet_send(pkt_len)
    await dut_wrapped.wait_for_tx_done()

    await dut_wrapped.status_get()
    await dut_wrapped.rx_buffer_metadata_get(7)
    newest_packet_data = await dut_wrapped.read_packet(7)
    assert newest_packet_data[0] == 0xa5, f"Expected newest packet [0] to be 0xa5, got {newest_packet_data[0]}"
    assert newest_packet_data[1] == 0xa5, f"Expected newest packet [1] to be 0xa5, got {newest_packet_data[1]}"

    await dut_wrapped.status_get()

##############
# CRC stress #
##############
@create_test(
    loopback=True,
    promiscuous=True
)
async def crc_error_injection_test(dut_wrapped):
    # Begin a loopback transmission
    pkt_len = random.randint(56,1518)
    for i in range((pkt_len+7)//8):
        await dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF))
    await dut_wrapped.tx_packet_send(pkt_len)

    # Wait until transmission is in progress
    while not (await dut_wrapped.wrapper.tx_busy()):
        await RisingEdge(dut_wrapped.dut.clk_125M_i)
    for _ in range(random.randint(1,30)):
        await RisingEdge(dut_wrapped.dut.clk_125M_i)

    # Inject an error
    await dut_wrapped.inject_crc_error()

    # Wait for TX to complete
    await dut_wrapped.wait_for_tx_done()

    # Check that no packet was received
    await dut_wrapped.status_get()
    assert not (await dut_wrapped.rx_packet_pending()), "Expected no packet after injecting CRC error"

######################
# Bad state recovery #
######################
# Each of these tests follows a similar structure:
# - configure the DUT
# - do something unexpected (e.g. reconfiguring midway through a transmission)
# - run the health test to ensure the DUT isn't locked in a bad state
# Because the simple packet-level model can't handle most of the unexpected behaviours, the onus is on these test cases to assert that the DUT is well-behaved

# we'll also run the health test alone a few times to make sure it's works
@create_test(with_mirror=False,health_test_after=True)
async def health_test_test(dut_wrapped):
    pass
    # call the health test on a fresh DUT to ensure it passes in a known-good state

@create_test(
    with_mirror=False,
    prep_tx_buffer=True,
    loopback=True,
    promiscuous=False,
    mac_addr=[0xDE,0xAD,0xBE,0xEF,0xCA,0xFE][::-1],
    health_test_after=True,
)
async def change_mac_during_rx_match_to_non_match(dut_wrapped):
    # This test follows a common design pattern:
    # - Configure the DUT
    # - Start something, then do something unexpected midway through, potentially placing the DUT in a bad state
    # - Run the health test to ensure the bad state is recoverable

    await dut_wrapped.tx_buffer_write64(0,0xBEBAFECAEFBEADDE) # start with matching MAC address
    await dut_wrapped.tx_packet_send(1518) # START sending a packet

    for _ in range(random.randint(1,32)): # range 1-32 gives a roughly 50/50 chance of the packet making it through or not
        await RisingEdge(dut_wrapped.dut.clk_125M_i) # wait a random number of cycles during the packet transmission

    await dut_wrapped.mac_address_set([0x12,0x34,0x56,0x78,0x9a,0xbc]) # change the MAC address during RX
    await dut_wrapped.wait_for_tx_done() # wait for the TX to finish

@create_test(
    with_mirror=False,
    prep_tx_buffer=True,
    loopback=True,
    promiscuous=True,
    health_test_after=True,
)
async def change_loopback_during_loopback(dut_wrapped):
    await dut_wrapped.tx_packet_send(1518) # START sending a packet

    for _ in range(random.randint(1,32)): # range 1-32 gives a roughly 50/50 chance of the packet making it through or not
        await RisingEdge(dut_wrapped.dut.clk_125M_i) # wait a random number of cycles during the packet transmission

    await dut_wrapped.mode_set(1,0) # disable loopback mode during RX

    await dut_wrapped.wait_for_tx_done() # wait for the TX to finish

@create_test(
    with_mirror=False,
    prep_tx_buffer=True,
    loopback=True,
    promiscuous=True,
    health_test_after=True,
)

async def change_promiscuous_during_loopback(dut_wrapped):
    await dut_wrapped.tx_packet_send(1518) # START sending a packet with promiscuous on

    for _ in range(random.randint(1,32)): # range 1-32 gives a roughly 50/50 chance of the packet making it through or not
        await RisingEdge(dut_wrapped.dut.clk_125M_i) # wait a random number of cycles during the packet transmission

    await dut_wrapped.mode_set(0,1) # disable promiscuous mode during RX

    await dut_wrapped.wait_for_tx_done() # wait for the TX to finish

# TODO there are so many cases to cover here for the bad state recovery tests:
#   - Circumstances:    TX to RGMII, RX from RGMII, or loopback?
#   - Disturbance:      register write, TX buffer write, RX pop, reset

@create_test(
    with_mirror=True, # this one can use the model, which gives some added checks
    promiscuous=True,
    loopback=True,
    prep_tx_buffer=True,
    health_test_after=True
)
async def pop_during_loopback(dut_wrapped):
    await dut_wrapped.tx_packet_send(1518) # START sending a packet
    await dut_wrapped.wait_for_tx_done() # wait for the TX to finish
    await dut_wrapped.tx_packet_send(1518) # START sending another packet

    for _ in range(random.randint(1,32)): # range 1-32 gives a roughly 50/50 chance of the packet making it through or not
        await RisingEdge(dut_wrapped.dut.clk_125M_i) # wait a random number of cycles during the packet transmission
    await dut_wrapped.rx_pop_packet() # pop the FIRST packet back out during RX of the second packet

    await dut_wrapped.wait_for_tx_done() # wait for the TX to finish

@create_test(
    with_mirror=False,
    promiscuous=True,
    loopback=True,
    prep_tx_buffer=True,
    health_test_after=True
)
async def tx_write_during_tx_recovery(dut_wrapped):
    await dut_wrapped.tx_packet_send(1518) # START sending a packet

    while await dut_wrapped.tx_busy():
        await dut_wrapped.tx_buffer_write64(random.randint(0,(1518+7)//8),random.randint(0,0xFFFFFFFFFFFFFFFF))
        # write random data to random locations in the buffer

    for _ in range(10):
        await RisingEdge(dut_wrapped.dut.clk_125M_i) # wait a few cycles to ensure the DUT is 'quiet' before running the health test

####################
# RGMII Simulation #
####################
@create_test(
    with_mirror=True,
    loopback=False,
    promiscuous=True
)
async def rgmii_rx_test(dut_wrapped):
    await dut_wrapped.simulate_rx_packet([random.randint(0,255) for _ in range(random.randint(56,1518))])

    n_packets = (await dut_wrapped.status_get()) >> 8
    assert n_packets == 1, f"Expected 1 packet pending after simulating RX, got {n_packets}"

@create_test(
    with_mirror=True,
    loopback=random.choice([True,False]),
    promiscuous=random.choice([True,False]),
    prep_tx_buffer=True
)
async def rgmii_tx_test(dut_wrapped):
    await dut_wrapped.tx_packet_send(1518)
    await dut_wrapped.wait_for_tx_done(tail_after_done=10)

    await dut_wrapped.get_transmitted_packet() # this will check the model and the DUT match

@create_test(
    with_mirror=True,
    loopback=False,
    promiscuous=True
)
async def rgmii_pop_during_rx(dut_wrapped):
    # Load one packet initially
    await dut_wrapped.simulate_rx_packet([random.randint(0,255) for _ in range(random.randint(56,1518))])

    # Then start a second packet
    await dut_wrapped.begin_rx_packet([random.randint(0,255) for _ in range(random.randint(56,1518))])

    for _ in range(random.randint(1,32)):
        await RisingEdge(dut_wrapped.dut.clk_125M_i) # wait a random number of cycles during the packet reception

    # Check status
    n_packets = (await dut_wrapped.status_get()) >> 8
    assert n_packets == 1, f"Expected 1 packet pending, got {n_packets}"

    # Pop the first packet back out during RX of the second packet
    await dut_wrapped.rx_pop_packet()

    # Check status again
    n_packets = (await dut_wrapped.status_get()) >> 8
    assert n_packets == 0, f"Expected 0 packet pending after popping during RX, got {n_packets}"

    # Wait for the second packet to finish
    await dut_wrapped.wait_for_rx_done()

    # Check status
    n_packets = (await dut_wrapped.status_get()) >> 8
    assert n_packets == 1, f"Expected 1 packet pending, got {n_packets}"

@create_test(
    with_mirror=True,
    loopback=False,
    promiscuous=True
)
async def rgmii_pop_during_rx_table_full(dut_wrapped):
    # Load 8 packets initially to fill the table
    for _ in range(8):
        await dut_wrapped.simulate_rx_packet([random.randint(0,255) for _ in range(random.randint(56,900))])
        # set an upper limit of 900 bytes to avoid filling the buffer as that is not the purpose of this test

    # Then start a ninth packet
    await dut_wrapped.begin_rx_packet([random.randint(0,255) for _ in range(random.randint(56,900))])

    for _ in range(random.randint(1,32)):
        await RisingEdge(dut_wrapped.dut.clk_125M_i) # wait a random number of cycles during the packet reception

    # Check status
    n_packets = (await dut_wrapped.status_get()) >> 8
    assert n_packets == 8, f"Expected 8 packets pending, got {n_packets}"

    # Pop the first packet back out during RX of the ninth packet
    await dut_wrapped.rx_pop_packet()

    # Check status again
    n_packets = (await dut_wrapped.status_get()) >> 8
    assert n_packets == 7, f"Expected 7 packets pending after popping during RX, got {n_packets}"

    # Wait for the ninth packet to finish
    await dut_wrapped.wait_for_rx_done()

    # Check status
    n_packets = (await dut_wrapped.status_get()) >> 8
    assert n_packets == 8, f"Expected 8 packets pending after finishing RX of ninth packet, got {n_packets}"

    # Also check the interrupt flags
    await dut_wrapped.intr_state_get()

@create_test(
    with_mirror=True,
    loopback=False,
    promiscuous=True
)
async def rgmii_b2b_rx(dut_wrapped):
    # queue up several packets for RX via RGMII
    for _ in range(5):
        await dut_wrapped.begin_rx_packet([random.randint(0,255) for _ in range(random.randint(56,1518))])
        await dut_wrapped.wait_for_rx_done(tail_after_done=0)
        # The cocotbext-eth RGMII model doesn't support locking the RX interface, so we have to manually queue them up here

    for _ in range(10):
        await RisingEdge(dut_wrapped.dut.clk_125M_i)

    await dut_wrapped.status_get()
    await dut_wrapped.intr_state_get()
    for i in range(5):
        await dut_wrapped.read_packet(i)

@create_test(
    with_mirror=True,
    loopback=False,
    promiscuous=True,
    prep_tx_buffer=True
)
async def rgmii_simultaneous_tx_rx(dut_wrapped):
    # queue up several packets for RX via RGMII
    # Start a packet TX via RGMII
    await dut_wrapped.tx_packet_send(random.randint(56,1518))

    # Start a packet RX via RGMII
    await dut_wrapped.begin_rx_packet([random.randint(0,255) for _ in range(random.randint(56,1518))])

    # Wait for both to finish
    await Combine(
        cocotb.start_soon(dut_wrapped.wait_for_rx_done()),
        cocotb.start_soon(dut_wrapped.wait_for_tx_done())
    )

    await dut_wrapped.status_get()
    await dut_wrapped.read_packet(0)
    await dut_wrapped.get_transmitted_packet()

# TODO need a test case that covers back-to-back TX/RX e.g. it is conceivable to have a bug that arises if you have back-to-back TX while RX is ongoing or vice-versa

#############
# Long test #
#############

# I would prefer to think that the more 'targeted' tests above are sufficient
# but I have found that a long-running test with a lot of random behaviour can
# catch some weird edge cases
# Ideally with better coverage metrics this test will be unnecessary but until
# we can get ~100% toggle coverage with the targeted tests, this will be a
# useful stress test

@create_test(
    loopback=True,
    promiscuous=True
)
async def long_random_test(dut_wrapped):
    # randomly pop and inject packets for 500 iterations
    # check the status every iteration
    # every 20 iterations, read the RX buffer metadata and see if all packets match the model
    for _ in range(1):
        for _ in range(20):
            status = await dut_wrapped.status_get()
            table_almost_full = (status >> 1) & 0x1
            table_full = (status >> 2) & 0x1
            buf_almost_full = (status >> 3) & 0x1

            if not table_almost_full and not table_full and not buf_almost_full:
                # no flags are set, 50% chance of a pop
                if random.randint(0,1):
                    await dut_wrapped.rx_pop_packet()
            elif table_almost_full or buf_almost_full:
                # if either of these flags are set, 75% chance of a pop
                if random.randint(0,3) < 3:
                    await dut_wrapped.rx_pop_packet()
            else:
                # if table is full, 90% chance of a pop
                if random.randint(0,9) < 9:
                    await dut_wrapped.rx_pop_packet()

            status = await dut_wrapped.status_get()

            # 90% chance of pushing a new packet
            if random.randint(0,9) < 9:
                pkt_len = random.randint(56,1518)
                for i in range((pkt_len+7)//8):
                    await dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF))
                await dut_wrapped.tx_packet_send(pkt_len)
                await dut_wrapped.wait_for_tx_done()

        await dut_wrapped.intr_state_get()

        n_pkts = (await dut_wrapped.status_get())>>8
        packets_to_check = list(range(n_pkts))
        random.shuffle(packets_to_check)
        for i in packets_to_check:
            await dut_wrapped.read_packet(i)

# TODO add a pre-test "prime" that will put the DUT in a random-ish state w.r.t to pointers

###################
# Test bus errors #
###################

@create_test(
    with_mirror=False,
    health_test_after=True # Run a health test to ensure the DUT isn't broken by this
)
async def err_write_rx_buffer(dut_wrapped):
    # Pick a random address in the RX buffer
    # Read its current value
    # Attempt a write
    # Check that the write gave an error
    # Read it again and check its value is unchanged
    # Then run a health test

    address = RX_BUFFER_BASE+8*(random.randint(0,8191)>>3)

    rresp = await dut_wrapped._axi_driver.read(address,8) # read first to ensure the address is valid
    original_data = rresp.data

    bresp = await dut_wrapped._axi_driver.write(
        address = address,
        data = random.randbytes(8)
    )
    assert bresp.resp == 2 # slave error expected after a write to read-only buffer

    # Ensure data was not changed
    rresp = await dut_wrapped._axi_driver.read(address,8) # read first to ensure the address is valid
    assert rresp.data == original_data, f"Expected RX buffer data to be unchanged after write error"
    # This is alright for now but it would be best if we were checking VALID data

@create_test(
    with_mirror=False,
    health_test_after=True # Run a health test to ensure the DUT isn't broken by this
)
async def err_write_rx_metadata(dut_wrapped):
    # Pick a random address in the RX metadata table
    # Attempt to write to it
    # Assert that the write gave an error
    address = RX_TABLE_BASE+8*(random.randint(0,7))
    bresp = await dut_wrapped._axi_driver.write(address,random.randbytes(8))
    assert bresp.resp == 2 # slave error expected

@create_test(
    with_mirror=False,
    health_test_after=True # Run a health test to ensure the DUT isn't broken by this
)
async def err_read_tx_buffer(dut_wrapped):
    # Pick a random address in the TX buffer
    # Attempt to read from it
    # Assert that the read gave an error
    address = TX_BUFFER_BASE+8*(random.randint(0,2048)>>3)
    rresp = await dut_wrapped._axi_driver.read(address,8)
    assert rresp.resp == 2 # slave error expected

@create_test(
    with_mirror=False,
    health_test_after=True # Run a health test to ensure the DUT isn't broken by this
)
async def err_read_invalid_rx_metadata(dut_wrapped):
    # Pick a random address in the RX metadata table
    # Attempt to read from it
    # Because there are no packets buffered, it should give an error
    # Assert that the read gave an error
    address = RX_TABLE_BASE+8*(random.randint(0,7))
    rresp = await dut_wrapped._axi_driver.read(address,8)
    assert rresp.resp == 2 # slave error expected

@create_test(
    with_mirror=False,
    health_test_after=True # Run a health test to ensure the DUT isn't broken by this
)
async def err_read_invalid_address(dut_wrapped):
    address = random.randint(0x6040,0x7FFF) # pick a random address in the unused space
    rresp = await dut_wrapped._axi_driver.read(address,8)
    assert rresp.resp >= 2 # slave error or decode error expected

@create_test(
    with_mirror=False,
    health_test_after=True # Run a health test to ensure the DUT isn't broken by this
)
async def err_write_invalid_address(dut_wrapped):
    address = random.randint(0x6040,0x7FFF) # pick a random address in the unused space
    bresp = await dut_wrapped._axi_driver.write(address,random.randbytes(8))
    assert bresp.resp >= 2 # slave error or decode error expected

@create_test(
    with_mirror=False,
    health_test_after=True # Run a health test to ensure the DUT isn't broken by this
)
async def err_write_status_reg(dut_wrapped):
    # Attempt to write to the status register
    # Assert that the write gave an error
    bresp = await dut_wrapped._axi_driver.write(0x0814,random.randbytes(4)) # TODO not ideal to have hardcoded this address
    assert bresp.resp == 2 # slave error expected

note = """
This file is now over 1k lines long and could do with refactoring

I would like to split it into a few files:
- a top-level that pulls in all the tests
- various different files for different categories of tests (though this may be difficult to do cleanly because some tests fall into multiple categories)
- utilities for driving the DUT - like the wrapper I already have but with more functionality
- SW models of the DUT - including the existing model but also maybe a cycle-accurate model would be good
- utilities for creating tests - e.g. decorators and wrappers so I can create tests with less boilerplate

What I would like:
@test(
    loopback=True,
    promiscuous=True,
    model="cycle-accurate",
    skip=False,
    prime_dut_state=True,         # before the test, push then pop some packets to move the pointers around a bit. There should be a global disable for this since it will slow down tests a lot
    seed=1234                     # not sure about this but it might be simpler to seed each test individually rather than globally
)

also things like:
    @test_recovery(*args)
which includes what I've described above but also runs a health test at the end to ensure the DUT is in a good state, useful for checking that the DUT can recover from unexpected behaviour

I also want to focus on writing more tests with lots of parallel things ongoing so it could be worth having a decorator to do things like:
- generate random bus activity (that won't interfere with the test)
- introduce clock jitter

"""