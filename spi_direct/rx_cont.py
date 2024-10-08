#!/usr/bin/env python3

"""A simple continuous receiver class."""

# Copyright 2015 Mayer Analytics Ltd.
#
# This file is part of spi-lora.
#
# spi-lora is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
# License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# spi-lora is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public License for more
# details.
#
# You can be released from the requirements of the license by obtaining a commercial license. Such a license is
# mandatory as soon as you develop commercial activities involving spi-lora without disclosing the source code of your
# own applications, or shipping spi-lora with a closed source product.
#
# You should have received a copy of the GNU General Public License aling with spi-lora.  If not, see
# <http://www.gnu.org/licenses/>.

import logging
import sys
from configparser import ConfigParser
from time import sleep, time

import psycopg2
from Cryptodome.Cipher import AES
from meshtastic import mesh_pb2, telemetry_pb2
from spi_lora.boards.RPi_Adafruit4074 import BOARD
from spi_lora.LoRa import BW, CODING_RATE, GAIN, MODE
from spi_lora.LoRaArgumentParser import LoRaArgumentParser

BOARD.setup()

parser = LoRaArgumentParser("Continous LoRa receiver.")

key = bytearray([0xD4, 0xF1, 0xBB, 0x3A, 0x20, 0x29, 0x07, 0x59, 0xF0, 0xBC, 0xFF, 0xAB, 0xCF, 0x4E, 0x69, 0x01])
last_msg = {}


class LoRaRcvCont(LoRa):
    def __init__(self, board=None, verbose=False):
        super(LoRaRcvCont, self).__init__(board=board, verbose=verbose)
        self.set_mode(MODE.SLEEP)
        self.set_dio_mapping([0] * 6)

    def on_rx_done(self):
        BOARD.led_on()
        self.clear_irq_flags(RxDone=1)
        payload = self.read_payload(nocheck=True)
        nonce = []
        nonce.append(payload[8])
        nonce.append(payload[9])
        nonce.append(payload[10])
        nonce.append(payload[11])
        nonce.append(0x00)
        nonce.append(0x00)
        nonce.append(0x00)
        nonce.append(0x00)
        nonce.append(payload[4])
        nonce.append(payload[5])
        nonce.append(payload[6])
        nonce.append(payload[7])
        nonce.append(0x00)
        nonce.append(0x00)
        nonce.append(0x00)
        sender = int.from_bytes(payload[7:3:-1])
        packet_id = int.from_bytes(payload[11:7:-1])
        packet = mesh_pb2.MeshPacket()
        setattr(packet, "from", int.from_bytes(payload[7:3:-1]))
        packet.to = int.from_bytes(payload[3::-1])
        packet.id = int.from_bytes(payload[11:7:-1])
        packet.channel = payload[13]
        packet.rx_time = int(time())
        packet.rx_snr = int(lora.get_pkt_snr_value())
        packet.rx_rssi = int(lora.get_pkt_rssi_value())
        packet.hop_limit = int(payload[12] & 7)
        packet.hop_start = int(payload[12] & 224) >> 5
        packet.want_ack = True if payload[12] & 8 == 8 else False
        insert_node(packet)
        if sender in last_msg:
            #            logging.debug("Sender {:02x} found, last packet is {}".format(sender, last_msg[sender]))
            if last_msg[sender] >= packet_id:
                #                logging.debug("dupe")
                self.set_mode(MODE.SLEEP)
                self.reset_ptr_rx()
                BOARD.led_off()
                self.set_mode(MODE.RXCONT)
                return
        last_msg[sender] = packet_id
        #        logging.debug(packet)
        #        logging.debug('Hop Limit: {}, Hop Start: {}, Want Ack? {}, Hash: {}'.format(payload[12] & 0x7, (payload[12] & 0xE0) >> 5, (payload[12] & 8 ) >> 3, payload[13]))
        #        logging.debug('Next Hop: {:02x}, Relay Node: {:02x}'.format(payload[14], payload[15]))

        ## decrypt the message and decode the enclosed protobuf
        decrypt_cipher = AES.new(key, AES.MODE_CTR, nonce=bytearray(nonce))
        plain_text = decrypt_cipher.decrypt(bytearray(payload[16:]))
        #        logging.debug('Plain text:  {}'.format(' '.join(hex(b) for b in plain_text)))
        data = mesh_pb2.Data()
        try:
            data.ParseFromString(plain_text)
        except (google.protobuf.message.DecodeError, Exception):
            logging.debug("Unable to decode protobuf from %s", sender)
        match data.portnum:
            case 1:
                logging.debug("Got a text message:  {}", data.payload())
            case 3:
                pos = mesh_pb2.Position()
                pos.ParseFromString(data.payload)
                insert_position(sender, pos)
            #                logging.debug('Position data: {}'.format(pos))
            case 4:
                ni = mesh_pb2.User()
                ni.ParseFromString(data.payload)
                insert_nodeinfo(sender, ni)
            #                logging.debug('NodeInfo data: {}'.format(ni))
            case 67:
                tel = telemetry_pb2.Telemetry()
                tel.ParseFromString(data.payload)
            #                logging.debug('Telemetry data: {}'.format(tel))
            case 71:
                ni = mesh_pb2.NeighborInfo()
                ni.ParseFromString(data.payload)
                insert_neighbor_info(sender, ni)
                logging.debug(f"Neighbor Info: {ni}")
            case _:
                logging.debug("I dunno, man")
        self.set_mode(MODE.SLEEP)
        self.reset_ptr_rx()
        BOARD.led_off()
        self.set_mode(MODE.RXCONT)

    def on_tx_done(self):
        logging.debug("\nTxDone")
        logging.debug(self.get_irq_flags())

    def on_cad_done(self):
        logging.debug("\non_CadDone")
        logging.debug(self.get_irq_flags())

    def on_rx_timeout(self):
        logging.debug("\non_RxTimeout")
        logging.debug(self.get_irq_flags())

    def on_valid_header(self):
        logging.debug("\non_ValidHeader")
        logging.debug(self.get_irq_flags())

    def on_payload_crc_error(self):
        logging.debug("\non_PayloadCrcError")
        logging.debug(self.get_irq_flags())

    def on_fhss_change_channel(self):
        logging.debug("\non_FhssChangeChannel")
        logging.debug(self.get_irq_flags())

    def start(self):
        self.reset_ptr_rx()
        self.set_mode(MODE.RXCONT)
        t = 0
        while True:
            sleep(0.1)
            rssi_value = self.get_rssi_value()
            status = self.get_modem_status()
            sys.stdout.flush()
            sys.stdout.write("\r%03d %d %d" % (rssi_value, status["rx_ongoing"], status["modem_clear"]))
            t = t + 1
            if t > 300:
                t = 0
                # logging.debug(last_msg)
            if not self.irq_events_available:
                self.handle_irq_flags()


