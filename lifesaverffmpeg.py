import cv2
import time
from collections import deque
import RPi.GPIO as GPIO
import gps
import keyboard
import os
import json
import subprocess
from datetime import datetime

# Constants
SHOCK_SENSOR_PIN = 17  # GPIO pin for the shock sensor
PRE_BUFFER_DURATION = 10  # Duration in seconds for pre-recording
POST_TRIGGER_DURATION = 5  # Duration in seconds for post-trigger recording
FPS = 20  # Frames per second

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(SHOCK_SENSOR_PIN, GPIO.IN)

# Set up video capture using OpenCV's default capture method
cap = cv2.VideoCapture(0)  # Using device 0, which corresponds to /dev/video0

# Check if the camera opened successfully
if not cap.isOpened():
    print("Error: Could not open camera.")
    GPIO.cleanup()
    exit()

# Circular buffer for pre-recording video
buffer_size = PRE_BUFFER_DURATION * FPS
video_buffer = deque(maxlen=buffer_size)

def get_lat_long():
    """Fetch 3 GPS coordinates and return them as a list in JSON format."""
    session = gps.gps(mode=gps.WATCH_ENABLE)
    lat_long_list = []

    try:
        while len(lat_long_list) < 3:
            report = session.next()
            if report['class'] == 'TPV' and hasattr(report, 'lat') and hasattr(report, 'lon'):
                lat = report.lat
                lon = report.lon
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                lat_long_list.append({"latitude": lat, "longitude": lon, "timestamp": timestamp})
                print(f"Latitude: {lat}, Longitude: {lon}, Time: {timestamp}")
                time.sleep(0.1)  # Delay between readings

    except Exception as e:
        print(f"GPS Error: {e}")

    return lat_long_list

def save_video_and_gps(video_buffer, cap):
    """Save the video and log GPS coordinates using FFmpeg for compression."""
    print("Saving video and fetching GPS coordinates...")

    # Create a folder for the event
    event_folder = datetime.now().strftime("event_%Y%m%d_%H%M%S")
    os.makedirs(event_folder, exist_ok=True)

    # GPS data as JSON
    gps_data = get_lat_long()
    gps_file_path = os.path.join(event_folder, 'gps_data.json')
    with open(gps_file_path, 'w') as f:
        json.dump(gps_data, f, indent=4)
    print(f"GPS data saved to {gps_file_path}.")

    # Start FFmpeg for real-time video compression and segment uploading
    video_path = os.path.join(event_folder, 'output_segment.mp4')
    ffmpeg_command = [
        "ffmpeg", 
        "-y",  # Overwrite output files without asking
        "-f", "rawvideo",  # Input format
        "-vcodec", "rawvideo", 
        "-pix_fmt", "bgr24",  # Input pixel format
        "-s", "640x480",  # Video resolution
        "-r", str(FPS),  # Frame rate
        "-i", "-",  # Input from stdin (pipe)
        "-c:v", "libx264",  # Use x264 codec for compression
        "-preset", "ultrafast",  # Ultra-fast encoding for real-time processing
        "-tune", "zerolatency",  # Optimize for low latency
        video_path
    ]

    # Start FFmpeg subprocess
    ffmpeg_process = subprocess.Popen(ffmpeg_command, stdin=subprocess.PIPE)
    
    # Write buffered frames (pre-recorded frames)
    for buffered_frame in list(video_buffer):
        ffmpeg_process.stdin.write(buffered_frame.tobytes())

    # Record additional frames for POST_TRIGGER_DURATION seconds
    start_time = time.time()
    while time.time() - start_time < POST_TRIGGER_DURATION:
        ret, frame = cap.read()
        if ret:
            ffmpeg_process.stdin.write(frame.tobytes())
            cv2.imshow('Camera Feed', frame)  # Optional: Show the current frame while recording
        else:
            break

    ffmpeg_process.stdin.close()
    ffmpeg_process.wait()

    print(f"Video saved as {video_path}. Now uploading...")

    # Upload video segment and GPS data using curl
    try:
        curl_command = [
            "curl",
            "-F", f"files=@{video_path}",
            "-F", f"files=@{gps_file_path}",
            "http://192.168.0.59:3000/upload"
        ]
        subprocess.run(curl_command, check=True)
        print("Files uploaded successfully.")
    except subprocess.CalledProcessError as e:
        print(f"File upload failed: {e}")

print("Monitoring for shocks...")

try:
    while True:
        # Read the state of the shock sensor
        sensor_value = GPIO.input(SHOCK_SENSOR_PIN)

        # Store frames in the circular buffer
        ret, frame = cap.read()
        if ret:
            video_buffer.append(frame)
            cv2.imshow('Camera Feed', frame)  # Display the current frame (optional)

        # Check for shock detection
        if sensor_value == GPIO.LOW:  # Shock detected
            print("Shock detected! (Value: LOW)")
            save_video_and_gps(video_buffer, cap)

        time.sleep(0.2)  # Small delay for debouncing

except KeyboardInterrupt:
    print("Exiting...")

finally:
    cap.release()  # Release camera resources
    GPIO.cleanup()  # Clean up GPIO settings on exit
    cv2.destroyAllWindows()  # Close any OpenCV windows

