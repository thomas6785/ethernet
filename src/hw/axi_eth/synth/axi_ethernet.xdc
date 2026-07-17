# For trial synthesis, don't worry about physical pin locations
set_property SEVERITY {Warning} [get_drc_checks UCIO-1]
set_property SEVERITY {Warning} [get_drc_checks NSTD-1]

# Create clocks
create_clock -period 8.000 -name clk_125M_i         [get_ports clk_125M_i]
create_clock -period 8.000 -name clk_125M_quad_i    [get_ports clk_125M_quad_i]
create_clock -period 5.000 -name clk_200M_i         [get_ports clk_200M_i]
