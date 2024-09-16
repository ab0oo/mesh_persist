import psycopg2
import time
import traceback
from configparser import ConfigParser
from meshtastic import portnums_pb2, mesh_pb2, config_pb2, telemetry_pb2

def hexToId(nodeId):
    n = nodeId.replace("!", "0x")
    return int(n,0)

def idToHex(nodeId):
    return '!' + hex(nodeId)[2:]

def load_config(filename='database.ini', section='postgresql'):
    parser = ConfigParser()
    parser.read(filename)

    # get section, default to postgresql
    config = {}
    if parser.has_section(section):
        params = parser.items(section)
        for param in params:
            config[param[0]] = param[1]
    else:
        raise Exception('Section {0} not found in the {1} file'.format(section, filename))

    return config

def connect(config):
    """ Connect to the PostgreSQL database server """
    try:
        # connecting to the PostgreSQL server
        with psycopg2.connect(**config) as conn:
            print('Connected to the PostgreSQL server.')
            return conn
    except (psycopg2.DatabaseError, Exception) as error:
        print(error)

def insert_mesh_packet(service_envelope):
    mp=service_envelope.packet
    pn = getattr(mp.decoded, 'portnum')
    portnum = portnums_pb2.PortNum.Name(pn)
    source = getattr(mp, 'from')
    dest = getattr(mp, 'to')
    print( idToHex(source)+"->"+idToHex(dest)+":  "+portnum )
    sql = """INSERT INTO mesh_packets (source, dest, packet_id, channel, rx_snr, rx_rssi,
             hop_limit, hop_start, portnum, toi, channel_id, gateway_id )
             VALUES(%s, %s, %s, %s, %s, 
                    %s, %s, %s, %s, to_timestamp(%s),
                    %s, %s);"""
    config = load_config()
    try:
        with  psycopg2.connect(**config) as conn:
            with  conn.cursor() as cur:
                if not mp.hop_start:
                    mp.hop_start = 3
                if not mp.hop_limit:
                    mp.hop_limit = 0
                if not mp.rx_time:
                    mp.rx_time = time.time()
                # execute the INSERT statement
                cur.execute(sql, (getattr(mp,'from'), mp.to,
                                  mp.id, 8, mp.rx_snr,
                                  mp.rx_rssi, mp.hop_limit,
                                  mp.hop_start,
                                  portnum,
                                  mp.rx_time,
                                  service_envelope.channel_id,
                                  hexToId(service_envelope.gateway_id)))
                # commit the changes to the database
                conn.commit()
    except (Exception, psycopg2.DatabaseError) as error:
        print("Got an error on node_insertion:  ",error)
        traceback.print_exc()

def insert_nodeinfo(from_node, nodeinfo, toi):
    upsert_sql = """INSERT INTO node_infos (node_id, long_name, short_name,
                     mac_addr, hw_model, role, created_at, updated_at)
                    VALUES(%s, %s, %s, %s, %s, %s, to_timestamp(%s), to_timestamp(%s))
                    ON CONFLICT (node_id, long_name, short_name)
                    DO UPDATE
                    SET updated_at=to_timestamp(%s)
                    WHERE node_infos.long_name = %s
                    AND node_infos.short_name = %s
                    AND node_infos.role = %s
                    AND node_infos.node_id = %s"""
    config = load_config()
    try:
        with  psycopg2.connect(**config) as conn:
            with  conn.cursor() as cur:
                role = config_pb2.Config.DeviceConfig.Role.Name(nodeinfo.role)
                hw = mesh_pb2.HardwareModel.Name(nodeinfo.hw_model)
                cur.execute(upsert_sql, (from_node, 
                                            nodeinfo.long_name, 
                                            nodeinfo.short_name, 
                                            nodeinfo.macaddr, 
                                            hw, 
                                            role,
                                            toi, toi,
                                         toi, nodeinfo.long_name, 
                                            nodeinfo.short_name, 
                                            role, 
                                            from_node,))
                print("NodeInfo upserted")
                conn.commit()
    except (Exception, psycopg2.DatabaseError) as error:
        print('Exception storing nodeinfo')
        traceback.print_exc()

