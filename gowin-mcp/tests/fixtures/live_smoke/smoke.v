// Build-bridge fixture only; never programmed to a board.
module smoke(input wire sys_clk, input wire key0_n, output wire status_led);
    reg [15:0] counter;
    always @(posedge sys_clk or negedge key0_n) begin
        if (!key0_n) counter <= 16'd0;
        else counter <= counter + 16'd1;
    end
    assign status_led = counter[15];
endmodule
