# mesh_persist
Persistence tools for Meshtastic/MQTT integration

This is a set of tools anc configurations that will allow you to pull data from any Meshtastic MQTT feed
and persist that data to a well-structured relational database for further analysis.  It is relatively
easy to set up and uses standard PiPy python libraries.
It can be run on a Raspberry Pi to provide a complete, local/disconnected information system

This project assumes you have a working Postgresql database set up on a reachable host, and have installed the PostGIS
Spatial Reference addons.  Begin by creating a pair of new users, mesh_ro and mesh_rw, and remember their passwords.
```
export db_host="localhost"
export db_port="5432"
export rw_pw=$( date | md5sum | head -c 12)
sleep 2
export ro_pw=$( date | md5sum | head -c 12)
echo "$db_host:$db_port:meshtastic:mesh_ro:$ro_pw" >> ~/.pgpass
echo "$db_host:$db_port:meshtastic:mesh_rw:$rw_pw" >> ~/.pgpass
sudo -u postgres createuser -s -d -l mesh_rw
sudo -u postgres -c "alter user mesh_rw with password '${rw_pw}'"
PGPASSWORD=${rw_pw} createdb -h $db_host -p $db_port -U mesh_rw meshtastic
PGPASSWORD=${rw_pw} psql -h ${db_host} -p ${db_port} -U mesh_rw meshtastic -f db/meshtastic.sql
```
