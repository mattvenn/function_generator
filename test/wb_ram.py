# SPDX-FileCopyrightText: © 2021 Uri Shaked <uri@wokwi.com>
# SPDX-License-Identifier: MIT

"""
Wishbone OpenRAM implementation for OpenMPW group submission

Usage example::

    ram_bus_signals = {
        "cyc": "rambus_wb_cyc_o",
        "stb": "rambus_wb_stb_o",
        "we": "rambus_wb_we_o",
        "adr": "rambus_wb_addr_o",
        "sel": "rambus_wb_sel_o",
        "datwr": "rambus_wb_dat_o",
        "datrd": "rambus_wb_dat_i",
        "ack": "rambus_wb_ack_i",
    }
    
    ram = WishboneRAM(dut, dut.rambus_wb_clk_o, ram_bus_signals)

Then, in your test case, read/write from/to ``ram.data``. For example::

    # Initialize the first byte of ram to 42
    ram.data[0] = 42

    # do something that causes the device under test (dut) to process data

    # Assert that the user project set the 5th byte to 0x55
    assert ram.data[5] == 0x55
"""


from cocotbext.wishbone.monitor import WishboneSlave


class WishboneRAMReader:
    def __init__(self, data, wb_addr, base_address):
        self._base_address = base_address
        self._data = data
        self._wb_addr = wb_addr

    def __iter__(self):
        return self

    def __next__(self):
        addr = self._wb_addr.value << 2
        addr -= self._base_address
        value = (
            self._data[addr]
            | (self._data[addr+1] << 8)
            | (self._data[addr+2] << 16)
            | (self._data[addr+3] << 24))
        return value


class WishboneRAM:
    def __init__(self, dut, clk, signals_dict, size=1024, base_address = 0):
        self._dut = dut
        self._base_address = base_address
        self.data = [0] * size
        adr_signal = getattr(self._dut, signals_dict['adr'])
        ram_reader = WishboneRAMReader(self.data, adr_signal, base_address)
        self._ram_bus = WishboneSlave(
            dut, "", clk, width=32, signals_dict=signals_dict, datgen=ram_reader)
        self._ram_bus.add_callback(self.rambus_callback)

    def rambus_callback(self, transactions):
        for transaction in transactions:
            sel = transaction.sel
            if transaction.datwr:
                for b in range(4):
                    if sel & (1 << b):
                        addr = ((transaction.adr - self._base_address) << 2) + b
                        print(hex(addr), hex(self._base_address), len(self.data))
                        self.data[addr] = (transaction.datwr >> (b*8)) & 0xff
