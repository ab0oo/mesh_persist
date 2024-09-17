"""Base mesh_persist class.

This module connects to MQTT and subscribes to a topic/set of topics, and
persists specific types of messages to the database.
"""
import logging
from configparser import ConfigParser
from sys import exit

import db_functions
import paho.mqtt.client as mqtt
from google.protobuf.message import DecodeError
from meshtastic import mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2

last_msg = {}

def load_mqtt_config(filename:str="mesh_persist.ini", section:str="mqtt") -> dict:
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
        logging.fatal(err)
        exit(1)

    return config

def on_message(client: any, userdata: any, message: any, properties=None) -> None: # noqa: ARG001
    """Callback function when message received from MQTT server."""
#    logging.info("Received message "+ str(message.payload)
#           + " on topic '"+ message.topic
#           + "' with QOS " + str(message.qos))
    service_envelope = mqtt_pb2.ServiceEnvelope()
    try:
        service_envelope.ParseFromString(message.payload)
        db_functions.insert_mesh_packet(service_envelope)
    except (DecodeError, Exception):
        logging.exception("Unable to decode protobuf from %s", service_envelope["from"])

    msg_pkt = service_envelope.packet
    toi = msg_pkt.rx_time
    pkt_id = msg_pkt.id
    source = getattr(msg_pkt, "from")
    if source in last_msg and last_msg[source] == pkt_id:
            logging.debug("dupe")
            return
    dest = msg_pkt.to
    last_msg[source] = pkt_id
    if not msg_pkt.decoded:
        logging.warning("Encrypted packets not yet handled.")
        return

    if msg_pkt.decoded.portnum == portnums_pb2.NODEINFO_APP:
        node_info = mesh_pb2.User()
        node_info.ParseFromString(msg_pkt.decoded.payload)
        db_functions.insert_nodeinfo(source, node_info, toi)

    if msg_pkt.decoded.portnum == portnums_pb2.POSITION_APP:
        pos = mesh_pb2.Position()
        pos.ParseFromString(msg_pkt.decoded.payload)
        db_functions.insert_position(source, pos, toi)

    if msg_pkt.decoded.portnum == portnums_pb2.NEIGHBORINFO_APP:
        message = mesh_pb2.NeighborInfo()
        message.ParseFromString(msg_pkt.decoded.payload)
        db_functions.insert_neighbor_info(source, message.neighbors, toi)

    if msg_pkt.decoded.portnum == portnums_pb2.TELEMETRY_APP:
        tel = telemetry_pb2.Telemetry()
        tel.ParseFromString(msg_pkt.decoded.payload)
        db_functions.insert_telemetry(source, pkt_id, toi, tel)

    if msg_pkt.decoded.portnum == portnums_pb2.ROUTING_APP:
        route = mesh_pb2.Routing()
        route.ParseFromString(msg_pkt.decoded.payload)
        logging.debug(route)

    if msg_pkt.decoded.portnum == portnums_pb2.TEXT_MESSAGE_APP:
        text_message = msg_pkt.decoded.payload.decode("utf-8")
        db_functions.insert_text_message(source, dest, pkt_id, toi, text_message)

def on_connect(client:any, userdata:any, flags:any, reason_code:any, properties=None) -> None: # noqa: ARG001
    """Callback function on connection to MQTT server."""
    logging.info("Connected, subscribing...")
    client.subscribe(topic="msh/2/e/#")

def on_subscribe(client:any, userdata:any, mid:any, qos:any, properties:None=None) -> None: # noqa: ARG001
    """Callback function on subscription to topic."""
    logging.info("Subscribed with QoS %s", qos)

if __name__ == "__main__":
    mqtt_config = load_mqtt_config()
    broker = mqtt_config.get("broker")
    broker_port = mqtt_config.get("port")
    broker_user = mqtt_config.get("username")
    broker_pass = mqtt_config.get("password")

    client = mqtt.Client(client_id="pytest",
                        transport="tcp",
                        protocol=mqtt.MQTTv311,
                        clean_session=True)
    client.username_pw_set(broker_user, broker_pass)
    client.on_message = on_message
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe

    client.connect(broker, port=broker_port, keepalive=60)

    client.loop_forever()