def load_config(filename="database.ini", section="postgresql"):
    parser = ConfigParser()
    parser.read(filename)

    # get section, default to postgresql
    config = {}
    if parser.has_section(section):
        params = parser.items(section)
        for param in params:
            config[param[0]] = param[1]
    else:
        raise Exception(f"Section {section} not found in the {filename} file")

    return config


def connect(config):
    """Connect to the PostgreSQL database server"""
    try:
        # connecting to the PostgreSQL server
        with psycopg2.connect(**config) as conn:
            logging.debug("Connected to the PostgreSQL server.")
            return conn
    except (psycopg2.DatabaseError, Exception) as error:
        logging.debug(error)


def insert_node(node):
    sql = """INSERT INTO nodes (id, packet_id, dest, channel, rx_time, rx_snr, rx_rssi, hop_limit, hop_start)
             VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s);"""
    config = load_config()
    try:
        with psycopg2.connect(**config) as conn:
            with conn.cursor() as cur:
                # execute the INSERT statement
                cur.execute(
                    sql,
                    (
                        getattr(node, "from"),
                        node.id,
                        node.to,
                        node.channel,
                        node.rx_time,
                        node.rx_snr,
                        node.rx_rssi,
                        node.hop_limit,
                        node.hop_start,
                    ),
                )
                # commit the changes to the database
                conn.commit()
                logging.debug("  Node packet stored")
    except (Exception, psycopg2.DatabaseError) as error:
        logging.debug(error)


