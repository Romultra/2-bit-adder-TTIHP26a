# SPDX-FileCopyrightText: © 2026 Roméo Estezet
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, FallingEdge


def is_gl(dut):
    """Check if running gate-level simulation (standalone SPI_RAM unavailable)."""
    try:
        _ = dut.spi_cs
        return False
    except AttributeError:
        return True


async def reset_dut(dut):
    """Apply reset and initialize all inputs."""
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    if not is_gl(dut):
        dut.spi_ready.value = 0
        dut.spi_address.value = 0
        dut.spi_data_in.value = 0
        dut.spi_command.value = 0
        dut.spi_miso.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def capture_spi_mosi(result, sck, mosi, num_bits):
    """Capture MOSI bits on rising SCK edges into result list."""
    for _ in range(num_bits):
        await RisingEdge(sck)
        result.append(int(mosi.value))


def bits_to_bytes(bits):
    """Convert a list of bits (MSB first) to a list of bytes."""
    result = []
    for i in range(0, len(bits), 8):
        byte_val = 0
        for j in range(8):
            if i + j < len(bits):
                byte_val = (byte_val << 1) | bits[i + j]
        result.append(byte_val)
    return result


@cocotb.test()
async def test_reset_state(dut):
    """Verify SPI signals are in correct idle state during reset."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    dut.rst_n.value = 0
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    if not is_gl(dut):
        dut.spi_ready.value = 0
        dut.spi_address.value = 0
        dut.spi_data_in.value = 0
        dut.spi_command.value = 0
        dut.spi_miso.value = 0
    await ClockCycles(dut.clk, 5)

    if not is_gl(dut):
        # Standalone SPI_RAM: CS high, SCK low, MOSI high
        assert dut.spi_cs.value == 1, "CS should be high (deasserted) during reset"
        assert dut.spi_sck.value == 0, "SCK should be low during reset"
        assert dut.spi_mosi.value == 1, "MOSI should default high during reset"

    # Top module: check via uio_out
    uio = int(dut.uio_out.value)
    assert (uio & 0x01) == 1, "Top CS (uio_out[0]) should be high during reset"
    assert (uio & 0x08) == 0, "Top SCK (uio_out[3]) should be low during reset"


@cocotb.test()
async def test_io_directions(dut):
    """Verify IO enable pins are configured correctly for SPI."""
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # uio_oe = 0b00001011: CS(0)=out, MOSI(1)=out, MISO(2)=in, SCK(3)=out
    expected = 0x0B
    actual = int(dut.uio_oe.value)
    assert actual == expected, f"Expected uio_oe=0x{expected:02X}, got 0x{actual:02X}"


@cocotb.test()
async def test_no_transaction_without_ready(dut):
    """Verify SPI stays idle when ready signal is deasserted."""
    if is_gl(dut):
        dut._log.info("Skipping - standalone SPI_RAM not available in GL test")
        return

    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    dut.spi_ready.value = 0
    dut.spi_command.value = 1
    dut.spi_address.value = 0x1234
    dut.spi_data_in.value = 0xAB
    await ClockCycles(dut.clk, 20)

    assert dut.spi_cs.value == 1, "CS should stay high when ready is deasserted"
    assert dut.spi_sck.value == 0, "SCK should stay low when idle"


@cocotb.test()
async def test_write_command(dut):
    """Verify WRITE transaction sends correct SPI frame (0x02 + addr + data)."""
    if is_gl(dut):
        dut._log.info("Skipping - standalone SPI_RAM not available in GL test")
        return

    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    address = 0x1234
    data = 0xAB

    dut.spi_command.value = 1  # WRITE
    dut.spi_address.value = address
    dut.spi_data_in.value = data

    bits = []
    cocotb.start_soon(capture_spi_mosi(bits, dut.spi_sck, dut.spi_mosi, 32))
    dut.spi_ready.value = 1

    await RisingEdge(dut.spi_cs)
    tx_bytes = bits_to_bytes(bits)

    dut._log.info(f"WRITE MOSI: {[f'0x{b:02X}' for b in tx_bytes]}")

    assert tx_bytes[0] == 0x02, f"Expected WRITE cmd 0x02, got 0x{tx_bytes[0]:02X}"
    assert tx_bytes[1] == 0x12, f"Expected addr high 0x12, got 0x{tx_bytes[1]:02X}"
    assert tx_bytes[2] == 0x34, f"Expected addr low 0x34, got 0x{tx_bytes[2]:02X}"
    assert tx_bytes[3] == 0xAB, f"Expected data 0xAB, got 0x{tx_bytes[3]:02X}"


@cocotb.test()
async def test_read_command(dut):
    """Verify READ transaction sends correct command and captures MISO data."""
    if is_gl(dut):
        dut._log.info("Skipping - standalone SPI_RAM not available in GL test")
        return

    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    address = 0x5678
    expected_data = 0xA5

    dut.spi_command.value = 0  # READ
    dut.spi_address.value = address
    dut.spi_data_in.value = 0

    async def spi_slave_respond():
        """Drive MISO with response data during READ data phase."""
        await FallingEdge(dut.spi_cs)
        # Skip command + address phase (24 rising SCK edges)
        for _ in range(24):
            await RisingEdge(dut.spi_sck)
        # Drive response data MSB first on falling SCK edges
        for i in range(8):
            await FallingEdge(dut.spi_sck)
            dut.spi_miso.value = (expected_data >> (7 - i)) & 1

    cocotb.start_soon(spi_slave_respond())
    bits = []
    cocotb.start_soon(capture_spi_mosi(bits, dut.spi_sck, dut.spi_mosi, 32))
    dut.spi_ready.value = 1

    await RisingEdge(dut.spi_cs)
    tx_bytes = bits_to_bytes(bits)

    dut._log.info(f"READ MOSI: {[f'0x{b:02X}' for b in tx_bytes]}")
    assert tx_bytes[0] == 0x03, f"Expected READ cmd 0x03, got 0x{tx_bytes[0]:02X}"
    assert tx_bytes[1] == 0x56, f"Expected addr high 0x56, got 0x{tx_bytes[1]:02X}"
    assert tx_bytes[2] == 0x78, f"Expected addr low 0x78, got 0x{tx_bytes[2]:02X}"

    received = int(dut.spi_data_out.value)
    dut._log.info(f"READ data: expected=0x{expected_data:02X}, got=0x{received:02X}")
    assert received == expected_data, \
        f"Data mismatch: expected 0x{expected_data:02X}, got 0x{received:02X}"


@cocotb.test()
async def test_top_module_write(dut):
    """Verify top module sends correct WRITE SPI frame (addr=0x0000, data=0x5B)."""
    if is_gl(dut):
        dut._log.info("Skipping - internal hierarchy not available in GL test")
        return

    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    # Access internal SPI signals from top module instance
    spi_sck = dut.user_project.u_spi_ram.o_SPI_SCK
    spi_mosi = dut.user_project.u_spi_ram.o_SPI_MOSI
    spi_cs = dut.user_project.u_spi_ram.o_SPI_CS

    # Top module auto-starts (ready=1, command=1/WRITE, addr=0x0000, data=0x5B)
    bits = []
    cocotb.start_soon(capture_spi_mosi(bits, spi_sck, spi_mosi, 32))

    await RisingEdge(spi_cs)
    tx_bytes = bits_to_bytes(bits)

    dut._log.info(f"Top module MOSI: {[f'0x{b:02X}' for b in tx_bytes]}")

    assert tx_bytes[0] == 0x02, f"Expected WRITE cmd 0x02, got 0x{tx_bytes[0]:02X}"
    assert tx_bytes[1] == 0x00, f"Expected addr high 0x00, got 0x{tx_bytes[1]:02X}"
    assert tx_bytes[2] == 0x00, f"Expected addr low 0x00, got 0x{tx_bytes[2]:02X}"
    assert tx_bytes[3] == 0x5B, f"Expected data 0x5B, got 0x{tx_bytes[3]:02X}"


@cocotb.test()
async def test_transaction_restart(dut):
    """Verify a new transaction starts automatically after completion."""
    if is_gl(dut):
        dut._log.info("Skipping - standalone SPI_RAM not available in GL test")
        return

    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    dut.spi_command.value = 1
    dut.spi_address.value = 0
    dut.spi_data_in.value = 0
    dut.spi_ready.value = 1

    # First transaction
    await FallingEdge(dut.spi_cs)
    dut._log.info("First transaction started")
    await RisingEdge(dut.spi_cs)
    dut._log.info("First transaction complete")

    # Second transaction should start since ready is still high
    await FallingEdge(dut.spi_cs)
    dut._log.info("Second transaction started - restart verified")
    assert dut.spi_cs.value == 0


@cocotb.test()
async def test_read_data_patterns(dut):
    """Test READ with multiple data patterns to verify all bits are captured."""
    if is_gl(dut):
        dut._log.info("Skipping - standalone SPI_RAM not available in GL test")
        return

    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    test_values = [0x00, 0xFF, 0xA5, 0x5A, 0x0F, 0xF0]

    for expected_data in test_values:
        await reset_dut(dut)
        dut.spi_command.value = 0  # READ
        dut.spi_address.value = 0x0000
        dut.spi_data_in.value = 0

        async def spi_slave_respond(data):
            await FallingEdge(dut.spi_cs)
            for _ in range(24):
                await RisingEdge(dut.spi_sck)
            for i in range(8):
                await FallingEdge(dut.spi_sck)
                dut.spi_miso.value = (data >> (7 - i)) & 1

        cocotb.start_soon(spi_slave_respond(expected_data))
        dut.spi_ready.value = 1

        await RisingEdge(dut.spi_cs)
        received = int(dut.spi_data_out.value)
        dut._log.info(f"Pattern 0x{expected_data:02X}: got 0x{received:02X}")
        assert received == expected_data, \
            f"Pattern 0x{expected_data:02X} failed: got 0x{received:02X}"

    dut._log.info("All READ data patterns passed")
