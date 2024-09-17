"""Base mesh_persist class.

This module connects to MQTT and subscribes to a topic/set of topics, and
persists specific types of messages to the database.
"""

import logging
from configparser import ConfigParser
from sys import exit

import paho.mqtt.client as mqtt
from google.protobuf.message import DecodeError
from meshtastic import mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2

from . import db_functions

last_msg = {}

class MeshPersist:
    """Main class for the meshtastic MQTT->DB gateway."""
    def __init__(self)-> None:
        """Initialization function for MeshPersist."""
        self.db = None
        self.logger = logging.getLogger(__name__)
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)


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
            exit(1)

        return config


    def on_message(self, client: any, userdata: any, message: any, properties=None) -> None:
        """Callback function when message received from MQTT server."""
        #    logging.info("Received message "+ str(message.payload)
        #           + " on topic '"+ message.topic
        #           + "' with QOS " + str(message.qos))
        service_envelope = mqtt_pb2.ServiceEnvelope()
        try:
            service_envelope.ParseFromString(message.payload)
            self.db.insert_mesh_packet(service_envelope)
        except (DecodeError, Exception):
            return

        msg_pkt = service_envelope.packet
        toi = msg_pkt.rx_time
        pkt_id = msg_pkt.id
        source = getattr(msg_pkt, "from")
        if source in last_msg and last_msg[source] == pkt_id:
            self.logger.debug("dupe")
            return
        dest = msg_pkt.to
        last_msg[source] = pkt_id
        if not msg_pkt.decoded:
            self.logger.warning("Encrypted packets not yet handled.")
            return
        logging.debug("Incoming packet")
        if msg_pkt.decoded.portnum == portnums_pb2.NODEINFO_APP:
            node_info = mesh_pb2.User()
            node_info.ParseFromString(msg_pkt.decoded.payload)
            self.db.insert_nodeinfo(source, node_info, toi)

        if msg_pkt.decoded.portnum == portnums_pb2.POSITION_APP:
            pos = mesh_pb2.Position()
            pos.ParseFromString(msg_pkt.decoded.payload)
            self.db.insert_position(source, pos, toi)

        if msg_pkt.decoded.portnum == portnums_pb2.NEIGHBORINFO_APP:
            message = mesh_pb2.NeighborInfo()
            message.ParseFromString(msg_pkt.decoded.payload)
            self.db.insert_neighbor_info(source, message.neighbors, toi)

        if msg_pkt.decoded.portnum == portnums_pb2.TELEMETRY_APP:
            tel = telemetry_pb2.Telemetry()
            tel.ParseFromString(msg_pkt.decoded.payload)
            self.db.insert_telemetry(source, pkt_id, toi, tel)

        if msg_pkt.decoded.portnum == portnums_pb2.ROUTING_APP:
            route = mesh_pb2.Routing()
            route.ParseFromString(msg_pkt.decoded.payload)
            self.logger.debug(route)

        if msg_pkt.decoded.portnum == portnums_pb2.TEXT_MESSAGE_APP:
            text_message = msg_pkt.decoded.payload.decode("utf-8")
            self.db.insert_text_message(source, dest, pkt_id, toi, text_message)


    def on_connect(self, client: any, userdata: any, flags: any, reason_code: any, properties=None) -> None:
        """Callback function on connection to MQTT server."""
        config = client.user_data_get()
        log_msg = "Connected, subscribing to %s...", config.get("topic")
        self.logger.info(log_msg)
        client.subscribe(config.get("topic"))


    def on_subscribe(self, client: any, userdata: any, mid: any, qos: any, properties: None = None) -> None:
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
        broker = mqtt_config.get("broker")
        broker_port = int(mqtt_config.get("port"))
        broker_user = mqtt_config.get("user")
        broker_pass = mqtt_config.get("pass")

        self.db = db_functions.DbFunctions(self.logger)

        self.logger.debug("Initializing MQTT connection")
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             transport="tcp", protocol=mqtt.MQTTv311, clean_session=True)
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
    mp.main()
