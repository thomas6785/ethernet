// Copyright lowRISC contributors (COSMIC project).
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

/*
Module: ethernet_top_tb + associated classes for testing
Author: Thomas O'Dea <thomas.odea@lowrisc.org>

-------------------------------------------------------------------------------
    DESCRIPTION
-------------------------------------------------------------------------------
Basic testbench and stimulus for ethernet_top.
Tests are not comprehensive but exercise core functionality. Better test
coverage is offered by the ethernet_top_axi testbench, but this is included
to allow testing in Vivado (instead of Verilator) and quicker smoke testing
during development.

NOTE: there are currently some concurrent assertions failing due to this
testbench reading undefined entries in the RX metadata table. However, the
immediate assertions which are created here should still be valid and the
testbench should otuput "x/x tests passed." after completing.

-------------------------------------------------------------------------------
    TESTS
-------------------------------------------------------------------------------
This is a testbench.

-------------------------------------------------------------------------------
    INSTANTIATION TEMPLATE
-------------------------------------------------------------------------------
N/A

*/

import ethernet_pkg::*;
import mem_if_utils_pkg::*;

function randomise_test_data(output logic [7:0] test_data[], input int length = 1522);
    test_data = new[length];
    for (int i = 0; i < length; i++) begin
        test_data[i] = 8'($urandom_range(0, 255));
    end
endfunction

function info(input string msg);
    //$display("       (%t) %s", $time, msg);
endfunction // TODO clean up logging in general

interface ethernet_tb_if();
    logic                   clk_125M_i;
    logic                   clk_125M_quad_i;
    logic                   clk_200M_i;
    logic                   rst_ni;
    mem_req_t               mem_req_i;
    mem_rsp_t               mem_rsp_o;
    logic                   phy_reset_no;
    eth_rgmii_rx_t          eth_rgmii_rx_i;
    eth_rgmii_tx_t          eth_rgmii_tx_o;
    eth_rgmii_mdio_in_t     eth_rgmii_mdio_i;
    eth_rgmii_mdio_out_t    eth_rgmii_mdio_o;
    logic                   irq_o;
endinterface

class scoreboard;
    int failed_assertions, passed_assertions, failed_tests, passed_tests;
    logic test_in_progress;
    string current_test_name;
    function new();
        this.failed_assertions = 0;
        this.passed_assertions = 0;
        this.failed_tests = 0;
        this.passed_tests = 0;
        this.current_test_name = "";
        this.test_in_progress = 0;
    endfunction

    function log(string msg);
        $display("       [scoreboard] ", msg);
    endfunction

    function end_test();
        this.log($sformatf("End test %s", this.current_test_name));
        this.log($sformatf("Result: %d/%d assertions passed", this.passed_assertions, this.passed_assertions+this.failed_assertions));
        if (this.failed_assertions > 0) begin
            this.failed_tests++;
        end else begin
            this.passed_tests++;
        end

        this.passed_assertions = 0;
        this.failed_assertions = 0;
        this.test_in_progress = 0;
    endfunction

    function new_test(string name);
        if (this.test_in_progress) begin
            this.end_test();
        end
        this.test_in_progress = 1;
        this.current_test_name = name;
        this.log($sformatf("Begin test %s",this.current_test_name));
    endfunction

    function assert_equal(input logic [63:0] measured, input logic [63:0] expected, input string name);
        if (expected !== measured) begin
            this.failed_assertions++;
            $display("[FAIL] Expected %s %h, got %h at %t", name, expected, measured, $time);
        end else begin
            this.passed_assertions++;
            //$display("[....] %s matches expected value: %h", name, expected);
        end
    endfunction

    function report_results();
        if (this.test_in_progress) begin
            this.end_test();
        end
        $display("=======================================================================");
        $display("Scoreboard tracked: ", this.passed_tests, "/", this.passed_tests+this.failed_tests, " tests passed.");
        $display("=======================================================================");
        if (this.failed_tests > 0) $error("--> ERROR <-- Some tests failed. Exiting with error.");
        else                       $display("RESULT: ALL TESTS PASSED"); // <---- magic string that CI will grep for
    endfunction
