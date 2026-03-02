import mido
import struct
import zlib
import shutil
import os

# --- CONFIGURATION ---
INPUT_MIDI = "input.mid"
TEMPLATE_MTP = "template.mtp"
OUTPUT_MTP = "pattern_01.mtp"

# --- POLYEND TRACKER BINARY SPECS ---
# Based on reverse engineering and visual maps of the .mtp format
HEADER_SIZE = 28
BYTES_PER_STEP = 6
STEPS_PER_TRACK = 128
TRACK_COUNT = 8

# Calculate the size of a single track block
# Structure: [Length Byte (1)] + [128 Steps * 6 Bytes]
BYTES_PER_TRACK_BLOCK = 1 + (STEPS_PER_TRACK * BYTES_PER_STEP)

def get_tracker_note_value(midi_note):
    """
    Converts a MIDI note number (0-127) to Polyend Tracker note value.
    
    Polyend Mapping Estimate:
    0 = No Note / Empty
    1 = C-0
    ...
    
    Note: Tracker 'Middle C' (C-5) is usually around value 61.
    We offset by +1 because 0 is reserved for 'Empty'.
    """
    tracker_val = midi_note + 1
    # Clamp value to ensure it fits within valid Tracker range (1-128)
    return max(1, min(tracker_val, 128))

def calculate_crc32(data):
    """Calculates the CRC32 checksum expected by the Polyend Tracker."""
    return zlib.crc32(data) & 0xffffffff

def midi_to_mtp():
    print(f"-------- MIDI TO TRACKER CONVERTER --------")
    
    # 1. Validation Checks
    if not os.path.exists(INPUT_MIDI):
        print(f"Error: Input file '{INPUT_MIDI}' not found.")
        return
    if not os.path.exists(TEMPLATE_MTP):
        print(f"Error: Template file '{TEMPLATE_MTP}' not found.")
        return

    print(f"Loading MIDI: {INPUT_MIDI}")
    mid = mido.MidiFile(INPUT_MIDI)

    print(f"Loading Template: {TEMPLATE_MTP}")
    with open(TEMPLATE_MTP, 'rb') as f:
        # Read file as mutable bytearray
        data = bytearray(f.read())

    # Verify template size integrity
    # Expected size = Header + (8 Tracks * Block Size) + 4 Bytes CRC
    expected_size = HEADER_SIZE + (TRACK_COUNT * BYTES_PER_TRACK_BLOCK) + 4
    if len(data) != expected_size:
        print(f"Warning: Template size ({len(data)} bytes) does not match expected size ({expected_size} bytes).")
        print("Proceeding, but output might be corrupt.")

    # 2. Prepare for conversion
    # Assuming 16th notes (4 ticks per beat)
    ticks_per_step = mid.ticks_per_beat / 4
    notes_processed = 0

    print("Injecting MIDI data into pattern structure...")

    # 3. Iterate through MIDI tracks
    for track in mid.tracks:
        current_time = 0
        for msg in track:
            current_time += msg.time
            
            # We only care about Note On events with velocity > 0
            if msg.type == 'note_on' and msg.velocity > 0:
                # Calculate Step Position
                step_idx = int(current_time / ticks_per_step)
                
                # MIDI Channel 0-7 maps to Tracker Track 1-8
                track_idx = msg.channel
                
                # Boundary Checks
                if 0 <= track_idx < TRACK_COUNT and step_idx < STEPS_PER_TRACK:
                    
                    # --- THE OFFSET FORMULA ---
                    # 1. Skip Header
                    # 2. Jump to correct Track Block
                    # 3. Skip Track Length Byte (+1)
                    # 4. Jump to correct Step
                    offset = HEADER_SIZE + (track_idx * BYTES_PER_TRACK_BLOCK) + 1 + (step_idx * BYTES_PER_STEP)
                    
                    # Convert Note
                    note_val = get_tracker_note_value(msg.note)
                    # Use Instrument Number corresponding to Track Number (1-8)
                    inst_val = track_idx + 1 
                    
                    # Write to binary data (Byte 0 = Note, Byte 1 = Instrument)
                    data[offset] = note_val
                    data[offset + 1] = inst_val
                    
                    notes_processed += 1
                else:
                    # Optional: Log ignored notes outside range
                    pass

    print(f"Success: Processed {notes_processed} notes.")

    # 4. Finalize and Sign (CRC)
    print("Recalculating CRC checksum...")
    
    # Strip the old CRC (last 4 bytes)
    payload = data[:-4]
    new_crc = calculate_crc32(payload)
    
    # Append new CRC (Little Endian format)
    final_data = payload + struct.pack('<I', new_crc)

    # 5. Save
    try:
        with open(OUTPUT_MTP, 'wb') as f:
            f.write(final_data)
        print(f"Done! Saved as: {OUTPUT_MTP}")
        print(f"Copy this file to your Tracker SD card: /Patterns/{OUTPUT_MTP}")
    except Exception as e:
        print(f"Error saving file: {e}")

if __name__ == "__main__":
    midi_to_mtp()