// Copyright lowRISC contributors (COSMIC project).
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

/*
Module: random_access_fifo
Author: Thomas O'Dea <thomas.odea@lowrisc.org>

-------------------------------------------------------------------------------
    DESCRIPTION
-------------------------------------------------------------------------------
FIFO with typical push/pop interface, but also a random-access read interface.
You may only pop the oldest entry but can read any entry.
Read 'addresses' are indices relative to the head of the FIFO i.e. reading 0
will read the oldest entry, reading 1 will read the second-oldest entry, etc.

The random-access interface behaves according to mem_if_utils_pkg.

Includes its own memory for the FIFO storage as a packed array of type dtype_t.
Therefore it MAY not be suitable for large FIFOs if your synthesis tool cannot
infer RAM from the packet array (however, most synthesis tools can do this).

DrawIO instance template:
%3CmxGraphModel%3E%3Croot%3E%3CmxCell%20id%3D%220%22%2F%3E%3CmxCell%20id%3D%221%22%20parent%3D%220%22%2F%3E%3CmxCell%20id%3D%222%22%20value%3D%22%22%20style%3D%22group%3BlabelPosition%3Dcenter%3BverticalLabelPosition%3Dtop%3Balign%3Dcenter%3BverticalAlign%3Dbottom%3BfontStyle%3D1%3BfontFamily%3DCourier%20New%3B%22%20vertex%3D%221%22%20connectable%3D%220%22%20parent%3D%221%22%3E%3CmxGeometry%20x%3D%22380%22%20y%3D%22200%22%20width%3D%22300%22%20height%3D%22310%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3CmxCell%20id%3D%223%22%20value%3D%22%26lt%3Bspan%20style%3D%26quot%3Bfont-weight%3A%20normal%3B%26quot%3B%26gt%3BRANDOM-ACCESS%26lt%3Bbr%26gt%3BFIFO%26lt%3B%2Fspan%26gt%3B%22%20style%3D%22rounded%3D0%3BwhiteSpace%3Dwrap%3Bhtml%3D1%3BfontFamily%3DCourier%20New%3BverticalAlign%3Dtop%3BfontStyle%3D1%22%20vertex%3D%221%22%20parent%3D%222%22%3E%3CmxGeometry%20width%3D%22300%22%20height%3D%22310%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3CmxCell%20id%3D%224%22%20value%3D%22%22%20style%3D%22shape%3Dcylinder3%3BwhiteSpace%3Dwrap%3Bhtml%3D1%3BboundedLbl%3D1%3BbackgroundOutline%3D1%3Bsize%3D15%3BfontFamily%3DCourier%20New%3B%22%20vertex%3D%221%22%20parent%3D%222%22%3E%3CmxGeometry%20x%3D%22120%22%20y%3D%22111%22%20width%3D%2260%22%20height%3D%2280%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3CmxCell%20id%3D%225%22%20value%3D%22wr_push_i%22%20style%3D%22text%3Bhtml%3D1%3Balign%3Dleft%3BverticalAlign%3Dmiddle%3BwhiteSpace%3Dwrap%3Brounded%3D0%3BfontFamily%3DCourier%20New%3B%22%20vertex%3D%221%22%20parent%3D%222%22%3E%3CmxGeometry%20width%3D%2260%22%20height%3D%2230%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3CmxCell%20id%3D%226%22%20value%3D%22wr_data_i%22%20style%3D%22text%3Bhtml%3D1%3Balign%3Dleft%3BverticalAlign%3Dmiddle%3BwhiteSpace%3Dwrap%3Brounded%3D0%3BfontFamily%3DCourier%20New%3B%22%20vertex%3D%221%22%20parent%3D%222%22%3E%3CmxGeometry%20y%3D%2230%22%20width%3D%2260%22%20height%3D%2230%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3CmxCell%20id%3D%227%22%20value%3D%22full_o%22%20style%3D%22text%3Bhtml%3D1%3Balign%3Dleft%3BverticalAlign%3Dmiddle%3BwhiteSpace%3Dwrap%3Brounded%3D0%3BfontFamily%3DCourier%20New%3B%22%20vertex%3D%221%22%20parent%3D%222%22%3E%3CmxGeometry%20y%3D%22121%22%20width%3D%2260%22%20height%3D%2230%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3CmxCell%20id%3D%228%22%20value%3D%22%26lt%3Bdiv%26gt%3B%26lt%3Bspan%20style%3D%26quot%3Bbackground-color%3A%20transparent%3B%20color%3A%20light-dark(rgb(0%2C%200%2C%200)%2C%20rgb(255%2C%20255%2C%20255))%3B%26quot%3B%26gt%3Balmost_full_o%26lt%3B%2Fspan%26gt%3B%26lt%3B%2Fdiv%26gt%3B%22%20style%3D%22text%3Bhtml%3D1%3Balign%3Dleft%3BverticalAlign%3Dmiddle%3BwhiteSpace%3Dwrap%3Brounded%3D0%3BfontFamily%3DCourier%20New%3B%22%20vertex%3D%221%22%20parent%3D%222%22%3E%3CmxGeometry%20y%3D%22151%22%20width%3D%2260%22%20height%3D%2230%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3CmxCell%20id%3D%229%22%20value%3D%22empty_o%22%20style%3D%22text%3Bhtml%3D1%3Balign%3Dleft%3BverticalAlign%3Dmiddle%3BwhiteSpace%3Dwrap%3Brounded%3D0%3BfontFamily%3DCourier%20New%3B%22%20vertex%3D%221%22%20parent%3D%222%22%3E%3CmxGeometry%20y%3D%22181%22%20width%3D%2260%22%20height%3D%2230%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3CmxCell%20id%3D%2210%22%20value%3D%22rd_pop_i%22%20style%3D%22text%3Bhtml%3D1%3Balign%3Dright%3BverticalAlign%3Dmiddle%3BwhiteSpace%3Dwrap%3Brounded%3D0%3BfontFamily%3DCourier%20New%3B%22%20vertex%3D%221%22%20parent%3D%222%22%3E%3CmxGeometry%20x%3D%22240%22%20width%3D%2260%22%20height%3D%2230%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3CmxCell%20id%3D%2211%22%20value%3D%22rd_head_data_o%22%20style%3D%22text%3Bhtml%3D1%3Balign%3Dright%3BverticalAlign%3Dmiddle%3BwhiteSpace%3Dwrap%3Brounded%3D0%3BfontFamily%3DCourier%20New%3B%22%20vertex%3D%221%22%20parent%3D%222%22%3E%3CmxGeometry%20x%3D%22240%22%20y%3D%2230%22%20width%3D%2260%22%20height%3D%2230%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3CmxCell%20id%3D%2212%22%20value%3D%22rd_req_i%22%20style%3D%22text%3Bhtml%3D1%3Balign%3Dright%3BverticalAlign%3Dmiddle%3BwhiteSpace%3Dwrap%3Brounded%3D0%3BfontFamily%3DCourier%20New%3B%22%20vertex%3D%221%22%20parent%3D%222%22%3E%3CmxGeometry%20x%3D%22240%22%20y%3D%2291%22%20width%3D%2260%22%20height%3D%2230%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3CmxCell%20id%3D%2213%22%20value%3D%22rd_gnt_o%22%20style%3D%22text%3Bhtml%3D1%3Balign%3Dright%3BverticalAlign%3Dmiddle%3BwhiteSpace%3Dwrap%3Brounded%3D0%3BfontFamily%3DCourier%20New%3B%22%20vertex%3D%221%22%20parent%3D%222%22%3E%3CmxGeometry%20x%3D%22240%22%20y%3D%22121%22%20width%3D%2260%22%20height%3D%2230%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3CmxCell%20id%3D%2214%22%20value%3D%22rd_addr_i%22%20style%3D%22text%3Bhtml%3D1%3Balign%3Dright%3BverticalAlign%3Dmiddle%3BwhiteSpace%3Dwrap%3Brounded%3D0%3BfontFamily%3DCourier%20New%3B%22%20vertex%3D%221%22%20parent%3D%222%22%3E%3CmxGeometry%20x%3D%22240%22%20y%3D%22151%22%20width%3D%2260%22%20height%3D%2230%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3CmxCell%20id%3D%2215%22%20value%3D%22rd_data_o%22%20style%3D%22text%3Bhtml%3D1%3Balign%3Dright%3BverticalAlign%3Dmiddle%3BwhiteSpace%3Dwrap%3Brounded%3D0%3BfontFamily%3DCourier%20New%3B%22%20vertex%3D%221%22%20parent%3D%222%22%3E%3CmxGeometry%20x%3D%22240%22%20y%3D%22181%22%20width%3D%2260%22%20height%3D%2230%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3CmxCell%20id%3D%2216%22%20value%3D%22rd_err_o%22%20style%3D%22text%3Bhtml%3D1%3Balign%3Dright%3BverticalAlign%3Dmiddle%3BwhiteSpace%3Dwrap%3Brounded%3D0%3BfontFamily%3DCourier%20New%3B%22%20vertex%3D%221%22%20parent%3D%222%22%3E%3CmxGeometry%20x%3D%22240%22%20y%3D%22211%22%20width%3D%2260%22%20height%3D%2230%22%20as%3D%22geometry%22%2F%3E%3C%2FmxCell%3E%3C%2Froot%3E%3C%2FmxGraphModel%3E

-------------------------------------------------------------------------------
    TESTS
-------------------------------------------------------------------------------
There are no dedicated tests for this module yet.
TODO write tests and assertions for this module.

-------------------------------------------------------------------------------
    INSTANTIATION TEMPLATE
-------------------------------------------------------------------------------
random_access_fifo #(
    .dtype_t                (),
    .AlmostFullThreshold    (),
    .Depth                  ()
) description_table (
    .clk_i,
    .rst_ni,
    .clr_i          (1'b0), // optional

    // Write IF for pushing onto queue
    .wr_push_i      (),
    .wr_data_i      (),

    // Read IF for popping off the queue
    .rd_pop_i       (),
    .rd_head_data_o (),

    // Random-access read interface
    .rd_req_i       (),
    .rd_gnt_o       (),
    .rd_addr_i      (),
    .rd_data_o      (),
    .rd_err_o       (),

    // FIFO status
    .full_o         (),
    .almost_full_o  (),
    .n_buffered_o   (),
    .empty_o        ()
);
*/

