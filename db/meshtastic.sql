--
-- PostgreSQL database dump
--

-- Dumped from database version 17.4 (Debian 17.4-1.pgdg130+2)
-- Dumped by pg_dump version 17.4 (Debian 17.4-1.pgdg130+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: meshtastic; Type: DATABASE; Schema: -; Owner: mesh_rw
--

CREATE DATABASE meshtastic WITH TEMPLATE = template0 ENCODING = 'UTF8' LOCALE_PROVIDER = libc LOCALE = 'en_US.UTF-8';


ALTER DATABASE meshtastic OWNER TO mesh_rw;

\connect meshtastic

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: mesh_rw
--

-- *not* creating schema, since initdb creates it


ALTER SCHEMA public OWNER TO mesh_rw;

--
-- Name: postgis; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;


--
-- Name: EXTENSION postgis; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION postgis IS 'PostGIS geometry and geography spatial types and functions';


--
-- Name: fn_add_geom_update(); Type: FUNCTION; Schema: public; Owner: mesh_rw
--

CREATE FUNCTION public.fn_add_geom_update() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
UPDATE node_positions SET geom=ST_MakePoint(NEW.longitude / 10000000, NEW.latitude/ 10000000, 0) 
       WHERE node_id=NEW.node_id and updated_at = NEW.updated_at;
RETURN NULL;
END;
$$;


ALTER FUNCTION public.fn_add_geom_update() OWNER TO mesh_rw;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: air_quality_metrics; Type: TABLE; Schema: public; Owner: mesh_rw
--

CREATE TABLE public.air_quality_metrics (
    node_id bigint NOT NULL,
    packet_id bigint NOT NULL,
    toi timestamp with time zone DEFAULT now() NOT NULL,
    pm10_std integer,
    pm25_std integer,
    pm100_std integer,
    pm10_env integer,
    pm25_env integer,
    pm100_env integer,
    particles_03um integer,
    particles_05um integer,
    particles_10um integer,
    particles_25um integer,
    particles_50um integer,
    particles_100um integer
);


ALTER TABLE public.air_quality_metrics OWNER TO mesh_rw;

--
-- Name: device_metrics; Type: TABLE; Schema: public; Owner: mesh_rw
--

CREATE TABLE public.device_metrics (
    node_id bigint NOT NULL,
    packet_id bigint NOT NULL,
    toi timestamp with time zone DEFAULT now() NOT NULL,
    battery_level integer,
    voltage double precision,
    channel_util double precision,
    air_util_tx double precision,
    uptime_seconds integer
);


ALTER TABLE public.device_metrics OWNER TO mesh_rw;

--
-- Name: last_device_metrics; Type: MATERIALIZED VIEW; Schema: public; Owner: mesh_rw
--

CREATE MATERIALIZED VIEW public.last_device_metrics AS
 SELECT DISTINCT ON (node_id) node_id,
    round((battery_level)::numeric, 2) AS battery_level,
    round((voltage)::numeric, 2) AS voltage,
    round((channel_util)::numeric, 2) AS channel_util,
    round((air_util_tx)::numeric, 2) AS air_util_tx
   FROM public.device_metrics
  ORDER BY node_id, toi DESC
  WITH NO DATA;


ALTER MATERIALIZED VIEW public.last_device_metrics OWNER TO mesh_rw;

--
-- Name: mesh_packets; Type: TABLE; Schema: public; Owner: mesh_rw
--

CREATE TABLE public.mesh_packets (
    source bigint NOT NULL,
    dest bigint,
    packet_id bigint NOT NULL,
    channel integer NOT NULL,
    rx_snr integer,
    rx_rssi integer,
    hop_limit integer,
    hop_start integer,
    portnum character varying,
    toi timestamp with time zone,
    channel_id character varying,
    gateway_id bigint
);


ALTER TABLE public.mesh_packets OWNER TO mesh_rw;

--
-- Name: node_infos; Type: TABLE; Schema: public; Owner: mesh_rw
--

CREATE TABLE public.node_infos (
    node_id bigint NOT NULL,
    long_name character varying(100),
    short_name character varying(10),
    mac_addr character varying(20),
    hw_model character varying(30),
    role character varying,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    public_key character varying(100)
);


ALTER TABLE public.node_infos OWNER TO mesh_rw;

--
-- Name: node_positions; Type: TABLE; Schema: public; Owner: mesh_rw
--

CREATE TABLE public.node_positions (
    node_id bigint NOT NULL,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    altitude double precision,
    geom public.geometry(PointZ,4326),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.node_positions OWNER TO mesh_rw;

--
-- Name: current_nodes; Type: VIEW; Schema: public; Owner: mesh_rw
--

CREATE VIEW public.current_nodes AS
 SELECT DISTINCT ON (n.source) n.source AS node_id,
    ni.short_name,
    ni.long_name,
    ni.hw_model,
    ni.role,
    np.altitude,
    np.latitude,
    np.longitude,
    dm.battery_level,
    dm.voltage,
    dm.channel_util,
    dm.air_util_tx,
    (now() - mp.toi) AS since
   FROM ((((public.mesh_packets n
     LEFT JOIN public.node_infos ni ON ((n.source = ni.node_id)))
     LEFT JOIN public.node_positions np ON ((n.source = np.node_id)))
     LEFT JOIN public.last_device_metrics dm ON ((n.source = dm.node_id)))
     LEFT JOIN LATERAL ( SELECT mesh_packets.toi
           FROM public.mesh_packets
          WHERE ((mesh_packets.source = n.source) AND (mesh_packets.toi >= (now() - '7 days'::interval)))
          ORDER BY mesh_packets.toi DESC
         LIMIT 1) mp ON (true))
  WHERE (n.toi >= (now() - '3 days'::interval))
  ORDER BY n.source, (now() - mp.toi) DESC;


ALTER VIEW public.current_nodes OWNER TO mesh_rw;

--
-- Name: environment_metrics; Type: TABLE; Schema: public; Owner: mesh_rw
--

CREATE TABLE public.environment_metrics (
    node_id bigint NOT NULL,
    packet_id bigint NOT NULL,
    toi timestamp with time zone DEFAULT now() NOT NULL,
    temperature double precision,
    relative_humidity double precision,
    barometric_pressure double precision,
    gas_resistance double precision,
    voltage double precision,
    current double precision,
    iaq integer,
    distance double precision,
    lux double precision,
    white_lux double precision,
    ir_lux double precision,
    uv_lux double precision,
    wind_direction integer,
    wind_speed double precision,
    weight double precision,
    wind_gus double precision,
    wind_lull double precision
);


ALTER TABLE public.environment_metrics OWNER TO mesh_rw;

--
-- Name: last_node_infos; Type: VIEW; Schema: public; Owner: mesh_rw
--

CREATE VIEW public.last_node_infos AS
 SELECT DISTINCT ON (node_id) node_id,
    long_name,
    short_name,
    mac_addr,
    hw_model,
    role,
    updated_at
   FROM public.node_infos
  ORDER BY node_id, updated_at DESC;


ALTER VIEW public.last_node_infos OWNER TO mesh_rw;

--
-- Name: last_position; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.last_position AS
 SELECT DISTINCT ON (node_id) node_id,
    updated_at,
    geom
   FROM public.node_positions
  ORDER BY node_id, updated_at DESC;


ALTER VIEW public.last_position OWNER TO postgres;

--
-- Name: local_stats; Type: TABLE; Schema: public; Owner: mesh_rw
--

CREATE TABLE public.local_stats (
    node_id bigint NOT NULL,
    toi timestamp with time zone DEFAULT now() NOT NULL,
    uptime_seconds integer,
    channel_utilization double precision,
    air_util_tx double precision,
    num_packets_tx integer,
    num_packets_rx integer,
    num_packets_rx_bad integer,
    num_online_nodes integer,
    num_total_nodes integer
);


ALTER TABLE public.local_stats OWNER TO mesh_rw;

--
-- Name: neighbor_info; Type: TABLE; Schema: public; Owner: mesh_rw
--

CREATE TABLE public.neighbor_info (
    id bigint NOT NULL,
    neighbor_id bigint NOT NULL,
    update_time timestamp with time zone DEFAULT now() NOT NULL,
    snr double precision
);


ALTER TABLE public.neighbor_info OWNER TO mesh_rw;

--
-- Name: neighbor_map; Type: VIEW; Schema: public; Owner: postgres
--

CREATE VIEW public.neighbor_map AS
 SELECT DISTINCT to_hex(i.id) AS id,
    i.update_time,
    i.neighbor_id,
    i.snr,
    l.geom
   FROM public.last_position l,
    public.neighbor_info i
  WHERE (i.id = l.node_id)
  ORDER BY (to_hex(i.id));


ALTER VIEW public.neighbor_map OWNER TO postgres;

--
-- Name: power_metrics; Type: TABLE; Schema: public; Owner: mesh_rw
--

CREATE TABLE public.power_metrics (
    node_id bigint NOT NULL,
    packet_id bigint NOT NULL,
    toi timestamp with time zone DEFAULT now() NOT NULL,
    ch1_voltage double precision,
    ch1_current double precision,
    ch2_voltage double precision,
    ch2_current double precision,
    ch3_voltage double precision,
    ch3_current double precision
);


ALTER TABLE public.power_metrics OWNER TO mesh_rw;

--
-- Name: text_messages; Type: TABLE; Schema: public; Owner: mesh_rw
--

CREATE TABLE public.text_messages (
    msg_id integer NOT NULL,
    source_id bigint NOT NULL,
    destination_id bigint NOT NULL,
    packet_id bigint NOT NULL,
    toi timestamp with time zone DEFAULT now() NOT NULL,
    body character varying
);


ALTER TABLE public.text_messages OWNER TO mesh_rw;

--
-- Name: text_messages_msg_id_seq; Type: SEQUENCE; Schema: public; Owner: mesh_rw
--

CREATE SEQUENCE public.text_messages_msg_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.text_messages_msg_id_seq OWNER TO mesh_rw;

--
-- Name: text_messages_msg_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: mesh_rw
--

ALTER SEQUENCE public.text_messages_msg_id_seq OWNED BY public.text_messages.msg_id;


--
-- Name: text_messages msg_id; Type: DEFAULT; Schema: public; Owner: mesh_rw
--

ALTER TABLE ONLY public.text_messages ALTER COLUMN msg_id SET DEFAULT nextval('public.text_messages_msg_id_seq'::regclass);


--
-- Name: idx_air_quality_metrics_uk; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE UNIQUE INDEX idx_air_quality_metrics_uk ON public.air_quality_metrics USING btree (node_id, toi);


--
-- Name: idx_device_metrics_node_id_toi_desc; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE INDEX idx_device_metrics_node_id_toi_desc ON public.device_metrics USING btree (node_id, toi DESC);


--
-- Name: idx_device_metrics_uk; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE UNIQUE INDEX idx_device_metrics_uk ON public.device_metrics USING btree (node_id, toi);


--
-- Name: idx_environment_metrics_uk; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE UNIQUE INDEX idx_environment_metrics_uk ON public.environment_metrics USING btree (node_id, toi);


--
-- Name: idx_local_stats_uk; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE UNIQUE INDEX idx_local_stats_uk ON public.local_stats USING btree (node_id, toi);


--
-- Name: idx_mesh_packets_source_toi; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE INDEX idx_mesh_packets_source_toi ON public.mesh_packets USING btree (source, toi DESC);


--
-- Name: idx_mesh_packets_toi; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE INDEX idx_mesh_packets_toi ON public.mesh_packets USING btree (toi);


--
-- Name: idx_mesh_packets_uk; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE UNIQUE INDEX idx_mesh_packets_uk ON public.mesh_packets USING btree (source, packet_id, channel, gateway_id);


--
-- Name: idx_neighbor_info_uk; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE UNIQUE INDEX idx_neighbor_info_uk ON public.neighbor_info USING btree (id, neighbor_id);


--
-- Name: idx_node_infos_node_id; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE INDEX idx_node_infos_node_id ON public.node_infos USING btree (node_id);


--
-- Name: idx_node_positions_geom; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE INDEX idx_node_positions_geom ON public.node_positions USING gist (geom);


--
-- Name: idx_node_positions_node_id; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE INDEX idx_node_positions_node_id ON public.node_positions USING btree (node_id);


--
-- Name: idx_node_positions_uk; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE UNIQUE INDEX idx_node_positions_uk ON public.node_positions USING btree (node_id, latitude, longitude);


--
-- Name: idx_nodes_infos_uk; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE UNIQUE INDEX idx_nodes_infos_uk ON public.node_infos USING btree (node_id, long_name, short_name);


--
-- Name: idx_power_metrics_uk; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE UNIQUE INDEX idx_power_metrics_uk ON public.power_metrics USING btree (node_id, toi);


--
-- Name: mesh_packets_source_idx; Type: INDEX; Schema: public; Owner: mesh_rw
--

CREATE INDEX mesh_packets_source_idx ON public.mesh_packets USING btree (source);


--
-- Name: node_positions geom_inserted; Type: TRIGGER; Schema: public; Owner: mesh_rw
--

CREATE TRIGGER geom_inserted AFTER INSERT ON public.node_positions FOR EACH ROW EXECUTE FUNCTION public.fn_add_geom_update();


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: mesh_rw
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO PUBLIC;


--
-- Name: TABLE air_quality_metrics; Type: ACL; Schema: public; Owner: mesh_rw
--

GRANT SELECT ON TABLE public.air_quality_metrics TO mesh_ro;


--
-- Name: TABLE device_metrics; Type: ACL; Schema: public; Owner: mesh_rw
--

GRANT SELECT ON TABLE public.device_metrics TO mesh_ro;


--
-- Name: TABLE mesh_packets; Type: ACL; Schema: public; Owner: mesh_rw
--

GRANT SELECT ON TABLE public.mesh_packets TO mesh_ro;


--
-- Name: TABLE node_infos; Type: ACL; Schema: public; Owner: mesh_rw
--

GRANT SELECT ON TABLE public.node_infos TO mesh_ro;


--
-- Name: TABLE node_positions; Type: ACL; Schema: public; Owner: mesh_rw
--

GRANT SELECT ON TABLE public.node_positions TO mesh_ro;


--
-- Name: TABLE environment_metrics; Type: ACL; Schema: public; Owner: mesh_rw
--

GRANT SELECT ON TABLE public.environment_metrics TO mesh_ro;


--
-- Name: TABLE geography_columns; Type: ACL; Schema: public; Owner: mesh_rw
--

GRANT SELECT ON TABLE public.geography_columns TO mesh_ro;


--
-- Name: TABLE geometry_columns; Type: ACL; Schema: public; Owner: mesh_rw
--

GRANT SELECT ON TABLE public.geometry_columns TO mesh_ro;


--
-- Name: TABLE last_node_infos; Type: ACL; Schema: public; Owner: mesh_rw
--

GRANT SELECT ON TABLE public.last_node_infos TO mesh_ro;


--
-- Name: TABLE last_position; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.last_position TO mesh_ro;


--
-- Name: TABLE local_stats; Type: ACL; Schema: public; Owner: mesh_rw
--

GRANT SELECT ON TABLE public.local_stats TO mesh_ro;


--
-- Name: TABLE neighbor_info; Type: ACL; Schema: public; Owner: mesh_rw
--

GRANT SELECT ON TABLE public.neighbor_info TO mesh_ro;


--
-- Name: TABLE neighbor_map; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT ON TABLE public.neighbor_map TO mesh_ro;


--
-- Name: TABLE power_metrics; Type: ACL; Schema: public; Owner: mesh_rw
--

GRANT SELECT ON TABLE public.power_metrics TO mesh_ro;


--
-- Name: TABLE spatial_ref_sys; Type: ACL; Schema: public; Owner: mesh_rw
--

GRANT SELECT ON TABLE public.spatial_ref_sys TO mesh_ro;


--
-- Name: TABLE text_messages; Type: ACL; Schema: public; Owner: mesh_rw
--

GRANT SELECT ON TABLE public.text_messages TO mesh_ro;


--
-- PostgreSQL database dump complete
--

