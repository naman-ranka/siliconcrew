module tb;

    // Inputs
    reg clk;
    reg rst;

    // Outputs
    wire [3:0] out;

    // Test status
    integer test_passed = 1;

    // Instantiate the Device Under Test (DUT)
    counter dut (
        .clk(clk),
        .rst(rst),
        .out(out)
    );

    // Clock generation
    initial begin
        clk = 0;
        forever #5 clk = ~clk; // 10ns period clock
    end

    // Test sequence
    initial begin
        $display("Starting test...");

        // 1. Test asynchronous reset
        $display("Step 1: Testing asynchronous reset...");
        rst = 1;
        #10; // Hold reset for some time
        #1; // Delay for checking
        if (out !== 4'b0000) begin
            $display("ERROR: Reset failed. Expected 0, got %d", out);
            test_passed = 0;
        end
        
        rst = 0;
        #1;
        if (out !== 4'b0000) begin
            $display("ERROR: Output changed on reset de-assertion. Expected 0, got %d", out);
            test_passed = 0;
        end
        
        // 2. Test normal counting sequence
        $display("Step 2: Testing normal counting...");
        for (integer i = 1; i <= 15; i = i + 1) begin
            @(posedge clk);
            #1; // Wait for output to settle
            if (out !== i) begin
                $display("ERROR: Count mismatch at time %0t. Expected %d, got %d", $time, i, out);
                test_passed = 0;
            end
        end

        // 3. Test rollover
        $display("Step 3: Testing rollover...");
        @(posedge clk); // Should go from 15 to 0
        #1;
        if (out !== 4'b0000) begin
            $display("ERROR: Rollover from 15 to 0 failed. Expected 0, got %d", out);
            test_passed = 0;
        end

        // 4. Test reset during operation
        $display("Step 4: Testing reset during operation...");
        // Count up to 5
        for (integer i = 1; i <= 5; i = i + 1) begin
            @(posedge clk);
        end
        #1;
        if (out !== 5) begin
             $display("ERROR: Pre-reset count mismatch. Expected 5, got %d", out);
             test_passed = 0;
        end

        // Assert reset
        rst = 1;
        #2; // Reset is asynchronous, should take effect immediately
        if (out !== 4'b0000) begin
            $display("ERROR: Mid-operation reset failed. Expected 0, got %d", out);
            test_passed = 0;
        end
        
        // De-assert reset and check if it starts from 0
        rst = 0;
        @(posedge clk);
        #1;
        if (out !== 4'b0001) begin
            $display("ERROR: Post-reset count failed. Expected 1, got %d", out);
            test_passed = 0;
        end
        
        // Final result
        #20;
        if (test_passed) begin
            $display("TEST PASSED");
        end else begin
            $display("TEST FAILED");
        end

        $finish;
    end

endmodule