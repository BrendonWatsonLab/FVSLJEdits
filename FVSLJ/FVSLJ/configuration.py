import re
from datetime import datetime

def get_device_configurations(file_path):
    device_configurations = {}
    with open(file_path, 'r') as file:
        for line in file:
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            name_match = re.match(r'labjack_\d+_name\s*:\s*"([^"]+)"', line)
            serial_match = re.match(r'labjack_\d+_serial\s*:\s*(\d+)', line)
            if name_match:
                current_name = name_match.group(1)
            elif serial_match:
                device_configurations[current_name] = int(serial_match.group(1))

    return device_configurations

def parse_aux_configurations(file_path):
    light_control = 0
    light_time_on = None
    light_time_off = None
    controller_labjack = None
    output_directory = None
    samples_per_second = None

    with open(file_path, 'r') as file:
        for line in file:
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            print(f"Parsing line: {line}")  # Debugging output
            if "light_control" in line:
                light_control = int(line.split(":")[1].strip())
            elif "light_time_on" in line:
                time_str = re.search(r'light_time_on\s*:\s*(\d{2}:\d{2})', line)
                if time_str:
                    try:
                        light_time_on = datetime.strptime(time_str.group(1), "%H:%M").time()
                    except ValueError as e:
                        print(f"Error parsing light_time_on: {e}")
            elif "light_time_off" in line:
                time_str = re.search(r'light_time_off\s*:\s*(\d{2}:\d{2})', line)
                if time_str:
                    try:
                        light_time_off = datetime.strptime(time_str.group(1), "%H:%M").time()
                    except ValueError as e:
                        print(f"Error parsing light_time_off: {e}")
            elif "controller_labjack" in line:
                controller_labjack = re.search(r'controller_labjack\s*:\s*"([^"]+)"', line).group(1)
            elif "output_directory" in line:
                output_directory = re.search(r'output_directory\s*:\s*"([^"]+)"', line).group(1)
            elif "samples_per_second" in line:
                samples_per_second = int(line.split(":")[1].strip())

    # Validation step
    if light_control == 1:
        if light_time_on is None or light_time_off is None:
            raise ValueError("light_control is set to 1, but light_time_on or light_time_off is not set.")

    return light_control, light_time_on, light_time_off, controller_labjack, output_directory, samples_per_second
