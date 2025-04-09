# mesh_persist
Persistence tools for Meshtastic/MQTT integration

This is a set of tools anf configurations that will allow you to pull data from any Meshtastic MQTT feed
and persist that data to a well-structured relational database for further analysis.  It is relatively
easy to set up and uses standard PyPI python libraries.
It can be run on a Raspberry Pi to provide a complete, local/disconnected information system.  Instructions can be found in [raspi_build.md](raspi_build.md)

To set up this python project:
```
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -e .
```
n.b. you will need the postgresql dev package installed to build psycopg.  On Debian/Ubuntu:
`apt get install libpq-dev`

To run in development mode, straight from the src tree, use `python3 -m src.main` from the root of the project.

This project assumes you have a working Postgresql database set up on a reachable host, and have installed the PostGIS
Spatial Reference addons.  Begin by creating a pair of new users, mesh_ro and mesh_rw, and remember their passwords.
```
export db_host="localhost" # put the hostname of your Postgres server here
export db_port="5432" # this is the default postgres port
export rw_pw=$( date | md5sum | head -c 12)
sleep 2
export ro_pw=$( date | md5sum | head -c 12)
touch ~/.pgpass
chmod 600 ~/.pgpass
echo "$db_host:$db_port:meshtastic:mesh_ro:$ro_pw" >> ~/.pgpass
echo "$db_host:$db_port:meshtastic:mesh_rw:$rw_pw" >> ~/.pgpass
sudo -u postgres createuser -s -d -l mesh_rw
sudo -u postgres psql -c "alter user mesh_rw with password '${rw_pw}'"
sudo -u postgres createuser -s -d -l mesh_ro
sudo -u postgres psql -c "alter user mesh_ro with password '${ro_pw}'"
PGPASSWORD=${rw_pw} createdb -h $db_host -p $db_port -U mesh_rw meshtastic
PGPASSWORD=${rw_pw} psql -h ${db_host} -p ${db_port} -U mesh_rw meshtastic -f db/meshtastic.sql
sed "s/PG_PASSWORD/${pg_rw}/g" mesh_persist.ini.template > mesh_persist.ini
sed -i "s/PG_HOST/${db_host}/g" mesh_persist.ini
sed -i "s/PG_PORT/${db_port}/g" mesh_persist.ini
# EDIT mesh_persist.ini to set your MQTT server information!!
```

If you're ambitious and have lots of DB disk space, you can take the full feed from the meshtastic core server.
To do so, use this in your mesh_persist.ini:
```
[mqtt]
broker=mqtt.meshtastic.org
port=1883
user=meshdev
pass=large4cats
topic=msh/#
```
For finer control over the stream, use the apprpriate country code, state, and region code for your area, i.e.:
`topic=msh/US/CA/SacValley`

