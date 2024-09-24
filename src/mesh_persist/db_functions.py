"""Database Functions.

This module contains the database functions that store various types of Meshtastic packets to the PostgreSQL database.
"""

import configparser
import logging
import sys
import time
import traceback

import psycopg2
from meshtastic import config_pb2, mesh_pb2, mqtt_pb2, portnums_pb2  # type: ignore


def hex_to_id(node_id) -> int:
    """Converts a Meshtastic string node_id to a hex int."""
    n = node_id.replace("!", "0x")
    return int(n, 0)


def id_to_hex(node_id) -> str:
    """Converts a hex node_id to a Meshtastic-style node address."""
    return "!" + hex(node_id)[2:]


def load_config(filename: str = "mesh_persist.ini", section: str = "postgresql") -> dict:
    """Loads database parameters from configfile-style configuration file."""
    parser = configparser.ConfigParser()
    try:
        parser.read(filename)
        config = {}
        if parser.has_section(section):
            params = parser.items(section)
            for param in params:
                config[param[0]] = param[1]
            return config
        err = f"Section {section} not found in the {filename} file"
        logging.fatal(err)
        sys.exit(1)

    except configparser.ParsingError:
        sys.exit(1)


def connect(config: dict):  # noqa: ANN201
    """Connect to the PostgreSQL database server."""
    try:
        # connecting to the PostgreSQL server
        with psycopg2.connect(**config) as conn:
            return conn
    except (psycopg2.DatabaseError, Exception):
        sys.exit(1)


