set _sc_clk_ports [get_ports {clk}]
if {[llength $_sc_clk_ports] > 0} {
  create_clock -period 20.0 $_sc_clk_ports
}
