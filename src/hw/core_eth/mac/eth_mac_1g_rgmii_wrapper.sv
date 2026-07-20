/*

Copyright (c) 2015-2018 Alex Forencich

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

*/

// Language: Verilog 2001

/*
 * 1G Ethernet MAC with RGMII interface
 */
module eth_mac_1g_rgmii_wrapper #
(
    // target ("SIM", "GENERIC", "XILINX", "ALTERA")
    parameter string TARGET = "GENERIC",
    // IODDR style ("IODDR", "IODDR2")
    // Use IODDR for Virtex-4, Virtex-5, Virtex-6, 7 Series, Ultrascale
    // Use IODDR2 for Spartan-6
    parameter string IODDR_STYLE = "IODDR2",
    // Clock input style ("BUFG", "BUFR", "BUFIO", "BUFIO2")
    // Use BUFR for Virtex-5, Virtex-6, 7-series
    // Use BUFG for Ultrascale
    // Use BUFIO2 for Spartan-6
    parameter string CLOCK_INPUT_STYLE = "BUFIO2",
    // Use 90 degree clock for RGMII transmit ("TRUE", "FALSE")
    parameter string USE_CLK90 = "TRUE"
)
(
    input wire         gtx_clk,
    input wire         gtx_clk90,
    input wire         gtx_rst,
    input wire         logic_clk,
    input wire         logic_rst,

    /*
     * AXI input
     */
    input wire [7:0]   tx_axis_tdata,
    input wire         tx_axis_tvalid,
    output wire        tx_axis_tready,
    input wire         tx_axis_tlast,
    input wire         tx_axis_tuser,

    /*
     * AXI output
     */
    output wire [7:0]  rx_axis_tdata,
    output wire        rx_axis_tvalid,
    output wire        rx_axis_tlast,
    output wire        rx_axis_tuser,

    /*
     * RGMII interface
     */
    input wire         rgmii_rx_clk,
    input wire [3:0]   rgmii_rxd,
    input wire         rgmii_rx_ctl,
    output wire        rgmii_tx_clk,
    output wire [3:0]  rgmii_txd,
    output wire        rgmii_tx_ctl,
    output wire        mac_gmii_tx_en,

    /*
     * Status
     */
    output wire        rx_error_bad_frame,
    output wire        rx_error_bad_fcs,
    output wire [1:0]  speed,
    output wire [31:0] rx_fcs_reg,
    output wire [31:0] tx_fcs_reg,

    /*
     * Configuration
     */
    input wire [7:0]   ifg_delay
);

wire rx_clk;
wire rx_rst;

// synchronize MAC status signals into logic clock domain
wire rx_error_bad_frame_int;

reg [1:0] rx_sync_reg_1;
reg [1:0] rx_sync_reg_2;
reg [1:0] rx_sync_reg_3;
reg [1:0] rx_sync_reg_4;

assign rx_error_bad_frame = rx_sync_reg_3[0] ^ rx_sync_reg_4[0];
assign rx_error_bad_fcs = rx_sync_reg_3[1] ^ rx_sync_reg_4[1];

always @(posedge rx_clk or posedge rx_rst) begin
    if (rx_rst) begin
        rx_sync_reg_1 <= 2'd0;
    end else begin
        rx_sync_reg_1 <= rx_sync_reg_1 ^ {rx_error_bad_frame_int, rx_error_bad_frame_int};
    end
end

always @(posedge logic_clk or posedge logic_rst) begin
    if (logic_rst) begin
        rx_sync_reg_2 <= 2'd0;
        rx_sync_reg_3 <= 2'd0;
        rx_sync_reg_4 <= 2'd0;
    end else begin
        rx_sync_reg_2 <= rx_sync_reg_1;
        rx_sync_reg_3 <= rx_sync_reg_2;
        rx_sync_reg_4 <= rx_sync_reg_3;
    end
end


wire [1:0] speed_int;

reg [1:0] speed_sync_reg_1;
reg [1:0] speed_sync_reg_2;

assign speed = speed_sync_reg_2;

always @(posedge logic_clk) begin
    speed_sync_reg_1 <= speed_int;
    speed_sync_reg_2 <= speed_sync_reg_1;
end

eth_mac_1g_rgmii #(
    .TARGET(TARGET),
    .IODDR_STYLE(IODDR_STYLE),
    .CLOCK_INPUT_STYLE(CLOCK_INPUT_STYLE),
    .USE_CLK90(USE_CLK90),
    .ENABLE_PADDING(0),
    .MIN_FRAME_LENGTH(0)
)
eth_mac_1g_rgmii_inst (
    .gtx_clk(gtx_clk),
    .gtx_clk90(gtx_clk90),
    .gtx_rst(gtx_rst),
    .tx_clk(),
    .tx_rst(),
    .rx_clk(rx_clk),
    .rx_rst(rx_rst),

    .tx_axis_tdata(tx_axis_tdata),
    .tx_axis_tvalid(tx_axis_tvalid),
    .tx_axis_tready(tx_axis_tready),
    .tx_axis_tlast(tx_axis_tlast),
    .tx_axis_tuser(tx_axis_tuser),

    .rx_axis_tdata(rx_axis_tdata),
    .rx_axis_tvalid(rx_axis_tvalid),
    .rx_axis_tlast(rx_axis_tlast),
    .rx_axis_tuser(rx_axis_tuser),

    .rgmii_rx_clk(rgmii_rx_clk),
    .rgmii_rxd(rgmii_rxd),
    .rgmii_rx_ctl(rgmii_rx_ctl),
    .rgmii_tx_clk(rgmii_tx_clk),
    .rgmii_txd(rgmii_txd),
    .rgmii_tx_ctl(rgmii_tx_ctl),
    .mac_gmii_tx_en(mac_gmii_tx_en),
    .rx_error_bad_frame(rx_error_bad_frame_int),
    .rx_error_bad_fcs(),
    .rx_fcs_reg(rx_fcs_reg),
    .tx_fcs_reg(tx_fcs_reg),
    .speed(speed_int),
    .ifg_delay(ifg_delay)
);

endmodule