class DbFunctions:
    """Set of Postgres Database functions for the Mesh Persist Meshtastic persister."""

    def __init__(self, logger: logging.Logger) -> None:
        """Initialization function for db_functions."""
        self.logger = logger
        self.config = load_config()
        self.conn = connect(self.config)

    def insert_mesh_packet(self, service_envelope: mqtt_pb2.ServiceEnvelope) -> None:
        """Called for every received packet:  insert the base packet infomation."""
        mp = service_envelope.packet
        pn = mp.decoded.portnum
        portnum = portnums_pb2.PortNum.Name(pn)

        sql = """INSERT INTO mesh_packets (source, dest, packet_id, channel, rx_snr, rx_rssi,
                hop_limit, hop_start, portnum, toi, channel_id, gateway_id )
                VALUES(%s, %s, %s, %s, %s,
                        %s, %s, %s, %s, to_timestamp(%s),
                        %s, %s);"""
        try:
            with self.conn.cursor() as cur:
                if not mp.hop_start:
                    mp.hop_start = 3
                if not mp.hop_limit:
                    mp.hop_limit = 0
                if not mp.rx_time:
                    mp.rx_time = int(time.time())
                # execute the INSERT statement
                cur.execute(
                    sql,
                    (
                        getattr(mp, "from"),
                        mp.to,
                        mp.id,
                        0,
                        mp.rx_snr,
                        mp.rx_rssi,
                        mp.hop_limit,
                        mp.hop_start,
                        portnum,
                        mp.rx_time,
                        service_envelope.channel_id,
                        hex_to_id(service_envelope.gateway_id),
                    ),
                )
                # commit the changes to the database
                self.conn.commit()
        except (Exception, psycopg2.DatabaseError):
            self.logger.exception("Got an error on node_insertion:  ")
            traceback.print_exc()

    def insert_nodeinfo(self, from_node: str, nodeinfo: mesh_pb2.User, toi: int) -> None:
        """Called for NodeInfo packets, to insert/update existing node info."""
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
        try:
            with self.conn.cursor() as cur:
                role = config_pb2.Config.DeviceConfig.Role.Name(nodeinfo.role)
                hw = mesh_pb2.HardwareModel.Name(nodeinfo.hw_model)
                cur.execute(
                    upsert_sql,
                    (
                        from_node,
                        nodeinfo.long_name,
                        nodeinfo.short_name,
                        nodeinfo.macaddr,
                        hw,
                        role,
                        toi,
                        toi,
                        toi,
                        nodeinfo.long_name,
                        nodeinfo.short_name,
                        role,
                        from_node,
                    ),
                )
                self.logger.debug("Upserted nodeinfo")
                self.conn.commit()
        except (Exception, psycopg2.DatabaseError):
            self.logger.exception("Exception storing nodeinfo")
            traceback.print_exc()

    def insert_position(self, from_node, pos, toi) -> None:
        """Inserts Meshtastic node position data into db."""
        upsert_sql = """INSERT INTO node_positions
                        (node_id, created_at, updated_at, latitude, longitude, altitude)
                        VALUES(%s, to_timestamp(%s), to_timestamp(%s), %s, %s, %s)
                        ON CONFLICT (node_id, latitude, longitude)
                        DO
                        UPDATE SET updated_at = to_timestamp(%s)
                        WHERE node_positions.node_id=%s
                        and node_positions.latitude=%s
                        and node_positions.longitude=%s"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    upsert_sql,
                    (
                        from_node,
                        toi,
                        toi,
                        pos.latitude_i,
                        pos.longitude_i,
                        pos.altitude,
                        toi,
                        from_node,
                        pos.latitude_i,
                        pos.longitude_i,
                    ),
                )
                # commit the changes to the database
                self.conn.commit()
                self.logger.debug("Upserted position")
        except (Exception, psycopg2.DatabaseError):
            self.logger.exception("Error altering position info")
            traceback.print_exc()

    def insert_neighbor_info(self, from_node: int, neighbor_info: mesh_pb2.NeighborInfo, rx_time: int) -> None:
        """Inserts Meshtastic NeighborInfo packet data into DB."""
        upsert_sql = """INSERT INTO neighbor_info
                        (id, neighbor_id, snr, update_time)
                        VALUES (%s, %s, %s, to_timestamp(%s))
                        ON CONFLICT (id, neighbor_id)
                        DO
                        UPDATE SET snr=%s, update_time=to_timestamp(%s)
                        WHERE neighbor_info.id=%s AND neighbor_info.neighbor_id=%s"""
        try:
            with self.conn.cursor() as cur:
                for neighbor in neighbor_info.neighbors:
                    cur.execute(
                        upsert_sql,
                        (
                            from_node,
                            neighbor.node_id,
                            neighbor.snr,
                            rx_time,
                            neighbor.snr,
                            rx_time,
                            from_node,
                            neighbor.node_id,
                        ),
                    )
                # commit the changes to the database
                self.conn.commit()
                self.logger.debug("Upserted Neighbor Info")
        except (Exception, psycopg2.DatabaseError):
            self.logger.exception("Database Error")

    def insert_text_message(self, from_node, to_node, packet_id, rx_time, body) -> None:
        """Inserts meshtastic text messages into db."""
        insert_sql = """INSERT INTO text_messages (source_id, destination_id, packet_id, toi, body )
                        VALUES ( %s, %s, %s, to_timestamp(%s), %s);"""
        try:
            with self.conn.cursor() as cur:
                cur.execute(insert_sql, (from_node, to_node, packet_id, rx_time, body))
                self.conn.commit()
                self.logger.debug("Inserted text message")
        except (Exception, psycopg2.DatabaseError):
            self.logger.exception("Database Error")

    def insert_telemetry(self, from_node, packet_id, rx_time, telem) -> None:
        """Inserts various telemetry data sent via Meshtastic packets.

        XXX TODO - add additional telemetry types
        """
        if telem.WhichOneof("variant") == "device_metrics":
            sql = """INSERT INTO device_metrics ( node_id, packet_id, toi, battery_level, voltage,
                    channel_util, air_util_tx, uptime_seconds )
                    VALUES ( %s, %s, to_timestamp(%s), %s, %s, %s, %s, %s)"""
            dm = telem.device_metrics
            if not dm.battery_level:
                dm.battery_level = 0
            if not dm.voltage:
                dm.voltage = 0
            if not dm.channel_utilization:
                dm.channel_utilization = 0.0
            if not dm.air_util_tx:
                dm.air_util_tx = 0.0
            if not dm.uptime_seconds:
                dm.uptime_seconds = 0
            try:
                with self.conn.cursor() as cur:
                    cur.execute(
                        sql,
                        (
                            from_node,
                            packet_id,
                            rx_time,
                            dm.battery_level,
                            dm.voltage,
                            dm.channel_utilization,
                            dm.air_util_tx,
                            dm.uptime_seconds,
                        ),
                    )
                    self.conn.commit()
                    self.logger.debug("Inserted telemetry")
            except (Exception, psycopg2.DatabaseError):
                self.logger.exception("Database Error")
