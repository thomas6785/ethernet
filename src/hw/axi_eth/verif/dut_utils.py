import random
import cocotb
from cocotb.triggers import Combine,Timer,RisingEdge

async def prep_tx_buffer(dut_wrapped):
    """
    Write random data to the TX buffer
    """
    processes = [
        cocotb.start_soon(dut_wrapped.tx_buffer_write64(i,random.randint(0,0xFFFFFFFFFFFFFFFF))) # fill the TX buffer with random data
        for i in range((1518+7)//8)
    ]
    await Combine(*processes) # wait for all those transactions to complete
    for _ in range(2):
        await RisingEdge(dut_wrapped.dut.clk_125M_i) # wait two clocks just in case
    return

async def reinitialise_dut_state(dut_wrapped):
    """
    Get the DUT back to its reset state without actually resetting it.
    Note that some state is never actually reset (buffers) and some is reset normally
    but not by this function (TX/RX pointers). This is deliberate as a way of
    randomising test conditions.
    """
    while await dut_wrapped.tx_busy():
        await Timer(8,"ns")
    while await dut_wrapped.rx_packet_pending():
        await dut_wrapped.rx_pop_packet()
    processes = [
        dut_wrapped.mode_set(0,0),
        dut_wrapped.mac_address_set([0,0,0,0,0,0]),
        dut_wrapped.intr_mask_set(0),
        # TODO its a bit annoying to have to call these when most tests don't even use them
        # plus they could be called all in one go instead of one at a time
        dut_wrapped.clear_test_intr(),
        dut_wrapped.clear_tx_done_flag(),
        dut_wrapped.clear_packet_lost_flag()
    ]
    await Combine(*[cocotb.start_soon(i) for i in processes]) # wait for all those transactions to complete
    for _ in range(2):
        await RisingEdge(dut_wrapped.dut.clk_125M_i) # wait two clocks just in case
    return

async def health_test(dut):
    """
    Accepts an AxiEthernetModel instance in any arbitrary state
    and performs a health test on it to check for bad states and deadlocks

    Returns the DUT in a mangled state so should only be used at the end of a test case

    This test is not exhaustive but is designed to:
        - hit all memory interfaces (RX data, RX metadata, TX data, CSRs)
        - hit the main TX/RX data paths
    This, combined with assertions in the SystemVerilog, should catch any
    deadlocked FSMs or other bad states that could occur in the DUT.
    """
    status = await dut.status_get()
    n_packets_buffered = status >> 8

    if n_packets_buffered > 0:
        # Try a pop
        await dut.rx_pop_packet()
        # this also guarantees there will now be space for a loopback
    new_status = await dut.status_get()
    n_packets_buffered_after_pop = new_status >> 8
    assert n_packets_buffered_after_pop == max(0, n_packets_buffered-1), f"Failed health test: RX packet pop failed"

    # Set loopback promiscuous mode for testing
    await dut.mode_set(1,1) # set to promiscuous loopback mode
    new_mode = await dut.mode_get()
    assert new_mode == (1,1), f"Failed health test: Mode register did not write correctly"

    # send a minimal packet
    for i in range(8):
        await dut.tx_buffer_write64(i,i)
    await dut.tx_packet_send(64)
    await dut.wait_for_tx_done()

    # Check it was received
    status = await dut.status_get()
    n_packets_buffered = status >> 8
    assert n_packets_buffered == n_packets_buffered_after_pop + 1, f"Failed health test: loopback packet not received"

    # Check the data
    _, ptr, length = await dut.rx_buffer_metadata_get(n_packets_buffered-1) # get the packet we just sent
    assert length == 64, f"Failed health test: loopback packet length mismatch"
    data = await dut.read_packet(n_packets_buffered-1)
    exp_data = [i//8 if i%8==0 else 0 for i in range(64)]
    assert data == exp_data, f"Failed health test: loopback packet data mismatch"

    # Try writing the MAC address
    await dut.mac_address_set([0xCA,0xFE,0xBE,0xEF,0xBA,0xDD])
    assert await dut.mac_address_get() == [0xCA,0xFE,0xBE,0xEF,0xBA,0xDD], f"Failed health test: MAC address register did not write correctly"
