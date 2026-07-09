# Synchronous FIFO

A single-clock, parameterized (WIDTH x DEPTH) FIFO with binary read/write
pointers and an extra MSB to disambiguate full from empty. Includes a
self-checking testbench that bursts writes, reads them back in order, and
asserts empty at the boundaries.
