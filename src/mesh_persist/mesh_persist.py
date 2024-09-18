"""Base mesh_persist class.

This module connects to MQTT and subscribes to a topic/set of topics, and
persists specific types of messages to the database.
"""

import logging
import sys
from configparser import ConfigParser
from typing import Any

import paho
import paho.mqtt.client as mqtt
from google.protobuf.message import DecodeError
from meshtastic import mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2

from . import db_functions


class MeshPersist:
    """Main class for the meshtastic MQTT->DB gateway."""

    def __init__(self) -> None:
        """Initialization function for MeshPersist."""
        self.last_msg: dict[int, int] = {}
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)
        self.db = db_functions.DbFunctions(self.logger)

    def load_mqtt_config(self, filename: str = "mesh_persist.ini", section: str = "mqtt") -> dict:
        """Reads configfile configuration for mqtt server."""
        parser = ConfigParser()
        parser.read(filename)

        # get section, default to postgresql
        config = {}
        if parser.has_section(section):
            params = parser.items(section)
            for param in params:
                config[param[0]] = param[1]
        else:
            err = f"Section {section} not found in the {filename} file"
            self.logger.fatal(err)
            sys.exit(1)

        return config

    def on_message(  # noqa: C901
        self,
        client: paho.mqtt.client.Client,
        userdata: dict[Any, Any],
        message: paho.mqtt.client.MQTTMessage,
        properties=None,
    ) -> None:
        """Callback function when message received from MQTT server."""
        service_envelope = mqtt_pb2.ServiceEnvelope()
        try:
            service_envelope.ParseFromString(message.payload)
            self.db.insert_mesh_packet(service_envelope=service_envelope)
        except (DecodeError, Exception):
            return

        msg_pkt = service_envelope.packet
        toi = msg_pkt.rx_time
        pkt_id = msg_pkt.id
        source = getattr(msg_pkt, "from")
        if source in self.last_msg and self.last_msg[source] == pkt_id:
            self.logger.debug("dupe")
            return
        dest = msg_pkt.to
        self.last_msg[source] = pkt_id
        try:
            if not msg_pkt.decoded:
                self.logger.warning("Encrypted packets not yet handled.")
                return
            if msg_pkt.decoded.portnum == portnums_pb2.NODEINFO_APP:
                node_info = mesh_pb2.User()
                node_info.ParseFromString(msg_pkt.decoded.payload)
                self.db.insert_nodeinfo(from_node=source, nodeinfo=node_info, toi=toi)

            if msg_pkt.decoded.portnum == portnums_pb2.POSITION_APP:
                pos = mesh_pb2.Position()
                pos.ParseFromString(msg_pkt.decoded.payload)
                self.db.insert_position(from_node=source, pos=pos, toi=toi)

            if msg_pkt.decoded.portnum == portnums_pb2.NEIGHBORINFO_APP:
                message = mesh_pb2.NeighborInfo()
                self.db.insert_neighbor_info(from_node=source, neighbor_info=message, rx_time=toi)

            if msg_pkt.decoded.portnum == portnums_pb2.TELEMETRY_APP:
                tel = telemetry_pb2.Telemetry()
                tel.ParseFromString(msg_pkt.decoded.payload)
                self.db.insert_telemetry(from_node=source, packet_id=pkt_id, rx_time=toi, telem=tel)

            if msg_pkt.decoded.portnum == portnums_pb2.ROUTING_APP:
                route = mesh_pb2.Routing()
                route.ParseFromString(msg_pkt.decoded.payload)
                self.logger.debug(route)

            if msg_pkt.decoded.portnum == portnums_pb2.TEXT_MESSAGE_APP:
                text_message = msg_pkt.decoded.payload.decode("utf-8")
                self.db.insert_text_message(
                    from_node=source, to_node=dest, packet_id=pkt_id, rx_time=toi, body=text_message
                )
        except (DecodeError, Exception):
            self.logger.exception("Failed to decode an on air message.  Punting on it.")
            return

    def on_connect(
        self,
        client: paho.mqtt.client.Client,
        userdata: dict[Any, Any],
        flags: paho.mqtt.client.ConnectFlags,
        reason_code: paho.mqtt.reasoncodes.ReasonCode,
        properties=None,
    ) -> None:
        """Callback function on connection to MQTT server."""
        config = client.user_data_get()
        log_msg = "Connected, subscribing to %s...", config.get("topic")
        self.logger.info(log_msg)
        client.subscribe(config.get("topic"))

    def on_subscribe(
        self,
        client: paho.mqtt.client.Client,
        userdata: dict[Any, Any],
        mid: int,
        qos: tuple[int, ...],
        properties: None = None,
    ) -> None:
        """Callback function on subscription to topic."""
        self.logger.info("Subscribed with QoS %s", qos)

    def main(self) -> None:
        """Main entry point for mesh_persist.

        This is the primary entry point, and sets up an infinite loop waiting
        for messages from the MQTT broker
        """
        self.logger.info("Starting mesh-persist.")
        self.logger.debug("Loading MQTT config")
        mqtt_config = self.load_mqtt_config()
        broker = str(mqtt_config.get("broker"))
        broker_port = int(str(mqtt_config.get("port")))
        broker_user = mqtt_config.get("user")
        broker_pass = mqtt_config.get("pass")

        self.db = db_functions.DbFunctions(self.logger)

        self.logger.debug("Initializing MQTT connection")
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, transport="tcp", protocol=mqtt.MQTTv311, clean_session=True
        )
        client.username_pw_set(broker_user, broker_pass)
        client.user_data_set(mqtt_config)
        client.on_message = self.on_message
        client.on_connect = self.on_connect
        client.on_subscribe = self.on_subscribe

        client.connect(broker, port=broker_port, keepalive=60)

        client.loop_forever()


def main() -> None:
    """Main entry point."""
    mp = MeshPersist()
    mp.logger.info("This is the beginning")
    mp.main()
