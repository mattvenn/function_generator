`default_nettype none
`timescale 1ns/1ns

module generator #(
    parameter   [31:0]  BASE_ADDRESS    = 32'h3000_0000,        // base address
    /*

    DATA PARTITION  NAME            DESCRIPTION
    15:0            period          clock cycles between putting next data on the output
    23:16           ram_end_addr  where to start reading the data in the shared RAM
    24              run             if high, set the design running

    */
    parameter   [15:0]  PERIOD          = 16'd8,                 // default period
    parameter   [7:0]   RAM_END_ADDR  = 8'd0                  // default start address in RAM to read pattern
)(
    // CaravelBus peripheral ports
    input wire          caravel_wb_clk_i,       // clock, runs at system clock
    input wire          caravel_wb_rst_i,       // main system reset
    input wire          caravel_wb_stb_i,       // write strobe
    input wire          caravel_wb_cyc_i,       // cycle
    input wire          caravel_wb_we_i,        // write enable
    input wire  [3:0]   caravel_wb_sel_i,       // write word select
    input wire  [31:0]  caravel_wb_dat_i,       // data in
    input wire  [31:0]  caravel_wb_addr_i,      // address
    output reg          caravel_wb_ack_o,       // ack
    output reg  [31:0]  caravel_wb_dat_o,       // data out

    // RAMBus controller ports
    output wire         rambus_wb_clk_o,        // clock, must run at system clock
    output wire         rambus_wb_rst_o,        // reset
    output reg          rambus_wb_stb_o,        // write strobe
    output reg          rambus_wb_cyc_o,        // cycle
    output reg          rambus_wb_we_o,         // write enable
    output reg  [3:0]   rambus_wb_sel_o,        // write word select
    output reg  [31:0]  rambus_wb_dat_o,        // data out
    output reg  [7:0]   rambus_wb_addr_o,       // address
    input wire          rambus_wb_ack_i,        // ack
    input wire  [31:0]  rambus_wb_dat_i,        // data in

    // output for driving DAC
    output reg [7:0]   dac
);

    wire clk = caravel_wb_clk_i;
    assign rambus_wb_clk_o = clk;
    wire reset = caravel_wb_rst_i;
    assign rambus_wb_rst_o = reset;


    reg [15:0] period;
    reg [7:0] ram_end_addr;
    reg run;

    // CaravelBus writes
    always @(posedge clk) begin
        if(reset) begin
            period          <= PERIOD;
            ram_end_addr  <= RAM_END_ADDR;
            run             <= 1'b0;
        end
        else if(caravel_wb_stb_i && caravel_wb_cyc_i && caravel_wb_we_i && caravel_wb_addr_i == BASE_ADDRESS) begin
            period          <= caravel_wb_dat_i[15:0];
            ram_end_addr  <= caravel_wb_dat_i[23:16];
            run             <= caravel_wb_dat_i[24];
        end
    end

    // CaravelBus reads
    always @(posedge clk) begin
        if(reset)
            caravel_wb_dat_o <= 0;
        else if(caravel_wb_stb_i && caravel_wb_cyc_i && !caravel_wb_we_i && caravel_wb_addr_i == BASE_ADDRESS) begin
            caravel_wb_dat_o <= { 7'b0, run, ram_end_addr, period };
        end
    end

    // CaravelBus acks
    always @(posedge clk) begin
        if(reset)
            caravel_wb_ack_o <= 0;
        else
            // return ack immediately
            caravel_wb_ack_o <= (caravel_wb_stb_i && caravel_wb_addr_i == BASE_ADDRESS);
    end

    // FSM for fetching and pushing data
    localparam DAC_STATE_STOP           = 0;
    localparam DAC_STATE_UPDATE         = 1;
    localparam DAC_STATE_WAIT           = 2;

    localparam RAM_STATE_WAIT           = 0;
    localparam RAM_STATE_ACK            = 1;

    reg [2:0]   dac_state;
    reg [31:0]  dac_data;
    reg [15:0]  wait_period;

    reg [2:0]   ram_state;
    reg [7:0]   ram_address;

    reg         fetch_next;
    reg         fetch_first;

    always @(posedge clk) begin
        if(reset) begin
            dac         <= 0;
            dac_state   <= DAC_STATE_STOP;
            dac_data    <= 0;
            wait_period <= period;
            fetch_next  <= 0;
            fetch_first <= 1;

            ram_address <= 0;
            ram_state   <= RAM_STATE_WAIT;
            rambus_wb_addr_o    <= 0;
            rambus_wb_stb_o     <= 0;
            rambus_wb_cyc_o     <= 0;
            rambus_wb_dat_o     <= 0;
            rambus_wb_sel_o     <= 4'b1111;
            rambus_wb_we_o      <= 0;

        end else begin

            case(dac_state)
                DAC_STATE_STOP: begin
                    if(run)
                        dac_state       <= DAC_STATE_UPDATE;
                    end

                DAC_STATE_UPDATE: begin
                    dac             <= dac_data[7:0];
                    dac_data        <= (dac_data >> 8);
                    dac_state       <= DAC_STATE_WAIT;
                    wait_period     <= period - 1;
                    if(dac_data[31:8] == 24'b0) // run out of data soon
                        fetch_next  <= 1;
                    end

                DAC_STATE_WAIT: begin
                    wait_period     <= wait_period - 1'b1;
                    fetch_next      <= 0;
                    if(wait_period == 1)
                        dac_state   <= DAC_STATE_UPDATE;
                    end

                default:
                    dac_state <= DAC_STATE_STOP;

            endcase

            case(ram_state)
                RAM_STATE_WAIT: begin
                    if(fetch_next || fetch_first) begin
                        ram_state           <= RAM_STATE_ACK;
                        rambus_wb_addr_o    <= ram_address;
                        ram_address         <= ram_address + 1;

                        rambus_wb_cyc_o     <= 1;
                        rambus_wb_stb_o     <= 1;

                        // wrap around at end address
                        if(ram_address == ram_end_addr - 1)
                            ram_address     <= 0;
                        end

                        fetch_first <= 0;

                    end

                RAM_STATE_ACK: begin
                    if(rambus_wb_ack_i) begin
                        rambus_wb_cyc_o     <= 0;
                        rambus_wb_stb_o     <= 0;
                        dac_data            <= rambus_wb_dat_i;
                        ram_state           <= RAM_STATE_WAIT;
                        end
                    end

                default:
                    ram_state <= RAM_STATE_WAIT;
            endcase
        end
    end
            /*
            // get the data from RAMBus
            STATE_FETCH:
                state <= STATE_WAIT_FETCH;

            STATE_WAIT_FETCH:
                state <= STATE_UPDATE_DAC;
                dac_data <= rambus_wb_dat_i;
                */

endmodule
