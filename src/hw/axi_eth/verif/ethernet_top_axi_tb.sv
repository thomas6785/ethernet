// Copyright lowRISC contributors (COSMIC project).
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

/*
Module: ethernet_top_axi_tb
Author: Thomas O'Dea <thomas.odea@lowrisc.org>

-------------------------------------------------------------------------------
    DESCRIPTION
-------------------------------------------------------------------------------
Wraps ethernet_top_axi but flattens AXI structs into individual signals.
Useful for cocotbext-axi, which doesn't support struct ports.
Signal naming follows cocotbext-axi convention: {prefix}_{channel}{signal}
    e.g. axi_awaddr, axi_rvalid

-------------------------------------------------------------------------------
    TESTS
-------------------------------------------------------------------------------
Wrapper around ethernet_top_axi for cocotb testing which is driven by CocoTB.
See README.md for details.

*/

`include "axi/typedef.svh"

module ethernet_top_axi_tb (
    input logic clk_125M_i,
    input logic clk_125M_quad_i,
    input logic clk_200M_i,
    input logic rst_ni,

    /////////////////////////////
    // Flatten the AXI signals //
    /////////////////////////////
    // AW channel
    input  logic [AxiIdWidth-1:0]                  axi_awid,
    input  logic [AxiAddrWidth-1:0]                axi_awaddr,
    input  logic [7:0]                             axi_awlen,
    input  logic [2:0]                             axi_awsize,
    input  logic [1:0]                             axi_awburst,
    input  logic                                   axi_awlock,
    input  logic [3:0]                             axi_awcache,
    input  logic [2:0]                             axi_awprot,
    input  logic [3:0]                             axi_awqos,
    input  logic [3:0]                             axi_awregion,
    input  logic [AxiUserWidth-1:0]                axi_awuser,
    input  logic                                   axi_awvalid,
    output logic                                   axi_awready,

    // W channel
    input  logic [AxiDataWidth-1:0]                axi_wdata,
    input  logic [AxiStrbWidth-1:0]                axi_wstrb,
    input  logic                                   axi_wlast,
    input  logic [AxiUserWidth-1:0]                axi_wuser,
    input  logic                                   axi_wvalid,
    output logic                                   axi_wready,

    // B channel
    output logic [AxiIdWidth-1:0]                  axi_bid,
    output logic [1:0]                             axi_bresp,
    output logic [AxiUserWidth-1:0]                axi_buser,
    output logic                                   axi_bvalid,
    input  logic                                   axi_bready,

    // AR channel
    input  logic [AxiIdWidth-1:0]                  axi_arid,
    input  logic [AxiAddrWidth-1:0]                axi_araddr,
    input  logic [7:0]                             axi_arlen,
    input  logic [2:0]                             axi_arsize,
    input  logic [1:0]                             axi_arburst,
    input  logic                                   axi_arlock,
    input  logic [3:0]                             axi_arcache,
    input  logic [2:0]                             axi_arprot,
    input  logic [3:0]                             axi_arqos,
    input  logic [3:0]                             axi_arregion,
    input  logic [AxiUserWidth-1:0]                axi_aruser,
    input  logic                                   axi_arvalid,
    output logic                                   axi_arready,

    // R channel
    output logic [AxiIdWidth-1:0]                  axi_rid,
    output logic [AxiDataWidth-1:0]                axi_rdata,
    output logic [1:0]                             axi_rresp,
    output logic                                   axi_rlast,
    output logic [AxiUserWidth-1:0]                axi_ruser,
    output logic                                   axi_rvalid,
    input  logic                                   axi_rready,

    ///////////////////////////////
    // Flatten the RGMII signals //
    ///////////////////////////////
    output logic       phy_reset_no,
    input  logic [3:0] eth_rgmii_rx_data,
    input  logic       eth_rgmii_rx_ctl,
    input  logic       eth_rgmii_rx_clk,
    output logic [3:0] eth_rgmii_tx_data,
    output logic       eth_rgmii_tx_ctl,
    output logic       eth_rgmii_tx_clk,
    input  logic       eth_rgmii_mdio_i_i,
    output logic       eth_rgmii_mdio_o_o,
    output logic       eth_rgmii_mdio_o_oen,
    output logic       eth_rgmii_mdio_o_c
);
    initial begin
        if ($test$plusargs("trace")) begin
            $dumpfile("dump.fst");
            $dumpvars();
        end
    end

    // Set up coverage collection for the CSR block
    bind ethernet_csr ethernet_csr_cov ethernet_csr_cg_inst();

    // Set up coverage collection for the ring buffer
    bind axis_pkt_ring_buffer axis_pkt_ring_buffer_cov axis_pkt_ring_buffer_cg_inst();

    // These don't do anything but they make it a whole lot easier to read the waveforms
    int tests_done = 0;
    int tests_passed = 0;
    int tests_failed = 0;

    localparam AxiDataWidth = 64;
    localparam AxiAddrWidth = 64;
    localparam AxiIdWidth   = 4;
    localparam AxiStrbWidth = AxiDataWidth/8;
    localparam AxiUserWidth = 1; // not used

    typedef logic [AxiDataWidth-1:0]    axi_data_t;
    typedef logic [AxiAddrWidth-1:0]    axi_addr_t;
    typedef logic [AxiDataWidth/8-1:0]  axi_strb_t;
    typedef logic [AxiIdWidth-1:0]      axi_id_t;
    typedef logic [AxiUserWidth-1:0]    axi_user_t;
    `AXI_TYPEDEF_ALL_CT(axi, axi_req_t, axi_rsp_t, axi_addr_t, axi_id_t, axi_data_t, axi_strb_t, axi_user_t)

    axi_req_t axi_req_i;
    axi_rsp_t axi_rsp_o;
    logic ethernet_irq_o;

    ethernet_pkg::eth_rgmii_rx_t         eth_rgmii_rx_i;
    ethernet_pkg::eth_rgmii_tx_t         eth_rgmii_tx_o;
    ethernet_pkg::eth_rgmii_mdio_in_t    eth_rgmii_mdio_i;
    ethernet_pkg::eth_rgmii_mdio_out_t   eth_rgmii_mdio_o;

    assign eth_rgmii_rx_i.d    = eth_rgmii_rx_data;
    assign eth_rgmii_rx_i.ctl  = eth_rgmii_rx_ctl;
    assign eth_rgmii_rx_i.clk  = eth_rgmii_rx_clk;
    assign eth_rgmii_mdio_i = eth_rgmii_mdio_i_i;

    assign eth_rgmii_tx_data = eth_rgmii_tx_o.d;
    assign eth_rgmii_tx_ctl  = eth_rgmii_tx_o.en;
    assign eth_rgmii_tx_clk  = eth_rgmii_tx_o.clk;
    assign eth_rgmii_mdio_o_o   = eth_rgmii_mdio_o.o;
    assign eth_rgmii_mdio_o_oen = eth_rgmii_mdio_o.oen;
    assign eth_rgmii_mdio_o_c   = eth_rgmii_mdio_o.c;

    assign axi_req_i.aw.id     = axi_awid;
    assign axi_req_i.aw.addr   = axi_awaddr;
    assign axi_req_i.aw.len    = axi_awlen;
    assign axi_req_i.aw.size   = axi_awsize;
    assign axi_req_i.aw.burst  = axi_awburst;
    assign axi_req_i.aw.lock   = axi_awlock;
    assign axi_req_i.aw.cache  = axi_awcache;
    assign axi_req_i.aw.prot   = axi_awprot;
    assign axi_req_i.aw.qos    = axi_awqos;
    assign axi_req_i.aw.region = axi_awregion;
    assign axi_req_i.aw.user   = axi_awuser;
    assign axi_req_i.aw_valid  = axi_awvalid;

    assign axi_req_i.w.data    = axi_wdata;
    assign axi_req_i.w.strb    = axi_wstrb;
    assign axi_req_i.w.last    = axi_wlast;
    assign axi_req_i.w.user    = axi_wuser;
    assign axi_req_i.w_valid   = axi_wvalid;

    assign axi_req_i.b_ready   = axi_bready;

    assign axi_req_i.ar.id     = axi_arid;
    assign axi_req_i.ar.addr   = axi_araddr;
    assign axi_req_i.ar.len    = axi_arlen;
    assign axi_req_i.ar.size   = axi_arsize;
    assign axi_req_i.ar.burst  = axi_arburst;
    assign axi_req_i.ar.lock   = axi_arlock;
    assign axi_req_i.ar.cache  = axi_arcache;
    assign axi_req_i.ar.prot   = axi_arprot;
    assign axi_req_i.ar.qos    = axi_arqos;
    assign axi_req_i.ar.region = axi_arregion;
    assign axi_req_i.ar.user   = axi_aruser;
    assign axi_req_i.ar_valid  = axi_arvalid;

    assign axi_req_i.r_ready   = axi_rready;

    assign axi_awready = axi_rsp_o.aw_ready;
    assign axi_wready  = axi_rsp_o.w_ready;
    assign axi_bid     = axi_rsp_o.b.id;
    assign axi_bresp   = axi_rsp_o.b.resp;
    assign axi_buser   = axi_rsp_o.b.user;
    assign axi_bvalid  = axi_rsp_o.b_valid;
    assign axi_arready = axi_rsp_o.ar_ready;
    assign axi_rid     = axi_rsp_o.r.id;
    assign axi_rdata   = axi_rsp_o.r.data;
    assign axi_rresp   = axi_rsp_o.r.resp;
    assign axi_rlast   = axi_rsp_o.r.last;
    assign axi_ruser   = axi_rsp_o.r.user;
    assign axi_rvalid  = axi_rsp_o.r_valid;

    ethernet_top_axi #(
        .TARGET("SIM"), // for Verilator simulation
        .axi_req_t(axi_req_t),
        .axi_rsp_t(axi_rsp_t)
    ) dut (
        .clk_125M_i,
        .clk_125M_quad_i,
        .clk_200M_i,
        .rst_ni,
        .axi_req_i,
        .axi_rsp_o,
        .ethernet_irq_o,
        .phy_reset_no,
        .eth_rgmii_rx_i,
        .eth_rgmii_tx_o,
        .eth_rgmii_mdio_i,
        .eth_rgmii_mdio_o
    );
endmodule
