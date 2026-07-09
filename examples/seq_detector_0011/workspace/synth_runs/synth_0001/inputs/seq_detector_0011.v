// Overlapping serial sequence detector for the pattern 0-0-1-1 (MSB-first in
// time). A 4-bit shift window holds the last four serial bits; `detected`
// asserts for the cycle whose window equals 0011. Async active-low reset.
module seq_detector_0011 (
    input  wire clk,
    input  wire rst_n,
    input  wire din,
    output wire detected
);
    reg [3:0] window;   // window[3] = oldest bit, window[0] = newest bit

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            window <= 4'b0000;
        else
            window <= {window[2:0], din};
    end

    // Bits arrive 0,0,1,1 in time → window becomes {0,0,1,1} = 4'b0011.
    assign detected = (window == 4'b0011);
endmodule
