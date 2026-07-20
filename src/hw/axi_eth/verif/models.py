from abc import ABC, abstractmethod
from cocotbext.axi import AxiBus, AxiMaster
from cocotbext.eth import RgmiiPhy,GmiiFrame
from cocotb.triggers import RisingEdge,Event,Combine
import cocotb
import logging

TX_BUFFER_BASE = 0x1000
RX_BUFFER_BASE = 0x4000
RX_TABLE_BASE = 0x6000

# Addresses
class csr():
    INTR_STATE  = 0x0800
    INTR_MASK   = 0x0804
    INTR_TEST   = 0x0808
    CTRL        = 0x0810
    STATUS      = 0x0814
    MACLO       = 0x0818
    MACHI       = 0x081C
    TX_CTRL     = 0x0820
    RX_POP      = 0x0828
    MDIO_CTRL   = 0x082C

def log_calls(func):
    logger = logging.getLogger(__name__) # TODO have a separate logger for the model
    logger.info(f"Set up this logger for {func} calls")
    def wrapper(*args, **kwargs):
        logger.debug(f"Calling {func.__name__} with args={args}, kwargs={kwargs}")
        result = func(*args, **kwargs)
        logger.debug(f"{func.__name__} returned {result}")
        logger.info(f"Packets in buffer: {len(args[0].rx_packets)}. Flags: manual_irq={args[0].manual_irq}, tx_done_irq={args[0].tx_done_irq}, packet_lost={args[0].packet_lost}")
        return result
    return wrapper

class TestbenchError(Exception):
    pass
    # Indicates an error with the testbench itself

class AxiEthernetABC(ABC):
    """
    Base class for the AXI Ethernet DUT and its model
    Only defines an interface as abstract methods which
    largely mirror the HAL methods available in ethernet.c
    """
    @abstractmethod
    def reset(self): pass
    @abstractmethod
    def intr_state_get(self): pass
    @abstractmethod
    def intr_mask_set(self, mask): pass
    @abstractmethod
    def intr_mask_get(self): pass
    @abstractmethod
    def test_intr(self): pass
    @abstractmethod
    def clear_test_intr(self): pass
    @abstractmethod
    def clear_tx_done_flag(self): pass
    @abstractmethod
    def status_get(self): pass
    @abstractmethod
    def mode_set(self, promiscuous_en, loopback_en): pass
    @abstractmethod
    def mode_get(self): pass
    @abstractmethod
    def mac_address_set(self, mac_address): pass
    @abstractmethod
    def mac_address_get(self): pass
    @abstractmethod
    def rx_pop_packet(self): pass
    @abstractmethod
    def tx_buffer_write64(self, word_offset, data): pass
    @abstractmethod
    def rx_buffer_metadata_get(self, index): pass
    @abstractmethod
    def rx_packet_pending(self): pass
    @abstractmethod
    def rx_buffer_read_byte(self, byte_offset): pass
    @abstractmethod
    def read_packet(self, idx): pass
    @abstractmethod
    def simulate_rx_packet(self, data): pass
    @abstractmethod
    def begin_rx_packet(self, data): pass
    @abstractmethod
    def wait_for_rx_done(self,*args): pass
    @abstractmethod
    def tx_packet_send(self, len_bytes): pass
    @abstractmethod
    def wait_for_tx_done(self,*args): pass
    @abstractmethod
    def irq_pending(self): pass
    @abstractmethod
    def get_transmitted_packet(self): pass

