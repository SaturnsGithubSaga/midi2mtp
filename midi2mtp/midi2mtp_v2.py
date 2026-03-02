import mido
import struct
import zlib
import os
import math

# --- CONFIGURATION ---
INPUT_MIDI = "input.mid"
TEMPLATE_MTP = "template.mtp"
BASE_OUTPUT_NAME = "pattern" # Will result in pattern_01.mtp, pattern_02.mtp etc.

# --- POLYEND TRACKER BINARY SPECS ---
# Based on the visual map provided
HEADER_SIZE = 28
BYTES_PER_STEP = 6
STEPS_PER_TRACK = 128
TRACK_COUNT = 8
# Calculate the size of a single track block
# Structure: [Length Byte (1)] + [128 Steps * 6 Bytes]
BYTES_PER_TRACK_BLOCK = 1 + (STEPS_PER_TRACK * BYTES_PER_STEP)

def get_tracker_note_value(midi_note):
    """
    Converts MIDI note to Tracker note value.
    Offset +1 because 0 is 'Empty'.
    """
    tracker_val = midi_note + 1
    return max(1, min(tracker_val, 128))

def calculate_crc32(data):
    """Calculates the standard CRC32 checksum."""
    return zlib.crc32(data) & 0xffffffff

def midi_to_mtp():
    print(f"-------- MIDI TO TRACKER CONVERTER V2 (MULTI-PATTERN) --------")
    
    # 1. Validation Checks
    if not os.path.exists(INPUT_MIDI) or not os.path.exists(TEMPLATE_MTP):
        print("Error: Input or Template file not found.")
        return

    print(f"Loading MIDI: {INPUT_MIDI}")
    mid = mido.MidiFile(INPUT_MIDI)
    
    # 2. Calculate Total Length and Number of Patterns needed
    # We assume 16th notes (4 ticks per beat)
    ticks_per_step = mid.ticks_per_beat / 4
    
    # Find the very last timestamp in the MIDI file to determine length
    last_tick = 0
    for track in mid.tracks:
        current_time = 0
        for msg in track:
            current_time += msg.time
            if msg.type == 'note_on' or msg.type == 'note_off':
                if current_time > last_tick:
                    last_tick = current_time
    
    # Calculate total steps and required patterns
    total_steps_needed = int(last_tick / ticks_per_step) + 1
    num_patterns = math.ceil(total_steps_needed / STEPS_PER_TRACK)
    
    print(f"Song Length: {total_steps_needed} steps. Generating {num_patterns} patterns...")

    # 3. Generate a file for each pattern
    for pattern_num in range(1, num_patterns + 1):
        # Create filename like 'pattern_01.mtp'
        output_filename = f"{BASE_OUTPUT_NAME}_{pattern_num:02d}.mtp"
        
        # Calculate start and end steps for THIS specific pattern
        start_step_global = (pattern_num - 1) * STEPS_PER_TRACK
        end_step_global = start_step_global + STEPS_PER_TRACK
        
        print(f"  -> Generating {output_filename} (Global Steps {start_step_global} to {end_step_global})...")

        # Reload the clean template for every new file
        with open(TEMPLATE_MTP, 'rb') as f:
            data = bytearray(f.read())

        notes_in_pattern = 0

        # Iterate through tracks to find notes that belong in this pattern
        for track in mid.tracks:
            current_time = 0
            for msg in track:
                current_time += msg.time
                
                if msg.type == 'note_on' and msg.velocity > 0:
                    step_idx_global = int(current_time / ticks_per_step)
                    
                    # Check if this note falls within the current pattern's range
                    if start_step_global <= step_idx_global < end_step_global:
                        
                        # Convert global step to local step (0-127)
                        step_idx_local = step_idx_global - start_step_global
                        
                        track_idx = msg.channel
                        
                        # Write data if within track limits
                        if 0 <= track_idx < TRACK_COUNT:
                            # Calculate binary offset
                            offset = HEADER_SIZE + (track_idx * BYTES_PER_TRACK_BLOCK) + 1 + (step_idx_local * BYTES_PER_STEP)
                            
                            note_val = get_tracker_note_value(msg.note)
                            # Assign Instrument based on Track number (1-8)
                            inst_val = track_idx + 1 
                            
                            data[offset] = note_val
                            data[offset + 1] = inst_val
                            notes_in_pattern += 1

        # 4. Finalize and Save
        # Remove old CRC and calculate new one
        payload = data[:-4]
        new_crc = calculate_crc32(payload)
        final_data = payload + struct.pack('<I', new_crc)

        with open(output_filename, 'wb') as f:
            f.write(final_data)
            
        print(f"     Saved {output_filename} with {notes_in_pattern} notes.")

    print("Done! Copy all generated .mtp files to your Tracker SD card.")

if __name__ == "__main__":
    midi_to_mtp()