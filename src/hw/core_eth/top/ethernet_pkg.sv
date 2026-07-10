// Copyright lowRISC contributors (COSMIC project).
// Licensed under the Apache License, Version 2.0, see LICENSE for details.
// SPDX-License-Identifier: Apache-2.0

/*
Module: ethernet_pkg
Author: Thomas O'Dea <thomas.odea@lowrisc.org>

-------------------------------------------------------------------------------
    DESCRIPTION
-------------------------------------------------------------------------------
Package of types and constants for the Ethernet IP.

-------------------------------------------------------------------------------
    TESTS
-------------------------------------------------------------------------------
N/A

-------------------------------------------------------------------------------
    INSTANTIATION TEMPLATE
-------------------------------------------------------------------------------
N/A

*/

package ethernet_pkg;
    // Error responses for memory interface
    localparam    BAD_ADDRESS_ERROR = 32'hDEADBEEF;
    localparam    WRITE_TO_RO_ERROR = 32'hBAD_CAFE;

    // Constants
    localparam int MAX_ETH_PKT_LEN = 1522; // maximum Ethernet packet length in bytes
    typedef logic [$clog2(MAX_ETH_PKT_LEN)-1:0] pkt_len_t;

endpackage
