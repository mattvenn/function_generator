"""
test caravel wishbone
"""

import cocotb
from cocotb.clock import Clock
from cocotb.binary import BinaryValue
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles
from cocotbext.wishbone.driver import WishboneMaster, WBOp
from cocotbext.wishbone.monitor import WishboneSlave

# from J Pallent: 
# https://github.com/thejpster/zube/blob/9299f0be074e2e30f670fd87dec2db9c495020db/test/test_zube.py
async def test_wb_set(caravel_bus, addr, value):
    """
    Test putting values into the given wishbone address.
    """
    await caravel_bus.send_cycle([WBOp(addr, value)])

async def test_wb_get(caravel_bus, addr):
    """
    Test getting values from the given wishbone address.
    """
    res_list = await caravel_bus.send_cycle([WBOp(addr)])
    rvalues = [entry.datrd for entry in res_list]
    return rvalues[0]

async def reset(dut):
    dut.caravel_wb_rst_i = 1
    dut.caravel_wb_dat_i = 0
    await ClockCycles(dut.caravel_wb_clk_i, 5)
    dut.caravel_wb_rst_i = 0
    await ClockCycles(dut.caravel_wb_clk_i, 5)

def split_data(data):

    period      = data & 0xFFFF
    ram_addr    = (data >> 16) & 0xFF
    run         = (data >> 24) & 0x1

    return period, ram_addr, run

def join_data(period, ram_addr, run):
    return (run << 24) + ((0xFF & ram_addr) << 16) + (0xFFFF & period)

# return an ack after configurable delay
class RAMBusACK:

    def __init__(self, delay=0):
        self.delay = delay

    def __iter__(self):
        return self

    def __next__(self):
        return self.delay

# triangle wave generator
class RAMBusDat:

    def __init__(self, start=0, end=255):
        self.start = start
        self.end = end
        self.num = self.start

    def __iter__(self):
        return self

    # generate next 4 numbers
    def __next__(self):
        num = 0
        for i in range(4):
            if self.num > self.end:
                self.num = self.start
            num += self.num << (i * 8)
            self.num += 1
        return num

@cocotb.test()
async def test_caravel_bus(dut):
    """
    Run all the tests
    """
    clock = Clock(dut.caravel_wb_clk_i, 10, units="us")

    #dut.rambus_wb_ack_i = 1;
    #dut.rambus_wb_dat_i = 0xABCDEFAB;

    cocotb.fork(clock.start())

    caravel_bus_signals_dict = {
        "cyc"   :   "caravel_wb_cyc_i",
        "stb"   :   "caravel_wb_stb_i",
        "we"    :   "caravel_wb_we_i",
        "adr"   :   "caravel_wb_addr_i",
        "datwr" :   "caravel_wb_dat_i",
        "datrd" :   "caravel_wb_dat_o",
        "ack"   :   "caravel_wb_ack_o"
    }
    ram_bus_signals_dict = {
        "cyc"   :   "rambus_wb_cyc_o",
        "stb"   :   "rambus_wb_stb_o",
        "we"    :   "rambus_wb_we_o",
        "adr"   :   "rambus_wb_addr_o",
        "datwr" :   "rambus_wb_dat_o",
        "datrd" :   "rambus_wb_dat_i",
        "ack"   :   "rambus_wb_ack_i"
    }

    caravel_bus = WishboneMaster(dut, "", dut.caravel_wb_clk_i, width=32, timeout=10, signals_dict=caravel_bus_signals_dict)
    ram_bus     = WishboneSlave (dut, "", dut.rambus_wb_clk_o, width=32, signals_dict=ram_bus_signals_dict, datgen=RAMBusDat(), waitreplygen=RAMBusACK(delay=4))

    await reset(dut)

    # default base addr
    base_addr = 0x3000_0000

    # test defaults
    data = await test_wb_get(caravel_bus, base_addr)
    period, ram_addr, run = split_data(data)
    assert period   == 8
    assert ram_addr == 0
    assert run      == 0

    # write some new data
    await test_wb_set(caravel_bus, base_addr, join_data(2000, 30, 0))
    # fetch it
    data = await test_wb_get(caravel_bus, base_addr)
    period, ram_addr, run = split_data(data)
    assert period   == 2000
    assert ram_addr == 30
    assert run      == 0

    # start running with period 10, up to address 5
    period = 20
    max_addr = 15
    await test_wb_set(caravel_bus, base_addr, join_data(period, max_addr, 1))

    # start at correct address
    assert dut.rambus_wb_addr_o == 0
    for i in range(255 * 2):
        await ClockCycles(dut.caravel_wb_clk_i, period)
        # ensure max address read is < max_addr
        assert int(dut.rambus_wb_addr_o.value) < max_addr
        # ensure value from DAC is correct
        assert dut.dac == (i % 256)

