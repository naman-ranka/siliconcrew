# March 2026 Run - Authoritative Docker Re-Evaluation Report

## Summary Metrics

- **Total Problems**: 92
- **Docker-verified Passed**: 43
- **Docker-verified Failed**: 49
- **Authoritative Pass Rate**: **46.74%**
- **Old Host-native Pass Rate**: **40.22%** (37 / 92)

## Side-by-Side Comparison

| Index | Problem ID | Host Verdict (Old) | Docker Verdict (New) | Status Change |
|---|---|---|---|---|
| 1 | cvdp_agentic_64b66b_codec_0001 | PASS | PASS | No Change |
| 2 | cvdp_agentic_AES_encryption_decryption_0003 | PASS | PASS | No Change |
| 3 | cvdp_agentic_AES_encryption_decryption_0005 | FAIL | FAIL | No Change |
| 4 | cvdp_agentic_AES_encryption_decryption_0009 | PASS | PASS | No Change |
| 5 | cvdp_agentic_AES_encryption_decryption_0012 | FAIL | FAIL | No Change |
| 6 | cvdp_agentic_AES_encryption_decryption_0018 | PASS | PASS | No Change |
| 7 | cvdp_agentic_DES_0001 | PASS | PASS | No Change |
| 8 | cvdp_agentic_DES_0003 | PASS | PASS | No Change |
| 9 | cvdp_agentic_DES_0005 | PASS | PASS | No Change |
| 10 | cvdp_agentic_DES_0007 | FAIL | FAIL | No Change |
| 11 | cvdp_agentic_Min_Hamming_Distance_Finder_0001 | PASS | PASS | No Change |
| 12 | cvdp_agentic_PCIe_endpoint_0001 | PASS | PASS | No Change |
| 13 | cvdp_agentic_arithmetic_progression_generator_0001 | FAIL | FAIL | No Change |
| 14 | cvdp_agentic_async_fifo_compute_ram_application_0001 | PASS | PASS | No Change |
| 15 | cvdp_agentic_async_fifo_compute_ram_application_0006 | PASS | PASS | No Change |
| 16 | cvdp_agentic_async_filo_0001 | FAIL | PASS | 🟢 FAIL -> PASS (False Negative) |
| 17 | cvdp_agentic_axi4lite_to_pcie_config_0003 | FAIL | PASS | 🟢 FAIL -> PASS (False Negative) |
| 18 | cvdp_agentic_axis_broadcaster_0001 | FAIL | FAIL | No Change |
| 19 | cvdp_agentic_axis_to_uart_0001 | PASS | FAIL | 🔴 PASS -> FAIL (False Positive) |
| 20 | cvdp_agentic_axis_to_uart_0004 | PASS | FAIL | 🔴 PASS -> FAIL (False Positive) |
| 21 | cvdp_agentic_barrel_shifter_0001 | PASS | PASS | No Change |
| 22 | cvdp_agentic_barrel_shifter_0002 | PASS | PASS | No Change |
| 23 | cvdp_agentic_bcd_adder_0004 | PASS | PASS | No Change |
| 24 | cvdp_agentic_binary_search_tree_algorithms_0001 | FAIL | FAIL | No Change |
| 25 | cvdp_agentic_binary_search_tree_algorithms_0014 | FAIL | FAIL | No Change |
| 26 | cvdp_agentic_binary_to_gray_0003 | PASS | PASS | No Change |
| 27 | cvdp_agentic_byte_enable_ram_0002 | PASS | PASS | No Change |
| 28 | cvdp_agentic_cache_controller_0001 | FAIL | FAIL | No Change |
| 29 | cvdp_agentic_caesar_cipher_0001 | PASS | PASS | No Change |
| 30 | cvdp_agentic_cellular_automata_0002 | PASS | PASS | No Change |
| 31 | cvdp_agentic_cic_decimator_0001 | FAIL | PASS | 🟢 FAIL -> PASS (False Negative) |
| 32 | cvdp_agentic_cipher_0001 | PASS | PASS | No Change |
| 33 | cvdp_agentic_cont_adder_0001 | PASS | PASS | No Change |
| 34 | cvdp_agentic_csr_using_apb_interface_0001 | FAIL | FAIL | No Change |
| 35 | cvdp_agentic_custom_fifo_0004 | FAIL | PASS | 🟢 FAIL -> PASS (False Negative) |
| 36 | cvdp_agentic_digital_stopwatch_0001 | FAIL | FAIL | No Change |
| 37 | cvdp_agentic_direct_map_cache_0001 | PASS | PASS | No Change |
| 38 | cvdp_agentic_direct_map_cache_0003 | FAIL | FAIL | No Change |
| 39 | cvdp_agentic_dma_xfer_engine_0001 | FAIL | PASS | 🟢 FAIL -> PASS (False Negative) |
| 40 | cvdp_agentic_door_lock_0001 | FAIL | FAIL | No Change |
| 41 | cvdp_agentic_dual_port_memory_0001 | PASS | PASS | No Change |
| 42 | cvdp_agentic_dual_port_memory_0004 | PASS | PASS | No Change |
| 43 | cvdp_agentic_dynamic_equalizer_0001 | FAIL | FAIL | No Change |
| 44 | cvdp_agentic_dynamic_equalizer_0004 | FAIL | FAIL | No Change |
| 45 | cvdp_agentic_dynamic_equalizer_0008 | FAIL | FAIL | No Change |
| 46 | cvdp_agentic_elevator_control_0004 | FAIL | FAIL | No Change |
| 47 | cvdp_agentic_ethernet_mii_0004 | FAIL | FAIL | No Change |
| 48 | cvdp_agentic_ethernet_mii_0006 | PASS | FAIL | 🔴 PASS -> FAIL (False Positive) |
| 49 | cvdp_agentic_event_scheduler_0001 | PASS | PASS | No Change |
| 50 | cvdp_agentic_event_scheduler_0004 | FAIL | FAIL | No Change |
| 51 | cvdp_agentic_event_storing_0001 | FAIL | FAIL | No Change |
| 52 | cvdp_agentic_fixed_arbiter_0010 | PASS | PASS | No Change |
| 53 | cvdp_agentic_gcd_0007 | PASS | PASS | No Change |
| 54 | cvdp_agentic_hdbn_codec_0001 | FAIL | FAIL | No Change |
| 55 | cvdp_agentic_jpeg_runlength_enc_0001 | FAIL | FAIL | No Change |
| 56 | cvdp_agentic_lfsr_0001 | PASS | PASS | No Change |
| 57 | cvdp_agentic_lfsr_0005 | FAIL | FAIL | No Change |
| 58 | cvdp_agentic_low_power_channel_0001 | PASS | PASS | No Change |
| 59 | cvdp_agentic_monte_carlo_0006 | FAIL | PASS | 🟢 FAIL -> PASS (False Negative) |
| 60 | cvdp_agentic_multiplexer_0001 | PASS | PASS | No Change |
| 61 | cvdp_agentic_nbit_swizzling_0001 | PASS | PASS | No Change |
| 62 | cvdp_agentic_nmea_gps_0008 | FAIL | FAIL | No Change |
| 63 | cvdp_agentic_phase_rotation_0010 | FAIL | FAIL | No Change |
| 64 | cvdp_agentic_phase_rotation_0013 | FAIL | FAIL | No Change |
| 65 | cvdp_agentic_phase_rotation_0015 | FAIL | FAIL | No Change |
| 66 | cvdp_agentic_phase_rotation_0019 | FAIL | FAIL | No Change |
| 67 | cvdp_agentic_phase_rotation_0028 | FAIL | FAIL | No Change |
| 68 | cvdp_agentic_phase_rotation_0031 | FAIL | FAIL | No Change |
| 69 | cvdp_agentic_phase_rotation_0038 | FAIL | FAIL | No Change |
| 70 | cvdp_agentic_poly_decimator_0001 | FAIL | FAIL | No Change |
| 71 | cvdp_agentic_prbs_0001 | FAIL | FAIL | No Change |
| 72 | cvdp_agentic_programmable_fsm_dynamic_state_encoding_0001 | FAIL | FAIL | No Change |
| 73 | cvdp_agentic_queue_0001 | FAIL | FAIL | No Change |
| 74 | cvdp_agentic_rc5_0001 | FAIL | FAIL | No Change |
| 75 | cvdp_agentic_rgb_color_space_conversion_0001 | FAIL | PASS | 🟢 FAIL -> PASS (False Negative) |
| 76 | cvdp_agentic_rgb_color_space_conversion_0004 | FAIL | PASS | 🟢 FAIL -> PASS (False Negative) |
| 77 | cvdp_agentic_secure_apb_history_shift_register_0001 | FAIL | FAIL | No Change |
| 78 | cvdp_agentic_sigma_delta_audio_0001 | FAIL | FAIL | No Change |
| 79 | cvdp_agentic_signed_comparator_0001 | PASS | PASS | No Change |
| 80 | cvdp_agentic_sorter_0009 | FAIL | FAIL | No Change |
| 81 | cvdp_agentic_sorter_0016 | FAIL | FAIL | No Change |
| 82 | cvdp_agentic_sorter_0026 | FAIL | FAIL | No Change |
| 83 | cvdp_agentic_spi_complex_mult_0002 | FAIL | FAIL | No Change |
| 84 | cvdp_agentic_swizzler_0001 | PASS | PASS | No Change |
| 85 | cvdp_agentic_swizzler_0005 | FAIL | FAIL | No Change |
| 86 | cvdp_agentic_sync_serial_communication_0001 | FAIL | FAIL | No Change |
| 87 | cvdp_agentic_systolic_array_0001 | PASS | PASS | No Change |
| 88 | cvdp_agentic_thermostat_secure_0001 | FAIL | FAIL | No Change |
| 89 | cvdp_agentic_traffic_light_controller_0001 | FAIL | FAIL | No Change |
| 90 | cvdp_agentic_ttc_lite_0001 | FAIL | FAIL | No Change |
| 91 | cvdp_agentic_universal_shift_reg_0001 | FAIL | PASS | 🟢 FAIL -> PASS (False Negative) |
| 92 | cvdp_agentic_universal_shift_reg_0003 | PASS | PASS | No Change |

**Total Changed Verdicts**: 12 / 92

Report generated by `docker_rerun_march_eval.py`.