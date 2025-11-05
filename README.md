# NovAtel OEM7 Driver
[**ROS**](https://www.ros.org) Driver for [**NovAtel**](https://www.novatel.com) OEM7 GNSS/SPAN Receivers.  

## Getting Started
This documents how to custom-build the novatel_oem7_driver for ROS from the provided source code. Typical users will prefer to 
install the pre-made binary release that has been published in the ROS distribution.

Refer to our documentation under the ROS community wiki for:
 * Hardware Setup
 * Binary Driver Installation
 * Driver Configuration
 * Driver Runtime Operation
 * Post-Processing data
 * Information on Relevant NovAtel Services and Products
 * Advanced Topics

novatel_oem7_driver documentation on ROS community wiki is located here:
http://wiki.ros.org/novatel_oem7_driver

<HR>

## Building novatel_oem7_driver from source code
### Prerequisites
* Install ROS Noetic, Melodic or Kinetic.
* Obtain OEM7 receiver.  


### Installation
#### Option A: Install binary package
There is substantial documention regarding use of the binary release of this driver on the ROS community wiki, located here:
https://wiki.ros.org/novatel_oem7_driver

The key step is:
```
sudo apt install ros-${ROS_DISTRO}-novatel-oem7-driver
```

Please refer to the Community Wiki for detailed run-time documentation for novatel_oem7_driver (link given above).


#### Option B: Build from source (docker)
These instructions assume that you are using Ubuntu 18.04.

1. Install Docker, add the user you intend on using to the 'docker' group. For example:
   1. Add the current user to the 'docker' group: `sudo usermod -aG docker ${USER}`
   1. Apply the membership changes to the current session: `su - ${USER}`
1. From the base directory of the repository, create container for the desired ROS architecture and distro, e.g. Noetic:  
   `./docker/run.sh -r amd64 noetic`  
   Note: only amd64 architecture is supported at this point.  
1. From within your docker container (where the prompt from above should land), run `./build.sh -f`

#### Option C: Build from source (local environment)
Here are approximate instructions for building this driver with your local ROS development environment. Please note this is for reference. The Docker approach is recommended.

1. Install ROS with developer support to your environment ([**ROS Wiki Ubuntu 18.04**](http://wiki.ros.org/Installation/Ubuntu))
1. Install ROS dependencies using `rosdep install --from-paths src --ignore-src -r -y`
1. Set `ROS_DISTRO` environment variable (Ex: `ROS_DISTRO=noetic`)
1. Run `source /opt/ros/${ROS_DISTRO}/setup.bash`
1. Run `source envsetup.sh`
1. Run build: `./build.sh -f`

#### Install .deb packages 
Building produces two deb package, novatel-oem7-driver and novatel-oem7-msgs.

You can then install these via `apt` or `dpkg`:
```
sudo apt install ./ros-{$ROS_DISTRO}-novatel-oem7*.deb
```

## Standalone USB GPS Monitor
The repository includes a minimal Python 3 helper that locates a connected GPS receiver on the USB serial ports and streams the raw sentences it receives. It does not depend on any third-party libraries.

```
python3 src/novatel_oem7_driver/tools/usb_gps_monitor.py
```

Run the script with the GPS connected. It will scan `/dev/ttyUSB*` and `/dev/ttyACM*`, probe common baud rates, and print the detected data. If no device is found, ensure your user has permission to access the serial port (usually by being a member of the `dialout` group on Ubuntu).

### USB GPS Init + Monitor
Run a single script to send a minimal initialization sequence and immediately stream the receiver output:

```
python3 src/novatel_oem7_driver/tools/gps_run.py
```

It defaults to `/dev/ttyUSB1` at 115200 baud, printing any NMEA-style lines it receives. Use `--nmea-only` to filter the output, or `--no-init` if you only want to monitor.

### USB GPS Initializer
To replay the full NovAtel initialization commands from the driver configuration, use:

```
python3 src/novatel_oem7_driver/tools/gps_init.py
```

The script loads the command sequences from `config/std_init_commands.yaml` and `config/ext_parameteres.yaml`, writes them to the serial port, and prints any responses. Options such as `--port`, `--baud`, `--timeout`, or `--list-only` are available; run with `-h` for details.

## ROS2 Bag Analyzer
`src/novatel_oem7_driver/test/oem7_message_test.py` now targets ROS 2 Humble. Source your ROS 2 environment (for example `source /opt/ros/humble/setup.bash`) and point it at a rosbag2 recording:

```
python3 -c "import oem7_message_test as omt; omt.analyze_hz('path/to/bag_directory', output_csv=False)"
```

If the bag resides under `~/.ros`, you can pass just the directory name. Setting `output_csv=True` writes CSV summaries alongside the recording.

## Next Steps
Refer to the novatel_oem7_driver documentation in the ROS wiki for more information:
http://wiki.ros.org/novatel_oem7_driver


## Authors

* [**NovAtel**](https://www.novatel.com), part of [**Hexagon**](https://hexagon.com)


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details