class AxiEthernetModel():
    """
    Model of the AXI Ethernet DUT
    Provides the same methods to compute expected outputs based on inputs
    """
    MAC_MATCHES     = 0
    MAC_BROADCAST   = 1
    MAC_MULTICAST   = 2
    NON_MAC_MATCH   = 3

    def __init__(self):
        self.rx_packets = []
        # should have entries of form (reason,bytearray) where bytearray is a list of ints between 0 and 255
        self.tx_buffer  = [0 for i in range(1522)] # max. 1522 bytes

        self.intr_mask = 0 # all interrupts disabled by default
        self.manual_irq = False
        self.tx_done_irq = False
        self.packet_lost = False
        self.promiscuous = False
        self.loopback = False
        self.mac_address = [0,0,0,0,0,0]

        self.tx_packet_in_progress = None
        self.rx_packet_in_progress = None

        self.tx_log = [] # log of packets sent out of the DUT (INCLUDING loopbacked packets)

    def reset(self):
        self.__init__()

    @log_calls
    def intr_state_get(self) -> int:
        state = 0
        if self.manual_irq:
            state |= (1 << 6) # manual irq bit
        if self.tx_done_irq:
            state |= (1 << 5) # tx done bit
        if self.packet_lost:
            state |= (1 << 4) # packet lost bit
        if len(self.rx_packets) > 0:
            state |= (1 << 0) # not empty bit
            if len(self.rx_packets) >= 6:
                state |= (1 << 1) # table almost full bit
            if len(self.rx_packets) == 8:
                state |= (1 << 2) # table full bit
            if sum([len(i[1]) for i in self.rx_packets]) > 8191-1524:
                state |= (1 << 3) # buffer almost full bit
        return state

    @log_calls
    def intr_mask_set(self, mask):
        self.intr_mask = mask & 0b1111111 # only 7 bits in this register

    @log_calls
    def intr_mask_get(self):
        return self.intr_mask

    @log_calls
    def test_intr(self):
        self.manual_irq = True

    @log_calls
    def clear_test_intr(self):
        self.manual_irq = False

    @log_calls
    def clear_tx_done_flag(self):
        self.tx_done_irq = False

    @log_calls
    def clear_packet_lost_flag(self):
        self.packet_lost = False

    @log_calls
    def status_get(self):
        # the status is similar to the INTR_STATE
        # but it excludes the wtc bits and includes tx_busy and n_packets_in_rx_buf
        intr_state = self.intr_state_get()
        status = intr_state & 0b1111 # mask away the wtc bits which are not included in STATUS
        status |= (len(self.rx_packets) << 8)
        status |= self.tx_busy() << 7
        return status

    @log_calls
    def mode_set(self,promiscuous_en, loopback_en):
        self.promiscuous = bool(promiscuous_en)
        self.loopback = bool(loopback_en)

    @log_calls
    def mode_get(self):
        return (self.promiscuous, self.loopback)

    @log_calls
    def mac_address_set(self, mac_address):
        assert len(mac_address) == 6
        assert all(0 <= i < 256 for i in mac_address)
        self.mac_address = mac_address

    @log_calls
    def mac_address_get(self):
        return self.mac_address

    @log_calls
    def rx_pop_packet(self):
        if self.rx_packets:
            return self.rx_packets.pop(0)

    @log_calls
    def tx_buffer_write64(self, word_offset, data):
        assert 0 <= word_offset < 1522//8, "Word offset out of range"
        assert 0 <= data < 2**64, "Data must be a 64-bit value"
        byte_offset = word_offset * 8
        # ensure the tx buffer is large enough
        # write the data to the tx buffer
        for i in range(8):
            self.tx_buffer[byte_offset + i] = (data >> (i*8)) & 0xFF

    @log_calls
    def rx_buffer_metadata_get(self, index):
        assert 0 <= index < len(self.rx_packets), "Index out of range"
        reason, data = self.rx_packets[index]
        return (reason, 0, len(data))
        # reason, ptr, length (bytes)
        # ptr is hardcoded to 0 since there is no concept of the ring buffer in this model

    @log_calls
    def rx_packet_pending(self):
        return len(self.rx_packets) > 0

    @log_calls
    def rx_buffer_read_byte(self, byte_offset):
        assert len(self.rx_packets) > 0, "No packets to read from"
        _byte_offset = byte_offset
        packet_idx = 0
        while _byte_offset > len(self.rx_packets[packet_idx][1]):
            _byte_offset -= len(self.rx_packets[packet_idx][1])
            packet_idx += 1
            assert packet_idx < len(self.rx_packets), "Byte offset out of range"
        data = self.rx_packets[packet_idx][1]
        return data[_byte_offset]

    @log_calls
    def rx_buffer_read64(self, word_offset):
        return [self.rx_buffer_read_byte(word_offset*8+i) for i in range(8)]

    @log_calls
    def read_packet(self, idx):
        return self.rx_packets[idx][1]

    @log_calls
    def tx_packet_send(self, len_bytes):
        assert len(self.tx_buffer) >= len_bytes, "Not enough data in tx buffer to send packet"
        packet_data = self.tx_buffer[:len_bytes]
        self.tx_packet_in_progress = packet_data

        if self.loopback:
            self.rx_packet_in_progress = packet_data

    @log_calls
    def wait_for_tx_done(self,*args):
        packet_data = self.tx_packet_in_progress
        self.tx_packet_in_progress = None

        if self.loopback:
            self.wait_for_rx_done()

        self.tx_log.append(packet_data)
        self.tx_done_irq = True

    @log_calls
    def simulate_rx_packet(self,data):
        # TODO it would be best if we could rework how RX packets are simulated
        # ideally by having the RGMII model call back into this model to indicate
        # when a packet has completed
        # That way the DUT and model will stay in sync with no effort, and we can
        # rely on the RGMII model to lock the bus and queue up a whole series of
        # packets
        self.begin_rx_packet(data)
        self.wait_for_rx_done()

    @log_calls
    def begin_rx_packet(self,data):
        if not self.loopback:
            if self.rx_packet_in_progress is not None:
                raise TestbenchError("RX packet already in progress")
            self.rx_packet_in_progress = data

    @log_calls
    def wait_for_rx_done(self):
        data = self.rx_packet_in_progress
        self.rx_packet_in_progress = None

        if data is None:
            return # no packet in progress
        else:
            assert len(data) <= 1522, "Illegally sized packet"
            if data[:6] == self.mac_address[::-1]:
                reason = self.MAC_MATCHES
            elif data[:6] == [0xFF]*6:
                reason = self.MAC_BROADCAST
            elif data[:3] == [0x01,0x00,0x5E]: # check for IPv4 multicast
                reason = self.MAC_MULTICAST
            else:
                reason = self.NON_MAC_MATCH

            if self.promiscuous or reason != self.NON_MAC_MATCH:
                if len(self.rx_packets) >= 8:
                    self.packet_lost = True
                elif sum([len(i[1]) for i in self.rx_packets]) + len(data) > 8192:
                    self.packet_lost = True
                else:
                    self.rx_packets.append((reason, data))

    @log_calls
    def irq_pending(self):
        return self.intr_mask_get() & self.intr_state_get() != 0

    @log_calls
    def tx_busy(self):
        return self.tx_packet_in_progress is not None

    @log_calls
    def get_transmitted_packet(self):
        assert len(self.tx_log) > 0, "No packets have been transmitted"
        return self.tx_log.pop(0)

