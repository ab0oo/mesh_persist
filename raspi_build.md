# Raspberry Pi Setup #

### Using Mesh Persist with a Raspberry Pi  ###

This guide is intended to completely set up a Raspberry Pi (or other Linux-based computer) as a complete stand-alone mesh-network control center.  It will take you from a completely fresh, out-of-the-box Raspberry Pi to a working web-server providing situational awareness, mapping, and long-term persistence of the mesh network state.

For starters, get yourself a Raspberry Pi.  For this particular project, anything from an RPi 3B+ to whatever the current model will be fine.  Also, get a high-quality SD card, because databases aren't kind to SD cards.  Google searching "Best Raspberry Pi SD Card for < year >" should lead you in the right direction.  16 or 32 GB should be ample for what we're doing.

Start with a fresh install of the Raspberry Pi OS, which is a Debian derivative.  I recommend using the [Raspberry Pi Imager](https://www.raspberrypi.com/software/).

Under the Operating System menu, select "Raspberry Pi OS (other)->Raspberry Pi OS Lite (64-bit)".
Make sure you "edit settings" before writing the OS to the SD card.  Set the hostname to something sensible, like `meshdb`.  The initial connections to the RasPi will need to be over ethernet, not WiFi.  We'll be using the WiFi on board the Pi as an access point for the Meshtastic device(s) to connect to.
Finally, make sure you enable SSH (under services).

Once you've booted the Pi for the first time, we need to start by installing software and setting up the Python virtual environment.
```
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
sudo apt install -y git
git clone https://github.com/ab0oo/mesh_persist
# install the PostgreSQL RDBMS and the Postgis geospatial addons
sudo apt install -y postgresql postgresql-client postgresql-postgis postgis
# install the MQTT server and client
sudo apt install -y mosquitto mosquitto-clients mosquitto-dev
# install podman so we can run the Web interface for meshtastic
sudo apt install -y podman
```
now we pull and run the meshtastic web interface via a container
 this comes straight from the README @ the [Meshtastic Web](https://github.com/meshtastic/web) repo
 this may take >5 minutes to complete.  Be patient.
```
podman run -d -p 8080:8080 -p 8443:8443 --restart always --name Meshtastic-Web ghcr.io/meshtastic/web
```

Next, we'll set up the WiFi on the RasPi as an access point.
```
sudo apt install -y hostapd dnsmasq
sudo systemctl stop hostapd
sudo systemctl stop dnsmasq
sudo systemctl disable hostapd
sudo systemctl disable dnsmasq
## set up the actual hotspot.  the SSID and password are up to you, but don't lose/forget them
sudo nmcli d wifi hotspot ifname wlan0 ssid meshspot password 87654321
sudo nmcli con mod hotspot connection.autoconnect true
```

Now, we need to set up the mqtt authentication.
```
export mqtt_pw=$( date | md5sum | head -c 12)
echo "mesh_rw:$mqtt_pw" > mqtt_pw
sudo mosquitto_passwd -c -b /etc/mosquitto/pwfile mesh_rw ${mqtt_pw}
cat << EOF | sudo tee /etc/mosquitto/conf.d/mesh.conf
listener 1883
allow_anonymous false
password_file /etc/mosquitto/pwfile
EOF
sudo systemctl restart mosquitto.service