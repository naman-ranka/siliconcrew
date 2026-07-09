`timescale 1ns/1ps
// Self-checking testbench for the AES inverse S-box.
//
// Drives all 256 possible input bytes and checks the combinational output y[x]
// against the FIPS-197 inverse S-box (the golden table below is the standard
// AES^-1 substitution, knowledge external to the DUT). It also verifies the
// registered copy cy, which the design latches one clock after the input.
// Emits "TEST PASSED" only when all 256 substitutions (and their registered
// copies) match.
module aes_invsbox_tb;
    reg        clk = 1'b0;
    reg  [7:0] x = 8'd0;
    wire [7:0] y;
    wire [7:0] cy;

    integer errors = 0;
    integer checks = 0;
    integer i;
    reg [7:0] golden [0:255];
    reg [7:0] xq;              // shadow of x, delayed one clock to match cy

    sbox_aesinv dut (.clk(clk), .x(x), .y(y), .cy(cy));

    always #5 clk = ~clk;

    initial begin
        $dumpfile("aes_invsbox_tb.vcd");
        $dumpvars(0, aes_invsbox_tb);

        // FIPS-197 inverse S-box (256 bytes, row-major from index 0x00).
        golden[  0]=8'h52; golden[  1]=8'h09; golden[  2]=8'h6a; golden[  3]=8'hd5;
        golden[  4]=8'h30; golden[  5]=8'h36; golden[  6]=8'ha5; golden[  7]=8'h38;
        golden[  8]=8'hbf; golden[  9]=8'h40; golden[ 10]=8'ha3; golden[ 11]=8'h9e;
        golden[ 12]=8'h81; golden[ 13]=8'hf3; golden[ 14]=8'hd7; golden[ 15]=8'hfb;
        golden[ 16]=8'h7c; golden[ 17]=8'he3; golden[ 18]=8'h39; golden[ 19]=8'h82;
        golden[ 20]=8'h9b; golden[ 21]=8'h2f; golden[ 22]=8'hff; golden[ 23]=8'h87;
        golden[ 24]=8'h34; golden[ 25]=8'h8e; golden[ 26]=8'h43; golden[ 27]=8'h44;
        golden[ 28]=8'hc4; golden[ 29]=8'hde; golden[ 30]=8'he9; golden[ 31]=8'hcb;
        golden[ 32]=8'h54; golden[ 33]=8'h7b; golden[ 34]=8'h94; golden[ 35]=8'h32;
        golden[ 36]=8'ha6; golden[ 37]=8'hc2; golden[ 38]=8'h23; golden[ 39]=8'h3d;
        golden[ 40]=8'hee; golden[ 41]=8'h4c; golden[ 42]=8'h95; golden[ 43]=8'h0b;
        golden[ 44]=8'h42; golden[ 45]=8'hfa; golden[ 46]=8'hc3; golden[ 47]=8'h4e;
        golden[ 48]=8'h08; golden[ 49]=8'h2e; golden[ 50]=8'ha1; golden[ 51]=8'h66;
        golden[ 52]=8'h28; golden[ 53]=8'hd9; golden[ 54]=8'h24; golden[ 55]=8'hb2;
        golden[ 56]=8'h76; golden[ 57]=8'h5b; golden[ 58]=8'ha2; golden[ 59]=8'h49;
        golden[ 60]=8'h6d; golden[ 61]=8'h8b; golden[ 62]=8'hd1; golden[ 63]=8'h25;
        golden[ 64]=8'h72; golden[ 65]=8'hf8; golden[ 66]=8'hf6; golden[ 67]=8'h64;
        golden[ 68]=8'h86; golden[ 69]=8'h68; golden[ 70]=8'h98; golden[ 71]=8'h16;
        golden[ 72]=8'hd4; golden[ 73]=8'ha4; golden[ 74]=8'h5c; golden[ 75]=8'hcc;
        golden[ 76]=8'h5d; golden[ 77]=8'h65; golden[ 78]=8'hb6; golden[ 79]=8'h92;
        golden[ 80]=8'h6c; golden[ 81]=8'h70; golden[ 82]=8'h48; golden[ 83]=8'h50;
        golden[ 84]=8'hfd; golden[ 85]=8'hed; golden[ 86]=8'hb9; golden[ 87]=8'hda;
        golden[ 88]=8'h5e; golden[ 89]=8'h15; golden[ 90]=8'h46; golden[ 91]=8'h57;
        golden[ 92]=8'ha7; golden[ 93]=8'h8d; golden[ 94]=8'h9d; golden[ 95]=8'h84;
        golden[ 96]=8'h90; golden[ 97]=8'hd8; golden[ 98]=8'hab; golden[ 99]=8'h00;
        golden[100]=8'h8c; golden[101]=8'hbc; golden[102]=8'hd3; golden[103]=8'h0a;
        golden[104]=8'hf7; golden[105]=8'he4; golden[106]=8'h58; golden[107]=8'h05;
        golden[108]=8'hb8; golden[109]=8'hb3; golden[110]=8'h45; golden[111]=8'h06;
        golden[112]=8'hd0; golden[113]=8'h2c; golden[114]=8'h1e; golden[115]=8'h8f;
        golden[116]=8'hca; golden[117]=8'h3f; golden[118]=8'h0f; golden[119]=8'h02;
        golden[120]=8'hc1; golden[121]=8'haf; golden[122]=8'hbd; golden[123]=8'h03;
        golden[124]=8'h01; golden[125]=8'h13; golden[126]=8'h8a; golden[127]=8'h6b;
        golden[128]=8'h3a; golden[129]=8'h91; golden[130]=8'h11; golden[131]=8'h41;
        golden[132]=8'h4f; golden[133]=8'h67; golden[134]=8'hdc; golden[135]=8'hea;
        golden[136]=8'h97; golden[137]=8'hf2; golden[138]=8'hcf; golden[139]=8'hce;
        golden[140]=8'hf0; golden[141]=8'hb4; golden[142]=8'he6; golden[143]=8'h73;
        golden[144]=8'h96; golden[145]=8'hac; golden[146]=8'h74; golden[147]=8'h22;
        golden[148]=8'he7; golden[149]=8'had; golden[150]=8'h35; golden[151]=8'h85;
        golden[152]=8'he2; golden[153]=8'hf9; golden[154]=8'h37; golden[155]=8'he8;
        golden[156]=8'h1c; golden[157]=8'h75; golden[158]=8'hdf; golden[159]=8'h6e;
        golden[160]=8'h47; golden[161]=8'hf1; golden[162]=8'h1a; golden[163]=8'h71;
        golden[164]=8'h1d; golden[165]=8'h29; golden[166]=8'hc5; golden[167]=8'h89;
        golden[168]=8'h6f; golden[169]=8'hb7; golden[170]=8'h62; golden[171]=8'h0e;
        golden[172]=8'haa; golden[173]=8'h18; golden[174]=8'hbe; golden[175]=8'h1b;
        golden[176]=8'hfc; golden[177]=8'h56; golden[178]=8'h3e; golden[179]=8'h4b;
        golden[180]=8'hc6; golden[181]=8'hd2; golden[182]=8'h79; golden[183]=8'h20;
        golden[184]=8'h9a; golden[185]=8'hdb; golden[186]=8'hc0; golden[187]=8'hfe;
        golden[188]=8'h78; golden[189]=8'hcd; golden[190]=8'h5a; golden[191]=8'hf4;
        golden[192]=8'h1f; golden[193]=8'hdd; golden[194]=8'ha8; golden[195]=8'h33;
        golden[196]=8'h88; golden[197]=8'h07; golden[198]=8'hc7; golden[199]=8'h31;
        golden[200]=8'hb1; golden[201]=8'h12; golden[202]=8'h10; golden[203]=8'h59;
        golden[204]=8'h27; golden[205]=8'h80; golden[206]=8'hec; golden[207]=8'h5f;
        golden[208]=8'h60; golden[209]=8'h51; golden[210]=8'h7f; golden[211]=8'ha9;
        golden[212]=8'h19; golden[213]=8'hb5; golden[214]=8'h4a; golden[215]=8'h0d;
        golden[216]=8'h2d; golden[217]=8'he5; golden[218]=8'h7a; golden[219]=8'h9f;
        golden[220]=8'h93; golden[221]=8'hc9; golden[222]=8'h9c; golden[223]=8'hef;
        golden[224]=8'ha0; golden[225]=8'he0; golden[226]=8'h3b; golden[227]=8'h4d;
        golden[228]=8'hae; golden[229]=8'h2a; golden[230]=8'hf5; golden[231]=8'hb0;
        golden[232]=8'hc8; golden[233]=8'heb; golden[234]=8'hbb; golden[235]=8'h3c;
        golden[236]=8'h83; golden[237]=8'h53; golden[238]=8'h99; golden[239]=8'h61;
        golden[240]=8'h17; golden[241]=8'h2b; golden[242]=8'h04; golden[243]=8'h7e;
        golden[244]=8'hba; golden[245]=8'h77; golden[246]=8'hd6; golden[247]=8'h26;
        golden[248]=8'he1; golden[249]=8'h69; golden[250]=8'h14; golden[251]=8'h63;
        golden[252]=8'h55; golden[253]=8'h21; golden[254]=8'h0c; golden[255]=8'h7d;

        xq = 8'd0;
        // Sweep all 256 inputs; check the combinational y, and the registered
        // cy against the input applied on the previous clock.
        for (i = 0; i < 256; i = i + 1) begin
            x = i[7:0];
            #1;   // settle combinational output
            checks = checks + 1;
            if (y !== golden[i]) begin
                errors = errors + 1;
                if (errors <= 10)
                    $display("ERROR y[%02h]: got %02h expected %02h", i, y, golden[i]);
            end
            @(posedge clk);   // cy latches the current x
            #1;
            if (cy !== golden[i]) begin
                errors = errors + 1;
                if (errors <= 10)
                    $display("ERROR cy[%02h]: got %02h expected %02h", i, cy, golden[i]);
            end
        end

        if (checks != 256) begin
            errors = errors + 1;
            $display("ERROR: expected 256 inputs, ran %0d", checks);
        end

        if (errors == 0) $display("TEST PASSED (%0d bytes)", checks);
        else             $display("TEST FAILED with %0d error(s)", errors);
        $finish;
    end
endmodule
