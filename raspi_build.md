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
sudo apt install -y postgresql postgresql-client postgresql-postgis postgis libpq-dev
# install the MQTT server and client
sudo apt install -y mosquitto mosquitto-clients mosquitto-dev
# install podman so we can run the Web interface for meshtastic
sudo apt install -y podman
# finally, we're going to need python dev files and screen
sudo apt install python3-dev screen
```
now we pull and run the meshtastic web interface via a container
 this comes straight from the README @ the [Meshtastic Web](https://github.com/meshtastic/web) repo
 this may take >5 minutes to complete.  Be patient.
```
podman run -d -p 8080:8080 -p 8443:8443 --restart always --name Meshtastic-Web ghcr.io/meshtastic/web
podman generate systemd --new --name Meshtastic-Web --files
mkdir -p ~/.config/systemd/user
mv ~/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable container-Meshtastic-Web.service 
systemctl --user enable podman-restart.service
sudo loginctl enable-linger
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
```

Now, go through the steps in the README.md for mesh_persist.  That will get all of your database tables set up.  After you've done that, come back here.

--- TIME PASSES ---

Now that the DB is set up, we need to set up the mesh_persist.ini file, and we're ready to run the persister.
```
sed -i "s/MQTT_BROKER/localhost/g" mesh_persist.ini
mqtt_pw=$(cut -d: -f 2 ~/mqtt_pw)
sed -i "s/MQTT_PASSWORD/${mqtt_pw}/g" mesh_persist.ini
```

Now, the only thing left is to set up the Meshtastic Node to talk to our Access Point and send MQTT to our broker.  
Connect to the meshtastic node with your phone.  First, we'll set up networking, and then we'll use the meshtastic CLI or the web interface to set up MQTT.  
Go to the Radio Config->Network menu on your phone.  
Enable wifi  
Set the SSID to meshspot  
set the PSK to your password (in my demo, it's 87654321)  
SEND IT... your node will reboot.  
Now, we wait.  Sometimes 30 second, sometimes 90.  Life is short, enjoy the break....  
```
sudo cat /var/lib/NetworkManager/dnsmasq-wlan0.leases
echo -n "The Raspi IP ADDRESS is "
ip addr show dev wlan0 | grep inet | cut -d " " -f 6
```
That file SHOULD contain the IP address of your mesh node.  In my case, it's on a line that looks like this
```
1730419766 58:bf:25:05:6d:48 10.42.0.78 esp32-056D48 01:58:bf:25:05:6d:48
```
The important part is that IP address.  

From a web browser on a machine that can access the network that the node is on (i.e. the meshspot 10.x.x.x network), connect to the [Meshtastic Web Interface](http://meshdb.local:8080)  
Click '+ New Connection' in the middle of the screen, and in the HTTP tab, enter the IP address you got from the dnsmasq leases file above.  Click connect.  
If you've lived a good, virtuous life and never kicked a puppy, you should be connected to your node via the HTTP interface.  In the Navigation bar on the left, click Config.  
When the menu changes, click "Module Config" in the "Config Sections" menu.  That will bring up the MQTT menu.  
Click the "Enabled" slider.  
Set the MQTT Server address to the IP address for the wlan0 interface of the Pi (it was printed in a line that says "The Raspi IP ADDRESS IS").  Leave off the netmask descriptor (/24)  
The MQTT username:password is here.  `cat ~/mqtt_pw`  
Finally, set the "Map Reporting Enabled" slider to ON and click the floppy-disk SAVE icon in the upper right corner.  The node will reboot.  
    
As the final step, we need to enable MQTT upload from the channel.  In the navigation bar on the left, go down to "Channels"  
In the Primary channel (the one that comes up first), set the "Uplink Enabled" slider to ON.  
Probably won't hurt to set "Precise Location" on, as well.  
Click Submit.  

At this point, it probably wouldn't hurt to restart the raspberry pi with a 'sudo reboot' command.  We've done a lot to it, and we want to make sure it all "stuck".
Once the Pi comes back up, run `sudo tail /var/log/mosquitto.log` and you should see something like
>1730418765: New connection from 10.42.0.78:61945 on port 1883.  
>1730418765: New client connected from 10.42.0.78:61945 as !25056d48 (p2, c1, k15, u'mesh_rw').
    
if you see
> 1730418727: New connection from 10.42.0.78:51592 on port 1883.  
>1730418727: Client <unknown> disconnected, not authorised.

You probably fat-fingered the MQTT password on the meshtastic node.  Go back and try again.  
Until you see the `client connected` line, don't go any further.  You need to fix whatever is broken.