def insert_nodeinfo(from_node, nodeinfo):
    update_sql = """UPDATE node_info set update_time=now(), long_name = %s, short_name = %s, role = %s where id = %s"""
    insert_sql = """INSERT INTO node_info (id, update_time, long_name, short_name, mac_addr, hw_model, role)
             VALUES(%s, now(), %s, %s, %s, %s, %s);"""
    config = load_config()
    try:
        with psycopg2.connect(**config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    update_sql,
                    (
                        nodeinfo.long_name,
                        nodeinfo.short_name,
                        nodeinfo.role,
                        from_node,
                    ),
                )
                update_row_count = cur.rowcount
                if update_row_count == 0:
                    # execute the INSERT statement
                    cur.execute(
                        sql,
                        (
                            from_node,
                            nodeinfo.long_name,
                            nodeinfo.short_name,
                            nodeinfo.macaddr,
                            nodeinfo.hw_model,
                            nodeinfo.role,
                        ),
                    )
                # commit the changes to the database
                conn.commit()
                logging.debug("  Nodeinfo stored")
    except (Exception, psycopg2.DatabaseError) as error:
        logging.debug("Exception storing nodeinfo")
        logging.debug(error)


def insert_position(from_node, pos):
    update_sql = """UPDATE node_position set toi = now() where id=%s and latitude=%s and longitude=%s"""
    insert_sql = """INSERT INTO node_position (id, toi, latitude, longitude, altitude)
             VALUES(%s, now(), %s, %s, %s);"""
    config = load_config()
    try:
        with psycopg2.connect(**config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    update_sql,
                    (
                        from_node,
                        pos.latitude_i,
                        pos.longitude_i,
                    ),
                )
                update_row_count = cur.rowcount
                if update_row_count == 0:
                    # execute the INSERT statement
                    cur.execute(
                        insert_sql,
                        (
                            from_node,
                            pos.latitude_i,
                            pos.longitude_i,
                            pos.altitude,
                        ),
                    )
                    logging.debug(f"  Inserted  location for {from_node}")
                else:
                    logging.debug(f"  Updated location for {from_node}")
                # commit the changes to the database
                conn.commit()
    except (Exception, psycopg2.DatabaseError) as error:
        logging.debug(error)


def insert_neighbor_info(from_node, neighbor_info):
    sql = """INSERT INTO neighbor_info (id, neighbor_id, snr)
             VALUES (%s, %s, %s);"""
    config = load_config()
    try:
        with psycopg2.connect(**config) as conn:
            with conn.cursor() as cur:
                # execute the INSERT statement
                for neighbor in neighbor_info.neighbors:
                    cur.execute(
                        sql,
                        (
                            from_node,
                            neighbor.node_id,
                            neighbor.snr,
                        ),
                    )
                # commit the changes to the database
                conn.commit()
                logging.debug("  Neighbor Info stored")
    except (Exception, psycopg2.DatabaseError) as error:
        logging.debug(error)


lora = LoRaRcvCont(BOARD, verbose=False)
args = parser.parse_args(lora)

lora.set_mode(MODE.STDBY)
lora.set_pa_config(pa_select=1)
lora.set_freq(906.875)
lora.set_rx_crc(False)
lora.set_coding_rate(CODING_RATE.CR4_5)
lora.set_bw(BW.BW250)
lora.set_spreading_factor(11)
lora.set_preamble(16)
lora.set_sync_word(0x2B)
# lora.set_pa_config(max_power=0, output_power=0)
lora.set_lna_gain(GAIN.G1)
lora.set_implicit_header_mode(False)
lora.set_low_data_rate_optim(False)
# lora.set_pa_ramp(PA_RAMP.RAMP_50_us)
lora.set_agc_auto_on(True)

logging.debug(lora)
assert lora.get_agc_auto_on() == 1


config = load_config()
connect(config)

try:
    lora.start()
except KeyboardInterrupt:
    sys.stdout.flush()
    logging.debug()
    sys.stderr.write("KeyboardInterrupt\n")
finally:
    sys.stdout.flush()
    logging.debug()
    lora.set_mode(MODE.SLEEP)
    #    logging.debug(lora)
    BOARD.teardown()
