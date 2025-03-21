"""Base mesh_persist class.

This module connects to MQTT and subscribes to a topic/set of topics, and
persists specific types of messages to the database.
"""

import logging
import sys
from configparser import ConfigParser
from typing import Any, ClassVar

import paho
import paho.mqtt.client as mqtt
from google.protobuf.message import DecodeError
from meshtastic import mesh_pb2, mqtt_pb2, portnums_pb2, protocols

from . import db_functions


class MeshPersist:
    """Main class for the meshtastic MQTT->DB gateway."""

    msg_queue: ClassVar[list[Any]] = []

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

    def on_message(  # noqa: C901  PLR0911 PLR0912 PLR0915
        self,
        client: paho.mqtt.client.Client,
        userdata: dict[Any, Any],
        message: paho.mqtt.client.MQTTMessage,
        properties=None,
    ) -> None:
        """Callback function when message received from MQTT server."""
        service_envelope = mqtt_pb2.ServiceEnvelope()
        if service_envelope is not None:
            try:
                service_envelope.ParseFromString(message.payload)
            except (DecodeError, Exception):
                self.logger.exception("Exception in initial Service Envelope decode")
                return
        else:
            return

        msg_pkt = service_envelope.packet
        portnum = msg_pkt.decoded.portnum
        toi = msg_pkt.rx_time
        pkt_id = msg_pkt.id
        gateway_id = service_envelope.gateway_id
        source = getattr(msg_pkt, "from")
        # we don't care to store map_report msgs, because they are locally generated and
        # will violate the unique key of the mesh_packets table.  We'll deal with them
        # separately
        if portnums_pb2.PortNum.Name(portnum) != "MAP_REPORT_APP":
            self.db.insert_mesh_packet(service_envelope=service_envelope)
            logline = "Portnum " + str(portnum) + " from GW " + str(gateway_id)
            self.logger.debug(logline)
        if source in self.last_msg and self.last_msg[source] == pkt_id:
            self.logger.debug("dupe")
            return
        dest = msg_pkt.to
        self.last_msg[source] = pkt_id

        handler = protocols.get(msg_pkt.decoded.portnum)
        if type(handler) is None or handler is None:
            return
        if handler.protobufFactory is not None:
            pb = handler.protobufFactory()
            try:
                pb.ParseFromString(msg_pkt.decoded.payload)
            except Exception:
                self.logger.exception("Unable to parse Service Envelope")
                return
        dbg = (
            db_functions.id_to_hex(source)
            + "->"
            + db_functions.id_to_hex(dest)
            + ":  "
            + portnums_pb2.PortNum.Name(portnum)
        )
        self.logger.info(dbg)

        self.msg_queue.append(msg_pkt)

        if not self.db.test_connection():
            return

        while len(self.msg_queue) > 0:
            msg_pkt = self.msg_queue.pop(0)

            try:
                if not msg_pkt.decoded:
                    self.logger.warning("Encrypted packets not yet handled.")
                    return
                if msg_pkt.decoded.portnum == portnums_pb2.NODEINFO_APP:
                    self.db.insert_nodeinfo(from_node=source, nodeinfo=pb, toi=toi)

                if msg_pkt.decoded.portnum == portnums_pb2.POSITION_APP:
                    self.db.insert_position(from_node=source, pos=pb, toi=toi)

                if msg_pkt.decoded.portnum == portnums_pb2.NEIGHBORINFO_APP:
                    self.db.insert_neighbor_info(from_node=source, neighbor_info=pb, rx_time=toi)

                if msg_pkt.decoded.portnum == portnums_pb2.TELEMETRY_APP:
                    self.db.insert_telemetry(from_node=source, packet_id=pkt_id, rx_time=toi, telem=pb)

                if msg_pkt.decoded.portnum == portnums_pb2.ROUTING_APP:
                    route = mesh_pb2.Routing()
                    route.ParseFromString(msg_pkt.decoded.payload)
                    self.logger.debug(route)

                if msg_pkt.decoded.portnum == portnums_pb2.TEXT_MESSAGE_APP:
                    text_message = msg_pkt.decoded.payload.decode("utf-8")
                    self.db.insert_text_message(
                        from_node=source, to_node=dest, packet_id=pkt_id, rx_time=toi, body=text_message
                    )

                if msg_pkt.decoded.portnum == portnums_pb2.MAP_REPORT_APP:
                    map_report = mqtt_pb2.MapReport()
                    map_report.ParseFromString(msg_pkt.decoded.payload)

            except (DecodeError, Exception):
                self.logger.exception("Failed to decode an on air message.  Punting on it.")

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
        topic = config.get("topic")
        log_msg = f"Connected, subscribing to {topic}..."
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
    mp.main()
