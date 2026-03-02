import mido
import struct
import zlib
import os
import math
import shutil

# --- CONFIGURATION: SYNOLOGY NAS PATHS ---
NAS_BASE_PATH = "/mnt/linux-server-storage/midi2mtp"
INPUT_FOLDER = os.path.join(NAS_BASE_PATH, "input")
OUTPUT_FOLDER = os.path.join(NAS_BASE_PATH, "output")
CONVERTED_FOLDER = os.path.join(NAS_BASE_PATH, "converted")
ERROR_FOLDER = os.path.join(NAS_BASE_PATH, "errors")

# Template file should also be placed on the NAS for easy access
TEMPLATE_MTP = os.path.join(NAS_BASE_PATH, "template.mtp")
BASE_PATTERN_NAME = "pattern"

# --- POLYEND TRACKER BINARY SPECS ---
HEADER_SIZE = 28
BYTES_PER_STEP = 6
STEPS_PER_TRACK = 128
TRACK_COUNT = 8
BYTES_PER_TRACK_BLOCK = 1 + (STEPS_PER_TRACK * BYTES_PER_STEP)

def setup_directories():
    """Ensures all necessary NAS directories exist."""
    folders = [INPUT_FOLDER, OUTPUT_FOLDER, CONVERTED_FOLDER, ERROR_FOLDER]
    for folder in folders:
        if not os.path.exists(folder):
            os.makedirs(folder)
            print(f"Created directory: {folder}")

def get_tracker_note_value(midi_note):
    """Converts a MIDI note to a Polyend Tracker note value."""
    tracker_val = midi_note + 1
    return max(1, min(tracker_val, 128))

def calculate_crc32(data):
    """Calculates the CRC32 checksum for the .mtp file."""
    return zlib.crc32(data) & 0xffffffff

def process_single_file(filename):
    """Processes a single MIDI file into Tracker patterns."""
    input_path = os.path.join(INPUT_FOLDER, filename)
    project_name = os.path.splitext(filename)[0]
    
    # Create specific output folder for this project
    project_output_dir = os.path.join(OUTPUT_FOLDER, project_name)
    if not os.path.exists(project_output_dir):
        os.makedirs(project_output_dir)
        
    print(f"Processing: {filename} -> Output to: {project_output_dir}/")

    try:
        mid = mido.MidiFile(input_path)
    except Exception as e:
        print(f"  Error reading MIDI file: {e}")
        return False

    # Calculate length and required pattern files
    ticks_per_step = mid.ticks_per_beat / 4
    last_tick = 0
    
    for track in mid.tracks:
        current_time = 0
        for msg in track:
            current_time += msg.time
            if msg.type in ['note_on', 'note_off']:
                if current_time > last_tick:
                    last_tick = current_time
    
    total_steps_needed = int(last_tick / ticks_per_step) + 1
    if total_steps_needed == 0:
        total_steps_needed = 1
        
    num_patterns = math.ceil(total_steps_needed / STEPS_PER_TRACK)
    print(f"  Length: {total_steps_needed} steps. Generating {num_patterns} patterns...")

    # Generate the pattern files
    for pattern_num in range(1, num_patterns + 1):
        output_filename = f"{BASE_PATTERN_NAME}_{pattern_num:02d}.mtp"
        output_full_path = os.path.join(project_output_dir, output_filename)
        
        start_step_global = (pattern_num - 1) * STEPS_PER_TRACK
        end_step_global = start_step_global + STEPS_PER_TRACK
        
        with open(TEMPLATE_MTP, 'rb') as f:
            data = bytearray(f.read())

        for track in mid.tracks:
            current_time = 0
            for msg in track:
                current_time += msg.time
                
                if msg.type == 'note_on' and msg.velocity > 0:
                    step_idx_global = int(current_time / ticks_per_step)
                    
                    if start_step_global <= step_idx_global < end_step_global:
                        step_idx_local = step_idx_global - start_step_global
                        track_idx = msg.channel
                        
                        if 0 <= track_idx < TRACK_COUNT:
                            offset = HEADER_SIZE + (track_idx * BYTES_PER_TRACK_BLOCK) + 1 + (step_idx_local * BYTES_PER_STEP)
                            data[offset] = get_tracker_note_value(msg.note)
                            data[offset + 1] = track_idx + 1  # Instrument assignment

        # Calculate CRC and write the file
        payload = data[:-4]
        new_crc = calculate_crc32(payload)
        final_data = payload + struct.pack('<I', new_crc)

        with open(output_full_path, 'wb') as f:
            f.write(final_data)
            
    print(f"  Success! Generated {num_patterns} files.")
    return True

def main():
    print("-------- MIDI TO TRACKER BATCH CONVERTER --------")
    
    setup_directories()

    if not os.path.exists(TEMPLATE_MTP):
        print(f"CRITICAL ERROR: Template file not found at {TEMPLATE_MTP}")
        print("Please place an empty 'template.mtp' on the NAS directory.")
        return

    midi_files = [f for f in os.listdir(INPUT_FOLDER) if f.lower().endswith(".mid")]
    
    if not midi_files:
        print(f"No .mid files found in '{INPUT_FOLDER}/'. Waiting for input...")
        return

    print(f"Found {len(midi_files)} MIDI files. Starting batch process...\n")

    for filename in midi_files:
        success = process_single_file(filename)
        source_path = os.path.join(INPUT_FOLDER, filename)
        
        if success:
            dest_path = os.path.join(CONVERTED_FOLDER, filename)
            if os.path.exists(dest_path):
                os.remove(dest_path)
            shutil.move(source_path, dest_path)
            print(f"  Moved {filename} to '{CONVERTED_FOLDER}/'\n")
        else:
            dest_path = os.path.join(ERROR_FOLDER, filename)
            if os.path.exists(dest_path):
                os.remove(dest_path)
            shutil.move(source_path, dest_path)
            print(f"  FAILED. Moved {filename} to '{ERROR_FOLDER}/'\n")

    print("-------- BATCH COMPLETED --------")

if __name__ == "__main__":
    main()