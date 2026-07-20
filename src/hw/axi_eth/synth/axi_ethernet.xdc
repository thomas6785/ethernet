# For trial synthesis, don't worry about physical pin locations
set_property SEVERITY {Warning} [get_drc_checks UCIO-1]
set_property SEVERITY {Warning} [get_drc_checks NSTD-1]

## Create clocks

# 200 MHz oscillator (5 ns period)
create_clock -name clk_200M_i -period 5.0 [get_ports clk_200M_i]

# eth_rgmii_rx_clk: independent 125 MHz clock with unknown phase
create_clock -name eth_rgmii_rx_clk -period 8.0 [get_ports eth_rgmii_rx_clk]

# The RX clock (and any clocks derived from it) are asynchronous to all other clocks
set_clock_groups -asynchronous -group [get_clocks eth_rgmii_rx_clk -include_generated_clocks];
