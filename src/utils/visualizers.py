import os
import streamlit as st
import matplotlib.pyplot as plt
import gdstk
from vcdvcd import VCDVCD
import numpy as np

def render_waveform(vcd_path):
    """Parses VCD and renders a step plot using Matplotlib."""
    try:
        vcd = VCDVCD(vcd_path)
        signals = vcd.get_signals()
        
        if not signals:
            st.warning("No signals found in VCD.")
            return

        # Filter signals to avoid clutter (e.g., top 10)
        # Prefer signals in the top module
        display_signals = [s for s in signals if "tb" in s or "clk" in s or "rst" in s][:15]
        if not display_signals:
            display_signals = signals[:15]

        fig, ax = plt.subplots(len(display_signals), 1, figsize=(10, len(display_signals) * 0.8), sharex=True)
        if len(display_signals) == 1:
            ax = [ax]

        endtime = vcd.endtime
        
        for i, sig_name in enumerate(display_signals):
            sig = vcd[sig_name]
            tv = sig.tv # List of (time, value)
            
            times = [t for t, v in tv]
            values = []
            
            # Determine if signal is a bus (multi-bit) based on max value
            is_bus = False
            max_val = 1
            
            for t, v in tv:
                val = 0
                try:
                    # Handle binary strings (e.g., '101', '0', '1')
                    if isinstance(v, str):
                        # Replace x/z with 0 (or handle differently)
                        v_clean = v.lower().replace('x', '0').replace('z', '0')
                        val = int(v_clean, 2)
                    else:
                        val = int(v)
                except ValueError:
                    val = 0 # Fallback
                
                values.append(val)
            
            if values:
                max_val = max(values)
                if max_val > 1:
                    is_bus = True
            
            # Add end time point for step plot continuity
            times.append(endtime)
            values.append(values[-1])
            
            if is_bus:
                # Bus Rendering Style: "Valid" block with text
                # We plot a "box" or just a line in the middle, and annotate
                
                # 1. Draw transitions
                # We'll plot a line at y=0.5, but add vertical markers at changes
                # To make it look like a bus, we can plot two lines at y=0.2 and y=0.8
                
                # Simplified: Plot a step at 0.5, but we need to see edges.
                # Let's iterate and draw rectangles or just place text.
                
                ax[i].set_ylim(0, 1)
                ax[i].set_yticks([]) # No Y ticks for bus
                
                # Draw "Bus Lines"
                ax[i].hlines(0.8, times[0], times[-1], colors='tab:blue', linewidth=1)
                ax[i].hlines(0.2, times[0], times[-1], colors='tab:blue', linewidth=1)
                
                # Annotate values
                for j in range(len(times) - 1):
                    t_start = times[j]
                    t_end = times[j+1]
                    val = values[j]
                    
                    # Draw vertical lines at transitions
                    ax[i].vlines(t_start, 0.2, 0.8, colors='tab:blue', linewidth=1)
                    
                    # Add Text (only if interval is wide enough)
                    duration = t_end - t_start
                    if duration > (endtime * 0.02): # 2% threshold to avoid clutter
                        center = t_start + (duration / 2)
                        ax[i].text(center, 0.5, str(val), ha='center', va='center', fontsize=8, clip_on=True)
                        
                ax[i].vlines(times[-1], 0.2, 0.8, colors='tab:blue', linewidth=1)

            else:
                # Standard Step Plot for single bits
                ax[i].step(times, values, where='post')
                ax[i].set_yticks([0, 1])
                ax[i].set_yticklabels(['0', '1'], fontsize=6)
            
            # Label formatting
            short_name = sig_name.split('.')[-1]
            if is_bus:
                short_name += f" [Bus]" 
                
            ax[i].set_ylabel(short_name, rotation=0, ha='right', fontsize=8)
            ax[i].grid(True, alpha=0.3)
            
            # Remove spines for cleaner look
            ax[i].spines['top'].set_visible(False)
            ax[i].spines['right'].set_visible(False)
            ax[i].spines['bottom'].set_visible(False)
            if i != len(display_signals) - 1:
                ax[i].set_xticks([])

        ax[-1].set_xlabel("Time (ns)")
        plt.tight_layout()
        st.pyplot(fig)
        
    except Exception as e:
        st.error(f"Failed to render Waveform: {e}")

def render_gds(gds_path):
    """Renders GDS to SVG using gdstk and displays it."""
    try:
        # Check if file exists and is not empty
        if os.path.getsize(gds_path) == 0:
            st.warning("GDS file is empty.")
            return

        lib = gdstk.read_gds(gds_path)
        top_cells = lib.top_level()
        if not top_cells:
            st.error("No top level cell found in GDS.")
            return
            
        cell = top_cells[0]
        
        # Create a temporary SVG path
        svg_path = gds_path + ".svg"
        cell.write_svg(svg_path)
        
        # Display
        st.image(svg_path, caption=f"Layout: {os.path.basename(gds_path)}")
        
    except Exception as e:
        st.error(f"Failed to render GDS: {e}")