`include "prim_assert.sv"

module random_access_fifo #(
    parameter type dtype_t             = logic,
    parameter int unsigned AlmostFullThreshold  = 2, // number of free entries at which the almost_full_o flag is raised (must be less than Depth)
    parameter int unsigned Depth       = 8, // maximum number of entries that can be buffered in the FIFO (must be a power of 2)
    parameter bit NeverClears          = 1'b0, // if set, the clr_i port is never high
    parameter bit Secure               = 1'b0, // use prim count for pointers
    // derived parameter
    localparam int          DepthW     = prim_util_pkg::vbits(Depth+1),
    localparam int          AddrW      = prim_util_pkg::vbits(Depth)
) (
    input                       clk_i,
    input                       rst_ni,
    input                       clr_i, // synchronous clear / flush port

    // FIFO write interface
    input  logic                wr_push_i,      // when asserted, push onto the FIFO queue
    input  dtype_t              wr_data_i,      // data to push onto FIFO

    // FIFO read interface
    input  logic                rd_pop_i,       // when asserted, pop the head of the FIFO
    output dtype_t              rd_head_data_o, // data at the head of the FIFO (i.e. the next to be popped)

    // Random-access read interface
    input  logic                rd_req_i,
    output logic                rd_gnt_o,
    input  logic [AddrW-1:0]    rd_addr_i,      // address for random access read (relative to the head of the FIFO)
    output dtype_t              rd_data_o,
    output logic                rd_err_o,       // indicates an attempt to read from bad address (i.e. beyond the number of buffered entries)

    // Statuses
    output                      full_o,
    output                      almost_full_o,
    output         [DepthW-1:0] n_buffered_o,   // number of entries currently buffered in the FIFO
    output                      empty_o
);
    // Normal FIFO construction
    localparam int unsigned PtrW = prim_util_pkg::vbits(Depth);

    dtype_t [Depth-1:0] fifo_storage;         // create main FIFO storage
    logic [PtrW-1:0]    fifo_wptr, fifo_rptr; // create read and write pointers
    logic               fifo_incr_wptr, fifo_incr_rptr; // whether to increment each pointer this cycle

    ////////////////////////
    // Reset synchroniser //
    ////////////////////////
    logic under_rst;
    always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            under_rst <= 1'b1;
        end else if (under_rst) begin
            under_rst <= ~under_rst;
        end
    end

    ///////////////////
    // Pointer logic //
    ///////////////////

    // prim_fifo_sync_cnt provides logic for incrementing read/write counters and detecting overflows
    // it does NOT provide an actual FIFO (memory), only the pointer logic and conflict detection

    logic [DepthW-1:0] n_buffered;
    assign n_buffered_o = n_buffered;

    prim_fifo_sync_cnt #(
        .Depth(Depth),
        .Secure(Secure),
        .NeverClears(NeverClears)
    ) u_fifo_cnt (
        .clk_i,
        .rst_ni,
        .clr_i,
        .incr_wptr_i(fifo_incr_wptr),
        .incr_rptr_i(fifo_incr_rptr),
        .wptr_o(fifo_wptr),
        .rptr_o(fifo_rptr),
        .full_o,
        .empty_o,
        .depth_o(n_buffered),
        .err_o() // not used here
    );
    // "full" and "not ready for write" are two different concepts.
    // The latter can be '0' when under reset, while the former is an indication that no more entries can be written.
    assign fifo_incr_wptr = wr_push_i & ~full_o  & ~under_rst;
    assign fifo_incr_rptr = rd_pop_i  & ~empty_o & ~under_rst;

    assign almost_full_o = (n_buffered >= (DepthW)'(Depth - AlmostFullThreshold));
    //                                             |--- this is a constant,  ---|
    //                                             |--- so no arithmetic will---|
    //                                             |--- be synthesised       ---|

    //////////////////////
    // FIFO write logic //
    //////////////////////
    always_ff @(posedge clk_i) begin
        if (fifo_incr_wptr) begin
            fifo_storage[fifo_wptr] <= wr_data_i;
        end
    end

    /////////////////////
    // FIFO read logic //
    /////////////////////
    assign rd_head_data_o = fifo_storage[fifo_rptr];

    /////////////////////////
    // Random-access reads //
    /////////////////////////
    assign rd_gnt_o = rd_req_i; // grant immediately (protocol expects data on the following cycle as below)
    always_ff @ (posedge clk_i or negedge rst_ni) begin
        if (~rst_ni) begin
            rd_data_o   <= '0;
            rd_err_o    <= '0;
        end else begin
            if (rd_req_i) begin
                rd_err_o  <= (DepthW)'(rd_addr_i) >= n_buffered; // error if attempting to read beyond the number of buffered data
                rd_data_o <= fifo_storage[fifo_rptr + rd_addr_i];  // return the data at the requested address (which is relative to the queue head)
             end
        end
    end

    ////////////////
    // Assertions //
    ////////////////
    `ASSERT(depthShallNotExceedParamDepth, !empty_o |-> n_buffered <= DepthW'(Depth))

    if (NeverClears) begin : gen_never_clears
        `ASSERT(NeverClears_A, !clr_i)
    end

    //////////////////////////////////
    // Assertions outputs are known //
    //////////////////////////////////

    `ASSERT_KNOWN_IF(RdRandDataKnown_O,  rd_data_o, rd_gnt_o) // it's fine if read data is undefined when rd_gnt_o is deasserted, so we use a condition for the assertion
    `ASSERT_KNOWN_IF(RdHeadDataKnown_O,  rd_head_data_o, ~empty_o) // head data should always be defined unless the FIFO is empty

    `ASSERT_KNOWN(RdGntKnown_A,      rd_gnt_o       )
    `ASSERT_KNOWN(RdErrKnown_A,      rd_err_o       )
    `ASSERT_KNOWN(FullKnown_A,       full_o         )
    `ASSERT_KNOWN(AlmostFullKnown_A, almost_full_o  )
    `ASSERT_KNOWN(EmptyKnown,        empty_o        )

    // TODO add assertion that pop will decrease depth
    // and push will increase depth
endmodule