class AxiEthernetWrapper():
    """
    Wrapper around the CocoTB AXI Ethernet DUT
    Provides utility methods to drive and monitor the DUT
    """
    def __init__(self, cocotb_dut):
        self.dut = cocotb_dut
        axibus = AxiBus.from_prefix(
            cocotb_dut, prefix="axi"
        )

        self._axi_driver = AxiMaster(
            bus=axibus,
            clock=cocotb_dut.clk_125M_i,
            reset=cocotb_dut.rst_ni,
            reset_active_level=False
        )

        self._rgmii_phy = RgmiiPhy(
            txd     = cocotb_dut.eth_rgmii_tx_data,
            tx_ctl  = cocotb_dut.eth_rgmii_tx_ctl,
            tx_clk  = cocotb_dut.eth_rgmii_tx_clk,
            rxd     = cocotb_dut.eth_rgmii_rx_data,
            rx_ctl  = cocotb_dut.eth_rgmii_rx_ctl,
            rx_clk  = cocotb_dut.eth_rgmii_rx_clk,
            reset   = cocotb_dut.phy_reset_no,
            reset_active_level=False
        )

    async def reset(self):
        self.dut.rst_ni.value = 0
        for _ in range(5):
            await RisingEdge(self.dut.clk_125M_i)
        self.dut.rst_ni.value = 1
        for _ in range(5):
            await RisingEdge(self.dut.clk_125M_i)
        return

    async def intr_state_get(self) -> int:
        return int.from_bytes((await self._axi_driver.read(csr.INTR_STATE, 4)).data, byteorder='little')

    async def intr_mask_set(self, mask):
        return (await self._axi_driver.write(csr.INTR_MASK, mask.to_bytes(4, byteorder='little')))

    async def intr_mask_get(self) -> int:
        return int.from_bytes((await self._axi_driver.read(csr.INTR_MASK, 4)).data, byteorder='little')

    async def test_intr(self):
        return (await self._axi_driver.write(csr.INTR_TEST, (1).to_bytes(4, byteorder='little')))

    async def clear_test_intr(self):
        return (await self._axi_driver.write(csr.INTR_STATE, (1 << 6).to_bytes(4, byteorder='little')))

    async def clear_tx_done_flag(self):
        return (await self._axi_driver.write(csr.INTR_STATE, (1 << 5).to_bytes(4, byteorder='little')))

    async def clear_packet_lost_flag(self):
        return (await self._axi_driver.write(csr.INTR_STATE, (1 << 4).to_bytes(4, byteorder='little')))

    async def status_get(self) -> int:
        return int.from_bytes((await self._axi_driver.read(csr.STATUS, 4)).data, byteorder='little')

    async def mode_set(self, promiscuous_en, loopback_en):
        return (await self._axi_driver.write(
            csr.CTRL,(
                promiscuous_en |
                (loopback_en<<1)
            ).to_bytes(4, byteorder='little')
        ))

    async def mode_get(self) -> tuple[bool, bool]:
        a = int.from_bytes((await self._axi_driver.read(csr.CTRL, 4)).data, byteorder='little') & 0b11
        return (bool(a & 0b01), bool(a & 0b10))

    async def mac_address_set(self, mac_address):
        a = await self._axi_driver.write(csr.MACLO, bytes(mac_address[0:4]))
        b = await self._axi_driver.write(csr.MACHI, bytes(mac_address[4:6]+[0,0]))
        return a.resp or b.resp

    async def mac_address_get(self) -> list[int]:
        return [int(i) for i in ((await self._axi_driver.read(csr.MACLO, 4)).data + (await self._axi_driver.read(csr.MACHI, 2)).data)]

    async def tx_packet_send(self, len_bytes):
        return (await self._axi_driver.write(csr.TX_CTRL, len_bytes.to_bytes(4, byteorder='little')))

    async def rx_pop_packet(self):
        return (await self._axi_driver.write(csr.RX_POP, (1).to_bytes(4, byteorder='little')))

    async def tx_buffer_write64(self, word_offset, data):
        return (await self._axi_driver.write(TX_BUFFER_BASE + word_offset*8, data.to_bytes(8, byteorder='little')))

    async def rx_buffer_metadata_get(self, index):
        raw_data = (await self._axi_driver.read(RX_TABLE_BASE + index*8, 8)).data
        raw_data_int = int.from_bytes(raw_data, byteorder='little')
        ptr     = (raw_data_int >> 32) & 0xFFFFFFFF
        length  = (raw_data_int >> 16) & 0xFFFF
        reason  = raw_data_int & 0x3
        return (reason, ptr, length)

    async def rx_packet_pending(self):
        return int.from_bytes((await self._axi_driver.read(csr.STATUS, 4)).data, byteorder='little') & (1 << 0) != 0

    async def rx_buffer_read_byte(self, byte_offset):
        return (await self._axi_driver.read(RX_BUFFER_BASE + byte_offset, 1)).data

    async def rx_buffer_read64(self, word_offset):
        data = (await self._axi_driver.read(RX_BUFFER_BASE + word_offset*8, 8)).data
        return [int(data[i]) for i in range(8)]

    async def read_packet(self, idx):
        _, ptr, length = await self.rx_buffer_metadata_get(idx)

        # this is a bit tricky - we want to queue up reads to all the bytes in the packet back-to-back, reading full words at a time
        lowest_word_idx = ptr // 8
        highest_word_idx = (ptr + length + 7) // 8
        requests = [
            cocotb.start_soon(self.rx_buffer_read64(word_idx % 1024))
            for word_idx in range(lowest_word_idx, highest_word_idx + 1)
        ]
        await Combine(*requests) # wait to read all the words

        data = []
        # first word handling
        for i in range(ptr % 8, 8):
            data.append(requests[0].result()[i])
        requests.pop(0)
        while len(data) < length:
            data += requests.pop(0).result()[:min(8,length-len(data))]

        assert len(data) == length, "GTGNTRJKS Something went wrong in the testbench!"
        return data

    async def simulate_rx_packet(self, data):
        await self.begin_rx_packet(data)
        await self.wait_for_rx_done(tail_after_done=10)

    async def begin_rx_packet(self,data):
        # begins the process of simulation a packet receipt
        frame = GmiiFrame.from_payload(data,tx_complete=Event())
        await self._rgmii_phy.rx.send(frame)

    async def wait_for_rx_done(self,tail_after_done=10):
        while self.dut.eth_rgmii_rx_ctl.value == 0: # make sure it has started
            await RisingEdge(self.dut.clk_125M_i)
        while self.dut.eth_rgmii_rx_ctl.value == 1: # wait for it to finish
            await RisingEdge(self.dut.clk_125M_i)
        for _ in range(tail_after_done):
            await RisingEdge(self.dut.clk_125M_i)

    async def irq_pending(self):
        return bool(self.dut.ethernet_irq_o.value)

    async def tx_busy(self):
        return bool((await self.status_get()) & (1 << 7))

    async def wait_for_tx_done(self,tail_after_done=10):
        while int(self.dut.dut.ethernet_top_inst.tx_status.value) == 0: # make sure it has started
            await RisingEdge(self.dut.clk_125M_i)
        while int(self.dut.dut.ethernet_top_inst.tx_status.value) > 0: # wait for it to finish
            await RisingEdge(self.dut.clk_125M_i)
        await RisingEdge(self.dut.clk_125M_i) # always wait at least one edge
        for _ in range(max(0,tail_after_done-1)):
            await RisingEdge(self.dut.clk_125M_i)

    async def get_transmitted_packet(self):
        raw_data = list((await self._rgmii_phy.tx.recv()).data)
        data = raw_data[raw_data.index(0xd5)+1:-4] # strip preamble and SFD and FCS - the RGMII model includes them but our model doesn't
        return data

    async def read_mdio_ctrl_reg(self):
        return int.from_bytes((await self._axi_driver.read(csr.MDIO_CTRL, 4)).data, byteorder='little')

    async def write_mdio_ctrl_reg(self, value):
        return (await self._axi_driver.write(csr.MDIO_CTRL, value.to_bytes(4, byteorder='little')))