def insert_position(from_node, pos, toi):
    upsert_sql = """INSERT INTO node_positions 
                      (node_id, created_at, updated_at, latitude, longitude, altitude)
                      VALUES(%s, to_timestamp(%s), to_timestamp(%s), %s, %s, %s)
                    ON CONFLICT (node_id, latitude, longitude)
                    DO
                      UPDATE SET updated_at = to_timestamp(%s) 
                      WHERE node_positions.node_id=%s 
                      and node_positions.latitude=%s
                      and node_positions.longitude=%s"""
    config = load_config()
    try:
        with  psycopg2.connect(**config) as conn:
            with  conn.cursor() as cur:
                cur.execute(upsert_sql, (from_node,
                                             toi, toi,
                                             pos.latitude_i, 
                                             pos.longitude_i, 
                                             pos.altitude,
                                         toi, 
                                         from_node, 
                                         pos.latitude_i, 
                                         pos.longitude_i,))
                print("Upserted position")
                # commit the changes to the database
                conn.commit()
    except (Exception, psycopg2.DatabaseError) as error:
        print("Error altering position info")
        traceback.print_exc()

def insert_neighbor_info(from_node, neighbor_info, rx_time):
    upsert_sql = """INSERT INTO neighbor_info 
                      (id, neighbor_id, snr, update_time)
                      VALUES (%s, %s, %s, to_timestamp(%s))
                    ON CONFLICT (id, neighbor_id)
                    DO
                      UPDATE SET snr=%s, update_time=to_timestamp(%s) 
                      WHERE neighbor_info.id=%s AND neighbor_info.neighbor_id=%s"""
    config = load_config()
    try:
        with  psycopg2.connect(**config) as conn:
            with  conn.cursor() as cur:
                for neighbor in neighbor_info:
                    cur.execute(upsert_sql, (from_node, 
                                             neighbor.node_id, 
                                             neighbor.snr, 
                                             rx_time,
                                             neighbor.snr, 
                                             rx_time, 
                                             from_node, 
                                             neighbor.node_id,))
                # commit the changes to the database
                conn.commit()
                print(f"Upserted Neighbor Info")
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)

def insert_text_message(from_node, to_node, packet_id, rx_time, body):
    insert_sql = """INSERT INTO text_messages (source_id, destination_id, packet_id, toi, body )
                    VALUES ( %s, %s, %s, to_timestamp(%s), %s);"""
    config = load_config()
    try:
        with  psycopg2.connect(**config) as conn:
            with  conn.cursor() as cur:
                inserts=0
                cur.execute(insert_sql, (from_node, to_node, packet_id, rx_time, body,))
                inserts = cur.rowcount
                conn.commit()
    except (Exception, psycopg2.DatabaseError) as error:
        print(error)

def insert_telemetry(from_node, packet_id, rx_time, telem):
    print("Telemetry:")
    print( telem )
    print("Inserting now...")
    if telem.WhichOneof("variant") == 'device_metrics':
        sql = """INSERT INTO device_metrics ( node_id, toi, battery_level, voltage,
                 channel_util, air_util_tx, uptime_seconds )
                 VALUES ( %s, to_timestamp(%s), %s, %s, %s, %s, %s)"""
        dm = telem.device_metrics
        if not dm.battery_level:
            dm.battery_level = 0
        if not dm.voltage:
            dm.voltage = 0
        if not dm.channel_utilization:
            dm.channel_utilization=0.0
        if not dm.air_util_tx:
            dm.air_util_tx = 0.0
        if not dm.uptime_seconds:
            dm.uptime_seconds = 0
        config = load_config()
        try:
            with  psycopg2.connect(**config) as conn:
                with  conn.cursor() as cur:
                    inserts=0
                    cur.execute(sql, (from_node, rx_time, dm.battery_level, dm.voltage,
                                             dm.channel_utilization, dm.air_util_tx,
                                             dm.uptime_seconds,))
                    inserts = cur.rowcount
                    conn.commit()
        except (Exception, psycopg2.DatabaseError) as error:
            print(error)


