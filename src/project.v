/*
 * Copyright (c) 2026 Roméo Estezet
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_romultra_top (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

  // All output pins must be assigned. If not used, assign to 0.
  // assign uo_out  = 0; // Unused outputs for now
  assign uio_out[7:4] = 0; // Unused IOs for now
  assign uio_oe  = 8'b00001011; // Set IO[0], IO[1], and IO[3] as outputs for SPI signals, the rest are inputs
  
  // List all unused inputs to prevent warnings
  wire _unused = &{ena, 1'b0};

  SPI_RAM u_spi_ram (
    .o_SPI_CS   (uio_out[0]),
    .o_SPI_MOSI (uio_out[1]),
    .i_SPI_MISO (uio_in[2]),
    .o_SPI_SCK  (uio_out[3]),

    .i_ready_to_execute (1),
    .i_address  (16'h0000), // Dummy address. TODO: Replace with actual wanted address
    .i_data_IN (8'h5B), // Dummy data. TODO: Replace with actual data
    .o_data_OUT (uo_out), // For now, the data retrived from the ram is wired to the 7-segment display. TODO: Rewire that to the actual target

    .i_command  (1), // TODO: Wire that to the command control
    .clk        (clk),
    .rst_n      (rst_n)
  );

endmodule

module SPI_RAM (
    // SPI Interface
    output reg o_SPI_CS, // Also used by the internal control to notify when spi action is done
    output reg o_SPI_MOSI,
    input wire i_SPI_MISO,
    output reg o_SPI_SCK,

    // data and address path
    input wire i_ready_to_execute,
    input wire [15:0] i_address,
    input wire [7:0] i_data_IN,
    output reg [7:0] o_data_OUT,

    input wire i_command, // RAM Command, 0 = READ, 1 = Write
    input wire clk,
    input wire rst_n
);

    reg [4:0] r_TX_Bit_Count;

    // The MSB (bit 8) of the command is always zero and is set at the same time as CS is pulled down as required by spi mode 0.
    // It is therefore not set here but in instead in the CS switching block, which lead the combined tx by one cycle, recreating the 8bit command properly.
    wire [6:0] o_command_byte;
    assign o_command_byte[6:0] = !i_command?  7'h03 : 7'h02; // READ Command or WRITE Command.
    wire [30:0] o_combined_TX  = !i_command? {o_command_byte, i_address, 8'h00} : {o_command_byte, i_address, i_data_IN};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            o_SPI_CS <= 1;
            o_SPI_SCK <= 0;
            r_TX_Bit_Count <= 5'b11110; // MSB first, so we start at bit 30
        end
        
        else begin case (o_SPI_CS)
                1'b1: if (i_ready_to_execute) begin
                    // On SPI Mode 0, the first clock edge is positive and therefore data sampling.
                    o_SPI_MOSI <= 0; 
                    o_SPI_CS <= 0; // The first bit shift must therefore be set at the same time as CS is pulled down
                    r_TX_Bit_Count <= 5'b11110;
                end
                1'b0: begin
                    o_SPI_SCK <= ~o_SPI_SCK;
                    if (o_SPI_SCK) begin //  Shifting data, execute on SCK negedge
                        if (r_TX_Bit_Count > 0) begin
                            o_SPI_MOSI <= o_combined_TX[r_TX_Bit_Count];
                            r_TX_Bit_Count <= r_TX_Bit_Count-1;
                        end else begin
                            o_SPI_CS <= 1;
                        end
                    end else if (!i_command && r_TX_Bit_Count <= 7) begin // Read
                        // Receive data, data sampling, so execute on SCK posedge
                        o_data_OUT[r_TX_Bit_Count[2:0]] <= i_SPI_MISO;
                    end 
                end
            endcase
        end
    end

endmodule