class AxiEthernetDutWithMirror():
    def __init__(self, cocotb_dut):
        self.dut = cocotb_dut
        self.model = AxiEthernetModel()
        self.wrapper = AxiEthernetWrapper(cocotb_dut)

    async def reset(self):
        await self.wrapper.reset()
        self.model.reset()

    async def intr_state_get(self) -> int:
        dut_state = await self.wrapper.intr_state_get()
        model_state = self.model.intr_state_get()
        assert dut_state == model_state, f"INTR_STATE mismatch: DUT={dut_state}, Model={model_state}"

        # Sneaky: let's also check the IRQ line against the model while we're here (costs no sim time)
        dut_irq = await self.irq_pending()
        model_irq = self.model.irq_pending()
        assert dut_irq == model_irq, f"IRQ_PENDING mismatch: DUT={dut_irq}, Model={model_irq}"

        # Then return the INTR state since that's what the caller expects
        return dut_state

    async def intr_mask_set(self, mask):
        await self.wrapper.intr_mask_set(mask)
        self.model.intr_mask_set(mask)

    async def intr_mask_get(self) -> int:
        dut_mask = await self.wrapper.intr_mask_get()
        model_mask = self.model.intr_mask_get()
        assert dut_mask == model_mask, f"INTR_MASK mismatch: DUT={dut_mask}, Model={model_mask}"
        return dut_mask

    async def test_intr(self):
        await self.wrapper.test_intr()
        self.model.test_intr()

    async def clear_test_intr(self):
        await self.wrapper.clear_test_intr()
        self.model.clear_test_intr()

    async def clear_tx_done_flag(self):
        await self.wrapper.clear_tx_done_flag()
        self.model.clear_tx_done_flag()

    async def clear_packet_lost_flag(self):
        await self.wrapper.clear_packet_lost_flag()
        self.model.clear_packet_lost_flag()

    async def status_get(self) -> int:
        dut_status = await self.wrapper.status_get()
        model_status = self.model.status_get()
        assert dut_status == model_status, f"STATUS mismatch: DUT={dut_status}, Model={model_status}"
        return dut_status

    async def mode_set(self, promiscuous_en, loopback_en):
        await self.wrapper.mode_set(promiscuous_en, loopback_en)
        self.model.mode_set(promiscuous_en, loopback_en)

    async def mode_get(self) -> tuple[bool, bool]:
        dut_mode = await self.wrapper.mode_get()
        model_mode = self.model.mode_get()
        assert dut_mode == model_mode, f"MODE mismatch: DUT={dut_mode}, Model={model_mode}"
        return dut_mode

    async def mac_address_set(self, mac_address):
        await self.wrapper.mac_address_set(mac_address)
        self.model.mac_address_set(mac_address)

    async def mac_address_get(self) -> list[int]:
        dut_mac = await self.wrapper.mac_address_get()
        model_mac = self.model.mac_address_get()
        assert dut_mac == model_mac, f"MAC_ADDRESS mismatch: DUT={dut_mac}, Model={model_mac}"
        return dut_mac

    async def rx_pop_packet(self):
        await self.wrapper.rx_pop_packet()
        self.model.rx_pop_packet()

    async def tx_buffer_write64(self, word_offset, data):
        await self.wrapper.tx_buffer_write64(word_offset, data)
        self.model.tx_buffer_write64(word_offset, data)

    async def rx_buffer_metadata_get(self, index):
        dut_metadata = await self.wrapper.rx_buffer_metadata_get(index)
        model_metadata = self.model.rx_buffer_metadata_get(index)
        assert dut_metadata[0] == model_metadata[0], f"RX_BUFFER_METADATA_GET reason mismatch at index {index}: DUT={dut_metadata[0]}, Model={model_metadata[0]}"
        # do not check the pointer - the model doesn't track pointers correctly, it uses a 2D array instead
        assert dut_metadata[2] == model_metadata[2], f"RX_BUFFER_METADATA_GET length mismatch at index {index}: DUT={dut_metadata[2]}, Model={model_metadata[2]}"
        return dut_metadata

    async def rx_packet_pending(self):
        dut_pending = await self.wrapper.rx_packet_pending()
        model_pending = self.model.rx_packet_pending()
        assert dut_pending == model_pending, f"RX_PACKET_PENDING mismatch: DUT={dut_pending}, Model={model_pending}"
        return dut_pending

    async def rx_buffer_read_byte(self, byte_offset):
        dut_byte = await self.wrapper.rx_buffer_read_byte(byte_offset)
        model_byte = self.model.rx_buffer_read_byte(byte_offset)
        assert dut_byte == model_byte, f"RX_BUFFER_READ_BYTE mismatch at offset {byte_offset}: DUT={dut_byte}, Model={model_byte}"
        return dut_byte

    async def rx_buffer_read64(self, word_offset):
        dut_data = await self.wrapper.rx_buffer_read64(word_offset)
        model_data = self.model.rx_buffer_read64(word_offset)
        assert dut_data == model_data, f"RX_BUFFER_READ64 mismatch at offset {word_offset}: DUT={dut_data}, Model={model_data}"
        return dut_data

    async def read_packet(self, idx):
        dut_packet = await self.wrapper.read_packet(idx)
        model_packet = self.model.read_packet(idx)
        assert len(dut_packet) == len(model_packet), f"READ_PACKET length mismatch at index {idx}: DUT={len(dut_packet)}, Model={len(model_packet)}"
        assert dut_packet == model_packet, f"READ_PACKET mismatch at index {idx}: DUT={dut_packet}, Model={model_packet}"
        return dut_packet

    async def tx_packet_send(self, len_bytes):
        await self.wrapper.tx_packet_send(len_bytes)
        self.model.tx_packet_send(len_bytes)

    async def wait_for_tx_done(self, tail_after_done=10):
        await self.wrapper.wait_for_tx_done(tail_after_done=0) # when we are using the mirror, we want to update the model as soon as its done, THEN wait for the tail
        self.model.wait_for_tx_done()
        for _ in range(tail_after_done):
            await RisingEdge(self.dut.clk_125M_i)

    async def simulate_rx_packet(self, data):
        await self.begin_rx_packet(data)
        await self.wait_for_rx_done(tail_after_done=10)

    async def begin_rx_packet(self,data):
        await self.wrapper.begin_rx_packet(data)
        self.model.begin_rx_packet(data)

    async def wait_for_rx_done(self,tail_after_done=10):
        await self.wrapper.wait_for_rx_done(tail_after_done=5)
        # this function monitors the RGMII interface to know when RX is done
        # I've set a tail_after_done of FOUR CYCLES because that's the propagation delay through the DUT
        # however this is not ideal as it closely couples the model with a non-specific implementation detail
        # it would be best if we had a more sophisticated testbench that let us say "the status of the model is unknown for 10 cycles" to allow for implementation-specific delay
        # when we are using the mirror, we want to update the model as soon as its done, THEN wait for the tail
        self.model.wait_for_rx_done()
        for _ in range(tail_after_done):
            await RisingEdge(self.dut.clk_125M_i)

    async def irq_pending(self):
        dut_irq = await self.wrapper.irq_pending()
        model_irq = self.model.irq_pending()
        assert dut_irq == model_irq, f"IRQ_PENDING mismatch: DUT={dut_irq}, Model={model_irq}"
        return dut_irq

    async def tx_busy(self):
        dut_busy = await self.wrapper.tx_busy()
        model_busy = self.model.tx_busy()
        assert dut_busy == model_busy, f"TX_BUSY mismatch: DUT={dut_busy}, Model={model_busy}"
        return dut_busy

    async def get_transmitted_packet(self):
        dut_packet = await self.wrapper.get_transmitted_packet()
        model_packet = self.model.get_transmitted_packet()
        assert dut_packet == model_packet, f"GET_TRANSMITTED_PACKET mismatch: DUT={dut_packet}, Model={model_packet}"
        return dut_packet
