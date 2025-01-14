import struct

class DataRecord:
    def __init__(self, timestamp, digitalStatus, lightStatus, wheel, pulse, camera):
        self.timestamp = timestamp
        self.digitalStatus = digitalStatus
        self.lightStatus = lightStatus
        self.wheel = wheel
        self.pulse = pulse
        self.camera = camera

    def __repr__(self):
        return (f"DataRecord(timestamp={self.timestamp}, digitalStatus={self.digitalStatus}, "
                f"lightStatus={self.lightStatus}, wheel={self.wheel}, pulse={self.pulse}, camera={self.camera})")

    def to_binary(self):
        # Pack lightStatus, pulse, and camera into a single byte
        bool_byte = (self.lightStatus << 2) | (self.pulse << 1) | self.camera
        return struct.pack('<Q B f B', self.timestamp, self.digitalStatus, self.wheel, bool_byte)

    @staticmethod
    def from_binary(data):
        unpacked_data = struct.unpack('<Q B f B', data)
        timestamp, digitalStatus, wheel, bool_byte = unpacked_data
        lightStatus = (bool_byte >> 2) & 1
        pulse = (bool_byte >> 1) & 1
        camera = bool_byte & 1
        return DataRecord(timestamp, digitalStatus, lightStatus, wheel, pulse, camera)

def read_next_record(file):
    record_size = struct.calcsize('<Q B f B')
    record_data = file.read(record_size)
    if not record_data:
        return None
    return DataRecord.from_binary(record_data)

def save_to_csv(csv_writer, record):
    csv_writer.writerow([
        record.timestamp,
        record.digitalStatus,
        record.lightStatus,
        f"{record.wheel:.3f}",
        int(record.pulse),
        int(record.camera)
    ])