endclass

class packet_level_model;
    /*
    simple model for tracking number of packets and number of bytes in the buffer used up
    has no concept of what is in the packets or associated metadata

    Methods to push new packets, pop old packets, and get/check the status flags
    If a push comes when full it is ignored
    If a pop comes when empty it is ignored
    */
    scoreboard scb;
    int pkt_lengths[$]; // queue to track lengths of packets in the buffer
    int buffer_occupancy; // arguably redundant since we could just sum over the lengths

    function new(scoreboard _scb);
        this.scb = _scb;
        this.buffer_occupancy = 0;
    endfunction

    function new_packet(input int length);
        info($sformatf("New packet of length %d bytes",length));
        if (this.pkt_lengths.size() < 8 && this.buffer_occupancy+length <= 8192) begin
            this.pkt_lengths.push_back(length);
            this.buffer_occupancy += length;
        end
        if (this.buffer_occupancy > 8192) begin
            $error("Bad test - buffer overflow in packet level model");
        end
        if (this.pkt_lengths.size() > 8) begin
            $error("Bad test - packet table overflow in packet level model");
        end
    endfunction

    function pop_packet();
        info("Popping packet");
        if (this.pkt_lengths.size() > 0) begin
            this.buffer_occupancy -= this.pkt_lengths.pop_front();
        end
        if (this.buffer_occupancy < 0) begin
            $error("How did we get here??? fnhbeskdhlvljiojhy7e58sugtrs <- greppable string");
        end
    endfunction

    function get_status(
        output logic rx_not_empty,
        output logic table_almost_full,
        output logic table_full,
        output logic buf_almost_full,
        output logic [3:0] n_packets_in_rx_buf);
        rx_not_empty = (this.pkt_lengths.size() > 0);
        table_almost_full = (this.pkt_lengths.size() >= 6); // 7 packets in the table means the 8th entry is reserved for the currently processing packet, so we consider it almost full at this point
        table_full = (this.pkt_lengths.size() == 8);
        buf_almost_full = (this.buffer_occupancy >= 8192-1524); // if there are less than a max-size frame of bytes left in the buffer, we consider it almost full
        n_packets_in_rx_buf = 4'(this.pkt_lengths.size());
        info($sformatf("Got model status, %p",pkt_lengths));
    endfunction

    function check_status(input logic [31:0] measured_status);
        logic rx_not_empty;
        logic table_almost_full;
        logic table_full;
        logic buf_almost_full;
        logic [3:0] n_packets_in_rx_buf;
        this.get_status(rx_not_empty, table_almost_full, table_full, buf_almost_full, n_packets_in_rx_buf);
        this.scb.assert_equal(measured_status[0], rx_not_empty, "rx_not_empty");
        this.scb.assert_equal(measured_status[1], table_almost_full, "table_almost_full");
        this.scb.assert_equal(measured_status[2], table_full, "table_full");
        this.scb.assert_equal(measured_status[3], buf_almost_full, "buf_almost_full");
        this.scb.assert_equal(measured_status[11:8], n_packets_in_rx_buf, "n_packets_in_rx_buf");
    endfunction
endclass

