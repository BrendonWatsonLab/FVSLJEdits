import threading
import signal
import os
import re
from labjack import ljm
from datetime import datetime
import time
from FVSLJ.data_record import DataRecord
from FVSLJ.configuration import get_device_configurations, parse_aux_configurations
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

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
        self.controller_labjack = None
        self.output_directory = None
        self.start_event = threading.Event()  # Event to synchronize stream start
        self.low_event = False
        self.device_data = {}
        self.device_lines = {}
        self.signals = ['Wheel', 'Light', 'Beam Break']
        self.start_time = time.time()

    #make code here to initialize graphs for all 4 labjacks 
    def initialize_graphs(self):
        num_devices = len(self.device_configurations) 
        self.fig, self.axes = plt.subplots(num_devices, 3, figsize=(15, 3 * num_devices), sharex=True)
        for i, (device_name, _) in enumerate (self.device_configurations.items()):     
            self.device_lines[device_name] = {}
            self.device_data[device_name] = {'x': [], 'Wheel': [], 'Light': [], 'Beam Break': []}  

            for j, signal in enumerate(self.signals):
                ax = self.axes[i][j]
                ax.set_title(f"{signal} - {device_name}")
                ax.set_xlim(0, 10)
                if signal == 'Wheel':
                    ax.set_ylim(-20, 20)
                elif signal == 'Light':
                    ax.set_ylim(-.5, 2)
                elif signal == 'Beam Break':
                    ax.set_ylim(-5, 280)
                    ax.set_yticks(np.linspace(0, 280, 8))
                    
                ax.tick_params(labelbottom=True) #forcing x-axis at bottom of each graph

                line, = ax.plot([], [], '-', label=signal)
                self.device_lines[device_name][signal] = line
        

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
                    self.digitalStatus = int(''.join(['1' if aData[i * len(self.aScanListNames) + self.aScanListNames.index(f"EIO{j}")] > 0.5 else '0' for j in range(8)]), 2)
                    self.lightStatus = aData[i * len(self.aScanListNames) + self.aScanListNames.index("AIN1")] > 0.5
                    self.wheel = aData[i * len(self.aScanListNames) + self.aScanListNames.index("AIN0")]
                    pulse = aData[i * len(self.aScanListNames) + self.aScanListNames.index("FIO1")] > 0.5
                    light = aData[i * len(self.aScanListNames) + self.aScanListNames.index("FIO0")] > 0.5

                    #change to append data for every single labjack
                    current_time = time.time() - self.start_time
                    signals = self.device_data[device_name]
                    signals['x'].append(current_time)
                    signals['Wheel'].append(self.wheel)
                    signals['Light'].append(self.lightStatus)
                    signals['Beam Break'].append(self.digitalStatus)

                    if len(signals['x']) > 1000:
                        for key in ['x', 'Wheel', 'Light', 'Beam Break']:
                            signals[key].pop(0)

                    data_record = DataRecord(timestamp, self.digitalStatus, self.lightStatus, self.wheel, pulse, light)
                    file.write(data_record.to_binary())
                   
                    if i == 0:
                        print(data_record)

                    timestamp += increment

                if self.low_event:
                    break

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

    def light_control_thread(self, handle, light_state):
        while self.keep_scanning:
            current_time = datetime.now().time()
            if self.light_control == 1 and self.light_time_on is not None and self.light_time_off is not None:
                if self.light_time_on <= current_time < self.light_time_off:
                    if light_state != True:
                        self.turn_light_on(handle) 
                        light_state = True
                else:
                    if light_state != False:
                        self.turn_light_off(handle)
                        light_state = False
            time.sleep(1)  # Check every second
            if self.low_event:
                break

    def wait_for_high_input(self, handle, dio_pin="FIO2", poll_interval=1.0):
        #Continuously monitor input pin and pause/resume data collection   
        while True:
            try:
                state = ljm.eReadName(handle, dio_pin)
                current_time = datetime.now().strftime("%H:%M:%S")
            
                if state > 0.5:
                    print(f"High input detected on FIO2.")
                    if not self.keep_scanning:
                        print("Resuming data collection")
                        self.keep_scanning = True
                        self.start_event.set()
                        self.low_event = False
                else:
                    print(f"Low input detected on FIO2.")
                    if self.keep_scanning:
                        print("Pausing data collection")
                        self.keep_scanning = False
                        self.start_event.clear()
                        self.low_event = True

                time.sleep(poll_interval)

            except Exception as e:
                print(f"Error monitoring input: {e}")
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

    def stream_device(self, name, serial, existing_handle=None, existing_device_type=None):
        print(f"\nConnecting to device {name} with serial number {serial}")
        try:
            handle, device_type = self.open_labjack(serial)
            self.configure_stream(handle, device_type)
            self.start_event.wait()  # Wait for the signal to start
            self.start_stream(handle)

            # Start light control thread
            light_state = None  # Initialize light state for this thread
            light_thread = threading.Thread(target=self.light_control_thread, args=(handle, light_state))
            light_thread.start()
            self.threads.append(light_thread)

            self.perform_stream_reads(handle, device_type, name)
        except ljm.LJMError as ljme:
            print(ljme)
        except Exception as e:
            print(e)
        finally:
            self.stop_stream(handle)
        
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
        controller_handle, controller_device_type = self.open_labjack(self.device_configurations[self.controller_labjack])

        # Check initial state and set accordingly
        initial_state = ljm.eReadName(controller_handle, "FIO2")
        if initial_state > 0.5:
            print("Initial high input detected - starting data collection")
            self.keep_scanning = True
            self.start_event.set()
        else:
            print("Initial low input detected - waiting for high input")
            self.keep_scanning = False
            self.start_event.clear()
    
        # Start the input monitoring thread
        controller_thread = threading.Thread(
            target=self.wait_for_high_input, 
            args=(controller_handle,),
            daemon=True
        )
        controller_thread.start()

        # Start the other devices
        for name, serial in self.device_configurations.items():
            thread = threading.Thread(target=self.stream_device, args=(name, serial))
            self.threads.append(thread)
            thread.start()

        print("BEFORE THREAD JOIN")
        for thread in self.threads:
            thread.join()
        print("AFTER THREAD JOIN")
        return True

    def stop_scanning(self, signum, frame):
        print("\nInterrupt received, stopping scans...")
        self.keep_scanning = False
        self.start_event.set()  # Ensure all threads are released
    
    def update_plot(self, frames):
        for device_name, signals in self.device_data.items():
            xdata = signals['x']
            if not xdata:
                continue

            current_time = xdata[-1]

            for signal_name in self.signals:
                ydata = signals[signal_name]
                line = self.device_lines[device_name][signal_name]
                line.set_data(xdata, ydata)

                i = list(self.device_configurations.keys()).index(device_name)
                j = self.signals.index(signal_name)
                ax = self.axes[i][j]
            
                ax.relim() #making sure x-axis is dynamically moving 
                ax.autoscale_view()
                ax.set_xlim(max(0, current_time - 10), current_time)

        return [line for dev in self.device_lines.values() for line in dev.values()]

    
    def start_animation(self):
        if self.low_event:
            print("\nLow event detected - skipping animation start")
            return
        
        print("Animation ready to start")


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
    
    streamer.device_configurations = get_device_configurations("configurations.txt")
   
    # Initialize graphs once
    streamer.initialize_graphs()
    
    # Start the data collection thread
    data_thread = threading.Thread(target=streamer.run)
    data_thread.daemon = True
    data_thread.start()

    # Wait a moment for data to start flowing before animation
    time.sleep(0.5)
    
    # Start the animation in the main thread
    print("Starting animation...")
    streamer.ani = animation.FuncAnimation(
        streamer.fig, 
        streamer.update_plot, 
        interval=1000 // streamer.scanRate,  # Update at scan rate
        cache_frame_data=False,
        blit=False
    )
    
    plt.tight_layout(pad=3.0)
    plt.show()  # This blocks until window is closed

    # Cleanup when animation window closes
    streamer.stop_scanning(None, None)

if __name__ == "__main__":
    main()