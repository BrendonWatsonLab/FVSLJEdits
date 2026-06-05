import os
import csv
from tkinter import Tk
from tkinter.filedialog import askopenfilenames
from FVSLJ.data_record import read_next_record, save_to_csv

def open_file_dialog():
    Tk().withdraw()  # We don't want a full GUI, so keep the root window from appearing
    file_paths = askopenfilenames(title="Select binary files", filetypes=[("Binary files", "*.bin")])
    return file_paths

def main():
    files = open_file_dialog()
    if not files:
        print("No files were selected or an error occurred.")
        return

    for path in files:
        try:
            with open(path, 'rb') as input_file:
                # Create output directory if it doesn't exist
                output_dir = os.path.join(os.path.dirname(path), "csv_files")
                os.makedirs(output_dir, exist_ok=True)

                # Create CSV file path
                base_name = os.path.splitext(os.path.basename(path))[0]
                csv_path = os.path.join(output_dir, f"{base_name}.csv")

                with open(csv_path, 'w', newline='') as output_file:
                    csv_writer = csv.writer(output_file)
                    csv_writer.writerow(["POSIX", "Digital Pins", "Light State", "Wheel Analog", "Sync Pulse", "Camera Pulse"])

                    while True:
                        record = read_next_record(input_file)
                        if record is None:
                            break
                        save_to_csv(csv_writer, record)

                print(f"Data read from binary file and saved to CSV: {path}")

        except IOError as e:
            print(f"Error opening file {path}: {e}")

if __name__ == "__main__":
    main()