from datetime import datetime as dt
from meshtastic import mesh_pb2, mqtt_pb2, portnums_pb2, telemetry_pb2
import paho.mqtt.client as mqtt
import db_functions as db_functions

last_msg = {}

def on_message(client, userdata, message, properties=None):
#    print("Received message "+ str(message.payload)
#           + " on topic '"+ message.topic
#           + "' with QOS " + str(message.qos))
    service_envelope = mqtt_pb2.ServiceEnvelope()
    try:
        service_envelope.ParseFromString(message.payload)
        db_functions.insert_mesh_packet(service_envelope)
    except (google.protobuf.message.DecodeError, Exception) as error:
        print("Unable to decode protobuf from %s", service_envelope['from'])

    msg_pkt = service_envelope.packet
    toi = msg_pkt.rx_time
    pkt_id = msg_pkt.id
    source = getattr(msg_pkt, 'from')
    if source in last_msg.keys():
        if last_msg[source] == pkt_id:
            print("dupe")
            return
    dest = getattr(msg_pkt, 'to')
    last_msg[source] = pkt_id
    if not msg_pkt.decoded:
        print("Encrypted packets not yet handled.")
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
        print(route)

    if msg_pkt.decoded.portnum == portnums_pb2.TEXT_MESSAGE_APP:
        text_message = msg_pkt.decoded.payload.decode("utf-8")
        print(text_message)
        db_functions.insert_text_message(source, dest, pkt_id, toi, text_message)

def on_connect(client, userdata, flags, reason_code, properties=None):
    print("Connected, subscribing...")
    client.subscribe(topic="msh/2/e/#")

def on_subscribe(client, userdata, mid, qos, properties=None):
    print(f"{dt.now()} Subscribed with QoS {qos}")

broker = "localhost"
broker_port = 1883

client = mqtt.Client(client_id="pytest",
                     transport="tcp",
                     protocol=mqtt.MQTTv311,
                     clean_session=True)
client.username_pw_set("mesh", "mesh123")
client.on_message = on_message
client.on_connect = on_connect
client.on_subscribe = on_subscribe

client.connect(broker, port=broker_port, keepalive=60)

client.loop_forever()