class test_base;
    virtual ethernet_tb_if tb_if;
    scoreboard scb;

    function new(virtual ethernet_tb_if _tb_if, scoreboard _scb);
        this.tb_if = _tb_if;
        this.scb = _scb;
    endfunction

    task send_random_packet(input logic [47:0] dest_mac, input int total_length);
        logic [7:0] test_data[];
        randomise_test_data(test_data,total_length-6); // -6 for the MAC address
        tx_packet(dest_mac, test_data);
    endtask

    task dump_descriptor_table();
        info("Index\tPtr\t\tLen\tReason");
        for(int i = 0; i < 8; i++) begin
            logic [63:0] addr, data;
            logic [$clog2(MAX_ETH_PKT_LEN)-1:0] length;
            pkt_metadata_t metadata;
            logic [31:0] ptr;

            addr = 'h6000+i*8; // read from RX descriptor table
            read_from_mem_if(addr); // read from RX descriptor table
            @(posedge tb_if.clk_125M_i); // wait for read data to be valid
            data = tb_if.mem_rsp_o.data;
            metadata = pkt_metadata_t'(data[15:0]);
            length = data[26:16];
            ptr = data[63:32];
            info($sformatf("%0d\t%h\t%0d\t%0b", i, ptr, length, metadata.capture_reason));
        end
    endtask

    task dump_rx_buf(input logic [15:0] len);
        for (int i = 0; i < len; i++) begin
            logic [63:0] addr;
            addr = 'h4000+i*8; // read from RX buffer
            read_from_mem_if(addr); // read from RX buffer
            @(posedge tb_if.clk_125M_i); // wait for read data to be valid
            info($sformatf("rx_buf[%h] = %h", addr, tb_if.mem_rsp_o.data));
        end
    endtask

    task dump();
        dump_descriptor_table();
        dump_rx_buf(30);
    endtask

    task write_reg(input logic [63:0] addr, input logic [31:0] data);
        logic [7:0] be;
        logic upper;
        if(addr[2:0] == 4) begin
            be = 8'hF0;
            upper = 1;
        end else if (addr[2:0] == 0) begin
            be = 8'h0F;
            upper = 0;
        end else begin
            $error("Testbench attempted to write bad address");
        end
        write_to_mem_if({data,data}, addr, be);
        @(posedge this.tb_if.clk_125M_i);
    endtask

    task write_and_check_reg(input logic [63:0] addr, input logic [31:0] data);
        logic [7:0] be;
        logic upper;
        if(addr[2:0] == 4) begin
            be = 8'hF0;
            upper = 1;
        end else if (addr[2:0] == 0) begin
            be = 8'h0F;
            upper = 0;
        end else begin
            $error("Testbench attempted to write bad address");
        end
        write_to_mem_if({data,data}, addr, be);
        @(posedge this.tb_if.clk_125M_i);
        read_from_mem_if(addr);
        @(posedge this.tb_if.clk_125M_i);
        this.scb.assert_equal(upper ? this.tb_if.mem_rsp_o.data[63:32] : this.tb_if.mem_rsp_o.data[31:0], data, $sformatf("register readback at address %h", addr));
    endtask

    task assert_reg_value(input logic [63:0] addr, input logic [63:0] expected_value);
        logic [31:0] read_data;
        read_from_mem_if(addr);
        @(posedge this.tb_if.clk_125M_i);
        if (addr[2:0]==0) begin
            read_data = this.tb_if.mem_rsp_o.data[31:0];
        end else if (addr[2:0] == 4) begin
            read_data = this.tb_if.mem_rsp_o.data[63:32];
        end else begin
            $error("Testbench attempted to read bad address");
        end
        this.scb.assert_equal(read_data, expected_value, $sformatf("register readback at address %h", addr));
    endtask

    task eth_send(input logic [7:0] data[]);
        foreach (data[i]) begin
            @(negedge tb_if.eth_rgmii_rx_i.clk); // wait for negedge so we can send the LS nybble on the rising edge
            tb_if.eth_rgmii_rx_i.d   <= data[i][3:0];
            @(posedge tb_if.eth_rgmii_rx_i.clk); // wait for posedge so we can send MS nybble on the next negedge
            tb_if.eth_rgmii_rx_i.d   <= data[i][7:4];
        end
    endtask

    task write_to_mem_if(input logic [63:0] data, input logic [63:0] addr, input logic [7:0] be);
        tb_if.mem_req_i.req  <= 1;
        tb_if.mem_req_i.we   <= 1;
        tb_if.mem_req_i.addr <= addr + 64'h3000_0000; // base being added shouldn't matter
        tb_if.mem_req_i.be   <= be;
        tb_if.mem_req_i.data <= data;
        @(posedge tb_if.clk_125M_i);
        tb_if.mem_req_i.req  <= 0;
        tb_if.mem_req_i.we   <= 0;
    endtask

    task read_from_mem_if(input logic [63:0] addr);
        tb_if.mem_req_i.req  <= 1;
        tb_if.mem_req_i.we   <= 0;
        tb_if.mem_req_i.addr <= addr + 64'h3000_0000; // base being added shouldn't matter
        @(posedge tb_if.clk_125M_i);
        tb_if.mem_req_i.req  <= 0;
        tb_if.mem_req_i.we   <= 0;
    endtask

    task read_status_reg(output logic [31:0] status);
        read_from_mem_if('h814);
        @(posedge tb_if.clk_125M_i);
        status = tb_if.mem_rsp_o.data[63:32];
    endtask

    task wait_for_idle();
        while (tb_if.eth_rgmii_tx_o.en || tb_if.eth_rgmii_rx_i.ctl) begin
            @(posedge tb_if.clk_125M_i);
        end
        repeat(4) @(posedge tb_if.clk_125M_i); // wait a few cycles for the packet to be processed
    endtask

    task simulate_rx_packet(input logic [47:0] dest_mac, input logic [7:0] payload[]);
        automatic logic [7:0] preamble [8] = '{8'h55, 8'h55, 8'h55, 8'h55, 8'h55, 8'h55, 8'h55, 8'hD5};

        @(posedge tb_if.eth_rgmii_rx_i.clk);
        tb_if.eth_rgmii_rx_i.ctl <= 1; // Assert control to indicate start of frame
        // Send the preamble + SFD
        eth_send(preamble);

        // Send dest MAC address
        for (int i = 0; i < 6; i++) begin
            eth_send({dest_mac[47-8*i -: 8]});
        end

        // Send the payload
        eth_send(payload);

        tb_if.eth_rgmii_rx_i.ctl <= 0; // deassert control to indicate end of frame
        @(posedge tb_if.eth_rgmii_rx_i.clk);
    endtask

    task write_tx_buf_bytes(input logic [10:0] base, input logic [7:0] data[]);
        // $display("Writing to TX buffer at offset %0d, data:", base);
        // $display("%p", data);
        for (int i = 0; i < $size(data); i=i+8) begin
            logic [63:0] addr, wdata;
            addr = 64'h1000+64'(base)+64'(i); // write to TX buffer
            wdata = '0;
            for (int j = 0; j < 8; j++) begin
                if (i + j >= $size(data)) begin
                    wdata[j*8 +: 8] = 8'h00; // pad with zeros if we run out of data
                end else begin
                    wdata[j*8 +: 8] = data[i+j];
                end
            end
            write_to_mem_if(wdata, addr, 8'hFF); // write to TX buffer with all byte lanes enabled
        end
    endtask

    task read_descriptor_table(
        output pkt_metadata_t metadata_out[8],
        output pkt_len_t      lengths_out[8],
        output logic [31:0]   ptrs_out[8]
    );
        for(int i = 0; i < 8; i++) begin
            logic [63:0] addr, data;

            addr = 'h6000+i*8; // read from RX descriptor table
            read_from_mem_if(addr); // read from RX descriptor table
            @(posedge tb_if.clk_125M_i); // wait for read data to be valid
            data = tb_if.mem_rsp_o.data;
            metadata_out[i] = pkt_metadata_t'(data[15:0]);
            lengths_out[i]  = data[26:16];
            ptrs_out[i]     = data[63:32];
        end
    endtask

    function expect_metadata(
        input pkt_metadata_t measured,
        input capture_reason_e expected_reason
    );
        this.scb.assert_equal(measured.capture_reason, expected_reason, "capture reason");
    endfunction

    task expect_rx_buf_data_match(input logic [31:0] ptr, input logic [7:0] expected_data[]);
        logic [63:0] read_data;
        int mismatches = 0;
        read_from_mem_if('h4000 + ((ptr>>3)<<3));
        @(posedge tb_if.clk_125M_i);
        read_data = tb_if.mem_rsp_o.data;

        for (int i = 0; i < expected_data.size(); i++) begin
            logic [63:0] addr;
            logic [7:0] read_byte;
            logic [2:0] offset;

            addr = 'h4000 + ptr + i; // read from RX buffer at the given pointer

            if (addr % 8 == 0) begin
                read_from_mem_if(addr); // read from RX buffer
                @(posedge tb_if.clk_125M_i); // wait for read data to be valid
                read_data = tb_if.mem_rsp_o.data;
            end
            offset = addr[2:0];

            read_byte = read_data[offset*8 +: 8]; // extract the relevant byte from the 64-bit word
            if (read_byte !== expected_data[i]) begin
                mismatches++;
            end
        end
        this.scb.assert_equal(mismatches, 0, "RX buffer data mismatches");
    endtask

    task tx_packet(input logic [47:0] dest_mac, input logic [7:0] data[]);
        // MAC address at the front of the buffer
        logic [7:0] first_word [8];
        first_word = {
            dest_mac[47:40],
            dest_mac[39:32],
            dest_mac[31:24],
            dest_mac[23:16],
            dest_mac[15:8],
            dest_mac[7:0],
            data[0],
            data[1]
        };
        write_tx_buf_bytes(0, first_word);
        // followed by the payload
        write_tx_buf_bytes(8,data[2:data.size()-1]);
        // start the transmission by writing the packet length to the control register
        write_and_check_reg('h820, 6+data.size()); // check that the TX packet length register readback is correct
        @(posedge tb_if.clk_125M_i iff tb_if.eth_rgmii_tx_o.en); // wait for transmission to start
        wait_for_idle(); // wait for it to end
    endtask

    task reset_dut();
        // Reset all interfaces initially
        tb_if.rst_ni                  <= '0;
        tb_if.mem_req_i               <= '0;
        tb_if.eth_rgmii_rx_i.d        <= '0;
        tb_if.eth_rgmii_rx_i.ctl      <= '0;
        tb_if.eth_rgmii_mdio_i        <= '0;
        repeat(2) @(posedge tb_if.clk_125M_i); // hold reset for a few cycles
        tb_if.rst_ni <= '1; // release reset
        repeat(2) @(posedge tb_if.clk_125M_i); // wait for reset to propagate
    endtask

    task enable_loopback();
        write_and_check_reg('h810, 2); // enable loopback mode
    endtask

    task enable_promiscuous_loopback();
        write_and_check_reg('h810, 3); // enable loopback mode and promiscuous mode
    endtask
endclass

class misc_test_cases extends test_base;
    function new(virtual ethernet_tb_if tb_if, scoreboard scb);
        super.new(tb_if, scb);
    endfunction

    task run();
        this.reset_dut();
        this.scb.new_test("Loopback test");
        this.basic_loopback_test();

        this.reset_dut();
        this.scb.new_test("MAC filtering test");
        this.mac_filtering_test();
        this.scb.new_test("Promiscuous mode test");
        this.promiscuous_mode_test();
        this.scb.new_test("Descriptor table full test");
        this.table_full_test();
        this.scb.new_test("Buffer almost full test");
        this.buf_almost_full_test();
        this.scb.end_test();
    endtask

    task basic_loopback_test();
        logic [7:0]     test_data[];
        pkt_metadata_t  metadata_out[8];
        pkt_len_t       lengths_out[8];
        logic [31:0]    ptrs_out[8];

        ///////////////////
        // Loopback test //
        ///////////////////
        // Enter loopback mode and send packets. Expect a new packet
        randomise_test_data(test_data);
        enable_loopback();
        tx_packet(48'hFF_FF_FF_FF_FF_FF, test_data[0:57]);
        read_descriptor_table(metadata_out, lengths_out, ptrs_out);
        expect_metadata(metadata_out[0], MAC_BROADCAST);
        this.scb.assert_equal(lengths_out[0], 64, "length"); // 64 = 58 payload, 6 MAC address
        expect_rx_buf_data_match(ptrs_out[0]+6, test_data[0:57]);
        // add 6 bytes to the pointer to skip the MAC address
    endtask

    task mac_filtering_test();
        logic [7:0]  test_data[];
        logic [31:0] status;
        randomise_test_data(test_data);

        enable_loopback();
        // Test MAC filtering
        tx_packet(48'hFF_FF_FF_FF_FF_F0, test_data[0:57]); // send a packet on a non-matching MAC address
        // packet should not have been captured, assert no new entries
        read_status_reg(status);
        this.scb.assert_equal(status, 32'h0, "status reg");
    endtask

    task promiscuous_mode_test();
        logic [7:0]     test_data[];
        logic [31:0] status;
        randomise_test_data(test_data);

        enable_promiscuous_loopback();
        tx_packet(48'hFF_FF_FF_FF_FF_F0, test_data[0:57]); // send a packet on a non-matching MAC address
        // packet should not have been captured, assert no new entries
        read_status_reg(status);
        this.scb.assert_equal(status, 32'h101, "status reg");
    endtask

    task table_full_test();
        logic [31:0] status_read;

        // reset DUT
        reset_dut();
        // enable loopback
        enable_loopback();

        // enable IRQ from table_almost_full and table_full conditions
        write_and_check_reg('h804, (1<<1)|(1<<2));

        // send 6 packets
        for (int i = 0; i < 6; i++) begin
            logic [7:0] test_data[];
            logic tx_busy;
            randomise_test_data(test_data);
            tx_packet(48'hFF_FF_FF_FF_FF_FF, test_data[0:57]);
            do begin
                logic [31:0] status;
                read_status_reg(status);
                tx_busy = status[7];
            end while (tx_busy);
            this.scb.assert_equal(tb_if.eth_rgmii_tx_o.en, 0, "TX still busy after packet transmission");
        end

        // read status and expect 6 packets captured, 'almost full' flag set
        read_status_reg(status_read);

        this.scb.assert_equal(status_read[11:8], 6, "status reg number of packets");
        this.scb.assert_equal(status_read[4:0], 3, "status reg flags");

        // expect IRQ, then mask and expect no IRQ
        this.scb.assert_equal(tb_if.irq_o, 1, "IRQ should be asserted when table is almost full");
        write_reg('h804, 1<<2); // leave the table_full IRQ enabled but disable table_almost_full
        repeat(2) @(posedge tb_if.clk_125M_i); // little delay
        this.scb.assert_equal(tb_if.irq_o, 0, "IRQ should be deasserted after masking table_almost_full IRQ");

        // send 2 more packets
        for (int i = 0; i < 2; i++) begin
            logic [7:0] test_data[];
            logic tx_busy;
            randomise_test_data(test_data);
            tx_packet(48'hFF_FF_FF_FF_FF_FF, test_data[0:57]);
            do begin
                logic [31:0] status;
                read_status_reg(status);
                tx_busy = status[7];
            end while (tx_busy);
            this.scb.assert_equal(tb_if.eth_rgmii_tx_o.en, 0, "TX still busy after packet transmission");
        end

        // read status and expect 8 packets captured, 'full' and 'almost full' to be set
        read_status_reg(status_read);

        this.scb.assert_equal(status_read[11:8], 8, "status reg number of packets");
        this.scb.assert_equal(status_read[4:0], 7, "status reg flags");

        // expect IRQ
        this.scb.assert_equal(tb_if.irq_o, 1, "IRQ should be asserted when table is full");
        write_reg('h804, 0); // disable IRQs
        repeat(2) @(posedge tb_if.clk_125M_i); // little delay
        this.scb.assert_equal(tb_if.irq_o, 0, "expect no IRQ when masked");
        write_reg('h804, 1<<2); // enable the almost_full IRQ
        repeat(2) @(posedge tb_if.clk_125M_i); // little delay
        this.scb.assert_equal(tb_if.irq_o, 1, "expect IRQ for almost_full when full");
    endtask

    task buf_almost_full_test();
        logic [31:0] read_status;
        // buf can hold 8192 bytes and will warn when there are <1528 left

        // reset DUT
        reset_dut();
        enable_loopback();

        // read status and expect no flags, no packets
        read_status_reg(read_status);
        this.scb.assert_equal(read_status, 32'h0, "status reg");

        // send 5 packets of 1340 bytes = 6700 bytes = 1492 left
        for (int i = 0; i < 5; i++) begin // 5 packets
            logic [7:0] test_data[];
            logic tx_busy = 1;
            randomise_test_data(test_data);
            tx_packet(48'hFF_FF_FF_FF_FF_FF, test_data[0:1333]); // payload of 1334 + 6 byte MAC address = 1340 bytes
            repeat(10) @(posedge this.tb_if.clk_125M_i); // wait a few cycles for the packet to be processed
            while (tx_busy) begin
                logic [31:0] status;
                read_status_reg(status);
                tx_busy = status[7];
            end
            repeat(3) @(posedge this.tb_if.clk_125M_i); // wait a few cycles for the packet to be processed
            this.scb.assert_equal(tb_if.eth_rgmii_tx_o.en, 0, "TX still busy after packet transmission");
        end

        // expect buf_almost_full_flag to be set
        read_status_reg(read_status);
        this.scb.assert_equal(read_status[3], 1, "buf_almost_full flag should be set when there are <1528 bytes left in the buffer");

        // pop a packet and expect the flag to be cleared
        write_reg('h828, 1);
        @(posedge this.tb_if.clk_125M_i);
        read_status_reg(read_status);
        this.scb.assert_equal(read_status[3], 0, "buf_almost_full flag should be cleared after popping a packet");
    endtask
endclass // TODO split misc_test_cases into separate focused test classes

class test_registers extends test_base;
    function new(virtual ethernet_tb_if tb_if, scoreboard scb);
        super.new(tb_if, scb);
    endfunction

    task run();
        logic [31:0] test_data;

        reset_dut();

        // Test INTR_STATE
        assert_reg_value('h800, 0); // check INTR_STATE is 0 after reset

        // Test INTR_MASK
        for (int i = 0; i < 32; i++) begin
            test_data = $urandom();
            write_and_check_reg('h804,test_data & 32'h7F); // write and check readback
        end

        // Test CTRL register
        for (int i = 0; i < 32; i++) begin
            test_data = $urandom();
            write_and_check_reg('h810,test_data & 32'h3); // write and check readback
        end

        // Test STATUS register
        assert_reg_value('h814, 0); // check STATUS is 0 after reset

        // Test MACLO
        for (int i = 0; i < 32; i++) begin
            test_data = $urandom();
            write_and_check_reg('h818,test_data); // write and check readback
        end

        // Test MACHI
        for (int i = 0; i < 32; i++) begin
            test_data = $urandom();
            write_and_check_reg('h81C,test_data & 64'hFFFF); // write and check readback
        end

        // Test TX_CTRL
        assert_reg_value('h820, 0);

        // Test MDIO CTRL
        for (int i = 0; i < 32; i++) begin
            test_data = $urandom();
            write_and_check_reg('h82C, test_data & 64'h7); // write and check readback
        end

    endtask
endclass

class test_fullness_flags_w_model extends test_base;
    packet_level_model model;
    function new(virtual ethernet_tb_if tb_if, scoreboard scb);
        super.new(tb_if, scb);
        this.model = new(scb);
    endfunction

    task get_and_check_status(output logic [31:0] status);
        info("Status check");
        read_status_reg(status);
        model.check_status(status);
    endtask

    task run();
        logic [31:0] read_status;
        reset_dut();
        enable_loopback();

        /*
        On each iteration:
        - check status
        - if no fullness warnings, 50% chance of a pop
        - if almost_full flags, 75% chance of a pop
        - if full flag, 90% chance of a pop
        - 90% chance of pushing a new packet - length is randomised
        This should give decent coverage across edge cases like empty pop, full push, full buffer, etc.
        */

        for (int i = 0; i < 50; i++) begin
            get_and_check_status(read_status);

            if (read_status[4:1] == 0) begin
                // no flags set, 50% chance of pop
                if ($urandom_range(0,1) == 0) begin
                    model.pop_packet();
                    write_reg('h828, 1); // pop DUT
                    @(posedge this.tb_if.clk_125M_i);
                end
            end else if (read_status[4] == 0 && read_status[2] == 0) begin
                // almost full but not full, 75% chance of pop
                if ($urandom_range(0,3) < 3) begin
                    model.pop_packet();
                    write_reg('h828, 1); // pop DUT
                    @(posedge this.tb_if.clk_125M_i);
                end
            end else begin
                // full buffer, should probably pop
                if ($urandom_range(0,9) < 9) begin
                    model.pop_packet();
                    write_reg('h828, 1); // pop DUT
                    @(posedge this.tb_if.clk_125M_i);
                end
            end

            get_and_check_status(read_status);

            if ($urandom_range(0,9) < 9) begin
                // 90% chance of pushing a new packet
                int pkt_len;
                if ($urandom_range(0,8) == 0) begin
                    pkt_len = $urandom_range(60,200); // small packet occasionally
                end else begin
                    pkt_len = $urandom_range(1200,1518); // large packet usually
                end
                model.new_packet(pkt_len);
                send_random_packet(48'hFF_FF_FF_FF_FF_FF, pkt_len);
            end
        end
    endtask
endclass


module ethernet_top_tb;
    //////////////////
    // Drive clocks //
    //////////////////

    // 125 MHz clock (period = 8ns)
    logic clk_125M_i;
    logic clk_125M_quad_i;
    initial begin
        clk_125M_i = 1;
        clk_125M_quad_i = 0;

        forever begin
            #2ns clk_125M_quad_i = 1;
            #2ns clk_125M_i = 0;
            #2ns clk_125M_quad_i = 0;
            #2ns clk_125M_i = 1;
        end
    end

    // 200 MHz clock (period = 5ns)
    logic clk_200M_i        = 0;
    always #2.5ns clk_200M_i = ~clk_200M_i;

    ////////////////////////
    // Create DUT + ports //
    ////////////////////////
    ethernet_tb_if tb_if();
    assign tb_if.clk_125M_i      = clk_125M_i;
    assign tb_if.clk_125M_quad_i = clk_125M_quad_i;
    assign tb_if.clk_200M_i      = clk_200M_i;

    ethernet_top #(
        .TARGET("SIM")
    ) dut (
        .clk_125M_i       (tb_if.clk_125M_i),
        .rst_ni           (tb_if.rst_ni),
        .clk_125M_quad_i  (tb_if.clk_125M_quad_i),
        .clk_200M_i       (tb_if.clk_200M_i),
        .mem_req_i        (tb_if.mem_req_i),
        .mem_rsp_o        (tb_if.mem_rsp_o),
        .phy_reset_no     (tb_if.phy_reset_no),
        .eth_rgmii_rx_i   (tb_if.eth_rgmii_rx_i),
        .eth_rgmii_tx_o   (tb_if.eth_rgmii_tx_o),
        .eth_rgmii_mdio_i (tb_if.eth_rgmii_mdio_i),
        .eth_rgmii_mdio_o (tb_if.eth_rgmii_mdio_o),
        .irq_o            (tb_if.irq_o)
    );

    assign tb_if.eth_rgmii_rx_i.clk = ~clk_125M_i;

    scoreboard scb;
    misc_test_cases misc_test_cases_inst;
    test_fullness_flags_w_model test_fullness_flags_inst;
    test_registers test_registers_inst;

    initial begin
        scb = new();

        misc_test_cases_inst = new(tb_if,scb);
        misc_test_cases_inst.reset_dut();
        misc_test_cases_inst.run();

        scb.new_test("Test registers");
        test_registers_inst = new(tb_if,scb);
        test_registers_inst.run();

        scb.new_test("Fullness flags vs. model test");
        test_fullness_flags_inst = new(tb_if,scb);
        test_fullness_flags_inst.run();

        scb.report_results();
        $finish;
    end

    initial begin
        $dumpvars(0);                // default "dump.vcd"
    end
endmodule
