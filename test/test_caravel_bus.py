"""
test caravel wishbone
"""

import cocotb
from cocotb.clock import Clock
from cocotb.binary import BinaryValue
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles
from cocotbext.wishbone.driver import WishboneMaster, WBOp
from cocotbext.wishbone.monitor import WishboneSlave
from wb_ram import WishboneRAM

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

# load a triangle wave into ram
def init_ram(ram_bus):
    num = 10 
    for addr in range(60):
        ram_bus.data[addr] = num
        num += 1

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
        "adr"   :   "caravel_wb_adr_i",
        "datwr" :   "caravel_wb_dat_i",
        "datrd" :   "caravel_wb_dat_o",
        "ack"   :   "caravel_wb_ack_o"
    }
    ram_bus_signals_dict = {
        "cyc"   :   "rambus_wb_cyc_o",
        "stb"   :   "rambus_wb_stb_o",
        "we"    :   "rambus_wb_we_o",
        "adr"   :   "rambus_wb_adr_o",
        "datwr" :   "rambus_wb_dat_o",
        "datrd" :   "rambus_wb_dat_i",
        "ack"   :   "rambus_wb_ack_i"
    }

    caravel_bus = WishboneMaster(dut, "", dut.caravel_wb_clk_i, width=32, timeout=10, signals_dict=caravel_bus_signals_dict)
    ram_bus     = WishboneRAM    (dut, dut.rambus_wb_clk_o, ram_bus_signals_dict)

    # load a triangle wave into the ram, first 15 words (4 bytes per word, so 60 data points), starting at 10, incremementing by 1 each time
    init_ram(ram_bus)

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
    assert dut.rambus_wb_adr_o == 0

    # sync to start of DAC output
    await FallingEdge(dut.dbg_dac_start)

    # wait for a 2 whole cycles before the data starts flowing
    await ClockCycles(dut.caravel_wb_clk_i, 2*period)

    for i in range(period * max_addr * 2):

        # ensure value from DAC is correct
        assert dut.dac == (i % 60) + 10

        # ensure max address read is < max_addr
        assert int(dut.rambus_wb_adr_o.value) < max_addr

        await ClockCycles(dut.caravel_wb_clk_i, period)

