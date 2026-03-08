`default_nettype none
`timescale 1ns / 1ps

/* This testbench instantiates the top module and a standalone SPI_RAM
   for direct testing with controllable inputs.
*/
module tb ();

  // Dump the signals to a FST file. You can view it with gtkwave or surfer.
  initial begin
    $dumpfile("tb.fst");
    $dumpvars(0, tb);
    #1;
  end

  // Wire up the inputs and outputs:
  reg clk;
  reg rst_n;
  reg ena;
  reg [7:0] ui_in;
  reg [7:0] uio_in;
  wire [7:0] uo_out;
  wire [7:0] uio_out;
  wire [7:0] uio_oe;

  tt_um_romultra_top user_project (
      .ui_in  (ui_in),    // Dedicated inputs
      .uo_out (uo_out),   // Dedicated outputs
      .uio_in (uio_in),   // IOs: Input path
      .uio_out(uio_out),  // IOs: Output path
      .uio_oe (uio_oe),   // IOs: Enable path (active high: 0=input, 1=output)
      .ena    (ena),      // enable - goes high when design is selected
      .clk    (clk),      // clock
      .rst_n  (rst_n)     // not reset
  );

  // Standalone SPI_RAM instance with controllable inputs for direct testing
  // Not available in gate-level simulation (module is synthesized away)
`ifndef GL_TEST
  reg        spi_ready;
  reg [15:0] spi_address;
  reg [7:0]  spi_data_in;
  reg        spi_command;
  wire       spi_cs;
  wire       spi_mosi;
  reg        spi_miso;
  wire       spi_sck;
  wire [7:0] spi_data_out;

  SPI_RAM spi_ram_test (
      .o_SPI_CS   (spi_cs),
      .o_SPI_MOSI (spi_mosi),
      .i_SPI_MISO (spi_miso),
      .o_SPI_SCK  (spi_sck),
      .i_ready_to_execute (spi_ready),
      .i_address  (spi_address),
      .i_data_IN  (spi_data_in),
      .o_data_OUT (spi_data_out),
      .i_command  (spi_command),
      .clk        (clk),
      .rst_n      (rst_n)
  );
`endif

endmodule
