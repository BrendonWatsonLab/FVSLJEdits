import threading
import signal
import os
import re
from labjack import ljm
from datetime import datetime
import time
from FVSLJ.data_record import DataRecord
from FVSLJ.configuration import get_device_configurations, parse_aux_configurations

# Default value for samples per second
SAMPLES_PER_SECOND = 51

def sanitize_filename(filename):
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', filename)

class FVSLJ:
    def __init__(self, aScanListNames, scanRate, scansPerRead):
        self.aScanListNames = aScanListNames
        self.scanRate = scanRate
        self.scansPerRead = scansPerRead
        self.device_configurations = {}
        self.threads = []
        self.keep_scanning = True
        self.light_control = 0
        self.light_time_on = None
        self.light_time_off = None
        self.light_state = None  # None means unknown, True means on, False means off
        self.controller_labjack = None
        self.output_directory = None
        self.start_event = threading.Event()  # Event to synchronize stream start

    def open_labjack(self, serial_number):
        handle = ljm.openS("ANY", "ANY", str(serial_number))
        info = ljm.getHandleInfo(handle)
        device_type = info[0]
        print(f"Opened a LabJack with Device type: {info[0]}, Connection type: {info[1]},\n"
              f"Serial number: {info[2]}, IP address: {ljm.numberToIP(info[3])}, Port: {info[4]},\n"
              f"Max bytes per MB: {info[5]}")
        return handle, device_type

    def configure_stream(self, handle, device_type):
        numAddresses = len(self.aScanListNames)
        aScanList = ljm.namesToAddresses(numAddresses, self.aScanListNames)[0]

        if device_type == ljm.constants.dtT4:
            aNames = ["STREAM_SETTLING_US", "STREAM_RESOLUTION_INDEX"]
            aValues = [0, 0]
        else:
            ljm.eWriteName(handle, "STREAM_TRIGGER_INDEX", 0)
            ljm.eWriteName(handle, "STREAM_CLOCK_SOURCE", 0)
            aNames = ["AIN0_RANGE", "AIN1_RANGE", "STREAM_RESOLUTION_INDEX"]
            aValues = [10.0, 10.0, 0]
            if device_type == ljm.constants.dtT7:
                aNames.extend(["AIN0_NEGATIVE_CH", "STREAM_SETTLING_US", "AIN1_NEGATIVE_CH"])
                aValues.extend([199, 0, 199])

        ljm.eWriteNames(handle, len(aNames), aNames, aValues)
        print(f"\nStream configured for device with serial number {ljm.getHandleInfo(handle)[2]}.")

    def start_stream(self, handle):
        numAddresses = len(self.aScanListNames)
        aScanList = ljm.namesToAddresses(numAddresses, self.aScanListNames)[0]
        scanRate = ljm.eStreamStart(handle, self.scansPerRead, numAddresses, aScanList, self.scanRate)
        print(f"\nStream started with a scan rate of {scanRate:.0f} Hz.")
        return scanRate

    def perform_stream_reads(self, handle, device_type, device_name):
        print(f"\nPerforming stream reads for {device_name} until interrupted.")
        start = datetime.now()
        start_time_str = start.strftime("%Y%m%d_%H%M%S")
        sanitized_device_name = sanitize_filename(device_name)
        file_name = os.path.join(self.output_directory, f"{sanitized_device_name}_{start_time_str}.bin")
        
        with open(file_name, 'wb') as file:
            totScans = 0
            totSkip = 0  # Total skipped samples
            timestamp = int(start.timestamp() * 1e6)  # Microseconds since epoch
            increment = int(1e6 / self.scanRate)  # Time increment per scan in microseconds

            while self.keep_scanning:
                ret = ljm.eStreamRead(handle)
                aData = ret[0]
                scans = len(aData) / len(self.aScanListNames)
                totScans += scans

                # Count the skipped samples which are indicated by -9999 values.
                curSkip = aData.count(-9999.0)
                totSkip += curSkip

                for i in range(int(scans)):
                    digitalStatus = int(''.join(['1' if aData[i * len(self.aScanListNames) + self.aScanListNames.index(f"EIO{j}")] > 0.5 else '0' for j in range(8)]), 2)
                    lightStatus = aData[i * len(self.aScanListNames) + self.aScanListNames.index("AIN1")] > 0.5
                    wheel = aData[i * len(self.aScanListNames) + self.aScanListNames.index("AIN0")]
                    pulse = aData[i * len(self.aScanListNames) + self.aScanListNames.index("FIO1")] > 0.5
                    camera = aData[i * len(self.aScanListNames) + self.aScanListNames.index("FIO0")] > 0.5

                    data_record = DataRecord(timestamp, digitalStatus, lightStatus, wheel, pulse, camera)
                    file.write(data_record.to_binary())
                    if i == 0:
                        print(data_record)

                    timestamp += increment

            end = datetime.now()
            tt = (end - start).seconds + float((end - start).microseconds) / 1000000
            print(f"\nTotal scans = {totScans}")
            print(f"Time taken = {tt} seconds")
            print(f"LJM Scan Rate = {self.scanRate} scans/second")
            print(f"Timed Scan Rate = {totScans / tt} scans/second")
            print(f"Timed Sample Rate = {totScans * len(self.aScanListNames) / tt} samples/second")
            print(f"Skipped scans = {totSkip / len(self.aScanListNames):.0f}")

    def turn_light_on(self, handle):
        ljm.eWriteName(handle, "DIO17", 1)
        print("Light turned on")

    def turn_light_off(self, handle):
        ljm.eWriteName(handle, "DIO17", 0)
        print("Light turned off")

    def light_control_thread(self, handle, name):
        while self.keep_scanning:
            current_time = datetime.now().time()
            #other labjacks get to this point?
            if self.light_control == 1 and self.light_time_on is not None and self.light_time_off is not None:
                if self.light_time_on <= current_time < self.light_time_off:
                    if self.light_state != True:
                        print(name)
                        self.turn_light_on(handle)
                        self.light_state = True
                else:
                    if self.light_state != False:
                        self.turn_light_off(handle)
                        self.light_state = False
            time.sleep(1)  # Check every second

    def wait_for_high_input(self, handle):
        print("Waiting for high input on FIO2...")
        while self.keep_scanning:
            state = ljm.eReadName(handle, "FIO2")
            if state > 0.5:
                print("High input detected on FIO2.")
                self.start_event.set()  # Signal all threads to start
                break
            time.sleep(1)

    def stop_stream(self, handle):
        try:
            print("\nStop Stream")
            ljm.eStreamStop(handle)
        except ljm.LJMError as ljme:
            print(ljme)
        except Exception as e:
            print(e)

    def close_labjack(self, handle):
        ljm.close(handle)

    def stream_device(self, name, serial):
        print(f"\nConnecting to device {name} with serial number {serial}")
        try:
            handle, device_type = self.open_labjack(serial)
            self.configure_stream(handle, device_type)
            self.start_event.wait()  # Wait for the signal to start
            self.start_stream(handle)

            # Start light control thread
            light_thread = threading.Thread(target=self.light_control_thread, args=(handle,name))
            light_thread.start()
            print(name)
            self.threads.append(light_thread)

            self.perform_stream_reads(handle, device_type, name)
        except ljm.LJMError as ljme:
            print(ljme)
        except Exception as e:
            print(e)
        finally:
            self.stop_stream(handle)
            self.close_labjack(handle)

    def run(self):
        self.device_configurations = get_device_configurations("configurations.txt")
        self.light_control, self.light_time_on, self.light_time_off, self.controller_labjack, self.output_directory, samples_per_second = parse_aux_configurations("configurations.txt")
        print(self.device_configurations)
        if self.controller_labjack not in self.device_configurations:
            raise ValueError(f"Controller_labjack '{self.controller_labjack}' is not a registered device.\nMake sure configuration file contains line to assign controller_labjack and that the assigned device exists.")

        # Ensure the output directory exists
        if not os.path.exists(self.output_directory):
            os.makedirs(self.output_directory)

        # Open the controller_labjack device and start the thread to wait for high input
        controller_handle, _ = self.open_labjack(self.device_configurations[self.controller_labjack])
        controller_thread = threading.Thread(target=self.wait_for_high_input, args=(controller_handle,))
        self.threads.append(controller_thread)
        controller_thread.start()

        # Start the other devices
        for name, serial in self.device_configurations.items():
            thread = threading.Thread(target=self.stream_device, args=(name, serial))
            self.threads.append(thread)
            thread.start()

        for thread in self.threads:
            thread.join()

    def stop_scanning(self, signum, frame):
        print("\nInterrupt received, stopping scans...")
        self.keep_scanning = False
        self.start_event.set()  # Ensure all threads are released

def main():
    # Parse configurations to get the sample rate
    _, _, _, _, _, samples_per_second = parse_aux_configurations("configurations.txt")

    # Use the samples_per_second from the configuration file if it exists
    global SAMPLES_PER_SECOND
    if samples_per_second is not None:
        SAMPLES_PER_SECOND = samples_per_second

    aScanListNames = ["AIN0", "AIN1", "FIO0", "FIO1", "EIO0", "EIO1", "EIO2", "EIO3", "EIO4", "EIO5", "EIO6", "EIO7"]
    scanRate = SAMPLES_PER_SECOND
    scansPerRead = scanRate
    streamer = FVSLJ(aScanListNames, scanRate, scansPerRead)

    # Set up signal handling to stop scanning on interrupt
    signal.signal(signal.SIGINT, streamer.stop_scanning)
    signal.signal(signal.SIGTERM, streamer.stop_scanning)

    streamer.run()

if __name__ == "__main__":
    main()