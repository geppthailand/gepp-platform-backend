--
-- PostgreSQL database dump
--

\restrict b7MWdqZfZHADxR4nmJhSbOaxismBf1hU2fwR7NoEyb6bCffvzENglk6KP3szeDO

-- Dumped from database version 17.6 (Ubuntu 17.6-1.pgdg24.04+1)
-- Dumped by pg_dump version 17.6 (Homebrew)

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
-- Name: pg_stat_statements; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA public;


--
-- Name: EXTENSION pg_stat_statements; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pg_stat_statements IS 'track planning and execution statistics of all SQL statements executed';


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: platform_enum; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.platform_enum AS ENUM (
    'NA',
    'WEB',
    'MOBILE',
    'API',
    'BUSINESS',
    'REWARDS',
    'GEPP_BUSINESS_WEB',
    'GEPP_REWARD_APP',
    'ADMIN_WEB',
    'GEPP_EPR_WEB'
);


ALTER TYPE public.platform_enum OWNER TO postgres;

--
-- Name: ensure_single_active_organization_setup(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.ensure_single_active_organization_setup() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    -- If setting is_active to true, deactivate all other versions for this organization
    IF NEW.is_active = TRUE THEN
        -- Use a more explicit update to avoid constraint violations
        UPDATE organization_setup
        SET is_active = FALSE, updated_date = NOW()
        WHERE organization_id = NEW.organization_id
          AND id != COALESCE(NEW.id, -1)  -- Handle case where NEW.id might be null during INSERT
          AND is_active = TRUE;
    END IF;

    RETURN NEW;
END;
$$;


ALTER FUNCTION public.ensure_single_active_organization_setup() OWNER TO postgres;

--
-- Name: update_organization_setup_updated_date(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_organization_setup_updated_date() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_date = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_organization_setup_updated_date() OWNER TO postgres;

--
-- Name: update_system_roles_updated_date(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_system_roles_updated_date() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_date = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_system_roles_updated_date() OWNER TO postgres;

--
-- Name: update_updated_at_column(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_updated_at_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_updated_at_column() OWNER TO postgres;

--
-- Name: update_updated_date_column(); Type: FUNCTION; Schema: public; Owner: postgres
--

CREATE FUNCTION public.update_updated_date_column() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    NEW.updated_date = NOW();
    RETURN NEW;
END;
$$;


ALTER FUNCTION public.update_updated_date_column() OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.audit_logs (
    id bigint NOT NULL,
    user_id bigint,
    organization_id bigint,
    action character varying(100),
    resource_type character varying(100),
    resource_id bigint,
    description text,
    changes jsonb,
    metadata jsonb,
    ip_address inet,
    user_agent text,
    request_method character varying(10),
    request_url text,
    session_id character varying(255),
    status character varying(50) DEFAULT 'success'::character varying,
    error_message text,
    compliance_category character varying(100),
    retention_period_days integer DEFAULT 2555,
    created_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.audit_logs OWNER TO postgres;

--
-- Name: audit_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.audit_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.audit_logs_id_seq OWNER TO postgres;

--
-- Name: audit_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.audit_logs_id_seq OWNED BY public.audit_logs.id;


--
-- Name: banks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.banks (
    id bigint NOT NULL,
    name_th character varying(255),
    name_en character varying(255),
    code character varying(10),
    swift_code character varying(20),
    country_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.banks OWNER TO postgres;

--
-- Name: banks_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.banks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.banks_id_seq OWNER TO postgres;

--
-- Name: banks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.banks_id_seq OWNED BY public.banks.id;


--
-- Name: base_materials; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.base_materials (
    id bigint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    updated_date timestamp with time zone DEFAULT now() NOT NULL,
    deleted_date timestamp with time zone,
    category_id bigint,
    main_material_id bigint,
    tag_groups bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    unit_name_th character varying(255) NOT NULL,
    unit_name_en character varying(255) NOT NULL,
    unit_weight numeric(10,3) DEFAULT 1 NOT NULL,
    color character varying(7) DEFAULT '#808080'::character varying NOT NULL,
    calc_ghg numeric(10,3) DEFAULT 0 NOT NULL,
    name_th character varying(255) NOT NULL,
    name_en character varying(255) NOT NULL,
    CONSTRAINT chk_base_materials_calc_ghg CHECK ((calc_ghg >= (0)::numeric)),
    CONSTRAINT chk_base_materials_color CHECK (((color)::text ~ '^#[0-9A-Fa-f]{6}$'::text)),
    CONSTRAINT chk_base_materials_unit_weight CHECK ((unit_weight > (0)::numeric))
);


ALTER TABLE public.base_materials OWNER TO postgres;

--
-- Name: TABLE base_materials; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.base_materials IS 'Fundamental material types (e.g., PET Plastic) that can be combined with material_tags to create specific materials';


--
-- Name: COLUMN base_materials.tag_groups; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.base_materials.tag_groups IS 'Array of material_tag_group IDs that define which conditions can be applied to this base material';


--
-- Name: base_materials_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.base_materials_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.base_materials_id_seq OWNER TO postgres;

--
-- Name: base_materials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.base_materials_id_seq OWNED BY public.base_materials.id;


--
-- Name: chat_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.chat_history (
    id bigint NOT NULL,
    chat_id bigint NOT NULL,
    message_type character varying(50) DEFAULT 'text'::character varying,
    message_content text,
    sender_type character varying(50),
    sender_id bigint,
    sender_name character varying(255),
    message_length integer,
    language character varying(10) DEFAULT 'en'::character varying,
    attachments jsonb,
    ai_confidence numeric(5,4),
    ai_model character varying(100),
    ai_tokens_used integer,
    is_read boolean DEFAULT false,
    read_at timestamp with time zone,
    user_rating integer,
    user_feedback text,
    created_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.chat_history OWNER TO postgres;

--
-- Name: chat_history_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.chat_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.chat_history_id_seq OWNER TO postgres;

--
-- Name: chat_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.chat_history_id_seq OWNED BY public.chat_history.id;


--
-- Name: chats; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.chats (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    expert_id bigint,
    chat_type character varying(50) DEFAULT 'support'::character varying,
    subject character varying(500),
    priority character varying(20) DEFAULT 'medium'::character varying,
    status character varying(50) DEFAULT 'active'::character varying,
    session_id character varying(255),
    platform character varying(50),
    ai_model character varying(100),
    ai_context jsonb,
    started_at timestamp with time zone DEFAULT now(),
    last_activity_at timestamp with time zone DEFAULT now(),
    closed_at timestamp with time zone,
    tags jsonb,
    category character varying(100),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.chats OWNER TO postgres;

--
-- Name: chats_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.chats_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.chats_id_seq OWNER TO postgres;

--
-- Name: chats_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.chats_id_seq OWNED BY public.chats.id;


--
-- Name: currencies; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.currencies (
    id bigint NOT NULL,
    name_th character varying(255),
    name_en character varying(255),
    code character varying(10),
    symbol character varying(10),
    exchange_rate numeric(15,6) DEFAULT 1.0,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.currencies OWNER TO postgres;

--
-- Name: currencies_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.currencies_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.currencies_id_seq OWNER TO postgres;

--
-- Name: currencies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.currencies_id_seq OWNED BY public.currencies.id;


--
-- Name: epr_audits; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.epr_audits (
    id bigint NOT NULL,
    registration_id bigint NOT NULL,
    audit_type character varying(50),
    audit_scope character varying(100),
    audit_date_start date,
    audit_date_end date,
    auditor_name character varying(255),
    auditor_organization character varying(255),
    auditor_certification character varying(100),
    overall_rating character varying(50),
    compliance_level numeric(5,2),
    findings jsonb,
    non_conformities jsonb,
    recommendations jsonb,
    corrective_actions jsonb,
    follow_up_date date,
    follow_up_status character varying(50),
    audit_report_url text,
    supporting_evidence jsonb,
    conducted_by_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.epr_audits OWNER TO postgres;

--
-- Name: epr_audits_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.epr_audits_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.epr_audits_id_seq OWNER TO postgres;

--
-- Name: epr_audits_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.epr_audits_id_seq OWNED BY public.epr_audits.id;


--
-- Name: epr_data_submissions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.epr_data_submissions (
    id bigint NOT NULL,
    registration_id bigint NOT NULL,
    reporting_period character varying(50),
    reporting_year integer,
    submission_date date,
    submission_status character varying(50) DEFAULT 'draft'::character varying,
    products_placed_market_kg numeric(12,3),
    waste_collected_kg numeric(12,3),
    waste_recycled_kg numeric(12,3),
    waste_recovered_kg numeric(12,3),
    waste_disposed_kg numeric(12,3),
    collection_rate numeric(5,2),
    recycling_rate numeric(5,2),
    recovery_rate numeric(5,2),
    fees_paid numeric(12,2),
    investments_made numeric(12,2),
    data_sources jsonb,
    methodology text,
    assumptions text,
    submitted_by_id bigint,
    reviewed_by character varying(255),
    review_date date,
    review_comments text,
    submission_file_url text,
    supporting_documents jsonb,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.epr_data_submissions OWNER TO postgres;

--
-- Name: epr_data_submissions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.epr_data_submissions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.epr_data_submissions_id_seq OWNER TO postgres;

--
-- Name: epr_data_submissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.epr_data_submissions_id_seq OWNED BY public.epr_data_submissions.id;


--
-- Name: epr_notifications; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.epr_notifications (
    id bigint NOT NULL,
    registration_id bigint,
    organization_id bigint,
    notification_type character varying(50),
    priority character varying(20) DEFAULT 'medium'::character varying,
    title character varying(255),
    message text,
    scheduled_date date,
    sent_date timestamp with time zone,
    read_date timestamp with time zone,
    recipient_emails jsonb,
    sent_to_users jsonb,
    status character varying(50) DEFAULT 'pending'::character varying,
    related_submission_id bigint,
    related_payment_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.epr_notifications OWNER TO postgres;

--
-- Name: epr_notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.epr_notifications_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.epr_notifications_id_seq OWNER TO postgres;

--
-- Name: epr_notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.epr_notifications_id_seq OWNED BY public.epr_notifications.id;


--
-- Name: epr_payments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.epr_payments (
    id bigint NOT NULL,
    registration_id bigint NOT NULL,
    payment_type character varying(50),
    payment_period character varying(50),
    payment_year integer,
    base_amount numeric(12,2),
    fee_rate numeric(8,4),
    calculated_amount numeric(12,2),
    penalty_amount numeric(12,2) DEFAULT 0,
    total_amount numeric(12,2),
    currency_id bigint DEFAULT 12,
    status character varying(50) DEFAULT 'pending'::character varying,
    due_date date,
    payment_date date,
    payment_method character varying(50),
    payment_reference character varying(100),
    bank_reference character varying(100),
    calculation_basis text,
    notes text,
    receipt_url text,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.epr_payments OWNER TO postgres;

--
-- Name: epr_payments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.epr_payments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.epr_payments_id_seq OWNER TO postgres;

--
-- Name: epr_payments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.epr_payments_id_seq OWNED BY public.epr_payments.id;


--
-- Name: epr_programs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.epr_programs (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    program_type character varying(50),
    regulation_reference character varying(100),
    authority character varying(255),
    country_id bigint,
    start_date date,
    end_date date,
    reporting_frequency character varying(50),
    collection_target_percent numeric(5,2),
    recycling_target_percent numeric(5,2),
    recovery_target_percent numeric(5,2),
    fee_structure jsonb,
    penalty_structure jsonb,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.epr_programs OWNER TO postgres;

--
-- Name: epr_programs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.epr_programs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.epr_programs_id_seq OWNER TO postgres;

--
-- Name: epr_programs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.epr_programs_id_seq OWNED BY public.epr_programs.id;


--
-- Name: epr_registrations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.epr_registrations (
    id bigint NOT NULL,
    organization_id bigint NOT NULL,
    program_id bigint NOT NULL,
    registration_number character varying(100),
    registration_date date,
    registration_status character varying(50) DEFAULT 'active'::character varying,
    participant_type character varying(50),
    responsibility_type character varying(50),
    product_categories jsonb,
    material_types jsonb,
    annual_tonnage_estimate numeric(12,3),
    market_share_percent numeric(5,2),
    compliance_officer_name character varying(255),
    compliance_officer_email character varying(255),
    compliance_officer_phone character varying(50),
    renewal_date date,
    expiry_date date,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.epr_registrations OWNER TO postgres;

--
-- Name: epr_registrations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.epr_registrations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.epr_registrations_id_seq OWNER TO postgres;

--
-- Name: epr_registrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.epr_registrations_id_seq OWNED BY public.epr_registrations.id;


--
-- Name: epr_reports; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.epr_reports (
    id bigint NOT NULL,
    registration_id bigint NOT NULL,
    report_type character varying(50),
    report_period character varying(50),
    report_year integer,
    report_title character varying(255),
    report_description text,
    status character varying(50) DEFAULT 'generating'::character varying,
    executive_summary text,
    key_findings text,
    recommendations text,
    compliance_score integer,
    target_achievement_rate numeric(5,2),
    improvement_areas jsonb,
    report_file_url text,
    charts_data jsonb,
    generated_by_id bigint,
    generated_at timestamp with time zone,
    published_at timestamp with time zone,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.epr_reports OWNER TO postgres;

--
-- Name: epr_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.epr_reports_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.epr_reports_id_seq OWNER TO postgres;

--
-- Name: epr_reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.epr_reports_id_seq OWNED BY public.epr_reports.id;


--
-- Name: epr_targets; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.epr_targets (
    id bigint NOT NULL,
    registration_id bigint NOT NULL,
    target_year integer,
    target_period character varying(50),
    collection_target_kg numeric(12,3),
    recycling_target_kg numeric(12,3),
    recovery_target_kg numeric(12,3),
    collection_rate_target numeric(5,2),
    recycling_rate_target numeric(5,2),
    recovery_rate_target numeric(5,2),
    fee_target_amount numeric(12,2),
    investment_target_amount numeric(12,2),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.epr_targets OWNER TO postgres;

--
-- Name: epr_targets_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.epr_targets_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.epr_targets_id_seq OWNER TO postgres;

--
-- Name: epr_targets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.epr_targets_id_seq OWNED BY public.epr_targets.id;


--
-- Name: experts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.experts (
    id bigint NOT NULL,
    name character varying(255) NOT NULL,
    title character varying(255),
    organization character varying(255),
    email character varying(255),
    phone character varying(50),
    website text,
    expertise_areas jsonb,
    specializations jsonb,
    languages jsonb,
    years_experience integer,
    education text,
    certifications jsonb,
    publications jsonb,
    bio text,
    profile_image_url text,
    availability_status character varying(50) DEFAULT 'available'::character varying,
    hourly_rate numeric(10,2),
    currency_id bigint DEFAULT 12,
    average_rating numeric(3,2),
    total_reviews integer DEFAULT 0,
    created_by_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.experts OWNER TO postgres;

--
-- Name: experts_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.experts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.experts_id_seq OWNER TO postgres;

--
-- Name: experts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.experts_id_seq OWNED BY public.experts.id;


--
-- Name: gri_indicators; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.gri_indicators (
    id bigint NOT NULL,
    standard_id bigint NOT NULL,
    indicator_code character varying(20) NOT NULL,
    indicator_name character varying(255),
    description text,
    measurement_unit character varying(50),
    calculation_method text,
    is_mandatory boolean DEFAULT false,
    reporting_frequency character varying(50),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.gri_indicators OWNER TO postgres;

--
-- Name: gri_indicators_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.gri_indicators_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gri_indicators_id_seq OWNER TO postgres;

--
-- Name: gri_indicators_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.gri_indicators_id_seq OWNED BY public.gri_indicators.id;


--
-- Name: gri_report_data; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.gri_report_data (
    id bigint NOT NULL,
    report_id bigint NOT NULL,
    indicator_id bigint NOT NULL,
    quantitative_value numeric(15,6),
    qualitative_value text,
    unit character varying(50),
    scope character varying(100),
    boundary text,
    methodology text,
    assumptions text,
    data_source character varying(255),
    collection_method character varying(100),
    verification_status character varying(50),
    measurement_date date,
    period_start date,
    period_end date,
    notes text,
    supporting_documents jsonb,
    entered_by_id bigint,
    verified_by_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.gri_report_data OWNER TO postgres;

--
-- Name: gri_report_data_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.gri_report_data_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gri_report_data_id_seq OWNER TO postgres;

--
-- Name: gri_report_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.gri_report_data_id_seq OWNED BY public.gri_report_data.id;


--
-- Name: gri_reports; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.gri_reports (
    id bigint NOT NULL,
    organization_id bigint NOT NULL,
    report_title character varying(255),
    reporting_period character varying(50),
    reporting_year integer,
    report_type character varying(50),
    gri_version character varying(20),
    status character varying(50) DEFAULT 'draft'::character varying,
    total_energy_consumption numeric(15,3),
    total_water_consumption numeric(15,3),
    total_waste_generated numeric(15,3),
    total_emissions numeric(15,3),
    executive_summary text,
    methodology text,
    data_collection_approach text,
    external_assurance boolean DEFAULT false,
    assurance_provider character varying(255),
    assurance_level character varying(50),
    published_date date,
    report_url text,
    prepared_by_id bigint,
    approved_by_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.gri_reports OWNER TO postgres;

--
-- Name: gri_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.gri_reports_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gri_reports_id_seq OWNER TO postgres;

--
-- Name: gri_reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.gri_reports_id_seq OWNED BY public.gri_reports.id;


--
-- Name: gri_standards; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.gri_standards (
    id bigint NOT NULL,
    standard_code character varying(20) NOT NULL,
    standard_name character varying(255),
    category character varying(100),
    description text,
    requirements text,
    guidance text,
    version character varying(20),
    effective_date date,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.gri_standards OWNER TO postgres;

--
-- Name: gri_standards_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.gri_standards_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.gri_standards_id_seq OWNER TO postgres;

--
-- Name: gri_standards_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.gri_standards_id_seq OWNED BY public.gri_standards.id;


--
-- Name: km_chunks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.km_chunks (
    id bigint NOT NULL,
    file_id bigint NOT NULL,
    chunk_index integer,
    chunk_text text NOT NULL,
    chunk_size integer,
    embedding_json jsonb,
    page_number integer,
    section_title character varying(500),
    created_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.km_chunks OWNER TO postgres;

--
-- Name: km_chunks_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.km_chunks_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.km_chunks_id_seq OWNER TO postgres;

--
-- Name: km_chunks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.km_chunks_id_seq OWNED BY public.km_chunks.id;


--
-- Name: km_files; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.km_files (
    id bigint NOT NULL,
    filename character varying(255) NOT NULL,
    original_filename character varying(255),
    file_path text,
    file_size integer,
    file_type character varying(100),
    category character varying(100),
    tags jsonb,
    language character varying(10) DEFAULT 'en'::character varying,
    title character varying(500),
    description text,
    summary text,
    access_level character varying(50) DEFAULT 'public'::character varying,
    organization_id bigint,
    version character varying(20) DEFAULT '1.0'::character varying,
    parent_file_id bigint,
    is_latest_version boolean DEFAULT true,
    processing_status character varying(50) DEFAULT 'pending'::character varying,
    extraction_status character varying(50) DEFAULT 'pending'::character varying,
    extracted_text text,
    content_hash character varying(64),
    uploaded_by_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.km_files OWNER TO postgres;

--
-- Name: km_files_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.km_files_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.km_files_id_seq OWNER TO postgres;

--
-- Name: km_files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.km_files_id_seq OWNED BY public.km_files.id;


--
-- Name: locales; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.locales (
    id bigint NOT NULL,
    name character varying(100),
    code character varying(15),
    language_code character varying(10),
    country_code character varying(10),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.locales OWNER TO postgres;

--
-- Name: locales_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.locales_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.locales_id_seq OWNER TO postgres;

--
-- Name: locales_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.locales_id_seq OWNED BY public.locales.id;


--
-- Name: location_countries; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.location_countries (
    id bigint NOT NULL,
    name_th character varying(255),
    name_en character varying(255),
    code character varying(10),
    region character varying(100),
    continent character varying(50),
    currency_code character varying(10),
    phone_code character varying(10),
    timezone character varying(50),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone,
    name_local character varying(255)
);


ALTER TABLE public.location_countries OWNER TO postgres;

--
-- Name: location_countries_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.location_countries_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.location_countries_id_seq OWNER TO postgres;

--
-- Name: location_countries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.location_countries_id_seq OWNED BY public.location_countries.id;


--
-- Name: location_districts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.location_districts (
    id bigint NOT NULL,
    province_id bigint NOT NULL,
    name_th character varying(255),
    name_en character varying(255),
    code character varying(10),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone,
    name_local character varying(255)
);


ALTER TABLE public.location_districts OWNER TO postgres;

--
-- Name: location_districts_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.location_districts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.location_districts_id_seq OWNER TO postgres;

--
-- Name: location_districts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.location_districts_id_seq OWNED BY public.location_districts.id;


--
-- Name: location_provinces; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.location_provinces (
    id bigint NOT NULL,
    region_id bigint,
    country_id bigint NOT NULL,
    name_th character varying(255),
    name_en character varying(255),
    code character varying(10),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone,
    name_local character varying(255)
);


ALTER TABLE public.location_provinces OWNER TO postgres;

--
-- Name: location_provinces_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.location_provinces_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.location_provinces_id_seq OWNER TO postgres;

--
-- Name: location_provinces_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.location_provinces_id_seq OWNED BY public.location_provinces.id;


--
-- Name: location_regions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.location_regions (
    id bigint NOT NULL,
    country_id bigint NOT NULL,
    name_th character varying(255),
    name_en character varying(255),
    code character varying(10),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone,
    name_local character varying(255)
);


ALTER TABLE public.location_regions OWNER TO postgres;

--
-- Name: location_regions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.location_regions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.location_regions_id_seq OWNER TO postgres;

--
-- Name: location_regions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.location_regions_id_seq OWNED BY public.location_regions.id;


--
-- Name: location_subdistricts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.location_subdistricts (
    id bigint NOT NULL,
    district_id bigint NOT NULL,
    name_th character varying(255),
    name_en character varying(255),
    code character varying(10),
    postal_code character varying(10),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone,
    name_local character varying(255)
);


ALTER TABLE public.location_subdistricts OWNER TO postgres;

--
-- Name: location_subdistricts_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.location_subdistricts_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.location_subdistricts_id_seq OWNER TO postgres;

--
-- Name: location_subdistricts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.location_subdistricts_id_seq OWNED BY public.location_subdistricts.id;


--
-- Name: main_materials; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.main_materials (
    id bigint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    updated_date timestamp without time zone DEFAULT now() NOT NULL,
    deleted_date timestamp with time zone,
    name_en character varying(255),
    name_th character varying(255),
    name_local character varying(255),
    code character varying(50),
    material_tag_groups bigint[] DEFAULT '{}'::bigint[] NOT NULL
);


ALTER TABLE public.main_materials OWNER TO postgres;

--
-- Name: TABLE main_materials; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.main_materials IS 'Main material types (renamed from material_main)';


--
-- Name: COLUMN main_materials.material_tag_groups; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.main_materials.material_tag_groups IS 'Array of material_tag_group IDs that can be applied to materials of this main material type';


--
-- Name: main_materials_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.main_materials_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.main_materials_id_seq OWNER TO postgres;

--
-- Name: main_materials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.main_materials_id_seq OWNED BY public.main_materials.id;


--
-- Name: material_categories; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.material_categories (
    id bigint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    updated_date timestamp without time zone DEFAULT now() NOT NULL,
    deleted_date timestamp with time zone,
    name_en character varying(255),
    name_th character varying(255),
    code character varying(50),
    description text
);


ALTER TABLE public.material_categories OWNER TO postgres;

--
-- Name: TABLE material_categories; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.material_categories IS 'Material categories for classification and organization';


--
-- Name: COLUMN material_categories.name_en; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.material_categories.name_en IS 'Category name in English';


--
-- Name: COLUMN material_categories.name_th; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.material_categories.name_th IS 'Category name in Thai';


--
-- Name: COLUMN material_categories.code; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.material_categories.code IS 'Unique category code';


--
-- Name: COLUMN material_categories.description; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.material_categories.description IS 'Category description';


--
-- Name: material_categories_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.material_categories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.material_categories_id_seq OWNER TO postgres;

--
-- Name: material_categories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.material_categories_id_seq OWNED BY public.material_categories.id;


--
-- Name: material_tag_groups; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.material_tag_groups (
    id bigint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    color character varying(7) DEFAULT '#808080'::character varying NOT NULL,
    is_global boolean DEFAULT false NOT NULL,
    tags bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    organization_id bigint,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    updated_date timestamp with time zone DEFAULT now() NOT NULL,
    deleted_date timestamp with time zone,
    CONSTRAINT chk_material_tag_groups_color CHECK (((color)::text ~ '^#[0-9A-Fa-f]{6}$'::text)),
    CONSTRAINT chk_material_tag_groups_global_org CHECK ((((is_global = true) AND (organization_id IS NULL)) OR ((is_global = false) AND (organization_id IS NOT NULL))))
);


ALTER TABLE public.material_tag_groups OWNER TO postgres;

--
-- Name: TABLE material_tag_groups; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.material_tag_groups IS 'Groups of similar category material tags (e.g., colors: red, blue, white; quality: good, bad)';


--
-- Name: COLUMN material_tag_groups.tags; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.material_tag_groups.tags IS 'Array of material_tag IDs belonging to this group';


--
-- Name: material_tag_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.material_tag_groups_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.material_tag_groups_id_seq OWNER TO postgres;

--
-- Name: material_tag_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.material_tag_groups_id_seq OWNED BY public.material_tag_groups.id;


--
-- Name: material_tags; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.material_tags (
    id bigint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    color character varying(7) DEFAULT '#808080'::character varying NOT NULL,
    is_global boolean DEFAULT false NOT NULL,
    organization_id bigint,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    updated_date timestamp with time zone DEFAULT now() NOT NULL,
    deleted_date timestamp with time zone,
    CONSTRAINT chk_material_tags_color CHECK (((color)::text ~ '^#[0-9A-Fa-f]{6}$'::text)),
    CONSTRAINT chk_material_tags_global_org CHECK ((((is_global = true) AND (organization_id IS NULL)) OR ((is_global = false) AND (organization_id IS NOT NULL))))
);


ALTER TABLE public.material_tags OWNER TO postgres;

--
-- Name: TABLE material_tags; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.material_tags IS 'Material tags for waste material conditions, can be organization-specific or global';


--
-- Name: COLUMN material_tags.is_global; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.material_tags.is_global IS 'If true, tag is available to all organizations; if false, only to the specific organization';


--
-- Name: COLUMN material_tags.organization_id; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.material_tags.organization_id IS 'Required when is_global is false, null when is_global is true';


--
-- Name: material_tags_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.material_tags_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.material_tags_id_seq OWNER TO postgres;

--
-- Name: material_tags_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.material_tags_id_seq OWNED BY public.material_tags.id;


--
-- Name: materials; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.materials (
    id bigint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    updated_date timestamp without time zone DEFAULT now() NOT NULL,
    deleted_date timestamp with time zone,
    category_id bigint,
    main_material_id bigint,
    unit_name_th character varying(255),
    unit_name_en character varying(255),
    unit_weight numeric(10,4),
    color character varying(7),
    calc_ghg numeric(10,4),
    name_th character varying(255),
    name_en character varying(255),
    migration_id integer,
    tags jsonb DEFAULT '[]'::jsonb NOT NULL,
    fixed_tags jsonb DEFAULT '[]'::jsonb NOT NULL
);


ALTER TABLE public.materials OWNER TO postgres;

--
-- Name: TABLE materials; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.materials IS 'Enhanced materials table with category and environmental data';


--
-- Name: COLUMN materials.category_id; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.materials.category_id IS 'Legacy reference to material_categories, will be replaced by base_material mapping if not null';


--
-- Name: COLUMN materials.main_material_id; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.materials.main_material_id IS 'Legacy reference to main_materials, will be replaced by base_material mapping if not null';


--
-- Name: COLUMN materials.unit_name_th; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.materials.unit_name_th IS 'Unit name in Thai';


--
-- Name: COLUMN materials.unit_name_en; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.materials.unit_name_en IS 'Unit name in English';


--
-- Name: COLUMN materials.unit_weight; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.materials.unit_weight IS 'Weight per unit for calculations';


--
-- Name: COLUMN materials.color; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.materials.color IS 'Hex color code for UI display';


--
-- Name: COLUMN materials.calc_ghg; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.materials.calc_ghg IS 'GHG calculation factor per unit';


--
-- Name: COLUMN materials.name_th; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.materials.name_th IS 'Material name in Thai';


--
-- Name: COLUMN materials.name_en; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.materials.name_en IS 'Material name in English';


--
-- Name: COLUMN materials.migration_id; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.materials.migration_id IS 'Original ID from CSV migration data for tracking purposes';


--
-- Name: COLUMN materials.tags; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.materials.tags IS 'JSON array of tuples mapping material_tag_groups to material_tags: [(tag_group_id, tag_id)]';


--
-- Name: COLUMN materials.fixed_tags; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.materials.fixed_tags IS 'JSON array for material condition descriptions, same data type as tags';


--
-- Name: materials_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.materials_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.materials_id_seq OWNER TO postgres;

--
-- Name: materials_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.materials_id_seq OWNED BY public.materials.id;


--
-- Name: meeting_participants; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.meeting_participants (
    id bigint NOT NULL,
    meeting_id bigint NOT NULL,
    user_id bigint NOT NULL,
    role character varying(50),
    invitation_status character varying(50) DEFAULT 'pending'::character varying,
    attendance_status character varying(50) DEFAULT 'unknown'::character varying,
    joined_at timestamp with time zone,
    left_at timestamp with time zone,
    email_sent boolean DEFAULT false,
    reminder_sent boolean DEFAULT false,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.meeting_participants OWNER TO postgres;

--
-- Name: meeting_participants_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.meeting_participants_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.meeting_participants_id_seq OWNER TO postgres;

--
-- Name: meeting_participants_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.meeting_participants_id_seq OWNED BY public.meeting_participants.id;


--
-- Name: meetings; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.meetings (
    id bigint NOT NULL,
    title character varying(500) NOT NULL,
    description text,
    meeting_type character varying(50),
    organizer_id bigint NOT NULL,
    expert_id bigint,
    scheduled_start timestamp with time zone,
    scheduled_end timestamp with time zone,
    actual_start timestamp with time zone,
    actual_end timestamp with time zone,
    timezone character varying(50) DEFAULT 'UTC'::character varying,
    platform character varying(50),
    meeting_url text,
    meeting_id character varying(255),
    passcode character varying(100),
    location text,
    room character varying(100),
    address text,
    status character varying(50) DEFAULT 'scheduled'::character varying,
    agenda jsonb,
    notes text,
    action_items jsonb,
    decisions jsonb,
    recording_url text,
    presentation_urls jsonb,
    documents jsonb,
    is_billable boolean DEFAULT false,
    hourly_rate numeric(10,2),
    duration_minutes integer,
    total_cost numeric(10,2),
    currency_id bigint DEFAULT 12,
    organizer_rating integer,
    organizer_feedback text,
    expert_rating integer,
    expert_feedback text,
    reminder_sent boolean DEFAULT false,
    reminder_sent_at timestamp with time zone,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.meetings OWNER TO postgres;

--
-- Name: meetings_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.meetings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.meetings_id_seq OWNER TO postgres;

--
-- Name: meetings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.meetings_id_seq OWNED BY public.meetings.id;


--
-- Name: nationalities; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.nationalities (
    id bigint NOT NULL,
    name_th character varying(255),
    name_en character varying(255),
    code character varying(10),
    country_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.nationalities OWNER TO postgres;

--
-- Name: nationalities_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.nationalities_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.nationalities_id_seq OWNER TO postgres;

--
-- Name: nationalities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.nationalities_id_seq OWNED BY public.nationalities.id;


--
-- Name: organization_info; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.organization_info (
    id bigint NOT NULL,
    company_name character varying(255),
    company_name_th character varying(255),
    company_name_en character varying(255),
    display_name character varying(255),
    business_type text,
    business_industry text,
    business_sub_industry text,
    account_type text,
    tax_id character varying(50),
    national_id character varying(50),
    business_registration_certificate text,
    phone_number character varying(50),
    company_phone character varying(50),
    company_email character varying(255),
    address text,
    country_id bigint,
    province_id bigint,
    district_id bigint,
    subdistrict_id bigint,
    profile_image_url text,
    company_logo_url text,
    footprint numeric(10,2),
    project_id character varying(100),
    use_purpose text,
    application_date text,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.organization_info OWNER TO postgres;

--
-- Name: organization_info_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.organization_info_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.organization_info_id_seq OWNER TO postgres;

--
-- Name: organization_info_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.organization_info_id_seq OWNED BY public.organization_info.id;


--
-- Name: organization_permissions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.organization_permissions (
    id bigint NOT NULL,
    code character varying(100) NOT NULL,
    name character varying(255),
    description text,
    category character varying(100),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.organization_permissions OWNER TO postgres;

--
-- Name: organization_permissions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.organization_permissions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.organization_permissions_id_seq OWNER TO postgres;

--
-- Name: organization_permissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.organization_permissions_id_seq OWNED BY public.organization_permissions.id;


--
-- Name: organization_role_permissions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.organization_role_permissions (
    role_id bigint NOT NULL,
    permission_id bigint NOT NULL
);


ALTER TABLE public.organization_role_permissions OWNER TO postgres;

--
-- Name: organization_roles; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.organization_roles (
    id bigint NOT NULL,
    organization_id bigint NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    is_system boolean DEFAULT false,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone,
    key character varying(50)
);


ALTER TABLE public.organization_roles OWNER TO postgres;

--
-- Name: organization_roles_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.organization_roles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.organization_roles_id_seq OWNER TO postgres;

--
-- Name: organization_roles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.organization_roles_id_seq OWNED BY public.organization_roles.id;


--
-- Name: organization_setup; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.organization_setup (
    id bigint NOT NULL,
    organization_id bigint NOT NULL,
    version character varying(20) DEFAULT '1.0'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    root_nodes jsonb,
    hub_node jsonb,
    metadata jsonb,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    updated_date timestamp without time zone DEFAULT now() NOT NULL,
    deleted_date timestamp with time zone
);


ALTER TABLE public.organization_setup OWNER TO postgres;

--
-- Name: TABLE organization_setup; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.organization_setup IS 'Versioned organization structure setup table storing hierarchical configurations';


--
-- Name: COLUMN organization_setup.organization_id; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.organization_setup.organization_id IS 'Reference to the organization this setup belongs to';


--
-- Name: COLUMN organization_setup.version; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.organization_setup.version IS 'Version identifier for this configuration (e.g., "1.0", "1.1")';


--
-- Name: COLUMN organization_setup.is_active; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.organization_setup.is_active IS 'Indicates if this is the current active version for the organization';


--
-- Name: COLUMN organization_setup.root_nodes; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.organization_setup.root_nodes IS 'Expected JSON structure: [{"nodeId": "{user_location.id}", "children": [{"nodeId": "{user_location.id}", "children": [...]}]}]';


--
-- Name: COLUMN organization_setup.hub_node; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.organization_setup.hub_node IS 'Expected JSON structure: {"children": [{"nodeId": "{user_location.id}", "hubData": {"traceabilityFlows": {"children": [{"nodeId": "{user_location.id}", "name": "", "children": [...]}]}}}]}';


--
-- Name: COLUMN organization_setup.metadata; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.organization_setup.metadata IS 'JSON object containing additional metadata like totalNodes, maxLevel, createdAt, version';


--
-- Name: organization_setup_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.organization_setup_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.organization_setup_id_seq OWNER TO postgres;

--
-- Name: organization_setup_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.organization_setup_id_seq OWNED BY public.organization_setup.id;


--
-- Name: organizations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.organizations (
    id bigint NOT NULL,
    name character varying(255),
    description text,
    organization_info_id bigint,
    owner_id bigint,
    subscription_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone,
    system_role_id bigint
);


ALTER TABLE public.organizations OWNER TO postgres;

--
-- Name: organizations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.organizations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.organizations_id_seq OWNER TO postgres;

--
-- Name: organizations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.organizations_id_seq OWNED BY public.organizations.id;


--
-- Name: phone_number_country_codes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.phone_number_country_codes (
    id bigint NOT NULL,
    country_id bigint NOT NULL,
    code character varying(10),
    country_name character varying(255),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.phone_number_country_codes OWNER TO postgres;

--
-- Name: phone_number_country_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.phone_number_country_codes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.phone_number_country_codes_id_seq OWNER TO postgres;

--
-- Name: phone_number_country_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.phone_number_country_codes_id_seq OWNED BY public.phone_number_country_codes.id;


--
-- Name: platform_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.platform_logs (
    id bigint NOT NULL,
    log_level character varying(20),
    category character varying(100),
    source character varying(100),
    message text,
    details jsonb,
    user_id bigint,
    organization_id bigint,
    session_id character varying(255),
    request_id character varying(255),
    server_name character varying(100),
    process_id integer,
    thread_id integer,
    error_code character varying(50),
    error_type character varying(100),
    stack_trace text,
    execution_time_ms integer,
    memory_usage_mb numeric(10,2),
    cpu_usage_percent numeric(5,2),
    related_resource_type character varying(100),
    related_resource_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.platform_logs OWNER TO postgres;

--
-- Name: platform_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.platform_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.platform_logs_id_seq OWNER TO postgres;

--
-- Name: platform_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.platform_logs_id_seq OWNED BY public.platform_logs.id;


--
-- Name: point_transactions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.point_transactions (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    transaction_type character varying(50),
    points_type character varying(50) DEFAULT 'general'::character varying,
    points_amount integer,
    balance_before integer,
    balance_after integer,
    source_type character varying(50),
    source_reference_id bigint,
    description text,
    notes text,
    expires_at timestamp with time zone,
    processed_by_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.point_transactions OWNER TO postgres;

--
-- Name: point_transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.point_transactions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.point_transactions_id_seq OWNER TO postgres;

--
-- Name: point_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.point_transactions_id_seq OWNED BY public.point_transactions.id;


--
-- Name: reward_redemptions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.reward_redemptions (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    reward_id bigint NOT NULL,
    points_redeemed integer,
    redemption_code character varying(100),
    status character varying(50) DEFAULT 'pending'::character varying,
    delivery_method character varying(50),
    delivery_address text,
    delivery_instructions text,
    fulfillment_date date,
    tracking_number character varying(100),
    redeemed_at timestamp with time zone DEFAULT now(),
    expires_at timestamp with time zone,
    notes text,
    processed_by_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.reward_redemptions OWNER TO postgres;

--
-- Name: reward_redemptions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.reward_redemptions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.reward_redemptions_id_seq OWNER TO postgres;

--
-- Name: reward_redemptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.reward_redemptions_id_seq OWNED BY public.reward_redemptions.id;


--
-- Name: rewards_catalog; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.rewards_catalog (
    id bigint NOT NULL,
    reward_name character varying(255) NOT NULL,
    description text,
    category character varying(100),
    points_required integer NOT NULL,
    points_type character varying(50) DEFAULT 'general'::character varying,
    reward_value numeric(10,2),
    currency_id bigint DEFAULT 12,
    quantity_available integer,
    quantity_redeemed integer DEFAULT 0,
    is_limited_quantity boolean DEFAULT false,
    valid_from date,
    valid_until date,
    is_active boolean DEFAULT true,
    terms_and_conditions text,
    redemption_instructions text,
    image_url text,
    additional_images jsonb,
    provider_organization_id bigint,
    provider_contact_info jsonb,
    created_by_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now()
);


ALTER TABLE public.rewards_catalog OWNER TO postgres;

--
-- Name: rewards_catalog_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.rewards_catalog_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.rewards_catalog_id_seq OWNER TO postgres;

--
-- Name: rewards_catalog_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.rewards_catalog_id_seq OWNED BY public.rewards_catalog.id;


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.schema_migrations (
    id integer NOT NULL,
    version character varying(50) NOT NULL,
    filename character varying(255) NOT NULL,
    description text,
    executed_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    execution_time_ms integer,
    checksum character varying(64),
    batch_id uuid DEFAULT public.uuid_generate_v4()
);


ALTER TABLE public.schema_migrations OWNER TO postgres;

--
-- Name: schema_migrations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.schema_migrations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.schema_migrations_id_seq OWNER TO postgres;

--
-- Name: schema_migrations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.schema_migrations_id_seq OWNED BY public.schema_migrations.id;


--
-- Name: subscription_permissions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.subscription_permissions (
    subscription_id bigint NOT NULL,
    permission_id bigint NOT NULL
);


ALTER TABLE public.subscription_permissions OWNER TO postgres;

--
-- Name: subscription_plans; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.subscription_plans (
    id bigint NOT NULL,
    name character varying(100) NOT NULL,
    display_name character varying(255),
    description text,
    price_monthly integer DEFAULT 0,
    price_yearly integer DEFAULT 0,
    max_users integer DEFAULT 1,
    max_transactions_monthly integer DEFAULT 100,
    max_storage_gb integer DEFAULT 1,
    max_api_calls_daily integer DEFAULT 1000,
    features jsonb,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.subscription_plans OWNER TO postgres;

--
-- Name: subscription_plans_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.subscription_plans_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.subscription_plans_id_seq OWNER TO postgres;

--
-- Name: subscription_plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.subscription_plans_id_seq OWNED BY public.subscription_plans.id;


--
-- Name: subscriptions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.subscriptions (
    id bigint NOT NULL,
    organization_id bigint NOT NULL,
    plan_id bigint NOT NULL,
    status character varying(50) DEFAULT 'active'::character varying,
    trial_ends_at timestamp with time zone,
    current_period_starts_at timestamp with time zone DEFAULT now(),
    current_period_ends_at timestamp with time zone,
    users_count integer DEFAULT 1,
    transactions_count_this_month integer DEFAULT 0,
    storage_used_gb integer DEFAULT 0,
    api_calls_today integer DEFAULT 0,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.subscriptions OWNER TO postgres;

--
-- Name: subscriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.subscriptions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.subscriptions_id_seq OWNER TO postgres;

--
-- Name: subscriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.subscriptions_id_seq OWNED BY public.subscriptions.id;


--
-- Name: system_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.system_events (
    id bigint NOT NULL,
    event_type character varying(100),
    event_source character varying(100),
    event_data jsonb,
    correlation_id character varying(255),
    processing_status character varying(50) DEFAULT 'pending'::character varying,
    processed_at timestamp with time zone,
    retry_count integer DEFAULT 0,
    max_retries integer DEFAULT 3,
    error_message text,
    last_error_at timestamp with time zone,
    priority integer DEFAULT 5,
    scheduled_for timestamp with time zone DEFAULT now(),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.system_events OWNER TO postgres;

--
-- Name: system_events_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.system_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.system_events_id_seq OWNER TO postgres;

--
-- Name: system_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.system_events_id_seq OWNED BY public.system_events.id;


--
-- Name: system_permissions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.system_permissions (
    id bigint NOT NULL,
    code character varying(100) NOT NULL,
    name character varying(255),
    description text,
    category character varying(100),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.system_permissions OWNER TO postgres;

--
-- Name: system_permissions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.system_permissions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.system_permissions_id_seq OWNER TO postgres;

--
-- Name: system_permissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.system_permissions_id_seq OWNED BY public.system_permissions.id;


--
-- Name: system_roles; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.system_roles (
    id bigint NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    permissions text,
    created_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.system_roles OWNER TO postgres;

--
-- Name: system_roles_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.system_roles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.system_roles_id_seq OWNER TO postgres;

--
-- Name: system_roles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.system_roles_id_seq OWNED BY public.system_roles.id;


--
-- Name: transaction_analytics; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.transaction_analytics (
    id bigint NOT NULL,
    transaction_id bigint,
    processing_efficiency numeric(5,2),
    cost_per_kg numeric(10,4),
    environmental_impact_score integer,
    collection_duration integer,
    processing_duration integer,
    total_cycle_time integer,
    contamination_rate numeric(5,2),
    recovery_rate numeric(5,2),
    quality_score integer,
    revenue numeric(12,2),
    costs numeric(12,2),
    profit_margin numeric(5,2),
    carbon_footprint numeric(10,3),
    energy_efficiency numeric(10,3),
    water_usage numeric(10,3),
    calculated_at timestamp with time zone DEFAULT now(),
    created_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.transaction_analytics OWNER TO postgres;

--
-- Name: transaction_analytics_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.transaction_analytics_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.transaction_analytics_id_seq OWNER TO postgres;

--
-- Name: transaction_analytics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.transaction_analytics_id_seq OWNED BY public.transaction_analytics.id;


--
-- Name: transaction_documents; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.transaction_documents (
    id bigint NOT NULL,
    transaction_id bigint NOT NULL,
    document_type character varying(50),
    document_name character varying(255),
    file_url text,
    file_size integer,
    file_type character varying(50),
    uploaded_by_id bigint,
    verified_by_id bigint,
    verification_status character varying(50) DEFAULT 'pending'::character varying,
    verification_date timestamp with time zone,
    expiry_date timestamp with time zone,
    is_required boolean DEFAULT false,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.transaction_documents OWNER TO postgres;

--
-- Name: transaction_documents_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.transaction_documents_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.transaction_documents_id_seq OWNER TO postgres;

--
-- Name: transaction_documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.transaction_documents_id_seq OWNED BY public.transaction_documents.id;


--
-- Name: transaction_items; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.transaction_items (
    id bigint NOT NULL,
    transaction_id bigint NOT NULL,
    material_id bigint,
    waste_type character varying(100),
    description text,
    quantity numeric(10,3),
    unit character varying(20),
    weight_kg numeric(10,3),
    price_per_unit numeric(12,2),
    total_amount numeric(12,2),
    condition_rating integer,
    contamination_level character varying(20),
    processing_notes text,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.transaction_items OWNER TO postgres;

--
-- Name: transaction_items_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.transaction_items_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.transaction_items_id_seq OWNER TO postgres;

--
-- Name: transaction_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.transaction_items_id_seq OWNED BY public.transaction_items.id;


--
-- Name: transaction_payments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.transaction_payments (
    id bigint NOT NULL,
    transaction_id bigint NOT NULL,
    payment_method character varying(50),
    payment_status character varying(50) DEFAULT 'pending'::character varying,
    amount numeric(12,2),
    currency_id bigint DEFAULT 12,
    payment_date timestamp with time zone,
    due_date timestamp with time zone,
    payer_id bigint,
    payee_id bigint,
    payment_reference character varying(100),
    bank_reference character varying(100),
    gateway_transaction_id character varying(255),
    gateway_response jsonb,
    notes text,
    receipt_url text,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.transaction_payments OWNER TO postgres;

--
-- Name: transaction_payments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.transaction_payments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.transaction_payments_id_seq OWNER TO postgres;

--
-- Name: transaction_payments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.transaction_payments_id_seq OWNED BY public.transaction_payments.id;


--
-- Name: transaction_records; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.transaction_records (
    id bigint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    created_transaction_id bigint NOT NULL,
    traceability bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    transaction_type character varying(50) NOT NULL,
    material_id bigint,
    main_material_id bigint NOT NULL,
    category_id bigint NOT NULL,
    tags jsonb DEFAULT '[]'::jsonb NOT NULL,
    unit character varying(100) NOT NULL,
    origin_quantity numeric(15,4) DEFAULT 0 NOT NULL,
    origin_weight_kg numeric(15,4) DEFAULT 0 NOT NULL,
    origin_price_per_unit numeric(15,4) DEFAULT 0 NOT NULL,
    total_amount numeric(15,4) DEFAULT 0 NOT NULL,
    currency_id bigint,
    notes text,
    images jsonb DEFAULT '[]'::jsonb NOT NULL,
    origin_coordinates jsonb,
    destination_coordinates jsonb,
    hazardous_level integer DEFAULT 0 NOT NULL,
    treatment_method character varying(255),
    disposal_method character varying(255),
    created_by_id bigint NOT NULL,
    approved_by_id bigint,
    completed_date timestamp with time zone,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    updated_date timestamp with time zone DEFAULT now() NOT NULL,
    deleted_date timestamp with time zone,
    CONSTRAINT chk_transaction_records_quantities CHECK (((origin_quantity >= (0)::numeric) AND (origin_weight_kg >= (0)::numeric) AND (origin_price_per_unit >= (0)::numeric) AND (total_amount >= (0)::numeric))),
    CONSTRAINT transaction_records_hazardous_level_check CHECK (((hazardous_level >= 0) AND (hazardous_level <= 5))),
    CONSTRAINT transaction_records_transaction_type_check CHECK (((transaction_type)::text = ANY ((ARRAY['manual_input'::character varying, 'rewards'::character varying, 'iot'::character varying])::text[])))
);


ALTER TABLE public.transaction_records OWNER TO postgres;

--
-- Name: TABLE transaction_records; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.transaction_records IS 'Individual material transaction records with detailed tracking and traceability';


--
-- Name: COLUMN transaction_records.created_transaction_id; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transaction_records.created_transaction_id IS 'Reference to the transaction that created this record';


--
-- Name: COLUMN transaction_records.traceability; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transaction_records.traceability IS 'Sorted array of transaction IDs showing the material journey';


--
-- Name: COLUMN transaction_records.transaction_type; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transaction_records.transaction_type IS 'Type of transaction: manual_input, rewards, or iot';


--
-- Name: COLUMN transaction_records.tags; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transaction_records.tags IS 'Material condition tags: [(tag_group_id, tag_id), ...]';


--
-- Name: transaction_records_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.transaction_records_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.transaction_records_id_seq OWNER TO postgres;

--
-- Name: transaction_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.transaction_records_id_seq OWNED BY public.transaction_records.id;


--
-- Name: transaction_status_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.transaction_status_history (
    id bigint NOT NULL,
    transaction_id bigint NOT NULL,
    status character varying(50),
    previous_status character varying(50),
    reason text,
    notes text,
    changed_by_id bigint,
    changed_at timestamp with time zone DEFAULT now(),
    created_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.transaction_status_history OWNER TO postgres;

--
-- Name: transaction_status_history_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.transaction_status_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.transaction_status_history_id_seq OWNER TO postgres;

--
-- Name: transaction_status_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.transaction_status_history_id_seq OWNED BY public.transaction_status_history.id;


--
-- Name: transactions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.transactions (
    id bigint NOT NULL,
    status character varying(50) DEFAULT 'pending'::character varying,
    weight_kg numeric(10,3),
    total_amount numeric(12,2),
    transaction_date timestamp with time zone DEFAULT now(),
    notes text,
    images jsonb,
    vehicle_info jsonb,
    driver_info jsonb,
    hazardous_level integer,
    treatment_method character varying(100),
    disposal_method character varying(100),
    created_by_id bigint,
    updated_by_id bigint,
    approved_by_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone,
    transaction_records bigint[] DEFAULT '{}'::bigint[] NOT NULL,
    transaction_method character varying(50) DEFAULT 'origin'::character varying NOT NULL,
    organization_id bigint,
    origin_id bigint,
    destination_id bigint,
    arrival_date timestamp with time zone,
    origin_coordinates jsonb,
    destination_coordinates jsonb,
    CONSTRAINT chk_hazardous_level CHECK (((hazardous_level >= 0) AND (hazardous_level <= 5))),
    CONSTRAINT chk_total_amount CHECK ((total_amount >= (0)::numeric)),
    CONSTRAINT chk_transaction_method CHECK (((transaction_method)::text = ANY ((ARRAY['origin'::character varying, 'transport'::character varying, 'transform'::character varying])::text[]))),
    CONSTRAINT chk_weight_kg CHECK ((weight_kg >= (0)::numeric)),
    CONSTRAINT transactions_transaction_method_check CHECK (((transaction_method)::text = ANY ((ARRAY['origin'::character varying, 'transport'::character varying, 'transform'::character varying])::text[])))
);


ALTER TABLE public.transactions OWNER TO postgres;

--
-- Name: TABLE transactions; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.transactions IS 'Transaction batches that group multiple transaction records';


--
-- Name: COLUMN transactions.weight_kg; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transactions.weight_kg IS 'Total weight of all materials in this transaction (kg)';


--
-- Name: COLUMN transactions.total_amount; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transactions.total_amount IS 'Total monetary value of this transaction';


--
-- Name: COLUMN transactions.transaction_date; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transactions.transaction_date IS 'When the transaction was initiated';


--
-- Name: COLUMN transactions.vehicle_info; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transactions.vehicle_info IS 'Vehicle information: {license, type, capacity, etc.}';


--
-- Name: COLUMN transactions.driver_info; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transactions.driver_info IS 'Driver information: {name, license, contact, etc.}';


--
-- Name: COLUMN transactions.hazardous_level; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transactions.hazardous_level IS 'Overall hazardous level for this transaction (0-5)';


--
-- Name: COLUMN transactions.transaction_records; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transactions.transaction_records IS 'Array of transaction_record IDs belonging to this transaction batch';


--
-- Name: COLUMN transactions.transaction_method; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transactions.transaction_method IS 'Transaction method: origin, transport, or transform';


--
-- Name: COLUMN transactions.organization_id; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transactions.organization_id IS 'Organization responsible for this transaction';


--
-- Name: COLUMN transactions.origin_id; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transactions.origin_id IS 'Starting location/user for this transaction';


--
-- Name: COLUMN transactions.destination_id; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transactions.destination_id IS 'Ending location/user for this transaction';


--
-- Name: COLUMN transactions.arrival_date; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.transactions.arrival_date IS 'When materials arrived at destination';


--
-- Name: transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.transactions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.transactions_id_seq OWNER TO postgres;

--
-- Name: transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.transactions_id_seq OWNED BY public.transactions.id;


--
-- Name: user_activities; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_activities (
    id bigint NOT NULL,
    user_location_id bigint NOT NULL,
    actor_id bigint,
    activity_type character varying(100) NOT NULL,
    resource character varying(100),
    action character varying(100),
    details jsonb,
    ip_address character varying(45),
    user_agent text,
    organization_id bigint,
    session_id character varying(255),
    is_active boolean DEFAULT true,
    created_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    deleted_date timestamp without time zone
);


ALTER TABLE public.user_activities OWNER TO postgres;

--
-- Name: TABLE user_activities; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.user_activities IS 'Track user activity and engagement metrics';


--
-- Name: user_activities_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_activities_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_activities_id_seq OWNER TO postgres;

--
-- Name: user_activities_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_activities_id_seq OWNED BY public.user_activities.id;


--
-- Name: user_analytics; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_analytics (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    event_type character varying(100),
    event_data jsonb,
    session_id bigint,
    created_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.user_analytics OWNER TO postgres;

--
-- Name: user_analytics_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_analytics_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_analytics_id_seq OWNER TO postgres;

--
-- Name: user_analytics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_analytics_id_seq OWNED BY public.user_analytics.id;


--
-- Name: user_bank; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_bank (
    id bigint NOT NULL,
    user_location_id bigint NOT NULL,
    organization_id bigint NOT NULL,
    bank_id bigint,
    account_number character varying(50),
    account_name character varying(255),
    account_type character varying(50),
    branch_name character varying(255),
    branch_code character varying(20),
    is_verified boolean DEFAULT false,
    verification_date timestamp without time zone,
    is_primary boolean DEFAULT false,
    note text,
    is_active boolean DEFAULT true,
    created_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    deleted_date timestamp without time zone
);


ALTER TABLE public.user_bank OWNER TO postgres;

--
-- Name: TABLE user_bank; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.user_bank IS 'User banking information for payments and transfers';


--
-- Name: user_bank_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_bank_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_bank_id_seq OWNER TO postgres;

--
-- Name: user_bank_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_bank_id_seq OWNED BY public.user_bank.id;


--
-- Name: user_business_roles; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_business_roles (
    id bigint NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    permissions jsonb,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.user_business_roles OWNER TO postgres;

--
-- Name: user_business_roles_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_business_roles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_business_roles_id_seq OWNER TO postgres;

--
-- Name: user_business_roles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_business_roles_id_seq OWNED BY public.user_business_roles.id;


--
-- Name: user_devices; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_devices (
    id bigint NOT NULL,
    user_location_id bigint NOT NULL,
    device_id character varying(255) NOT NULL,
    device_name character varying(255),
    device_type character varying(50),
    platform character varying(50),
    browser character varying(100),
    browser_version character varying(50),
    os_version character varying(50),
    app_version character varying(50),
    is_trusted boolean DEFAULT false,
    push_token text,
    last_active timestamp without time zone,
    first_seen timestamp without time zone,
    is_active boolean DEFAULT true,
    created_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    deleted_date timestamp without time zone
);


ALTER TABLE public.user_devices OWNER TO postgres;

--
-- Name: TABLE user_devices; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.user_devices IS 'Track user devices and login sessions';


--
-- Name: user_devices_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_devices_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_devices_id_seq OWNER TO postgres;

--
-- Name: user_devices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_devices_id_seq OWNED BY public.user_devices.id;


--
-- Name: user_input_channels; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_input_channels (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    channel character varying(50),
    device_id character varying(255),
    last_accessed_at timestamp with time zone,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.user_input_channels OWNER TO postgres;

--
-- Name: user_input_channels_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_input_channels_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_input_channels_id_seq OWNER TO postgres;

--
-- Name: user_input_channels_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_input_channels_id_seq OWNED BY public.user_input_channels.id;


--
-- Name: user_invitations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_invitations (
    id bigint NOT NULL,
    email character varying(255) NOT NULL,
    phone character varying(50),
    invited_by_id bigint NOT NULL,
    organization_id bigint NOT NULL,
    intended_role character varying(50),
    intended_organization_role bigint,
    intended_platform character varying(50),
    status character varying(50) DEFAULT 'pending'::character varying,
    invitation_token character varying(255),
    expires_at timestamp without time zone NOT NULL,
    accepted_at timestamp without time zone,
    created_user_id bigint,
    custom_message text,
    invitation_data jsonb,
    is_active boolean DEFAULT true,
    created_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    deleted_date timestamp without time zone
);


ALTER TABLE public.user_invitations OWNER TO postgres;

--
-- Name: TABLE user_invitations; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.user_invitations IS 'Track user invitations and their acceptance status';


--
-- Name: user_invitations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_invitations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_invitations_id_seq OWNER TO postgres;

--
-- Name: user_invitations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_invitations_id_seq OWNED BY public.user_invitations.id;


--
-- Name: user_locations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_locations (
    id bigint NOT NULL,
    is_user boolean DEFAULT false NOT NULL,
    is_location boolean DEFAULT false NOT NULL,
    name_th character varying(255),
    name_en character varying(255),
    display_name character varying(255),
    email character varying(255),
    is_email_active boolean DEFAULT false NOT NULL,
    email_notification character varying(255),
    phone character varying(255),
    username character varying(255),
    password character varying(255),
    facebook_id character varying(255),
    apple_id character varying(255),
    google_id_gmail character varying(255),
    platform public.platform_enum DEFAULT 'BUSINESS'::public.platform_enum NOT NULL,
    role_id bigint,
    organization_role_id bigint,
    coordinate text,
    address text,
    postal_code character varying(10),
    country_id bigint DEFAULT 212 NOT NULL,
    province_id bigint,
    district_id bigint,
    subdistrict_id bigint,
    business_type text,
    business_industry text,
    business_sub_industry text,
    company_name text,
    company_phone text,
    company_email character varying(255),
    tax_id text,
    functions text,
    type text,
    population text,
    material text,
    profile_image_url text,
    national_id text,
    national_card_image text,
    business_registration_certificate text,
    organization_id bigint,
    parent_location_id bigint,
    created_by_id bigint,
    auditor_id bigint,
    parent_user_id bigint,
    organization_level integer DEFAULT 0,
    organization_path text,
    sub_users jsonb,
    locale character varying(15) DEFAULT 'TH'::character varying,
    nationality_id bigint,
    currency_id bigint DEFAULT 12 NOT NULL,
    phone_code_id bigint,
    note text,
    expired_date timestamp with time zone,
    footprint numeric(10,2),
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone,
    hub_type text,
    members jsonb
);


ALTER TABLE public.user_locations OWNER TO postgres;

--
-- Name: COLUMN user_locations.hub_type; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.user_locations.hub_type IS 'Hub type for waste management locations (from hubData.type), e.g. Collectors, Sorters, Aggregators, etc.';


--
-- Name: COLUMN user_locations.members; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON COLUMN public.user_locations.members IS 'JSON array of member objects with user_id and role for location user assignments, e.g. [{"user_id": "27", "role": "admin"}]';


--
-- Name: user_locations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_locations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_locations_id_seq OWNER TO postgres;

--
-- Name: user_locations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_locations_id_seq OWNED BY public.user_locations.id;


--
-- Name: user_organization_role_mapping; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_organization_role_mapping (
    user_location_id bigint NOT NULL,
    organization_id bigint NOT NULL,
    role_id bigint NOT NULL
);


ALTER TABLE public.user_organization_role_mapping OWNER TO postgres;

--
-- Name: user_organization_roles; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_organization_roles (
    user_location_id bigint NOT NULL,
    organization_id bigint NOT NULL,
    role_id bigint NOT NULL
);


ALTER TABLE public.user_organization_roles OWNER TO postgres;

--
-- Name: user_point_balances; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_point_balances (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    points_type character varying(50) DEFAULT 'general'::character varying,
    current_balance integer DEFAULT 0,
    lifetime_earned integer DEFAULT 0,
    lifetime_redeemed integer DEFAULT 0,
    pending_points integer DEFAULT 0,
    expired_points integer DEFAULT 0,
    last_activity_date timestamp with time zone,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.user_point_balances OWNER TO postgres;

--
-- Name: user_point_balances_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_point_balances_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_point_balances_id_seq OWNER TO postgres;

--
-- Name: user_point_balances_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_point_balances_id_seq OWNED BY public.user_point_balances.id;


--
-- Name: user_preferences; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_preferences (
    id bigint NOT NULL,
    user_location_id bigint NOT NULL,
    email_notifications boolean DEFAULT true,
    push_notifications boolean DEFAULT true,
    sms_notifications boolean DEFAULT false,
    language character varying(10) DEFAULT 'th'::character varying,
    timezone character varying(50) DEFAULT 'Asia/Bangkok'::character varying,
    theme character varying(20) DEFAULT 'light'::character varying,
    currency character varying(10) DEFAULT 'THB'::character varying,
    show_tutorials boolean DEFAULT true,
    compact_view boolean DEFAULT false,
    auto_save boolean DEFAULT true,
    profile_visibility character varying(20) DEFAULT 'organization'::character varying,
    share_analytics boolean DEFAULT true,
    custom_settings jsonb,
    is_active boolean DEFAULT true,
    created_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    deleted_date timestamp without time zone
);


ALTER TABLE public.user_preferences OWNER TO postgres;

--
-- Name: TABLE user_preferences; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.user_preferences IS 'User preferences and settings for personalization';


--
-- Name: user_preferences_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_preferences_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_preferences_id_seq OWNER TO postgres;

--
-- Name: user_preferences_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_preferences_id_seq OWNED BY public.user_preferences.id;


--
-- Name: user_roles; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_roles (
    id bigint NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    permissions jsonb,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone,
    organization_id bigint
);


ALTER TABLE public.user_roles OWNER TO postgres;

--
-- Name: user_roles_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_roles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_roles_id_seq OWNER TO postgres;

--
-- Name: user_roles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_roles_id_seq OWNED BY public.user_roles.id;


--
-- Name: user_sessions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_sessions (
    id bigint NOT NULL,
    user_id bigint NOT NULL,
    session_token character varying(255) NOT NULL,
    device_info text,
    ip_address inet,
    expires_at timestamp with time zone,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    deleted_date timestamp with time zone
);


ALTER TABLE public.user_sessions OWNER TO postgres;

--
-- Name: user_sessions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_sessions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_sessions_id_seq OWNER TO postgres;

--
-- Name: user_sessions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_sessions_id_seq OWNED BY public.user_sessions.id;


--
-- Name: user_subscriptions; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_subscriptions (
    id bigint NOT NULL,
    user_location_id bigint NOT NULL,
    organization_id bigint NOT NULL,
    subscription_package_id bigint,
    start_date date NOT NULL,
    end_date date,
    status character varying(50) DEFAULT 'active'::character varying,
    billing_cycle character varying(20),
    next_billing_date date,
    auto_renew boolean DEFAULT true,
    usage_data jsonb,
    is_active boolean DEFAULT true,
    created_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_date timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    deleted_date timestamp without time zone
);


ALTER TABLE public.user_subscriptions OWNER TO postgres;

--
-- Name: TABLE user_subscriptions; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON TABLE public.user_subscriptions IS 'User subscription information and billing details';


--
-- Name: user_subscriptions_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.user_subscriptions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_subscriptions_id_seq OWNER TO postgres;

--
-- Name: user_subscriptions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.user_subscriptions_id_seq OWNED BY public.user_subscriptions.id;


--
-- Name: user_subusers; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_subusers (
    parent_user_id bigint NOT NULL,
    subuser_id bigint NOT NULL,
    created_date timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean DEFAULT true NOT NULL
);


ALTER TABLE public.user_subusers OWNER TO postgres;

--
-- Name: waste_collections; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.waste_collections (
    id bigint NOT NULL,
    transaction_id bigint,
    collection_date timestamp with time zone,
    collection_address text,
    collection_coordinate text,
    collector_id bigint,
    collection_team jsonb,
    vehicle_type character varying(50),
    vehicle_plate character varying(20),
    vehicle_capacity numeric(10,3),
    collection_method character varying(50),
    container_types jsonb,
    weather_conditions character varying(50),
    traffic_conditions character varying(50),
    start_time timestamp with time zone,
    end_time timestamp with time zone,
    notes text,
    images jsonb,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.waste_collections OWNER TO postgres;

--
-- Name: waste_collections_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.waste_collections_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.waste_collections_id_seq OWNER TO postgres;

--
-- Name: waste_collections_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.waste_collections_id_seq OWNED BY public.waste_collections.id;


--
-- Name: waste_processing; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.waste_processing (
    id bigint NOT NULL,
    transaction_id bigint,
    processing_date timestamp with time zone,
    processing_facility_id bigint,
    input_weight numeric(10,3),
    output_weight numeric(10,3),
    waste_reduction_percent numeric(5,2),
    processing_method character varying(100),
    processing_equipment jsonb,
    processing_duration integer,
    quality_grade character varying(20),
    contamination_removed numeric(10,3),
    byproducts jsonb,
    residue_amount numeric(10,3),
    residue_disposal_method character varying(100),
    energy_consumed numeric(10,3),
    water_used numeric(10,3),
    operator_id bigint,
    supervisor_id bigint,
    notes text,
    processing_report_url text,
    created_date timestamp with time zone DEFAULT now(),
    updated_date timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true
);


ALTER TABLE public.waste_processing OWNER TO postgres;

--
-- Name: waste_processing_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.waste_processing_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.waste_processing_id_seq OWNER TO postgres;

--
-- Name: waste_processing_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.waste_processing_id_seq OWNED BY public.waste_processing.id;


--
-- Name: audit_logs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audit_logs ALTER COLUMN id SET DEFAULT nextval('public.audit_logs_id_seq'::regclass);


--
-- Name: banks id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.banks ALTER COLUMN id SET DEFAULT nextval('public.banks_id_seq'::regclass);


--
-- Name: base_materials id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.base_materials ALTER COLUMN id SET DEFAULT nextval('public.base_materials_id_seq'::regclass);


--
-- Name: chat_history id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chat_history ALTER COLUMN id SET DEFAULT nextval('public.chat_history_id_seq'::regclass);


--
-- Name: chats id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chats ALTER COLUMN id SET DEFAULT nextval('public.chats_id_seq'::regclass);


--
-- Name: currencies id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.currencies ALTER COLUMN id SET DEFAULT nextval('public.currencies_id_seq'::regclass);


--
-- Name: epr_audits id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_audits ALTER COLUMN id SET DEFAULT nextval('public.epr_audits_id_seq'::regclass);


--
-- Name: epr_data_submissions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_data_submissions ALTER COLUMN id SET DEFAULT nextval('public.epr_data_submissions_id_seq'::regclass);


--
-- Name: epr_notifications id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_notifications ALTER COLUMN id SET DEFAULT nextval('public.epr_notifications_id_seq'::regclass);


--
-- Name: epr_payments id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_payments ALTER COLUMN id SET DEFAULT nextval('public.epr_payments_id_seq'::regclass);


--
-- Name: epr_programs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_programs ALTER COLUMN id SET DEFAULT nextval('public.epr_programs_id_seq'::regclass);


--
-- Name: epr_registrations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_registrations ALTER COLUMN id SET DEFAULT nextval('public.epr_registrations_id_seq'::regclass);


--
-- Name: epr_reports id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_reports ALTER COLUMN id SET DEFAULT nextval('public.epr_reports_id_seq'::regclass);


--
-- Name: epr_targets id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_targets ALTER COLUMN id SET DEFAULT nextval('public.epr_targets_id_seq'::regclass);


--
-- Name: experts id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.experts ALTER COLUMN id SET DEFAULT nextval('public.experts_id_seq'::regclass);


--
-- Name: gri_indicators id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_indicators ALTER COLUMN id SET DEFAULT nextval('public.gri_indicators_id_seq'::regclass);


--
-- Name: gri_report_data id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_report_data ALTER COLUMN id SET DEFAULT nextval('public.gri_report_data_id_seq'::regclass);


--
-- Name: gri_reports id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_reports ALTER COLUMN id SET DEFAULT nextval('public.gri_reports_id_seq'::regclass);


--
-- Name: gri_standards id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_standards ALTER COLUMN id SET DEFAULT nextval('public.gri_standards_id_seq'::regclass);


--
-- Name: km_chunks id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.km_chunks ALTER COLUMN id SET DEFAULT nextval('public.km_chunks_id_seq'::regclass);


--
-- Name: km_files id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.km_files ALTER COLUMN id SET DEFAULT nextval('public.km_files_id_seq'::regclass);


--
-- Name: locales id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.locales ALTER COLUMN id SET DEFAULT nextval('public.locales_id_seq'::regclass);


--
-- Name: location_countries id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_countries ALTER COLUMN id SET DEFAULT nextval('public.location_countries_id_seq'::regclass);


--
-- Name: location_districts id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_districts ALTER COLUMN id SET DEFAULT nextval('public.location_districts_id_seq'::regclass);


--
-- Name: location_provinces id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_provinces ALTER COLUMN id SET DEFAULT nextval('public.location_provinces_id_seq'::regclass);


--
-- Name: location_regions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_regions ALTER COLUMN id SET DEFAULT nextval('public.location_regions_id_seq'::regclass);


--
-- Name: location_subdistricts id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_subdistricts ALTER COLUMN id SET DEFAULT nextval('public.location_subdistricts_id_seq'::regclass);


--
-- Name: main_materials id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.main_materials ALTER COLUMN id SET DEFAULT nextval('public.main_materials_id_seq'::regclass);


--
-- Name: material_categories id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.material_categories ALTER COLUMN id SET DEFAULT nextval('public.material_categories_id_seq'::regclass);


--
-- Name: material_tag_groups id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.material_tag_groups ALTER COLUMN id SET DEFAULT nextval('public.material_tag_groups_id_seq'::regclass);


--
-- Name: material_tags id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.material_tags ALTER COLUMN id SET DEFAULT nextval('public.material_tags_id_seq'::regclass);


--
-- Name: materials id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.materials ALTER COLUMN id SET DEFAULT nextval('public.materials_id_seq'::regclass);


--
-- Name: meeting_participants id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.meeting_participants ALTER COLUMN id SET DEFAULT nextval('public.meeting_participants_id_seq'::regclass);


--
-- Name: meetings id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.meetings ALTER COLUMN id SET DEFAULT nextval('public.meetings_id_seq'::regclass);


--
-- Name: nationalities id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.nationalities ALTER COLUMN id SET DEFAULT nextval('public.nationalities_id_seq'::regclass);


--
-- Name: organization_info id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_info ALTER COLUMN id SET DEFAULT nextval('public.organization_info_id_seq'::regclass);


--
-- Name: organization_permissions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_permissions ALTER COLUMN id SET DEFAULT nextval('public.organization_permissions_id_seq'::regclass);


--
-- Name: organization_roles id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_roles ALTER COLUMN id SET DEFAULT nextval('public.organization_roles_id_seq'::regclass);


--
-- Name: organization_setup id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_setup ALTER COLUMN id SET DEFAULT nextval('public.organization_setup_id_seq'::regclass);


--
-- Name: organizations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organizations ALTER COLUMN id SET DEFAULT nextval('public.organizations_id_seq'::regclass);


--
-- Name: phone_number_country_codes id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.phone_number_country_codes ALTER COLUMN id SET DEFAULT nextval('public.phone_number_country_codes_id_seq'::regclass);


--
-- Name: platform_logs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.platform_logs ALTER COLUMN id SET DEFAULT nextval('public.platform_logs_id_seq'::regclass);


--
-- Name: point_transactions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.point_transactions ALTER COLUMN id SET DEFAULT nextval('public.point_transactions_id_seq'::regclass);


--
-- Name: reward_redemptions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reward_redemptions ALTER COLUMN id SET DEFAULT nextval('public.reward_redemptions_id_seq'::regclass);


--
-- Name: rewards_catalog id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rewards_catalog ALTER COLUMN id SET DEFAULT nextval('public.rewards_catalog_id_seq'::regclass);


--
-- Name: schema_migrations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.schema_migrations ALTER COLUMN id SET DEFAULT nextval('public.schema_migrations_id_seq'::regclass);


--
-- Name: subscription_plans id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscription_plans ALTER COLUMN id SET DEFAULT nextval('public.subscription_plans_id_seq'::regclass);


--
-- Name: subscriptions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscriptions ALTER COLUMN id SET DEFAULT nextval('public.subscriptions_id_seq'::regclass);


--
-- Name: system_events id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.system_events ALTER COLUMN id SET DEFAULT nextval('public.system_events_id_seq'::regclass);


--
-- Name: system_permissions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.system_permissions ALTER COLUMN id SET DEFAULT nextval('public.system_permissions_id_seq'::regclass);


--
-- Name: system_roles id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.system_roles ALTER COLUMN id SET DEFAULT nextval('public.system_roles_id_seq'::regclass);


--
-- Name: transaction_analytics id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_analytics ALTER COLUMN id SET DEFAULT nextval('public.transaction_analytics_id_seq'::regclass);


--
-- Name: transaction_documents id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_documents ALTER COLUMN id SET DEFAULT nextval('public.transaction_documents_id_seq'::regclass);


--
-- Name: transaction_items id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_items ALTER COLUMN id SET DEFAULT nextval('public.transaction_items_id_seq'::regclass);


--
-- Name: transaction_payments id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_payments ALTER COLUMN id SET DEFAULT nextval('public.transaction_payments_id_seq'::regclass);


--
-- Name: transaction_records id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_records ALTER COLUMN id SET DEFAULT nextval('public.transaction_records_id_seq'::regclass);


--
-- Name: transaction_status_history id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_status_history ALTER COLUMN id SET DEFAULT nextval('public.transaction_status_history_id_seq'::regclass);


--
-- Name: transactions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transactions ALTER COLUMN id SET DEFAULT nextval('public.transactions_id_seq'::regclass);


--
-- Name: user_activities id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_activities ALTER COLUMN id SET DEFAULT nextval('public.user_activities_id_seq'::regclass);


--
-- Name: user_analytics id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_analytics ALTER COLUMN id SET DEFAULT nextval('public.user_analytics_id_seq'::regclass);


--
-- Name: user_bank id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_bank ALTER COLUMN id SET DEFAULT nextval('public.user_bank_id_seq'::regclass);


--
-- Name: user_business_roles id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_business_roles ALTER COLUMN id SET DEFAULT nextval('public.user_business_roles_id_seq'::regclass);


--
-- Name: user_devices id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_devices ALTER COLUMN id SET DEFAULT nextval('public.user_devices_id_seq'::regclass);


--
-- Name: user_input_channels id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_input_channels ALTER COLUMN id SET DEFAULT nextval('public.user_input_channels_id_seq'::regclass);


--
-- Name: user_invitations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_invitations ALTER COLUMN id SET DEFAULT nextval('public.user_invitations_id_seq'::regclass);


--
-- Name: user_locations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations ALTER COLUMN id SET DEFAULT nextval('public.user_locations_id_seq'::regclass);


--
-- Name: user_point_balances id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_point_balances ALTER COLUMN id SET DEFAULT nextval('public.user_point_balances_id_seq'::regclass);


--
-- Name: user_preferences id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_preferences ALTER COLUMN id SET DEFAULT nextval('public.user_preferences_id_seq'::regclass);


--
-- Name: user_roles id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_roles ALTER COLUMN id SET DEFAULT nextval('public.user_roles_id_seq'::regclass);


--
-- Name: user_sessions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_sessions ALTER COLUMN id SET DEFAULT nextval('public.user_sessions_id_seq'::regclass);


--
-- Name: user_subscriptions id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_subscriptions ALTER COLUMN id SET DEFAULT nextval('public.user_subscriptions_id_seq'::regclass);


--
-- Name: waste_collections id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.waste_collections ALTER COLUMN id SET DEFAULT nextval('public.waste_collections_id_seq'::regclass);


--
-- Name: waste_processing id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.waste_processing ALTER COLUMN id SET DEFAULT nextval('public.waste_processing_id_seq'::regclass);


--
-- Data for Name: audit_logs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.audit_logs (id, user_id, organization_id, action, resource_type, resource_id, description, changes, metadata, ip_address, user_agent, request_method, request_url, session_id, status, error_message, compliance_category, retention_period_days, created_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: banks; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.banks (id, name_th, name_en, code, swift_code, country_id, created_date, updated_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: base_materials; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.base_materials (id, is_active, created_date, updated_date, deleted_date, category_id, main_material_id, tag_groups, unit_name_th, unit_name_en, unit_weight, color, calc_ghg, name_th, name_en) FROM stdin;
\.


--
-- Data for Name: chat_history; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.chat_history (id, chat_id, message_type, message_content, sender_type, sender_id, sender_name, message_length, language, attachments, ai_confidence, ai_model, ai_tokens_used, is_read, read_at, user_rating, user_feedback, created_date, is_active) FROM stdin;
\.


--
-- Data for Name: chats; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.chats (id, user_id, expert_id, chat_type, subject, priority, status, session_id, platform, ai_model, ai_context, started_at, last_activity_at, closed_at, tags, category, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: currencies; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.currencies (id, name_th, name_en, code, symbol, exchange_rate, created_date, updated_date, is_active, deleted_date) FROM stdin;
1	ดอลลาร์สหรัฐ	US Dollar	USD	$	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
2	ยูโร	Euro	EUR	€	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
3	ปอนด์อังกฤษ	British Pound	GBP	£	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
4	เยนญี่ปุ่น	Japanese Yen	JPY	¥	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
5	หยวนจีน	Chinese Yuan	CNY	¥	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
10	ดอลลาร์สิงคโปร์	Singapore Dollar	SGD	S$	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
11	รินกิตมาเลเซีย	Malaysian Ringgit	MYR	RM	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
12	บาทไทย	Thai Baht	THB	฿	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
13	รูเปียห์อินโดนีเซีย	Indonesian Rupiah	IDR	Rp	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
14	เปโซฟิลิปปินส์	Philippine Peso	PHP	₱	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
15	ดองเวียดนาม	Vietnamese Dong	VND	₫	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
20	วอนเกาหลีใต้	South Korean Won	KRW	₩	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
21	ดอลลาร์ไต้หวัน	Taiwan Dollar	TWD	NT$	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
22	ดอลลาร์ฮ่องกง	Hong Kong Dollar	HKD	HK$	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
23	รูปีอินเดีย	Indian Rupee	INR	₹	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
30	เดอร์แฮมสหรัฐอาหรับเอมิเรตส์	UAE Dirham	AED	د.إ	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
31	ริยาลซาอุดีอาระเบีย	Saudi Riyal	SAR	﷼	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
32	ริยาลกาตาร์	Qatari Riyal	QAR	﷼	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
33	ดีนาร์คูเวต	Kuwaiti Dinar	KWD	د.ك	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
40	ดอลลาร์ออสเตรเลีย	Australian Dollar	AUD	A$	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
41	ดอลลาร์แคนาดา	Canadian Dollar	CAD	C$	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
42	ฟรังค์สวิส	Swiss Franc	CHF	CHF	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
43	โครนาสวีเดน	Swedish Krona	SEK	kr	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
44	โครเนนอร์เวย์	Norwegian Krone	NOK	kr	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
45	โครเนเดนมาร์ก	Danish Krone	DKK	kr	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
50	เรียลบราซิล	Brazilian Real	BRL	R$	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
51	เปโซอาร์เจนตินา	Argentine Peso	ARS	$	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
52	เปโซชิลี	Chilean Peso	CLP	$	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
53	เปโซเม็กซิโก	Mexican Peso	MXN	$	1.000000	2025-09-04 09:45:16.853099+00	2025-09-04 09:45:16.853099+00	t	\N
\.


--
-- Data for Name: epr_audits; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.epr_audits (id, registration_id, audit_type, audit_scope, audit_date_start, audit_date_end, auditor_name, auditor_organization, auditor_certification, overall_rating, compliance_level, findings, non_conformities, recommendations, corrective_actions, follow_up_date, follow_up_status, audit_report_url, supporting_evidence, conducted_by_id, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: epr_data_submissions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.epr_data_submissions (id, registration_id, reporting_period, reporting_year, submission_date, submission_status, products_placed_market_kg, waste_collected_kg, waste_recycled_kg, waste_recovered_kg, waste_disposed_kg, collection_rate, recycling_rate, recovery_rate, fees_paid, investments_made, data_sources, methodology, assumptions, submitted_by_id, reviewed_by, review_date, review_comments, submission_file_url, supporting_documents, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: epr_notifications; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.epr_notifications (id, registration_id, organization_id, notification_type, priority, title, message, scheduled_date, sent_date, read_date, recipient_emails, sent_to_users, status, related_submission_id, related_payment_id, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: epr_payments; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.epr_payments (id, registration_id, payment_type, payment_period, payment_year, base_amount, fee_rate, calculated_amount, penalty_amount, total_amount, currency_id, status, due_date, payment_date, payment_method, payment_reference, bank_reference, calculation_basis, notes, receipt_url, created_date, updated_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: epr_programs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.epr_programs (id, name, description, program_type, regulation_reference, authority, country_id, start_date, end_date, reporting_frequency, collection_target_percent, recycling_target_percent, recovery_target_percent, fee_structure, penalty_structure, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: epr_registrations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.epr_registrations (id, organization_id, program_id, registration_number, registration_date, registration_status, participant_type, responsibility_type, product_categories, material_types, annual_tonnage_estimate, market_share_percent, compliance_officer_name, compliance_officer_email, compliance_officer_phone, renewal_date, expiry_date, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: epr_reports; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.epr_reports (id, registration_id, report_type, report_period, report_year, report_title, report_description, status, executive_summary, key_findings, recommendations, compliance_score, target_achievement_rate, improvement_areas, report_file_url, charts_data, generated_by_id, generated_at, published_at, created_date, updated_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: epr_targets; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.epr_targets (id, registration_id, target_year, target_period, collection_target_kg, recycling_target_kg, recovery_target_kg, collection_rate_target, recycling_rate_target, recovery_rate_target, fee_target_amount, investment_target_amount, created_date, updated_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: experts; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.experts (id, name, title, organization, email, phone, website, expertise_areas, specializations, languages, years_experience, education, certifications, publications, bio, profile_image_url, availability_status, hourly_rate, currency_id, average_rating, total_reviews, created_by_id, created_date, updated_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: gri_indicators; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.gri_indicators (id, standard_id, indicator_code, indicator_name, description, measurement_unit, calculation_method, is_mandatory, reporting_frequency, created_date, updated_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: gri_report_data; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.gri_report_data (id, report_id, indicator_id, quantitative_value, qualitative_value, unit, scope, boundary, methodology, assumptions, data_source, collection_method, verification_status, measurement_date, period_start, period_end, notes, supporting_documents, entered_by_id, verified_by_id, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: gri_reports; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.gri_reports (id, organization_id, report_title, reporting_period, reporting_year, report_type, gri_version, status, total_energy_consumption, total_water_consumption, total_waste_generated, total_emissions, executive_summary, methodology, data_collection_approach, external_assurance, assurance_provider, assurance_level, published_date, report_url, prepared_by_id, approved_by_id, created_date, updated_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: gri_standards; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.gri_standards (id, standard_code, standard_name, category, description, requirements, guidance, version, effective_date, created_date, updated_date, is_active) FROM stdin;
1	GRI-301	Materials	environmental	Materials used and waste generated	\N	\N	\N	\N	2025-09-04 09:23:23.578818+00	2025-09-04 09:23:23.578818+00	t
2	GRI-302	Energy	environmental	Energy consumption and efficiency	\N	\N	\N	\N	2025-09-04 09:23:23.578818+00	2025-09-04 09:23:23.578818+00	t
3	GRI-303	Water	environmental	Water usage and conservation	\N	\N	\N	\N	2025-09-04 09:23:23.578818+00	2025-09-04 09:23:23.578818+00	t
4	GRI-305	Emissions	environmental	Greenhouse gas emissions	\N	\N	\N	\N	2025-09-04 09:23:23.578818+00	2025-09-04 09:23:23.578818+00	t
5	GRI-306	Waste	environmental	Waste generation and disposal	\N	\N	\N	\N	2025-09-04 09:23:23.578818+00	2025-09-04 09:23:23.578818+00	t
\.


--
-- Data for Name: km_chunks; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.km_chunks (id, file_id, chunk_index, chunk_text, chunk_size, embedding_json, page_number, section_title, created_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: km_files; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.km_files (id, filename, original_filename, file_path, file_size, file_type, category, tags, language, title, description, summary, access_level, organization_id, version, parent_file_id, is_latest_version, processing_status, extraction_status, extracted_text, content_hash, uploaded_by_id, created_date, updated_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: locales; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.locales (id, name, code, language_code, country_code, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: location_countries; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.location_countries (id, name_th, name_en, code, region, continent, currency_code, phone_code, timezone, created_date, updated_date, is_active, deleted_date, name_local) FROM stdin;
1	ประเทศไทย	Thailand	TH	\N	\N	THB	+66	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
2	มาเลเซีย	Malaysia	MY	\N	\N	MYR	+60	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
3	สิงคโปร์	Singapore	SG	\N	\N	SGD	+65	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
4	อินโดนีเซีย	Indonesia	ID	\N	\N	IDR	+62	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
5	ฟิลิปปินส์	Philippines	PH	\N	\N	PHP	+63	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
6	เวียดนาม	Vietnam	VN	\N	\N	VND	+84	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
7	กัมพูชา	Cambodia	KH	\N	\N	KHR	+855	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
8	ลาว	Laos	LA	\N	\N	LAK	+856	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
9	พม่า	Myanmar	MM	\N	\N	MMK	+95	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
10	บรูไน	Brunei	BN	\N	\N	BND	+673	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
20	จีน	China	CN	\N	\N	CNY	+86	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
21	ญี่ปุ่น	Japan	JP	\N	\N	JPY	+81	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
22	เกาหลีใต้	South Korea	KR	\N	\N	KRW	+82	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
23	เกาหลีเหนือ	North Korea	KP	\N	\N	KPW	+850	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
24	ไต้หวัน	Taiwan	TW	\N	\N	TWD	+886	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
25	ฮ่องกง	Hong Kong	HK	\N	\N	HKD	+852	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
26	มาเก๊า	Macau	MO	\N	\N	MOP	+853	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
30	อินเดีย	India	IN	\N	\N	INR	+91	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
31	ปากีสถาน	Pakistan	PK	\N	\N	PKR	+92	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
32	บังคลาเทศ	Bangladesh	BD	\N	\N	BDT	+880	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
33	ศรีลังกา	Sri Lanka	LK	\N	\N	LKR	+94	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
34	เนปาล	Nepal	NP	\N	\N	NPR	+977	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
35	ภูฏาน	Bhutan	BT	\N	\N	BTN	+975	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
36	มัลดีฟส์	Maldives	MV	\N	\N	MVR	+960	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
100	สหรัฐอเมริกา	United States	US	\N	\N	USD	+1	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
101	แคนาดา	Canada	CA	\N	\N	CAD	+1	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
102	เม็กซิโก	Mexico	MX	\N	\N	MXN	+52	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
103	บราซิล	Brazil	BR	\N	\N	BRL	+55	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
104	อาร์เจนตินา	Argentina	AR	\N	\N	ARS	+54	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
105	ชิลี	Chile	CL	\N	\N	CLP	+56	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
150	สหราชอาณาจักร	United Kingdom	GB	\N	\N	GBP	+44	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
151	เยอรมนี	Germany	DE	\N	\N	EUR	+49	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
152	ฝรั่งเศส	France	FR	\N	\N	EUR	+33	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
153	อิตาลี	Italy	IT	\N	\N	EUR	+39	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
154	สเปน	Spain	ES	\N	\N	EUR	+34	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
155	เนเธอร์แลนด์	Netherlands	NL	\N	\N	EUR	+31	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
156	สวิตเซอร์แลนด์	Switzerland	CH	\N	\N	CHF	+41	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
157	สวีเดน	Sweden	SE	\N	\N	SEK	+46	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
158	นอร์เวย์	Norway	NO	\N	\N	NOK	+47	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
159	เดนมาร์ก	Denmark	DK	\N	\N	DKK	+45	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
200	สหรัฐอาหรับเอมิเรตส์	United Arab Emirates	AE	\N	\N	AED	+971	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
201	ซาอุดีอาระเบีย	Saudi Arabia	SA	\N	\N	SAR	+966	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
202	อิสราเอล	Israel	IL	\N	\N	ILS	+972	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
203	ตุรกี	Turkey	TR	\N	\N	TRY	+90	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
204	กาตาร์	Qatar	QA	\N	\N	QAR	+974	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
205	คูเวต	Kuwait	KW	\N	\N	KWD	+965	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
210	ออสเตรเลีย	Australia	AU	\N	\N	AUD	+61	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
211	นิวซีแลนด์	New Zealand	NZ	\N	\N	NZD	+64	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
212	ประเทศไทย (ค่าเริ่มต้น)	Thailand (Default)	TH_DEFAULT	\N	\N	THB	+66	\N	2025-09-04 09:45:15.37523+00	2025-09-04 09:45:15.37523+00	t	\N	\N
\.


--
-- Data for Name: location_districts; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.location_districts (id, province_id, name_th, name_en, code, created_date, updated_date, is_active, deleted_date, name_local) FROM stdin;
\.


--
-- Data for Name: location_provinces; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.location_provinces (id, region_id, country_id, name_th, name_en, code, created_date, updated_date, is_active, deleted_date, name_local) FROM stdin;
\.


--
-- Data for Name: location_regions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.location_regions (id, country_id, name_th, name_en, code, created_date, updated_date, is_active, deleted_date, name_local) FROM stdin;
\.


--
-- Data for Name: location_subdistricts; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.location_subdistricts (id, district_id, name_th, name_en, code, postal_code, created_date, updated_date, is_active, deleted_date, name_local) FROM stdin;
\.


--
-- Data for Name: main_materials; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.main_materials (id, is_active, created_date, updated_date, deleted_date, name_en, name_th, name_local, code, material_tag_groups) FROM stdin;
1	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	Plastic	พลาสติก	\N	PLASTIC	{}
2	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	Glass	แก้ว	\N	GLASS	{}
3	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	Others	อื่นๆ	\N	OTHERS	{}
4	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	Paper	กระดาษ	\N	PAPER	{}
5	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	Metal	โลหะ	\N	METAL	{}
6	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	Computer Equipment	อุปกรณ์คอมพิวเตอร์	\N	COMPUTER	{}
7	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	Telecommunication	โทรคมนาคม	\N	TELECOM	{}
8	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	Electrical Appliances	เครื่องใช้ไฟฟ้า	\N	ELECTRICAL	{}
9	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	Electrical Wire	สายไฟ	\N	WIRE	{}
10	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	Food and Plant Waste	เศษอาหารและพืช	\N	FOOD_PLANT	{}
11	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	General Waste	ขยะทั่วไป	\N	GENERAL_WASTE	{}
12	t	2025-09-22 17:40:56.799169+00	2025-09-22 17:40:56.799169	\N	Bulbs and Sprays	หลอดไฟและสเปรย์	\N	BULBS_SPRAYS	{}
13	t	2025-09-22 17:40:56.799169+00	2025-09-22 17:40:56.799169	\N	Batteries	แบตเตอรี่	\N	BATTERIES	{}
14	t	2025-09-22 17:40:56.799169+00	2025-09-22 17:40:56.799169	\N	Wood	ไม้	\N	WOOD	{}
15	t	2025-09-22 17:40:56.799169+00	2025-09-22 17:40:56.799169	\N	Waste to Energy Material	วัสดุเผาทำเชื้อเพลิง	\N	WASTE_TO_ENERGY	{}
16	t	2025-09-22 17:40:56.799169+00	2025-09-22 17:40:56.799169	\N	Contaminated Plastic	พลาสติกปนเปื้อน	\N	CONTAMINATED_PLASTIC	{}
17	t	2025-09-22 17:40:56.799169+00	2025-09-22 17:40:56.799169	\N	Personal Items	ของใช้ส่วนตัว	\N	PERSONAL_ITEMS	{}
18	t	2025-09-22 17:40:56.799169+00	2025-09-22 17:40:56.799169	\N	Chemicals and Liquids	เคมีและของเหลว	\N	CHEMICALS	{}
19	t	2025-09-22 17:40:56.799169+00	2025-09-22 17:40:56.799169	\N	Liquids and Sludge	ของเหลวและตะกอน	\N	LIQUIDS_SLUDGE	{}
20	t	2025-09-22 17:40:56.799169+00	2025-09-22 17:40:56.799169	\N	Construction Materials	วัสดุก่อสร้าง	\N	CONSTRUCTION_MATERIALS	{}
\.


--
-- Data for Name: material_categories; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.material_categories (id, is_active, created_date, updated_date, deleted_date, name_en, name_th, code, description) FROM stdin;
1	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	Recyclable Waste	ขยะรีไซเคิล	RECYCLABLE	\N
2	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	Electronic Waste	ขยะอิเล็กทรอนิกส์	ELECTRONIC	\N
3	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	Organic Waste	ขยะอินทรีย์	ORGANIC	\N
4	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:17:25.835567	\N	General Waste	ขยะทั่วไป	GENERAL	\N
5	t	2025-09-22 17:40:56.799169+00	2025-09-22 17:40:56.799169	\N	Hazardous Waste	ขยะอันตราย	HAZARDOUS	\N
6	t	2025-09-22 17:40:56.799169+00	2025-09-22 17:40:56.799169	\N	Medical/Infectious Waste	ขยะทางการแพทย์/ติดเชื้อ	MEDICAL	\N
7	t	2025-09-22 17:40:56.799169+00	2025-09-22 17:40:56.799169	\N	Construction Waste	ขยะก่อสร้าง	CONSTRUCTION	\N
\.


--
-- Data for Name: material_tag_groups; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.material_tag_groups (id, is_active, name, description, color, is_global, tags, organization_id, created_date, updated_date, deleted_date) FROM stdin;
\.


--
-- Data for Name: material_tags; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.material_tags (id, is_active, name, description, color, is_global, organization_id, created_date, updated_date, deleted_date) FROM stdin;
\.


--
-- Data for Name: materials; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.materials (id, is_active, created_date, updated_date, deleted_date, category_id, main_material_id, unit_name_th, unit_name_en, unit_weight, color, calc_ghg, name_th, name_en, migration_id, tags, fixed_tags) FROM stdin;
25	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#c6db7b	1.8320	ตะกั่ว	Lead	56	[]	[]
50	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	3	ลัง	Carton	4.2000	#0a100b	0.2760	Asahi ลัง	Asahi (Carton)	31	[]	[]
79	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#336359	1.0310	พลาสติกใส (PET)	Clear Plastic (PET)	1	[]	[]
78	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#477269	1.0310	พลาสติก HDPE ขาวขุ่น	Opague Plastic (HDPE)	2	[]	[]
77	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#8df79e	1.0310	ถุงพลาสติก	Plastic Bag	3	[]	[]
76	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#2e8b57	1.0310	ท่อพีวีซีสีเขียว	PVC Pipes Green	4	[]	[]
75	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#b6e077	1.0310	โฟม	Foam	5	[]	[]
74	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#93ad6e	1.0310	พลาสติกรวม	Other plastic	6	[]	[]
73	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#bfd575	1.0310	พลาสติกกรอบ (PS)	Breakable Plastic (PS)	7	[]	[]
72	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#4c552e	1.0310	วีดีโอ	VDO	8	[]	[]
71	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#626262	1.0310	ซีดี	CD DVD	9	[]	[]
70	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#a5cca5	1.0310	สายยาง	Hose	10	[]	[]
69	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#4e7f52	1.0310	รองเท้าบู้ท	Boots	11	[]	[]
94	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	9	กิโลกรัม	Kilogram	1.0000	#20519d	1.0310	ปลอกสายไฟ	Electric wire coating	12	[]	[]
68	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	2	กิโลกรัม	Kilogram	1.0000	#8b4513	0.2760	ลีโอ ขวด	LEO (Bottle)	13	[]	[]
67	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	2	กิโลกรัม	Kilogram	1.0000	#6a996d	0.2760	ช้าง ขวด	Chang (Bottle)	14	[]	[]
66	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	2	กิโลกรัม	Kilogram	1.0000	#5b827a	0.2760	สิงห์ ขวด	Singha (Bottle)	15	[]	[]
65	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	2	กิโลกรัม	Kilogram	1.0000	#94bd9c	0.2760	ไฮเนเก้น ขวด	Heineken (Bottle)	16	[]	[]
64	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	2	กิโลกรัม	Kilogram	1.0000	#a3c7aa	0.2760	อาซาฮี ขวด	Asahi (Bottle)	17	[]	[]
63	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	2	กิโลกรัม	Kilogram	1.0000	#b3d0b8	0.2760	เหล้าขาว ขวด	Rice Whiskey (Bottle)	18	[]	[]
62	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	2	กิโลกรัม	Kilogram	1.0000	#66CC99	0.2760	ขวดแก้วใส	White Clear (Bottle)	19	[]	[]
61	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	2	กิโลกรัม	Kilogram	1.0000	#8df79e	0.2760	ขวดแก้วสีชา	Red Glass (Bottle)	20	[]	[]
60	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	2	กิโลกรัม	Kilogram	1.0000	#9edea8	0.2760	ขวดแก้วสีเขียว	Green Glass (Bottle)	21	[]	[]
59	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	2	กิโลกรัม	Kilogram	1.0000	#2E8B57	0.2760	ขวดแก้วสีรวมอื่น ๆ	Colored Glass (Bottle)	22	[]	[]
58	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	3	ลัง	Carton	4.2000	#5c9166	0.2760	ลีโอ ลัง 12 ขวด	LEO (12 bottle Carton)	23	[]	[]
57	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	3	ลัง	Carton	7.0000	#52815b	0.2760	ลีโอ ขวดเล็ก ลัง 24 ขวด	LEO 320ml (24 bottle carton)	24	[]	[]
56	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	3	ลัง	Carton	4.2000	#48714f	0.2760	ช้าง ลัง 12 ขวด	Chang (12 bottle Carton)	25	[]	[]
55	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	3	ลัง	Carton	7.0000	#3d6144	0.2760	ช้าง ขวดเล็ก ลัง 24 ขวด	Chang 320ml (24 bottle carton)	26	[]	[]
54	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	3	ลัง	Carton	4.2000	#335139	0.2760	สิงห์ ลัง 12 ขวด	Singha (12 bottle Carton)	27	[]	[]
53	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	3	ลัง	Carton	7.0000	#29402d	0.2760	สิงห์ ขวดเล็ก ลัง 24 ขวด	Singha 320ml (24 bottle carton)	28	[]	[]
52	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	3	ลัง	Carton	4.2000	#1e3022	0.2760	ไฮเนเก้น ลัง 12 ขวด	Heineken (12 bottle Carton)	29	[]	[]
51	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	3	ลัง	Carton	7.0000	#a7ccad	0.2760	ไฮเนเก้น ขวดเล็ก ลัง 24 ขวด	Heineken 320ml (24 bottle carton)	30	[]	[]
49	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	3	ลัง	Carton	4.2000	#808080	0.2760	เหล้าขาว ลัง	Thai Rice Whiskey (Carton)	32	[]	[]
48	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	3	ลัง	Carton	4.2000	#808080	0.2760	เหล้าขาวเล็ก ลัง	Thai Rice Whiskey (small box)	33	[]	[]
47	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	3	ลัง	Carton	4.2000	#808080	0.2760	คิริน (ลัง)	Kirin (Carton)	34	[]	[]
46	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	2	กิโลกรัม	Kilogram	1.0000	#1e7042	0.2760	เศษแก้วใส	White Cullet	35	[]	[]
45	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	2	กิโลกรัม	Kilogram	1.0000	#808080	0.2760	เศษแก้วสีชา	Red Cullet	36	[]	[]
44	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	2	กิโลกรัม	Kilogram	1.0000	#808080	0.2760	เศษแก้วสีเขียว	Green Cullet	37	[]	[]
43	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	2	กิโลกรัม	Kilogram	1.0000	#808080	0.2760	เศษแก้วสีรวมอื่น ๆ	Colored Cullet	38	[]	[]
42	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	4	กิโลกรัม	Kilogram	1.0000	#b6e077	5.6740	กระดาษลังสีน้ำตาล	Brown Paper Box / Carton / Cardboard	39	[]	[]
41	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	4	กิโลกรัม	Kilogram	1.0000	#86a35c	5.6740	กระดาษสีทั่วไป	Colored paper	40	[]	[]
40	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	4	กิโลกรัม	Kilogram	1.0000	#93ad6e	5.6740	กระดาษสีขาวดำ	Black and White paper	41	[]	[]
39	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	4	กิโลกรัม	Kilogram	1.0000	#a1b780	5.6740	หนังสือพิมพ์	Newspaper	42	[]	[]
38	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	4	กิโลกรัม	Kilogram	1.0000	#aec192	5.6740	นิตยสาร / หนังสือเล่มรวม	Magazines / Books	43	[]	[]
37	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	4	กิโลกรัม	Kilogram	1.0000	#bccca4	5.6740	กระดาษอื่น ๆ	Other paper	44	[]	[]
36	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	4	กิโลกรัม	Kilogram	1.0000	#c9d6b6	5.6740	เศษกระดาษฉีก ย่อยเส้น ไม่ฝอย	Shredded Paper	45	[]	[]
35	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	4	กิโลกรัม	Kilogram	1.0000	#92ba56	5.6740	กระดาษรวม (จับจั๊ว)	Mixed Paper	46	[]	[]
34	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#bfd575	1.8320	เหล็กเส้น	Steel bar	47	[]	[]
33	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#c5d982	1.8320	เหล็กแผ่น	Steel plate	48	[]	[]
32	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#cbdd90	1.8320	ท่อเหล็ก	Steel pipe	49	[]	[]
31	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#d2e19e	1.8320	ผลิตภัณฑ์เหล็กอื่น ๆ	Other steel	50	[]	[]
30	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#d8e5ac	1.8320	เหล็กหนา	Thick Steel	51	[]	[]
29	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#CCCC99	1.8320	เหล็กบาง	Thin Steel	52	[]	[]
28	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#a8a856	1.8320	ทองแดงปอกสวย (1)	Copper 1 (pre treated)	53	[]	[]
27	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#7d7d43	1.8320	ทองเหลืองบาง	Brass Thin	54	[]	[]
26	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#9e9e75	1.8320	สแตนเลส	Stainless Steel	55	[]	[]
24	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#abbf69	1.8320	สังกะสี	Zinc	57	[]	[]
23	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#98aa5d	1.8320	ทองแดงปอกดำ ช๊อต (2)	Copper Short Circuit 2 (thick)	58	[]	[]
22	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#859551	1.8320	ทองแดงเส้นใหญ่ เผา (3)	Copper Burn 3 (thick)	59	[]	[]
21	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#727f46	1.8320	ทองแดงเส้นเล็ก เผา (4)	Copper Burn 4 (thin small)	60	[]	[]
20	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#5f6a3a	1.8320	ทองแดงเส้นเล็ก (เครือบขาว)	Copper (mixed aluminum)	61	[]	[]
19	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#4c552e	1.8320	ทองแดง	Copper	62	[]	[]
93	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	6	ตามราคาประเมินหน้างาน	Estimate price on site	1.0000	#393f23	1.8320	บัลลาสไฟ	Ballast	63	[]	[]
92	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	6	เครื่อง	Price per unit	1.0000	#626262	0.0000	อุปกรณ์คอมพิวเตอร์	Computer accessories	64	[]	[]
91	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	7	เครื่อง	Price per unit	1.0000	#717171	0.0000	โทรศัพท์มือถือ	Mobile Phone	65	[]	[]
90	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	6	เครื่อง	Price per unit	1.0000	#818181	0.0000	ทีวี	TV	66	[]	[]
89	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	6	เครื่อง	Price per unit	1.0000	#919191	0.0000	เครื่องถ่ายเอกสาร แฟ๊กซ์ ปริ๊นเตอร์	Fax Printer Xerox	67	[]	[]
88	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	6	เครื่อง	Price per unit	1.0000	#a0a0a0	0.0000	เครื่องเล่นเสียง วิทยุ สเตอริโอ	Radio Stereo	68	[]	[]
87	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	8	เครื่อง	Price per unit	1.0000	#b0b0b0	0.0000	พัดลมตั้งโต๊ะ พัดลมเพดาน	Fan	69	[]	[]
86	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	8	เครื่อง	Price per unit	1.0000	#c0c0c0	0.0000	เครื่องครัวทำอาหาร หม้อหุงข้าว เตาอบ	Rice Cooker Oven	70	[]	[]
85	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	8	เครื่อง	Price per unit	1.0000	#cfcfcf	0.0000	อุปกรณ์ทำความสะอาด เครื่องดูดฝุ่น	Vacuum Cleaner	71	[]	[]
84	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	8	เครื่อง	Price per unit	1.0000	#dfdfdf	0.0000	เครื่องซักผ้า เครื่องอบผ้า	Washing Machine Dryer	72	[]	[]
83	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	8	เครื่อง	Price per unit	1.0000	#BEBEBE	0.0000	อิเล็กทรอนิกส์อื่น ๆ	Other electronic appliances	73	[]	[]
18	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#a5cca5	9.1270	อลูมิเนียม หนา	Aluminum Thick	74	[]	[]
17	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#88B288	9.1270	กระป๋องอลูมิเนียม (ขายตามน้ำหนักกิโลกรัม)	Aluminum Can (Kg)	75	[]	[]
16	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	ตามราคาประเมินต่อกระป๋อง	Price per can	0.0150	#9fc19f	9.1270	กระป๋องอลูมิเนียม (ขายนับกระป๋อง)	Aluminum Can (by can)	76	[]	[]
97	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	3	10	กิโลกรัม	Kilogram	1.0000	#4e7f52	0.4650	เศษอาหาร	Foodwaste	77	[]	[]
96	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	3	10	กิโลกรัม	Kilogram	1.0000	#628d65	0.8540	ใบไม้ ต้นไม้	Leaves Trees	78	[]	[]
95	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	3	10	กิโลกรัม	Kilogram	1.0000	#759b78	0.4650	ขยะย่อยสลายได้อื่น ๆ	Other organic waste	79	[]	[]
15	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#23453e	1.0310	ท่อพีวีซีสีขาว	PVC Pipes White	80	[]	[]
14	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#1e3b35	1.0310	แก้วพลาสติกนิ่ม	Soft Plastic Cup	81	[]	[]
13	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	4	กิโลกรัม	Kilogram	1.0000	#669933	5.6740	กระดาษย่อยเส้น ขาวดำ	Shredded Paper (White and Black)	82	[]	[]
12	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	4	กิโลกรัม	Kilogram	1.0000	#99CC33	5.6740	กระดาษย่อยเส้น สี รวมสี	Shredded Paper (Mixed Color)	83	[]	[]
11	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#bccfbc	9.1270	อลูนิเนียม บาง	Aluminum Thin	84	[]	[]
10	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	5	กิโลกรัม	Kilogram	1.0000	#5f7025	1.8320	ทองเหลืองหนา	Brass thick	85	[]	[]
9	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#19312c	1.0310	ฟิวเจอร์บอร์ด	Coroplast Sign Board	86	[]	[]
8	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#142723	1.0310	ถุงปุ๋ย	Fertilizer Plastic Sack	87	[]	[]
7	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#0f1d1a	1.0310	แฟ้มพลาสติก	Plastic Folder / Binder	88	[]	[]
6	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#02382c	1.0310	ท่อพีวีซีสีเทา เหลือง	PVC Pipes Grey Yellow	89	[]	[]
5	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#6c8278	1.0310	ท่อพีวีซีสีฟ้า	PVC Pipes Cyan	90	[]	[]
4	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#6c8942	5.6740	แผงไข่	Egg Packaging	91	[]	[]
3	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#486b64	1.0310	หลอดพลาสติก	Plastic Straw	92	[]	[]
82	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	9	กิโลกรัม	Kilogram	1.0000	#13150b	1.8320	สายไฟบ้าน	Electrical Wire	93	[]	[]
98	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	4	11	กิโลกรัม	Kilogram	1.0000	#20519d	0.0000	ขยะทั่วไป	General Waste	94	[]	[]
81	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	9	กิโลกรัม	Kilogram	1.0000	#808080	1.8320	สายไฟในอาคาร	Building Electrical Wire	95	[]	[]
80	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	2	9	กิโลกรัม	Kilogram	1.0000	#808080	1.8320	สายยูเอสบี	USB Cord	96	[]	[]
2	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#808080	1.0310	กระสอบข้าว	Rice Plastic Sack	97	[]	[]
1	t	2025-09-22 17:17:25.835567+00	2025-09-22 17:40:56.799169	\N	1	1	กิโลกรัม	Kilogram	1.0000	#808080	1.0310	กระสอบน้ำตาล	Sugar Plastic Sack	98	[]	[]
99	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#808080	1.0310	แก้วพลาสติก	PET Cup	307	[]	[]
100	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	3	กิโลกรัม	Kilogram	1.0000	#808080	2.3200	รีไซเคิลรวม	Recyclables	298	[]	[]
101	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	14	กิโลกรัม	Kilogram	1.0000	#808080	0.0000	เศษไม้	Wood scrap	297	[]	[]
102	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	3	กิโลกรัม	Kilogram	1.0000	#20519d	1.0310	วัสดุรีไซเคิลรวม	Recyclable Material	290	[]	[]
103	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#808080	1.0310	ขวดใส PET แบบไม่ลอกสลาก	PET with label	289	[]	[]
104	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#808080	1.0310	ขวดใส PET แบบลอกสลาก	PET with no label	288	[]	[]
105	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#808080	1.0310	ขวดใส PET แบบสกรีน	Screened color PET	287	[]	[]
106	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	3	กิโลกรัม	Kilogram	1.0000	#628c8a	1.0310	ถังน้ำแข็ง	Ice Bucket	285	[]	[]
107	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	กิโลกรัม	Kilogram	1.0000	#6a8a6a	9.1270	หม้อน้ำอลูมิเนียม	Aluminium Radiator	284	[]	[]
108	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#69b39d	1.0310	HDPE ขาวขุ่น สกรีน	Transparent HDPE with screening	273	[]	[]
109	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#41ab7b	1.0310	พลาสติกสีรวม (PET)	Mixed color plastic (PET)	272	[]	[]
110	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#0c7871	1.0310	ไบโอพลาสติก	Bio Plastic	261	[]	[]
111	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#02362b	1.0310	พลาสติก LDPE รวม	Other Plastic LDPE	260	[]	[]
112	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#3cd6ce	1.0310	ขวดและแกลลอน HDPE หลากสีทึบ	Colored and opaque HDPE bottle/gallon	259	[]	[]
113	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#09b5ac	1.0310	ขวดและแกลลอน HDPE สีขาวทึบ	White opaque HDPE bottle/gallon	258	[]	[]
114	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#0b8a83	1.0310	ขวดและแกลลอน HDPE โปร่งแสง	Transparent HDPE bottle/gallon	257	[]	[]
115	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#004f3f	1.0310	แก้วพลาสติกรวม (PET PP PS BIO)	Other Plastic Cup (PET PP PS BIO)	251	[]	[]
116	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#ccba6c	0.0000	ไวนิล	Vinyl	250	[]	[]
117	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#b0bfbc	1.0310	พลาสติกใส สกรีน PP	Clear Plastic Screen PP	247	[]	[]
118	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#d1e6e1	1.0310	พลาสติกใส PP	Clear Plastic PP	246	[]	[]
119	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#7ac2bc	1.0310	เชือกฟาง	Plastic Rope (PP)	243	[]	[]
120	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	กิโลกรัม	Kilogram	1.0000	#87a35d	1.8320	หม้อน้ำทองเหลือง	Brass Radiator	242	[]	[]
121	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	ถัง	Bucket	20.0000	#1c8562	1.0310	ถังพลาสติก 1000 ลิตร (ขาไม้)	Plastic Bucket 1000 liter (Wood stand)	241	[]	[]
122	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	ถัง	Bucket	20.0000	#1bcc91	1.0310	ถังพลาสติก 1000 ลิตร (ขาเหล็ก)	Plastic Bucket 1000 liter (Steel stand)	240	[]	[]
123	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	14	ชิ้น	Piece	15.0000	#1d4220	0.8540	ไม้พาเลท (นับเป็นชิ้น)	Wood Pallet (counted as a piece)	239	[]	[]
124	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	กิโลกรัม	Kilogram	1.0000	#596659	9.1270	อลูมิเนียมสายไฟปอกสวย	Aluminum Wire (Unwrap)	236	[]	[]
125	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	14	กิโลกรัม	Kilogram	1.0000	#086910	0.8540	ขาไม้ (ถังพลาสติก 1000 ลิตร)	Wooden legs of plastic bucket (Plastic Bucket 1000 liter)	235	[]	[]
126	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	ถัง	Bucket	15.0000	#b1c961	1.8320	ถังเหล็ก 200 ลิตร	Steel Bucket 200 liter	232	[]	[]
127	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	ถัง	Bucket	9.0000	#53827a	1.0310	ถังพลาสติก 200 ลิตร	Plastic Bucket 200 liter	231	[]	[]
128	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	ถัง	Bucket	7.0000	#9dc4bd	1.0310	ถังพลาสติก 150 ลิตร	Plastic Bucket 150 liter	230	[]	[]
129	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	ถัง	Bucket	20.0000	#638a82	1.0310	ถังพลาสติก 1000 ลิตร	Plastic Bucket 1000 liter	229	[]	[]
130	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#9cab85	5.6740	ถุงกระสอบ	Paper Sack Bag	225	[]	[]
131	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	4	กิโลกรัม	Kilogram	1.0000	#caff7d	5.6740	กระดาษเคลือบมัน	Coated Paper	224	[]	[]
132	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#b2f551	5.6740	แฟ้ม	Document Folder	223	[]	[]
133	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#00ffb3	1.0310	เชือกโพลีเอสเตอร์	Polyester Rope	222	[]	[]
134	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#12c48f	1.0310	โพลีคาร์บอเนต	Polycarbonate	221	[]	[]
135	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	3	กิโลกรัม	Kilogram	1.0000	#9abef5	0.0000	เรซิ่น กรองน้ำ	Resin filter	217	[]	[]
136	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#73807d	1.0310	พาเลทพลาสติกรวม (HDPE PP)	Other Plastic Pallet (HDPE PP)	214	[]	[]
137	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	14	กิโลกรัม	Kilogram	1.0000	#5bb07c	0.8540	ไม้พาเลท	Wood Pallet	213	[]	[]
138	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	กิโลกรัม	Kilogram	1.0000	#749406	1.8320	ถังเหล็กเปล่า 210 ลิตร	Steel Container 210 liter	212	[]	[]
139	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	กิโลกรัม	Kilogram	1.0000	#c5f522	1.8320	ถังโลหะ	Metal Bucket	211	[]	[]
140	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#486660	1.0310	สายรัดพลาสติกรวม (PET PP HDPE)	Plastic Strap (PET PP HDPE)	210	[]	[]
141	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#ebd8ca	0.0000	พลาสติกรวม	Other plastic (Waste to Energy)	205	[]	[]
142	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	3	กิโลกรัม	Kilogram	1.0000	#a88f7d	0.0000	เศษผ้า	Contaminated Fabric	204	[]	[]
143	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	2	ลัง	Carton	7.0000	#5cc470	0.2760	ขวดแก้วรวม ขวดเล็ก ลัง 24 ขวด	Colored Glass 320ml (24 bottle carton)	203	[]	[]
144	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	2	ลัง	Carton	4.2000	#4bad5e	0.2760	ขวดแก้วรวม ลัง 12 ขวด	Colored Glass (12 bottle Carton)	202	[]	[]
145	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#5bc7b1	1.0310	ตาข่ายรวม (PE PP Nylon)	Fishing Net	201	[]	[]
146	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	กิโลกรัม	Kilogram	1.0000	#4b7d4b	9.1270	อลูมิเนียมฉาก	Aluminum Angle	200	[]	[]
147	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	กิโลกรัม	Kilogram	1.0000	#9cbf1d	1.8320	หม้อน้ำทองแดง	Copper Radiator	199	[]	[]
148	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	กิโลกรัม	Kilogram	1.0000	#6a8a6a	9.1270	หม้อน้ำอลูมิเนียม	Aluminium Radiator	198	[]	[]
149	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#b6ccc7	1.0310	เศษผงพลาสติก (PP)	PP Plastic Powder	197	[]	[]
150	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#7bedd3	1.0310	พลาสติกดำ	Black Plastic	195	[]	[]
151	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	2	กิโลกรัม	Kilogram	1.0000	#3a6642	0.2760	ขวดแก้วสีรวม (รีไซเคิลทางเลือก)	Mixed Glass (Recycling Alternative)	192	[]	[]
152	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#a2bdb7	1.0310	ตาข่าย Nylon	Nylon Net	191	[]	[]
153	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#9dc7be	1.0310	ตาข่าย HDPE	HDPE Net	190	[]	[]
154	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#7dd1bf	1.0310	เชือก PP/PE	PP/PE Rope	189	[]	[]
155	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#d9baa3	0.0000	ถุงขนม / ซองอ่อนหลายชั้น	Multilayer packaging (Waste to energy)	159	[]	[]
156	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#95a8c4	0.0000	ถุงพลาสติก	Plastic Bag (Waste to energy)	158	[]	[]
157	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#f09a59	0.0000	โฟม	Foam (Waste to energy)	156	[]	[]
158	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	กิโลกรัม	Kilogram	1.0000	#828267	1.8320	กระป๋องสเปรย์ (รีไซเคิล)	Aerosol Cans (Recycle)	154	[]	[]
159	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	กิโลกรัม	Kilogram	1.0000	#ccccab	1.8320	ปี๊บ	Bucket Steel	153	[]	[]
160	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#69857e	1.0310	สายรัดพลาสติก (PP)	Plastic Strap (PP)	152	[]	[]
161	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#808080	1.0310	สายรัดพลาสติก (PET)	Plastic Strap (PET)	151	[]	[]
162	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#49786d	1.0310	ฟิล์มยืด	Stretch Film	150	[]	[]
163	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	3	ลัง	Carton	4.2000	#84ab8b	0.2760	แสงโสม ลัง 12 ขวด	Sang Som (12 bottle Carton)	149	[]	[]
164	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	3	กิโลกรัม	Kilogram	1.0000	#ed0a02	0.0000	อุปกรณ์สำนักงาน	Office supplies	146	[]	[]
165	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	14	กิโลกรัม	Kilogram	1.0000	#cc9266	0.0000	ไม้พาเลท	Pallet wood	142	[]	[]
166	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	3	ลัง	Carton	4.2000	#b3e3bc	0.2760	หงส์ทอง ลัง 12 ขวด	Hong Thong (12 bottle Carton)	141	[]	[]
167	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	14	กิโลกรัม	Kilogram	1.0000	#6a996d	0.8540	เศษไม้พาเลท	Pallet wood chips	137	[]	[]
168	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	กิโลกรัม	Kilogram	1.0000	#77b577	9.1270	เศษอลูมิเนียม	Aluminium Scrap	136	[]	[]
169	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	กิโลกรัม	Kilogram	1.0000	#bfdb63	1.8320	เศษเหล็กรวม	Steel Scrap	133	[]	[]
170	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	กิโลกรัม	Kilogram	1.0000	#b2cc5c	1.8320	เศษขี้กลึงเหล็ก	Steel Turning Scrap	132	[]	[]
171	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	5	กิโลกรัม	Kilogram	1.0000	#a89676	1.8320	กระป๋องเหล็ก	Metal Cans	131	[]	[]
172	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	4	กิโลกรัม	Kilogram	1.0000	#5cb504	5.6740	ถุงกระสอบเคลือบกระดาษ	Multiwall Paper Sacks	130	[]	[]
173	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	4	กิโลกรัม	Kilogram	1.0000	#4c9404	5.6740	แกนกระดาษ	Paper Cores	129	[]	[]
174	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#0bdeb4	1.0310	เศษก้อน (PP)	PP Lumps	128	[]	[]
175	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#0ccfa8	1.0310	เศษก้อน (PS)	PS Lumps	127	[]	[]
176	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	ใบ	Price per bag	3.0000	#0bbf9b	1.0310	ถุงบิ๊กแบ็ก (ไม่ตัดปาก)	Big Bags Narrow	126	[]	[]
177	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	ใบ	Price per bag	3.0000	#08997b	1.0310	ถุงบิ๊กแบ็ก (ตัดปาก)	Big Bags Wide	125	[]	[]
178	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	ถัง	Price per gallon	1.5000	#42fcd6	1.0310	ถังน้ำมันพลาสติกเปล่า 20 ลิตร (HDPE)	HDPE Oil container	124	[]	[]
179	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#3febc8	1.0310	เกล็ดโม่ (PP)	PP Flakes	123	[]	[]
180	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#35b89d	1.0310	แก้วพลาสติกรวม (PP PS BIO)	Other Plastic Cup	120	[]	[]
181	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#2fa38b	1.0310	แก้วพลาสติกนิ่ม (PP)	PP Soft Plastic Cup	119	[]	[]
182	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#1d8079	1.0310	ท่อพีวีซีรวม	Other PVC Pipes	118	[]	[]
183	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#669999	1.0310	พลาสติกพีวีซี รวม	Other PVC	117	[]	[]
184	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#4c73b0	0.0000	แก้ว PLA	PLA Cup	116	[]	[]
185	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	14	กิโลกรัม	Kilogram	1.0000	#89a98b	0.8540	ไม้	Wood	107	[]	[]
186	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#808080	1.0310	ซองอ่อนหลายชั้น	Multilayer flexible packaging	104	[]	[]
187	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#808080	1.0310	อะคริลิค	Acrylic	102	[]	[]
188	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#84a19b	1.0310	พลาสติกรวมสี PP	Other Color Plastic PP	101	[]	[]
189	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#808080	1.0310	พลาสติก HDPE สี	Colored Plastic (HDPE)	100	[]	[]
190	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	1	1	กิโลกรัม	Kilogram	1.0000	#607a3b	4.2550	กล่องนม กล่องน้ำผลไม้	UHT Carton	99	[]	[]
191	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	2	9	กิโลกรัม	Kilogram	1.0000	#808080	0.0000	สายแลน	LAN Cable	304	[]	[]
192	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	2	3	กิโลกรัม	Kilogram	1.0000	#20519d	0.0000	ขยะอิเล็กทรอนิกส์รวม	Electronic Waste	295	[]	[]
193	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	2	9	กิโลกรัม	Kilogram	1.0000	#ad9393	0.0000	สายชาร์จ	Charging Cable	254	[]	[]
194	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	2	6	กิโลกรัม	Kilogram	1.0000	#b5b5b5	0.0000	เครื่องคอมพิวเตอร์	Desktop PC	252	[]	[]
195	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	2	8	เครื่อง	Price per unit	1.0000	#decaca	0.0000	ตู้เย็น	Refrigerator	238	[]	[]
196	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	2	6	เครื่อง	Price per unit	1.0000	#918686	0.0000	จอคอมพิวเตอร์	Computer Monitor	237	[]	[]
197	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	2	6	กิโลกรัม	Kilogram	1.0000	#dec3b1	0.0000	ตลับหมึกจากเครื่องปริ้นท์	Ink cartridges from printers	208	[]	[]
198	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	2	9	กิโลกรัม	Kilogram	1.0000	#d10902	0.0000	สายโฮส	Hose line	145	[]	[]
199	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	2	6	กิโลกรัม	Kilogram	1.0000	#de4b45	0.0000	แมคเนติก และ แผงวงจรที่ชำรุด	Magnetic and Damaged circuit board	106	[]	[]
200	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	2	8	เครื่อง	Price per unit	1.0000	#585858	0.0000	เครื่องปรับอากาศและคอมเพรสเซอร์แอร์ 1 คู่	Fancoil Unit FCU and Condensing Unit CDU	103	[]	[]
201	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	3	10	กิโลกรัม	Kilogram	1.0000	#808080	2.5310	อาหารส่วนเกิน	Food Surplus	308	[]	[]
202	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	3	10	กิโลกรัม	Kilogram	1.0000	#4bcf31	0.4650	เศษอาหารจากจาน	Plate waste	306	[]	[]
203	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	3	10	กิโลกรัม	Kilogram	1.0000	#4bcf31	0.4650	เศษอาหารจากการจัดเตรียม	Preparation waste	305	[]	[]
204	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	3	19	กิโลกรัม	Kilogram	1.0000	#808080	0.0000	อุจจาระและสิ่งปฏิกูล	Sanitary waste	299	[]	[]
205	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	3	19	กิโลกรัม	Kilogram	1.0000	#617fad	0.0000	กากตะกอนไขมัน (ฝังกลบ)	Fat Sludge (Landfill)	263	[]	[]
206	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	3	19	ตัน	Tonne	1000.0000	#667894	0.0000	กากตะกอน (กาวน้ำ)	Sludge (Water Glue)	226	[]	[]
207	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	3	19	กิโลกรัม	Kilogram	1.0000	#073d0c	0.4650	กากตะกอนจากระบบบำบัดน้ำเสีย	Sludge from the wastewater treatment system	219	[]	[]
208	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	3	19	กิโลกรัม	Kilogram	1.0000	#b1fab7	0.4650	กากตะกอนไขมัน	Fat Sludge	218	[]	[]
209	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	3	19	กิโลกรัม	Kilogram	1.0000	#29d936	0.4650	แป้งเสื่อมสภาพ	Starch is not of good quality	216	[]	[]
210	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	3	19	กิโลกรัม	Kilogram	1.0000	#808080	0.4650	เนยและชีสเสื่อมสภาพ น้ำมันพืช น้ำมัน Stearin	Decay Butter and Cheese, Vegetable Cooking Oil, Stearin Oil	215	[]	[]
211	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	11	กิโลกรัม	Kilogram	1.0000	#20519d	0.0000	ขยะพลังงานรวม	Waste to Energy	293	[]	[]
212	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	11	กิโลกรัม	Kilogram	1.0000	#20519d	0.4650	ขยะอินทรีย์และเศษอาหาร	Organic and Food Waste	291	[]	[]
213	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	11	กิโลกรัม	Kilogram	1.0000	#628c8a	0.0000	ไม้ (ขยะทั่วไป)	Wood (General Waste)	286	[]	[]
214	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	\N	กิโลกรัม	Kilogram	1.0000	#bd959d	0.0000	กระดาษชำระ	Toilet Paper	256	[]	[]
215	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	15	กิโลกรัม	Kilogram	1.0000	#f0c84f	0.0000	ฟิวเจอร์บอร์ด (ขยะทำเชื้อเพลิง)	Corrugated plastic board	249	[]	[]
216	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	15	กิโลกรัม	Kilogram	1.0000	#F5CB06	0.0000	ไส้กรองน้ำมัน (ขยะทำเชื้อเพลิง)	Oil Filter (Waste to energy)	248	[]	[]
217	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	11	กิโลกรัม	Kilogram	1.0000	#3269bf	0.0000	ขยะฝังกลบ	Waste to Landfill	186	[]	[]
218	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	15	กิโลกรัม	Kilogram	1.0000	#98a3a1	0.0000	ถุงขนม / ซองอ่อนหลายชั้น (เผากำจัด)	Multilayer packaging (Inceneration)	160	[]	[]
219	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	15	กิโลกรัม	Kilogram	1.0000	#728581	0.0000	ถุงพลาสติก (เผากำจัด)	Plastic Bag (Inceneration)	157	[]	[]
220	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	15	กิโลกรัม	Kilogram	1.0000	#6d90c7	0.0000	โฟม (เผากำจัด)	Foam (Inceneration)	155	[]	[]
221	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	11	เส้น	Price per line	17.0000	#ea3bff	0.0000	ยางรถโฟล์คลิฟท์	Forklift car tires	140	[]	[]
222	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	11	เส้น	Price per line	15.0000	#c747d6	0.0000	ยางรถยนต์	Car tires	139	[]	[]
223	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	11	เส้น	Price per line	40.0000	#ad4db8	0.0000	ยางรถ 6 ล้อ	Six wheel car tires	138	[]	[]
224	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	16	กิโลกรัม	Kilogram	1.0000	#3bdbbb	1.0310	เม็ดพลาสติกปนเปื้อน (PP)	PP Pellets Contaminate	122	[]	[]
225	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	16	กิโลกรัม	Kilogram	1.0000	#38c9ac	1.0310	เม็ดพลาสติกปนเปื้อน (PS)	PS Pellets Contaminate	121	[]	[]
226	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	15	กิโลกรัม	Kilogram	1.0000	#3662a6	0.0000	พลาสติกรวม ทำพลังงาน	Waste to energy	111	[]	[]
227	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	4	15	กิโลกรัม	Kilogram	1.0000	#e7853a	0.0000	ขยะทำเชื้อเพลิง	Waste to Energy Material	110	[]	[]
228	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	18	กิโลกรัม	Kilogram	1.0000	#000000	0.0000	บรรจุภัณฑ์สารเคมี	Chemical packaging	311	[]	[]
229	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	18	กิโลกรัม	Kilogram	1.0000	#000000	0.0000	สารเคมีใช้แล้ว	Used chemicals	310	[]	[]
230	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	18	กิโลกรัม	Kilogram	1.0000	#000000	0.0000	ยาหมดอายุ	Expired medicine	309	[]	[]
231	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	3	กิโลกรัม	Kilogram	1.0000	#20519d	0.0000	ขยะอันตรายรวม	Hazardous Waste	292	[]	[]
232	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	13	กิโลกรัม	Kilogram	1.0000	#e6a94e	0.0000	แบตเตอรี่รวม	Other Battery	262	[]	[]
233	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	13	กิโลกรัม	Kilogram	1.0000	#c9c9c9	0.0000	แบตเตอรี่คอมพิวเตอร์	Computer Battery	253	[]	[]
234	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	12	กิโลกรัม	Kilogram	1.0000	#e36e1b	0.0000	ไส้กรองน้ำมัน	Oil Filter	233	[]	[]
235	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	18	กิโลกรัม	Kilogram	1.0000	#f7b68b	0.0000	น้ำจากแอร์คอมเพลสเซอร์ปนเปื้อนน้ำมัน	Waste water from compressor	209	[]	[]
236	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	18	กิโลกรัม	Kilogram	1.0000	#b0896f	0.0000	น้ำมันหล่อลื่น	Lubricant Oil	207	[]	[]
237	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	18	กิโลกรัม	Kilogram	1.0000	#66391a	0.0000	สารเคมีอันตราย	Hazardous Chemicals	206	[]	[]
238	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	13	กิโลกรัม	Kilogram	1.0000	#825738	0.0000	แบตเตอรี่รถยนต์และมอเตอร์ไซค์	Automotive Battery	196	[]	[]
239	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	13	กิโลกรัม	Kilogram	1.0000	#b37244	0.0000	แบตเตอรี่ วิทยุสื่อสาร	Walkie Talkie Battery	193	[]	[]
240	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	18	กิโลกรัม	Kilogram	1.0000	#660300	0.0000	ขี้เลื่อยปนเปื้อนน้ำมัน	Sawdust contaminated with oil	148	[]	[]
241	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	18	กิโลกรัม	Kilogram	1.0000	#800703	0.0000	วัสดุปนเปื้อน	Contaminated fabric	147	[]	[]
242	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	18	กิโลกรัม	Kilogram	1.0000	#b30802	0.0000	ภาชนะปนเปื้อน	Contaminated containers	144	[]	[]
243	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	12	กิโลกรัม	Kilogram	1.0000	#8c0500	0.0000	กระป๋องสเปรย์	Aerosol cans	143	[]	[]
244	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	18	กิโลกรัม	Kilogram	1.0000	#9db89f	0.4650	น้ำมันพืช	Vegetable Cooking Oil	114	[]	[]
245	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	3	กิโลกรัม	Kilogram	1.0000	#e5736e	0.0000	ขยะอันตรายรวม	Mix Hazardous Waste	113	[]	[]
246	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	13	กิโลกรัม	Kilogram	1.0000	#e25f5a	0.0000	ถ่านไฟฉายเก่า	Old batteries	109	[]	[]
247	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	5	12	กิโลกรัม	Kilogram	1.0000	#db3831	0.0000	หลอดไฟที่ชำรุด	Damaged bulb	105	[]	[]
248	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	6	3	กิโลกรัม	Kilogram	1.0000	#20519d	0.0000	ขยะติดเชื้อรวม	Biohazardous Waste	294	[]	[]
249	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	6	3	กิโลกรัม	Kilogram	1.0000	#8a6a70	0.0000	ชุดตรวจ ATK	Antigen Test Kit (ATK)	255	[]	[]
250	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	6	17	กิโลกรัม	Kilogram	1.0000	#e899a9	0.0000	หน้ากากอนามัย	Face mask	188	[]	[]
251	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	6	17	กิโลกรัม	Kilogram	1.0000	#bd6073	0.0000	ผ้าอนามัย	Sanitary napkin	187	[]	[]
252	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	6	3	กิโลกรัม	Kilogram	1.0000	#e98783	0.0000	ขยะติดเชื้อ	Bio Hazardous	115	[]	[]
253	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	7	20	กิโลกรัม	Kilogram	1.0000	#116773	0.0000	คอนกรีต	Concrete	245	[]	[]
254	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	7	5	กิโลกรัม	Kilogram	1.0000	#3de0f5	0.0000	หัวเสาเข็ม	Pile Head	244	[]	[]
255	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	7	5	กิโลกรัม	Kilogram	1.0000	#586628	1.8320	ขาเหล็ก (ถังพลาสติก 1000 ลิตร)	Steel legs of plastic bucket (Plastic Bucket 1000 liter)	234	[]	[]
256	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	7	20	ตัน	Tonne	1000.0000	#aecaf5	0.0000	ฝุ่นปูน (ฝังกลบ)	Mortar Powder (Landfill)	228	[]	[]
257	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	7	20	กิโลกรัม	Kilogram	1.0000	#f0ac78	0.0000	ฝุ่นปูน	Mortar Powder	227	[]	[]
258	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	7	20	กิโลกรัม	Kilogram	1.0000	#7d92b3	0.0000	วัสดุกรองน้ำ (หินกรวด)	Water filter material (Gravel Stones)	220	[]	[]
259	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	7	5	กิโลกรัม	Kilogram	1.0000	#8da18d	9.1270	ล้อแม็กซ์	Max Wheel (Aluminium Alloy)	194	[]	[]
260	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	7	5	ถัง	Bucket	18.0000	#afd13f	1.8320	ถังน้ำมันเหล็กเปล่า 200 ลิตร ถังเก่า	Metal Oil Container 200 liter (Old Bucket)	135	[]	[]
261	t	2025-09-22 17:40:58.113766+00	2025-09-22 17:40:58.113766	\N	7	5	ถัง	Bucket	18.0000	#9ab837	1.8320	ถังน้ำมันเหล็กเปล่า 200 ลิตร ถังใหม่	Metal Oil Container 200 liter (New Bucket)	134	[]	[]
\.


--
-- Data for Name: meeting_participants; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.meeting_participants (id, meeting_id, user_id, role, invitation_status, attendance_status, joined_at, left_at, email_sent, reminder_sent, created_date, updated_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: meetings; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.meetings (id, title, description, meeting_type, organizer_id, expert_id, scheduled_start, scheduled_end, actual_start, actual_end, timezone, platform, meeting_url, meeting_id, passcode, location, room, address, status, agenda, notes, action_items, decisions, recording_url, presentation_urls, documents, is_billable, hourly_rate, duration_minutes, total_cost, currency_id, organizer_rating, organizer_feedback, expert_rating, expert_feedback, reminder_sent, reminder_sent_at, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: nationalities; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.nationalities (id, name_th, name_en, code, country_id, created_date, updated_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: organization_info; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.organization_info (id, company_name, company_name_th, company_name_en, display_name, business_type, business_industry, business_sub_industry, account_type, tax_id, national_id, business_registration_certificate, phone_number, company_phone, company_email, address, country_id, province_id, district_id, subdistrict_id, profile_image_url, company_logo_url, footprint, project_id, use_purpose, application_date, created_date, updated_date, is_active, deleted_date) FROM stdin;
3	qwe	\N	\N	qwe	\N			personal	\N	\N	\N	123	\N	asd@asd.com	\N	\N	\N	\N	\N	\N	\N	\N	\N	Waste Management	\N	2025-09-04 09:46:04.919487+00	2025-09-04 09:46:04.919487+00	t	\N
4	Belle	\N	\N	Belle	\N			personal	\N	\N	\N	0967863555	\N	pakpolkiller@gmail.com	\N	\N	\N	\N	\N	\N	\N	\N	\N	Waste Management	\N	2025-09-16 05:55:27.683091+00	2025-09-16 05:55:27.683091+00	t	\N
5	toptop	\N	\N	toptop	\N			personal	\N	\N	\N	123	\N	top@asd.com	\N	\N	\N	\N	\N	\N	\N	\N	\N	Waste Management	\N	2025-09-16 09:01:29.337448+00	2025-09-16 09:01:29.337448+00	t	\N
6	topasd	\N	\N	topasd	\N			personal	\N	\N	\N	123	\N	top2@asd.com	\N	\N	\N	\N	\N	\N	\N	\N	\N	Waste Management	\N	2025-09-17 06:43:38.81813+00	2025-09-17 06:43:38.81813+00	t	\N
7	toptop	\N	\N	toptop	\N			personal	\N	\N	\N	123	\N	top3@asd.com	\N	\N	\N	\N	\N	\N	\N	\N	\N	Waste Management	\N	2025-09-17 06:59:17.406163+00	2025-09-17 06:59:17.406163+00	t	\N
8	toptoptop	\N	\N	toptoptop	\N			personal	\N	\N	\N	123	\N	top3@top.com	\N	\N	\N	\N	\N	\N	\N	\N	\N	Waste Management	\N	2025-09-18 05:42:31.977491+00	2025-09-18 05:42:31.977491+00	t	\N
\.


--
-- Data for Name: organization_permissions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.organization_permissions (id, code, name, description, category, created_date, updated_date, is_active, deleted_date) FROM stdin;
1	transaction.create	Create Transaction	Create waste transactions	transaction	2025-09-04 09:23:10.849828+00	2025-09-04 09:23:10.849828+00	t	\N
2	transaction.view	View Transaction	View waste transactions	transaction	2025-09-04 09:23:10.849828+00	2025-09-04 09:23:10.849828+00	t	\N
3	transaction.edit	Edit Transaction	Edit waste transactions	transaction	2025-09-04 09:23:10.849828+00	2025-09-04 09:23:10.849828+00	t	\N
4	transaction.delete	Delete Transaction	Delete waste transactions	transaction	2025-09-04 09:23:10.849828+00	2025-09-04 09:23:10.849828+00	t	\N
5	transaction.audit	Audit Transaction	Audit waste transactions	transaction	2025-09-04 09:23:10.849828+00	2025-09-04 09:23:10.849828+00	t	\N
6	user.create	Create User	Create new users	user_management	2025-09-04 09:23:10.849828+00	2025-09-04 09:23:10.849828+00	t	\N
7	user.view	View User	View users	user_management	2025-09-04 09:23:10.849828+00	2025-09-04 09:23:10.849828+00	t	\N
8	user.edit	Edit User	Edit users	user_management	2025-09-04 09:23:10.849828+00	2025-09-04 09:23:10.849828+00	t	\N
9	user.delete	Delete User	Delete users	user_management	2025-09-04 09:23:10.849828+00	2025-09-04 09:23:10.849828+00	t	\N
10	permission.grant	Grant Permission	Grant permissions to users	user_management	2025-09-04 09:23:10.849828+00	2025-09-04 09:23:10.849828+00	t	\N
11	report.view	View Report	View reports	reporting	2025-09-04 09:23:10.849828+00	2025-09-04 09:23:10.849828+00	t	\N
12	report.create	Create Report	Create reports	reporting	2025-09-04 09:23:10.849828+00	2025-09-04 09:23:10.849828+00	t	\N
13	log.view	View Log	View system logs	system	2025-09-04 09:23:10.849828+00	2025-09-04 09:23:10.849828+00	t	\N
\.


--
-- Data for Name: organization_role_permissions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.organization_role_permissions (role_id, permission_id) FROM stdin;
\.


--
-- Data for Name: organization_roles; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.organization_roles (id, organization_id, name, description, is_system, created_date, updated_date, is_active, deleted_date, key) FROM stdin;
9	7	Administrator	Full administrative access to organization	t	2025-09-17 06:59:17.406163+00	2025-09-17 06:59:17.406163+00	t	\N	admin
10	7	Data Input Specialist	Can input and manage transaction data	t	2025-09-17 06:59:17.406163+00	2025-09-17 06:59:17.406163+00	t	\N	data_input
11	7	Auditor	Can review and audit data, read-only access to reports	t	2025-09-17 06:59:17.406163+00	2025-09-17 06:59:17.406163+00	t	\N	auditor
12	7	Viewer	Read-only access to organizational data	t	2025-09-17 06:59:17.406163+00	2025-09-17 06:59:17.406163+00	t	\N	viewer
13	8	Administrator	Full administrative access to organization	t	2025-09-18 05:42:31.977491+00	2025-09-18 05:42:31.977491+00	t	\N	admin
14	8	Data Input Specialist	Can input and manage transaction data	t	2025-09-18 05:42:31.977491+00	2025-09-18 05:42:31.977491+00	t	\N	data_input
15	8	Auditor	Can review and audit data, read-only access to reports	t	2025-09-18 05:42:31.977491+00	2025-09-18 05:42:31.977491+00	t	\N	auditor
16	8	Viewer	Read-only access to organizational data	t	2025-09-18 05:42:31.977491+00	2025-09-18 05:42:31.977491+00	t	\N	viewer
\.


--
-- Data for Name: organization_setup; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.organization_setup (id, organization_id, version, is_active, root_nodes, hub_node, metadata, created_date, updated_date, deleted_date) FROM stdin;
103	8	1.4000000000000004	f	[{"nodeId": 2167, "children": [{"nodeId": 2168, "children": [{"nodeId": 2169, "children": [{"nodeId": 2170, "position": {"x": -88.6, "y": 420}}, {"nodeId": 2171, "position": {"x": 0, "y": 420}}, {"nodeId": 2172, "position": {"x": 88.6, "y": 420}}], "position": {"x": 0, "y": 280}}], "position": {"x": 0, "y": 140}}], "position": {"x": 0, "y": 0}}]	{"children": [{"nodeId": 2174, "hubData": {"id": "1", "name": "Cafe Collection Point", "type": "Collectors", "location": "Shop Floor", "description": "Collectors - 2 tons/day"}, "position": {"x": -320, "y": 840}}, {"nodeId": 2175, "hubData": {"id": "2", "name": "Kitchen Waste Station", "type": "Collectors", "location": "Prep Area", "description": "Collectors - 1.5 tons/day"}, "position": {"x": -160, "y": 840}}, {"nodeId": 2176, "hubData": {"id": "3", "name": "Basic Sorting Station", "type": "Sorters", "location": "Back Storage", "description": "Sorters - 3 tons/day"}, "position": {"x": 0, "y": 840}}, {"nodeId": 2177, "hubData": {"id": "4", "name": "Local Pickup Point", "type": "Transfer Station", "location": "Alley Access", "description": "Transfer Station - 5 tons/day"}, "position": {"x": 160, "y": 840}}, {"nodeId": 2178, "hubData": {"id": "5", "name": "Community Recycling Center", "type": "MRF", "location": "Neighborhood", "description": "MRF - 20 tons/day"}, "position": {"x": 320, "y": 840}}, {"nodeId": 2179, "hubData": {"id": "6", "name": "Cup & Lid Processor", "type": "Recycling Plant", "location": "City Processing", "description": "Recycling Plant - 15 tons/day"}, "position": {"x": -320, "y": 960}}, {"nodeId": 2180, "hubData": {"id": "7", "name": "Paper Cup Mill", "type": "Recycling Plant", "location": "Regional Facility", "description": "Recycling Plant - 12 tons/day"}, "position": {"x": -160, "y": 960}}, {"nodeId": 2181, "hubData": {"id": "8", "name": "Organic Waste Composter", "type": "Compost Facility", "location": "Urban Farm", "description": "Compost Facility - 8 tons/day"}, "position": {"x": 0, "y": 960}}, {"nodeId": 2182, "hubData": {"id": "9", "name": "Municipal Landfill", "type": "Landfill", "location": "City Outskirts", "description": "Landfill - 100 tons/day"}, "position": {"x": 160, "y": 960}}, {"nodeId": 2183, "hubData": {"id": "10", "name": "Local Energy Plant", "type": "Waste-to-Energy", "location": "Industrial Zone", "description": "Waste-to-Energy - 25 tons/day"}, "position": {"x": 320, "y": 960}}], "position": {"x": 0, "y": 700}}	{"version": "1.0", "maxLevel": 0, "createdAt": "2025-09-19T15:15:10.316Z", "totalNodes": 0}	2025-09-19 15:15:10.771925+00	2025-09-19 15:20:00.864304	\N
104	8	1.5000000000000004	f	[{"nodeId": 2167, "children": [{"nodeId": 2168, "children": [{"nodeId": 2169, "children": [{"nodeId": 2170, "position": {"x": -88.6, "y": 420}}, {"nodeId": 2171, "position": {"x": 0, "y": 420}}, {"nodeId": 2172, "position": {"x": 88.6, "y": 420}}], "position": {"x": 0, "y": 280}}], "position": {"x": 0, "y": 140}}], "position": {"x": 0, "y": 0}}]	{"children": [{"nodeId": 2174, "hubData": {"id": "1", "name": "Cafe Collection Point", "type": "Collectors", "location": "Shop Floor", "description": "Collectors - 2 tons/day"}, "position": {"x": -320, "y": 840}}, {"nodeId": 2175, "hubData": {"id": "2", "name": "Kitchen Waste Station", "type": "Collectors", "location": "Prep Area", "description": "Collectors - 1.5 tons/day"}, "position": {"x": -160, "y": 840}}, {"nodeId": 2176, "hubData": {"id": "3", "name": "Basic Sorting Station", "type": "Sorters", "location": "Back Storage", "description": "Sorters - 3 tons/day"}, "position": {"x": 0, "y": 840}}, {"nodeId": 2177, "hubData": {"id": "4", "name": "Local Pickup Point", "type": "Transfer Station", "location": "Alley Access", "description": "Transfer Station - 5 tons/day"}, "position": {"x": 160, "y": 840}}, {"nodeId": 2178, "hubData": {"id": "5", "name": "Community Recycling Center", "type": "MRF", "location": "Neighborhood", "description": "MRF - 20 tons/day"}, "position": {"x": 320, "y": 840}}, {"nodeId": 2179, "hubData": {"id": "6", "name": "Cup & Lid Processor", "type": "Recycling Plant", "location": "City Processing", "description": "Recycling Plant - 15 tons/day"}, "position": {"x": -320, "y": 960}}, {"nodeId": 2180, "hubData": {"id": "7", "name": "Paper Cup Mill", "type": "Recycling Plant", "location": "Regional Facility", "description": "Recycling Plant - 12 tons/day"}, "position": {"x": -160, "y": 960}}, {"nodeId": 2181, "hubData": {"id": "8", "name": "Organic Waste Composter", "type": "Compost Facility", "location": "Urban Farm", "description": "Compost Facility - 8 tons/day"}, "position": {"x": 0, "y": 960}}, {"nodeId": 2182, "hubData": {"id": "9", "name": "Municipal Landfill", "type": "Landfill", "location": "City Outskirts", "description": "Landfill - 100 tons/day"}, "position": {"x": 160, "y": 960}}, {"nodeId": 2183, "hubData": {"id": "10", "name": "Local Energy Plant", "type": "Waste-to-Energy", "location": "Industrial Zone", "description": "Waste-to-Energy - 25 tons/day"}, "position": {"x": 320, "y": 960}}], "position": {"x": 0, "y": 700}}	{"version": "1.0", "maxLevel": 0, "createdAt": "2025-09-19T15:20:00.421Z", "totalNodes": 0}	2025-09-19 15:20:00.864304+00	2025-09-19 15:47:20.641267	\N
105	8	1.6000000000000005	f	[{"nodeId": 2167, "children": [{"nodeId": 2168, "children": [{"nodeId": 2169, "children": [{"nodeId": 2170, "position": {"x": -88.6, "y": 420}}, {"nodeId": 2171, "position": {"x": 0, "y": 420}}, {"nodeId": 2172, "position": {"x": 88.6, "y": 420}}], "position": {"x": 0, "y": 280}}], "position": {"x": 0, "y": 140}}], "position": {"x": 0, "y": 0}}]	{"children": [{"nodeId": 2174, "hubData": {"id": "1", "name": "Cafe Collection Point", "type": "Collectors", "location": "Shop Floor", "description": "Collectors - 2 tons/day"}, "position": {"x": -320, "y": 840}}, {"nodeId": 2175, "hubData": {"id": "2", "name": "Kitchen Waste Station", "type": "Collectors", "location": "Prep Area", "description": "Collectors - 1.5 tons/day"}, "position": {"x": -160, "y": 840}}, {"nodeId": 2176, "hubData": {"id": "3", "name": "Basic Sorting Station", "type": "Sorters", "location": "Back Storage", "description": "Sorters - 3 tons/day"}, "position": {"x": 0, "y": 840}}, {"nodeId": 2177, "hubData": {"id": "4", "name": "Local Pickup Point", "type": "Transfer Station", "location": "Alley Access", "description": "Transfer Station - 5 tons/day"}, "position": {"x": 160, "y": 840}}, {"nodeId": 2178, "hubData": {"id": "5", "name": "Community Recycling Center", "type": "MRF", "location": "Neighborhood", "description": "MRF - 20 tons/day"}, "position": {"x": 320, "y": 840}}, {"nodeId": 2179, "hubData": {"id": "6", "name": "Cup & Lid Processor", "type": "Recycling Plant", "location": "City Processing", "description": "Recycling Plant - 15 tons/day"}, "position": {"x": -320, "y": 960}}, {"nodeId": 2180, "hubData": {"id": "7", "name": "Paper Cup Mill", "type": "Recycling Plant", "location": "Regional Facility", "description": "Recycling Plant - 12 tons/day"}, "position": {"x": -160, "y": 960}}, {"nodeId": 2181, "hubData": {"id": "8", "name": "Organic Waste Composter", "type": "Compost Facility", "location": "Urban Farm", "description": "Compost Facility - 8 tons/day"}, "position": {"x": 0, "y": 960}}, {"nodeId": 2182, "hubData": {"id": "9", "name": "Municipal Landfill", "type": "Landfill", "location": "City Outskirts", "description": "Landfill - 100 tons/day"}, "position": {"x": 160, "y": 960}}, {"nodeId": 2183, "hubData": {"id": "10", "name": "Local Energy Plant", "type": "Waste-to-Energy", "location": "Industrial Zone", "description": "Waste-to-Energy - 25 tons/day"}, "position": {"x": 320, "y": 960}}], "position": {"x": 0, "y": 700}}	{"version": "1.0", "maxLevel": 0, "createdAt": "2025-09-19T15:47:20.325Z", "totalNodes": 0}	2025-09-19 15:47:20.641267+00	2025-09-19 16:25:17.137033	\N
106	8	1.7000000000000006	f	[{"nodeId": 2167, "children": [{"nodeId": 2168, "children": [{"nodeId": 2169, "children": [{"nodeId": 2170, "position": {"x": -88.6, "y": 420}}, {"nodeId": 2171, "position": {"x": 0, "y": 420}}, {"nodeId": 2172, "position": {"x": 88.6, "y": 420}}], "position": {"x": 0, "y": 280}}], "position": {"x": 0, "y": 140}}], "position": {"x": 0, "y": 0}}]	{"children": [{"nodeId": 2174, "hubData": {"id": "1", "name": "Cafe Collection Point", "type": "Collectors", "location": "Shop Floor", "description": "Collectors - 2 tons/day"}, "position": {"x": -320, "y": 840}}, {"nodeId": 2175, "hubData": {"id": "2", "name": "Kitchen Waste Station", "type": "Collectors", "location": "Prep Area", "description": "Collectors - 1.5 tons/day"}, "position": {"x": -160, "y": 840}}, {"nodeId": 2176, "hubData": {"id": "3", "name": "Basic Sorting Station", "type": "Sorters", "location": "Back Storage", "description": "Sorters - 3 tons/day"}, "position": {"x": 0, "y": 840}}, {"nodeId": 2177, "hubData": {"id": "4", "name": "Local Pickup Point", "type": "Transfer Station", "location": "Alley Access", "description": "Transfer Station - 5 tons/day"}, "position": {"x": 160, "y": 840}}, {"nodeId": 2178, "hubData": {"id": "5", "name": "Community Recycling Center", "type": "MRF", "location": "Neighborhood", "description": "MRF - 20 tons/day"}, "position": {"x": 320, "y": 840}}, {"nodeId": 2179, "hubData": {"id": "6", "name": "Cup & Lid Processor", "type": "Recycling Plant", "location": "City Processing", "description": "Recycling Plant - 15 tons/day"}, "position": {"x": -320, "y": 960}}, {"nodeId": 2180, "hubData": {"id": "7", "name": "Paper Cup Mill", "type": "Recycling Plant", "location": "Regional Facility", "description": "Recycling Plant - 12 tons/day"}, "position": {"x": -160, "y": 960}}, {"nodeId": 2181, "hubData": {"id": "8", "name": "Organic Waste Composter", "type": "Compost Facility", "location": "Urban Farm", "description": "Compost Facility - 8 tons/day"}, "position": {"x": 0, "y": 960}}, {"nodeId": 2182, "hubData": {"id": "9", "name": "Municipal Landfill", "type": "Landfill", "location": "City Outskirts", "description": "Landfill - 100 tons/day"}, "position": {"x": 160, "y": 960}}, {"nodeId": 2183, "hubData": {"id": "10", "name": "Local Energy Plant", "type": "Waste-to-Energy", "location": "Industrial Zone", "description": "Waste-to-Energy - 25 tons/day"}, "position": {"x": 320, "y": 960}}], "position": {"x": 0, "y": 700}}	{"version": "1.0", "maxLevel": 0, "createdAt": "2025-09-19T16:25:16.655Z", "totalNodes": 0}	2025-09-19 16:25:17.137033+00	2025-09-19 16:25:33.620275	\N
108	8	1.9000000000000008	t	[{"nodeId": 2167, "children": [{"nodeId": 2168, "children": [{"nodeId": 2169, "children": [{"nodeId": 2170, "position": {"x": -88.6, "y": 420}}, {"nodeId": 2171, "position": {"x": 0, "y": 420}}, {"nodeId": 2172, "position": {"x": 88.6, "y": 420}}], "position": {"x": 0, "y": 280}}], "position": {"x": 0, "y": 140}}], "position": {"x": 0, "y": 0}}]	{"children": [{"nodeId": 2174, "hubData": {"id": "1", "name": "Cafe Collection Point", "type": "Collectors", "location": "Shop Floor", "description": "Collectors - 2 tons/day"}, "position": {"x": -320, "y": 840}}, {"nodeId": 2175, "hubData": {"id": "2", "name": "Kitchen Waste Station", "type": "Collectors", "location": "Prep Area", "description": "Collectors - 1.5 tons/day"}, "position": {"x": -160, "y": 840}}, {"nodeId": 2176, "hubData": {"id": "3", "name": "Basic Sorting Station", "type": "Sorters", "location": "Back Storage", "description": "Sorters - 3 tons/day"}, "position": {"x": 0, "y": 840}}, {"nodeId": 2177, "hubData": {"id": "4", "name": "Local Pickup Point", "type": "Transfer Station", "location": "Alley Access", "description": "Transfer Station - 5 tons/day"}, "position": {"x": 160, "y": 840}}, {"nodeId": 2178, "hubData": {"id": "5", "name": "Community Recycling Center", "type": "MRF", "location": "Neighborhood", "description": "MRF - 20 tons/day"}, "position": {"x": 320, "y": 840}}, {"nodeId": 2179, "hubData": {"id": "6", "name": "Cup & Lid Processor", "type": "Recycling Plant", "location": "City Processing", "description": "Recycling Plant - 15 tons/day"}, "position": {"x": -320, "y": 960}}, {"nodeId": 2180, "hubData": {"id": "7", "name": "Paper Cup Mill", "type": "Recycling Plant", "location": "Regional Facility", "description": "Recycling Plant - 12 tons/day"}, "position": {"x": -160, "y": 960}}, {"nodeId": 2181, "hubData": {"id": "8", "name": "Organic Waste Composter", "type": "Compost Facility", "location": "Urban Farm", "description": "Compost Facility - 8 tons/day"}, "position": {"x": 0, "y": 960}}, {"nodeId": 2182, "hubData": {"id": "9", "name": "Municipal Landfill", "type": "Landfill", "location": "City Outskirts", "description": "Landfill - 100 tons/day"}, "position": {"x": 160, "y": 960}}, {"nodeId": 2183, "hubData": {"id": "10", "name": "Local Energy Plant", "type": "Waste-to-Energy", "location": "Industrial Zone", "description": "Waste-to-Energy - 25 tons/day"}, "position": {"x": 320, "y": 960}}], "position": {"x": 0, "y": 700}}	{"version": "1.0", "maxLevel": 0, "createdAt": "2025-09-19T16:32:31.147Z", "totalNodes": 0}	2025-09-19 16:32:31.627273+00	2025-09-19 16:32:31.627273	\N
107	8	1.8000000000000007	f	[{"nodeId": 2167, "children": [{"nodeId": 2168, "children": [{"nodeId": 2169, "children": [{"nodeId": 2170, "position": {"x": -88.6, "y": 420}}, {"nodeId": 2171, "position": {"x": 0, "y": 420}}, {"nodeId": 2172, "position": {"x": 88.6, "y": 420}}], "position": {"x": 0, "y": 280}}], "position": {"x": 0, "y": 140}}], "position": {"x": 0, "y": 0}}]	{"children": [{"nodeId": 2174, "hubData": {"id": "1", "name": "Cafe Collection Point", "type": "Collectors", "location": "Shop Floor", "description": "Collectors - 2 tons/day"}, "position": {"x": -320, "y": 840}}, {"nodeId": 2175, "hubData": {"id": "2", "name": "Kitchen Waste Station", "type": "Collectors", "location": "Prep Area", "description": "Collectors - 1.5 tons/day"}, "position": {"x": -160, "y": 840}}, {"nodeId": 2176, "hubData": {"id": "3", "name": "Basic Sorting Station", "type": "Sorters", "location": "Back Storage", "description": "Sorters - 3 tons/day"}, "position": {"x": 0, "y": 840}}, {"nodeId": 2177, "hubData": {"id": "4", "name": "Local Pickup Point", "type": "Transfer Station", "location": "Alley Access", "description": "Transfer Station - 5 tons/day"}, "position": {"x": 160, "y": 840}}, {"nodeId": 2178, "hubData": {"id": "5", "name": "Community Recycling Center", "type": "MRF", "location": "Neighborhood", "description": "MRF - 20 tons/day"}, "position": {"x": 320, "y": 840}}, {"nodeId": 2179, "hubData": {"id": "6", "name": "Cup & Lid Processor", "type": "Recycling Plant", "location": "City Processing", "description": "Recycling Plant - 15 tons/day"}, "position": {"x": -320, "y": 960}}, {"nodeId": 2180, "hubData": {"id": "7", "name": "Paper Cup Mill", "type": "Recycling Plant", "location": "Regional Facility", "description": "Recycling Plant - 12 tons/day"}, "position": {"x": -160, "y": 960}}, {"nodeId": 2181, "hubData": {"id": "8", "name": "Organic Waste Composter", "type": "Compost Facility", "location": "Urban Farm", "description": "Compost Facility - 8 tons/day"}, "position": {"x": 0, "y": 960}}, {"nodeId": 2182, "hubData": {"id": "9", "name": "Municipal Landfill", "type": "Landfill", "location": "City Outskirts", "description": "Landfill - 100 tons/day"}, "position": {"x": 160, "y": 960}}, {"nodeId": 2183, "hubData": {"id": "10", "name": "Local Energy Plant", "type": "Waste-to-Energy", "location": "Industrial Zone", "description": "Waste-to-Energy - 25 tons/day"}, "position": {"x": 320, "y": 960}}], "position": {"x": 0, "y": 700}}	{"version": "1.0", "maxLevel": 0, "createdAt": "2025-09-19T16:25:33.126Z", "totalNodes": 0}	2025-09-19 16:25:33.620275+00	2025-09-19 16:32:31.627273	\N
99	8	1.0	f	[{"nodeId": 2167, "children": [{"nodeId": 2168, "children": [{"nodeId": 2169, "children": [{"nodeId": 2170, "position": {"x": -88.6, "y": 420}}, {"nodeId": 2171, "position": {"x": 0, "y": 420}}, {"nodeId": 2172, "position": {"x": 88.6, "y": 420}}], "position": {"x": 0, "y": 280}}], "position": {"x": 0, "y": 140}}], "position": {"x": 0, "y": 0}}]	{"children": [{"nodeId": 2174, "hubData": {"id": "1", "name": "Cafe Collection Point", "type": "Collectors", "location": "Shop Floor", "description": "Collectors - 2 tons/day"}, "position": {"x": -320, "y": 840}}, {"nodeId": 2175, "hubData": {"id": "2", "name": "Kitchen Waste Station", "type": "Collectors", "location": "Prep Area", "description": "Collectors - 1.5 tons/day"}, "position": {"x": -160, "y": 840}}, {"nodeId": 2176, "hubData": {"id": "3", "name": "Basic Sorting Station", "type": "Sorters", "location": "Back Storage", "description": "Sorters - 3 tons/day"}, "position": {"x": 0, "y": 840}}, {"nodeId": 2177, "hubData": {"id": "4", "name": "Local Pickup Point", "type": "Transfer Station", "location": "Alley Access", "description": "Transfer Station - 5 tons/day"}, "position": {"x": 160, "y": 840}}, {"nodeId": 2178, "hubData": {"id": "5", "name": "Community Recycling Center", "type": "MRF", "location": "Neighborhood", "description": "MRF - 20 tons/day"}, "position": {"x": 320, "y": 840}}, {"nodeId": 2179, "hubData": {"id": "6", "name": "Cup & Lid Processor", "type": "Recycling Plant", "location": "City Processing", "description": "Recycling Plant - 15 tons/day"}, "position": {"x": -320, "y": 960}}, {"nodeId": 2180, "hubData": {"id": "7", "name": "Paper Cup Mill", "type": "Recycling Plant", "location": "Regional Facility", "description": "Recycling Plant - 12 tons/day"}, "position": {"x": -160, "y": 960}}, {"nodeId": 2181, "hubData": {"id": "8", "name": "Organic Waste Composter", "type": "Compost Facility", "location": "Urban Farm", "description": "Compost Facility - 8 tons/day"}, "position": {"x": 0, "y": 960}}, {"nodeId": 2182, "hubData": {"id": "9", "name": "Municipal Landfill", "type": "Landfill", "location": "City Outskirts", "description": "Landfill - 100 tons/day"}, "position": {"x": 160, "y": 960}}, {"nodeId": 2183, "hubData": {"id": "10", "name": "Local Energy Plant", "type": "Waste-to-Energy", "location": "Industrial Zone", "description": "Waste-to-Energy - 25 tons/day"}, "position": {"x": 320, "y": 960}}], "position": {"x": 0, "y": 700}}	{"version": "1.0", "maxLevel": 0, "createdAt": "2025-09-19T14:59:39.287Z", "totalNodes": 0}	2025-09-19 14:59:39.709313+00	2025-09-19 15:00:00.54146	\N
100	8	1.1	f	[{"nodeId": 2167, "children": [{"nodeId": 2168, "children": [{"nodeId": 2169, "children": [{"nodeId": 2170, "position": {"x": -88.6, "y": 420}}, {"nodeId": 2171, "position": {"x": 0, "y": 420}}, {"nodeId": 2172, "position": {"x": 88.6, "y": 420}}], "position": {"x": 0, "y": 280}}], "position": {"x": 0, "y": 140}}], "position": {"x": 0, "y": 0}}]	{"children": [{"nodeId": 2174, "hubData": {"id": "1", "name": "Cafe Collection Point", "type": "Collectors", "location": "Shop Floor", "description": "Collectors - 2 tons/day"}, "position": {"x": -320, "y": 840}}, {"nodeId": 2175, "hubData": {"id": "2", "name": "Kitchen Waste Station", "type": "Collectors", "location": "Prep Area", "description": "Collectors - 1.5 tons/day"}, "position": {"x": -160, "y": 840}}, {"nodeId": 2176, "hubData": {"id": "3", "name": "Basic Sorting Station", "type": "Sorters", "location": "Back Storage", "description": "Sorters - 3 tons/day"}, "position": {"x": 0, "y": 840}}, {"nodeId": 2177, "hubData": {"id": "4", "name": "Local Pickup Point", "type": "Transfer Station", "location": "Alley Access", "description": "Transfer Station - 5 tons/day"}, "position": {"x": 160, "y": 840}}, {"nodeId": 2178, "hubData": {"id": "5", "name": "Community Recycling Center", "type": "MRF", "location": "Neighborhood", "description": "MRF - 20 tons/day"}, "position": {"x": 320, "y": 840}}, {"nodeId": 2179, "hubData": {"id": "6", "name": "Cup & Lid Processor", "type": "Recycling Plant", "location": "City Processing", "description": "Recycling Plant - 15 tons/day"}, "position": {"x": -320, "y": 960}}, {"nodeId": 2180, "hubData": {"id": "7", "name": "Paper Cup Mill", "type": "Recycling Plant", "location": "Regional Facility", "description": "Recycling Plant - 12 tons/day"}, "position": {"x": -160, "y": 960}}, {"nodeId": 2181, "hubData": {"id": "8", "name": "Organic Waste Composter", "type": "Compost Facility", "location": "Urban Farm", "description": "Compost Facility - 8 tons/day"}, "position": {"x": 0, "y": 960}}, {"nodeId": 2182, "hubData": {"id": "9", "name": "Municipal Landfill", "type": "Landfill", "location": "City Outskirts", "description": "Landfill - 100 tons/day"}, "position": {"x": 160, "y": 960}}, {"nodeId": 2183, "hubData": {"id": "10", "name": "Local Energy Plant", "type": "Waste-to-Energy", "location": "Industrial Zone", "description": "Waste-to-Energy - 25 tons/day"}, "position": {"x": 320, "y": 960}}], "position": {"x": 0, "y": 700}}	{"version": "1.0", "maxLevel": 0, "createdAt": "2025-09-19T15:00:00.120Z", "totalNodes": 0}	2025-09-19 15:00:00.54146+00	2025-09-19 15:11:16.292722	\N
102	8	1.3000000000000003	f	[{"nodeId": 2167, "children": [{"nodeId": 2168, "children": [{"nodeId": 2169, "children": [{"nodeId": 2170, "position": {"x": -88.6, "y": 420}}, {"nodeId": 2171, "position": {"x": 0, "y": 420}}, {"nodeId": 2172, "position": {"x": 88.6, "y": 420}}], "position": {"x": 0, "y": 280}}], "position": {"x": 0, "y": 140}}], "position": {"x": 0, "y": 0}}]	{"children": [{"nodeId": 2174, "hubData": {"id": "1", "name": "Cafe Collection Point", "type": "Collectors", "location": "Shop Floor", "description": "Collectors - 2 tons/day"}, "position": {"x": -320, "y": 840}}, {"nodeId": 2175, "hubData": {"id": "2", "name": "Kitchen Waste Station", "type": "Collectors", "location": "Prep Area", "description": "Collectors - 1.5 tons/day"}, "position": {"x": -160, "y": 840}}, {"nodeId": 2176, "hubData": {"id": "3", "name": "Basic Sorting Station", "type": "Sorters", "location": "Back Storage", "description": "Sorters - 3 tons/day"}, "position": {"x": 0, "y": 840}}, {"nodeId": 2177, "hubData": {"id": "4", "name": "Local Pickup Point", "type": "Transfer Station", "location": "Alley Access", "description": "Transfer Station - 5 tons/day"}, "position": {"x": 160, "y": 840}}, {"nodeId": 2178, "hubData": {"id": "5", "name": "Community Recycling Center", "type": "MRF", "location": "Neighborhood", "description": "MRF - 20 tons/day"}, "position": {"x": 320, "y": 840}}, {"nodeId": 2179, "hubData": {"id": "6", "name": "Cup & Lid Processor", "type": "Recycling Plant", "location": "City Processing", "description": "Recycling Plant - 15 tons/day"}, "position": {"x": -320, "y": 960}}, {"nodeId": 2180, "hubData": {"id": "7", "name": "Paper Cup Mill", "type": "Recycling Plant", "location": "Regional Facility", "description": "Recycling Plant - 12 tons/day"}, "position": {"x": -160, "y": 960}}, {"nodeId": 2181, "hubData": {"id": "8", "name": "Organic Waste Composter", "type": "Compost Facility", "location": "Urban Farm", "description": "Compost Facility - 8 tons/day"}, "position": {"x": 0, "y": 960}}, {"nodeId": 2182, "hubData": {"id": "9", "name": "Municipal Landfill", "type": "Landfill", "location": "City Outskirts", "description": "Landfill - 100 tons/day"}, "position": {"x": 160, "y": 960}}, {"nodeId": 2183, "hubData": {"id": "10", "name": "Local Energy Plant", "type": "Waste-to-Energy", "location": "Industrial Zone", "description": "Waste-to-Energy - 25 tons/day"}, "position": {"x": 320, "y": 960}}], "position": {"x": 0, "y": 700}}	{"version": "1.0", "maxLevel": 0, "createdAt": "2025-09-19T15:12:01.798Z", "totalNodes": 0}	2025-09-19 15:12:02.182845+00	2025-09-19 15:15:10.771925	\N
101	8	1.2000000000000002	f	[{"nodeId": 2167, "children": [{"nodeId": 2168, "children": [{"nodeId": 2169, "children": [{"nodeId": 2170, "position": {"x": -88.6, "y": 420}}, {"nodeId": 2171, "position": {"x": 0, "y": 420}}, {"nodeId": 2172, "position": {"x": 88.6, "y": 420}}], "position": {"x": 0, "y": 280}}], "position": {"x": 0, "y": 140}}], "position": {"x": 0, "y": 0}}]	{"children": [{"nodeId": 2174, "hubData": {"id": "1", "name": "Cafe Collection Point", "type": "Collectors", "location": "Shop Floor", "description": "Collectors - 2 tons/day"}, "position": {"x": -320, "y": 840}}, {"nodeId": 2175, "hubData": {"id": "2", "name": "Kitchen Waste Station", "type": "Collectors", "location": "Prep Area", "description": "Collectors - 1.5 tons/day"}, "position": {"x": -160, "y": 840}}, {"nodeId": 2176, "hubData": {"id": "3", "name": "Basic Sorting Station", "type": "Sorters", "location": "Back Storage", "description": "Sorters - 3 tons/day"}, "position": {"x": 0, "y": 840}}, {"nodeId": 2177, "hubData": {"id": "4", "name": "Local Pickup Point", "type": "Transfer Station", "location": "Alley Access", "description": "Transfer Station - 5 tons/day"}, "position": {"x": 160, "y": 840}}, {"nodeId": 2178, "hubData": {"id": "5", "name": "Community Recycling Center", "type": "MRF", "location": "Neighborhood", "description": "MRF - 20 tons/day"}, "position": {"x": 320, "y": 840}}, {"nodeId": 2179, "hubData": {"id": "6", "name": "Cup & Lid Processor", "type": "Recycling Plant", "location": "City Processing", "description": "Recycling Plant - 15 tons/day"}, "position": {"x": -320, "y": 960}}, {"nodeId": 2180, "hubData": {"id": "7", "name": "Paper Cup Mill", "type": "Recycling Plant", "location": "Regional Facility", "description": "Recycling Plant - 12 tons/day"}, "position": {"x": -160, "y": 960}}, {"nodeId": 2181, "hubData": {"id": "8", "name": "Organic Waste Composter", "type": "Compost Facility", "location": "Urban Farm", "description": "Compost Facility - 8 tons/day"}, "position": {"x": 0, "y": 960}}, {"nodeId": 2182, "hubData": {"id": "9", "name": "Municipal Landfill", "type": "Landfill", "location": "City Outskirts", "description": "Landfill - 100 tons/day"}, "position": {"x": 160, "y": 960}}, {"nodeId": 2183, "hubData": {"id": "10", "name": "Local Energy Plant", "type": "Waste-to-Energy", "location": "Industrial Zone", "description": "Waste-to-Energy - 25 tons/day"}, "position": {"x": 320, "y": 960}}], "position": {"x": 0, "y": 700}}	{"version": "1.0", "maxLevel": 0, "createdAt": "2025-09-19T15:11:15.761Z", "totalNodes": 0}	2025-09-19 15:11:16.292722+00	2025-09-19 15:12:02.182845	\N
\.


--
-- Data for Name: organizations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.organizations (id, name, description, organization_info_id, owner_id, subscription_id, created_date, updated_date, is_active, deleted_date, system_role_id) FROM stdin;
3	qwe	Organization for qwe	3	3	1	2025-09-04 09:46:04.919487+00	2025-09-04 09:46:04.919487+00	t	\N	\N
4	Belle	Organization for Belle	4	4	2	2025-09-16 05:55:27.683091+00	2025-09-16 05:55:27.683091+00	t	\N	\N
5	toptop	Organization for toptop	5	5	3	2025-09-16 09:01:29.337448+00	2025-09-16 09:01:29.337448+00	t	\N	\N
6	topasd	Organization for topasd	6	6	4	2025-09-17 06:43:38.81813+00	2025-09-17 06:43:38.81813+00	t	\N	\N
7	toptop	Organization for toptop	7	7	5	2025-09-17 06:59:17.406163+00	2025-09-17 06:59:17.406163+00	t	\N	\N
8	toptoptop	Organization for toptoptop	8	26	6	2025-09-18 05:42:31.977491+00	2025-09-18 05:42:31.977491+00	t	\N	\N
\.


--
-- Data for Name: phone_number_country_codes; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.phone_number_country_codes (id, country_id, code, country_name, created_date, updated_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: platform_logs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.platform_logs (id, log_level, category, source, message, details, user_id, organization_id, session_id, request_id, server_name, process_id, thread_id, error_code, error_type, stack_trace, execution_time_ms, memory_usage_mb, cpu_usage_percent, related_resource_type, related_resource_id, created_date, is_active) FROM stdin;
\.


--
-- Data for Name: point_transactions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.point_transactions (id, user_id, transaction_type, points_type, points_amount, balance_before, balance_after, source_type, source_reference_id, description, notes, expires_at, processed_by_id, created_date, is_active) FROM stdin;
\.


--
-- Data for Name: reward_redemptions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.reward_redemptions (id, user_id, reward_id, points_redeemed, redemption_code, status, delivery_method, delivery_address, delivery_instructions, fulfillment_date, tracking_number, redeemed_at, expires_at, notes, processed_by_id, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: rewards_catalog; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.rewards_catalog (id, reward_name, description, category, points_required, points_type, reward_value, currency_id, quantity_available, quantity_redeemed, is_limited_quantity, valid_from, valid_until, is_active, terms_and_conditions, redemption_instructions, image_url, additional_images, provider_organization_id, provider_contact_info, created_by_id, created_date, updated_date) FROM stdin;
\.


--
-- Data for Name: schema_migrations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.schema_migrations (id, version, filename, description, executed_at, execution_time_ms, checksum, batch_id) FROM stdin;
1	20250904_120000_001	20250904_120000_001_core_foundation.sql	Creates foundation tables for locations, references, and core system data	2025-09-04 09:23:06.369093	1000	2770f2cdec4292dd66aaef60abb5d507	592e1951-e3f5-4452-9215-a49e5ef405c9
2	20250904_120500_002	20250904_120500_002_user_management.sql	Creates user management tables including roles, locations, and authentication	2025-09-04 09:23:08.674238	2000	47109f8311d3dda8e5d2ba05cbcbaf92	9ddb1ff3-81ca-4334-a007-29ddf15d2672
3	20250904_121000_003	20250904_121000_003_organization_subscription.sql	Creates organization, subscription, and permission management tables	2025-09-04 09:23:11.202427	1000	eeced4f61efcf6652ce87c16a80bc66a	6c3a029b-06bf-46d8-b645-214e814a3cdc
4	20250904_121500_004	20250904_121500_004_add_foreign_keys.sql	Adds foreign key constraints between tables created in previous migrations	2025-09-04 09:23:12.818805	1000	8eeb064bdab7910da4f630ddb6a6df62	07a81286-86e8-400b-bc73-57221a7c37c3
5	20250904_122000_005	20250904_122000_005_transaction_system.sql	Creates comprehensive transaction and waste management tables	2025-09-04 09:23:15.521096	2000	2e60ea0ad5994e8744c056f19fab82fc	db062456-0a33-42b1-82f1-28d8c9fd487a
6	20250904_122500_006	20250904_122500_006_epr_compliance.sql	Creates Extended Producer Responsibility compliance and reporting tables	2025-09-04 09:23:18.423832	2000	9c3cf1704515427bf03738d0c37cdeb1	4fdbb47b-1103-400b-8279-8974a97b64c9
7	20250904_123000_007	20250904_123000_007_gri_rewards_km.sql	Creates GRI reporting, rewards system, and knowledge management tables	2025-09-04 09:23:21.149765	2000	c24ff7cfa0048b7fd64c6d498675adea	3858e1d7-6613-481e-9d3a-61182977f7c7
8	20250904_123500_008	20250904_123500_008_chat_logs_system.sql	Creates chat system, meetings, and comprehensive logging tables	2025-09-04 09:23:23.888759	2000	1730ed035893032676772ff5f8aec381	ad53e2fe-c2c6-4795-8996-117dbb6fc814
9	20250904_124000_009	20250904_124000_009_add_deleted_date_columns.sql	Add deleted_date columns to support soft delete functionality across all main tables	2025-09-04 09:27:57.927805	3000	3f064336fd686e48e1db5bedf1a5f3c9	0f164763-ec15-408e-8a8a-d7a97216742e
10	20250904_124500_010	20250904_124500_010_fix_country_default.sql	Fix the hardcoded country_id default to use actual Thailand ID	2025-09-04 09:33:11.137863	0	bf9e4df992b5b57f096aa49b6c346864	720a3260-6733-4ea7-acc4-b587c80d4fd3
11	20250904_125000_011	20250904_125000_011_insert_countries_data.sql	Insert comprehensive country data including Thailand with ID 212	2025-09-04 09:45:15.725437	1000	925ec896537c6418b0e070a56189feca	3ae12691-d9da-4fda-85fa-00f55202af48
12	20250904_125100_012	20250904_125100_012_insert_currencies_data.sql	Insert comprehensive currency data including THB with ID 12	2025-09-04 09:45:17.231418	0	4553417cd2985c1cffb6f7a29ec12fa5	b65411e8-a5b5-4dfe-b308-3fd0193e69a5
13	20250916_130000_013	20250916_130000_013_refactor_organization_roles.sql	-- Description:	2025-09-16 08:01:23.770394	1000	68b27ad1a6563dc4641774080915f1f2	1c9325e6-327b-428a-8193-9afa6340d95b
14	20250916_140000_009	20250916_140000_009_add_platform_enum_values.sql	Add BUSINESS, REWARDS, GEPP_BUSINESS_WEB, GEPP_REWARD_APP, ADMIN_WEB, GEPP_EPR_WEB values to platform_enum	2025-09-16 08:01:27.906233	2000	e36d35e3c47a7a049103bf1aa3c3742a	3b33bb3a-e735-4d8e-a8fe-3e62b7a81198
15	20250916_150000_010	20250916_150000_010_add_key_to_organization_roles.sql	Add key column to organization_roles table	2025-09-16 08:58:15.494545	500	test123	09188b7f-46c4-4ede-9684-e23e9f33ec9a
16	20250916_160000_011	20250916_160000_011_add_organization_id_to_user_roles.sql	Add organization_id column to user_roles table	2025-09-16 09:06:43.090438	300	abc123	61a299b0-3917-436a-9442-3dbd404e3522
17	20250916_170000_012	20250916_170000_012_add_name_local_to_location_tables.sql	Add name_local columns to location tables	2025-09-16 09:11:18.309688	400	def456	49adaea7-2694-439b-b9df-4c5a3b4d5b2a
18	20250917_150000_014	20250917_150000_014_create_user_related_tables.sql	Create missing user-related tables that are referenced in models but missing from database	2025-09-17 08:54:12.290083	1000	d6e6a73fa4131e29	429c83f3-c1e3-4b18-bf3a-78cbce6be7f8
19	20250917_153000_015	20250917_153000_015_add_system_roles.sql	Create SystemRole table and add system_role_id foreign key to organizations table	2025-09-17 08:54:13.793476	1000	02a24f0a07ad9b8f	429c83f3-c1e3-4b18-bf3a-78cbce6be7f8
20	20250918_130000_016	20250918_130000_016_create_organization_setup.sql	Creates the organization_setup table to store versioned hierarchical structure configurations for organizations	2025-09-18 08:07:30.725575	1000	0d32ebd9c40da062	9ffee73a-42d9-40ab-b2df-5030fa1e256c
21	20250918_140000_017	20250918_140000_017_fix_organization_setup_constraint.sql	Fix the unique constraint to only apply when is_active=true	2025-09-18 12:46:33.550589	1000	f7b09dc2356bec4b	de10f506-79bb-439b-8549-86bebe03722f
22	20250918_150000_018	20250918_150000_018_add_hub_type_to_user_locations.sql	Add hub_type field to support waste management hub classification	2025-09-18 14:58:22.621484	1000	48b936b28c6ef6bd	4c9ad868-b4df-4c1e-bbb0-1ea84d971c3e
23	20250919_160000_019	20250919_160000_019_add_members_to_user_locations.sql	Add members field to support user assignments for locations	2025-09-19 14:57:21.891408	0	5842b2ff7723b37c	90fe6a75-46a4-48ea-b537-f27900b6cd69
24	20250922_100000_020	20250922_100000_020_restructure_materials_tables.sql	Restructure materials table architecture	2025-09-22 17:17:25.145873	2000	ac47d2e472942f08	0e7c1eb1-9276-4d99-8f86-78ba7fdc8a7a
25	20250922_110000_021	20250922_110000_021_migrate_materials_data_from_csv.sql	Migrate materials data from CSV to new three-tier structure	2025-09-22 17:17:26.421806	1000	4e01044f590b0623	0e7c1eb1-9276-4d99-8f86-78ba7fdc8a7a
26	20250922_120000_022	20250922_120000_022_add_migration_id_and_complete_materials.sql	Add migration_id column and complete materials migration from CSV	2025-09-22 17:40:57.434501	1000	b6032e20792a8741	14b13c1d-1d2b-496e-a320-0f9d67bcd3a8
27	20250922_130000_023	20250922_130000_023_complete_materials_migration.sql	Complete materials migration with all remaining materials (99-311)	2025-09-22 17:40:58.61625	1000	69bce081079c4509	14b13c1d-1d2b-496e-a320-0f9d67bcd3a8
28	20250923_140000_024	20250923_140000_024_materials_restructure.sql	Restructure materials system with tags, tag groups, and base materials	2025-09-23 06:52:35.233027	2000	ad7f7278ff92656f	79156828-b956-40f4-ab58-618a87d7d370
29	20250923_140100_025	20250923_140100_025_fix_main_materials_tag_groups.sql	Fix main_materials table to add material_tag_groups column	2025-09-23 08:17:45.173276	1000	ed1d9e187e587d5e	84f8c268-bece-4cbc-97a0-c36038e2477c
30	20250923_140200_026	20250923_140200_026_fix_materials_table_structure.sql	Fix materials table structure - remove legacy_tags and base_material_id, add fixed_tags	2025-09-23 08:20:18.403295	1000	dc329c2f43fbba2c	0a2d2dfe-a3df-438f-8ac3-81118b7df507
31	20250923_140300_027	20250923_140300_027_restructure_transactions_system.sql	Create transaction_records table and restructure transactions table	2025-09-23 09:04:35.042145	5000	b950c8efbedad33f	b835f430-8684-4043-a4e0-33e8e40721dc
32	20250923_140400_028	20250923_140400_028_fix_transaction_tables_structure.sql	Fix transaction and transaction_records tables to match new schema	2025-09-23 09:18:35.78208	4000	a5047889af0dd5fd	77e9ae92-1071-4918-8fec-96c8f883c0bb
33	20250923_140500_029	20250923_140500_029_complete_transaction_schema_cleanup.sql	Complete cleanup of transactions table (partially successful)	2025-09-23 09:29:11.798271	\N	\N	cc8c6c83-46f4-4208-ac98-339946e355d5
34	20250923_140600_030	20250923_140600_030_fix_transaction_hazardous_level_type.sql	Fix hazardous_level column type and complete transaction schema cleanup	2025-09-23 09:30:07.389278	1000	555762cd5955bebb	b3a192a2-a43d-497f-a79a-7089613873a8
35	20250923_140700_031	20250923_140700_031_simple_constraint_fix.sql	Simple fix for hazardous_level constraint issue	2025-09-23 09:30:09.434182	1000	db163bac297dcf27	b3a192a2-a43d-497f-a79a-7089613873a8
36	20250923_140800_032	20250923_140800_032_mark_failed_migration_complete.sql	Mark the partially successful migration 029 as completed to prevent re-runs	2025-09-23 09:30:11.31979	1000	00b8c2e1f812fae4	b3a192a2-a43d-497f-a79a-7089613873a8
37	20250923_141000_033	20250923_141000_033_exact_transaction_columns.sql	Ensure transactions table has exactly the specified columns	2025-09-23 09:33:16.642514	4000	42d1e013fcdd5219	2a9310a3-509e-4b0d-b5a5-b2800828ee94
\.


--
-- Data for Name: subscription_permissions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.subscription_permissions (subscription_id, permission_id) FROM stdin;
\.


--
-- Data for Name: subscription_plans; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.subscription_plans (id, name, display_name, description, price_monthly, price_yearly, max_users, max_transactions_monthly, max_storage_gb, max_api_calls_daily, features, created_date, updated_date, is_active, deleted_date) FROM stdin;
1	free	Free Plan	Basic features for getting started	0	0	5	100	1	1000	["Basic waste tracking", "Up to 5 users", "100 transactions/month", "1GB storage", "Basic reporting"]	2025-09-04 09:23:10.776074+00	2025-09-04 09:23:10.776074+00	t	\N
\.


--
-- Data for Name: subscriptions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.subscriptions (id, organization_id, plan_id, status, trial_ends_at, current_period_starts_at, current_period_ends_at, users_count, transactions_count_this_month, storage_used_gb, api_calls_today, created_date, updated_date, is_active, deleted_date) FROM stdin;
1	3	1	active	2025-09-18 09:46:05.264729+00	2025-09-04 09:46:05.264729+00	2025-10-04 09:46:05.264729+00	1	0	0	0	2025-09-04 09:46:04.919487+00	2025-09-04 09:46:04.919487+00	t	\N
2	4	1	active	2025-09-30 05:55:28.03698+00	2025-09-16 05:55:28.03698+00	2025-10-16 05:55:28.03698+00	1	0	0	0	2025-09-16 05:55:27.683091+00	2025-09-16 05:55:27.683091+00	t	\N
3	5	1	active	2025-09-30 09:01:29.605883+00	2025-09-16 09:01:29.605883+00	2025-10-16 09:01:29.605883+00	1	0	0	0	2025-09-16 09:01:29.337448+00	2025-09-16 09:01:29.337448+00	t	\N
4	6	1	active	2025-10-01 06:43:39.130465+00	2025-09-17 06:43:39.130465+00	2025-10-17 06:43:39.130465+00	1	0	0	0	2025-09-17 06:43:38.81813+00	2025-09-17 06:43:38.81813+00	t	\N
5	7	1	active	2025-10-01 06:59:17.774996+00	2025-09-17 06:59:17.774996+00	2025-10-17 06:59:17.774996+00	1	0	0	0	2025-09-17 06:59:17.406163+00	2025-09-17 06:59:17.406163+00	t	\N
6	8	1	active	2025-10-02 05:42:32.292634+00	2025-09-18 05:42:32.292634+00	2025-10-18 05:42:32.292634+00	1	0	0	0	2025-09-18 05:42:31.977491+00	2025-09-18 05:42:31.977491+00	t	\N
\.


--
-- Data for Name: system_events; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.system_events (id, event_type, event_source, event_data, correlation_id, processing_status, processed_at, retry_count, max_retries, error_message, last_error_at, priority, scheduled_for, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: system_permissions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.system_permissions (id, code, name, description, category, created_date, updated_date, is_active, deleted_date) FROM stdin;
1	waste_transaction.create	Create Waste Transaction	Create new waste transactions	waste_transaction	2025-09-04 09:23:10.813056+00	2025-09-04 09:23:10.813056+00	t	\N
2	waste_transaction.view	View Waste Transaction	View waste transactions	waste_transaction	2025-09-04 09:23:10.813056+00	2025-09-04 09:23:10.813056+00	t	\N
3	waste_transaction.edit	Edit Waste Transaction	Edit existing waste transactions	waste_transaction	2025-09-04 09:23:10.813056+00	2025-09-04 09:23:10.813056+00	t	\N
4	waste_transaction.delete	Delete Waste Transaction	Delete waste transactions	waste_transaction	2025-09-04 09:23:10.813056+00	2025-09-04 09:23:10.813056+00	t	\N
5	reporting.basic	Basic Reporting	Access basic reports	reporting	2025-09-04 09:23:10.813056+00	2025-09-04 09:23:10.813056+00	t	\N
6	reporting.advanced	Advanced Reporting	Access advanced reports and analytics	reporting	2025-09-04 09:23:10.813056+00	2025-09-04 09:23:10.813056+00	t	\N
7	analytics.dashboard	Analytics Dashboard	Access analytics dashboard	analytics	2025-09-04 09:23:10.813056+00	2025-09-04 09:23:10.813056+00	t	\N
8	user_management.basic	Basic User Management	Manage users within limit	user_management	2025-09-04 09:23:10.813056+00	2025-09-04 09:23:10.813056+00	t	\N
9	api.basic	Basic API Access	Basic API access with rate limits	api	2025-09-04 09:23:10.813056+00	2025-09-04 09:23:10.813056+00	t	\N
10	api.advanced	Advanced API Access	Advanced API access with higher limits	api	2025-09-04 09:23:10.813056+00	2025-09-04 09:23:10.813056+00	t	\N
\.


--
-- Data for Name: system_roles; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.system_roles (id, name, description, permissions, created_date, updated_date) FROM stdin;
1	basic	Basic system access - Standard business features	{"transactions": true, "basic_reports": true, "user_management": false, "advanced_analytics": false, "api_access": false}	2025-09-17 08:54:13.154941	2025-09-17 08:54:13.154941
2	premium	Premium system access - Enhanced business features	{"transactions": true, "basic_reports": true, "advanced_reports": true, "user_management": true, "basic_analytics": true, "api_access": false}	2025-09-17 08:54:13.154941	2025-09-17 08:54:13.154941
3	enterprise	Enterprise system access - Full platform capabilities	{"transactions": true, "basic_reports": true, "advanced_reports": true, "user_management": true, "advanced_analytics": true, "api_access": true, "custom_integrations": true, "bulk_operations": true}	2025-09-17 08:54:13.154941	2025-09-17 08:54:13.154941
4	admin	System administrator - Full platform control	{"*": true}	2025-09-17 08:54:13.154941	2025-09-17 08:54:13.154941
\.


--
-- Data for Name: transaction_analytics; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.transaction_analytics (id, transaction_id, processing_efficiency, cost_per_kg, environmental_impact_score, collection_duration, processing_duration, total_cycle_time, contamination_rate, recovery_rate, quality_score, revenue, costs, profit_margin, carbon_footprint, energy_efficiency, water_usage, calculated_at, created_date, is_active) FROM stdin;
\.


--
-- Data for Name: transaction_documents; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.transaction_documents (id, transaction_id, document_type, document_name, file_url, file_size, file_type, uploaded_by_id, verified_by_id, verification_status, verification_date, expiry_date, is_required, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: transaction_items; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.transaction_items (id, transaction_id, material_id, waste_type, description, quantity, unit, weight_kg, price_per_unit, total_amount, condition_rating, contamination_level, processing_notes, created_date, updated_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: transaction_payments; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.transaction_payments (id, transaction_id, payment_method, payment_status, amount, currency_id, payment_date, due_date, payer_id, payee_id, payment_reference, bank_reference, gateway_transaction_id, gateway_response, notes, receipt_url, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: transaction_records; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.transaction_records (id, is_active, status, created_transaction_id, traceability, transaction_type, material_id, main_material_id, category_id, tags, unit, origin_quantity, origin_weight_kg, origin_price_per_unit, total_amount, currency_id, notes, images, origin_coordinates, destination_coordinates, hazardous_level, treatment_method, disposal_method, created_by_id, approved_by_id, completed_date, created_date, updated_date, deleted_date) FROM stdin;
\.


--
-- Data for Name: transaction_status_history; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.transaction_status_history (id, transaction_id, status, previous_status, reason, notes, changed_by_id, changed_at, created_date, is_active) FROM stdin;
\.


--
-- Data for Name: transactions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.transactions (id, status, weight_kg, total_amount, transaction_date, notes, images, vehicle_info, driver_info, hazardous_level, treatment_method, disposal_method, created_by_id, updated_by_id, approved_by_id, created_date, updated_date, is_active, deleted_date, transaction_records, transaction_method, organization_id, origin_id, destination_id, arrival_date, origin_coordinates, destination_coordinates) FROM stdin;
\.


--
-- Data for Name: user_activities; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_activities (id, user_location_id, actor_id, activity_type, resource, action, details, ip_address, user_agent, organization_id, session_id, is_active, created_date, updated_date, deleted_date) FROM stdin;
1	25	7	user_created	user	user_created	{"method": "direct"}	\N	\N	\N	\N	t	2025-09-18 05:19:29.842749	2025-09-18 05:19:29.842749	\N
2	27	26	user_created	user	user_created	{"method": "direct"}	\N	\N	\N	\N	t	2025-09-18 06:09:52.893309	2025-09-18 06:09:52.893309	\N
3	28	26	user_created	user	user_created	{"method": "direct"}	\N	\N	\N	\N	t	2025-09-18 06:17:38.426669	2025-09-18 06:17:38.426669	\N
4	29	26	user_created	user	user_created	{"method": "direct"}	\N	\N	\N	\N	t	2025-09-18 06:17:59.268628	2025-09-18 06:17:59.268628	\N
5	2070	26	user_created	user	user_created	{"method": "direct"}	\N	\N	\N	\N	t	2025-09-19 08:34:00.315837	2025-09-19 08:34:00.315837	\N
6	2184	26	user_created	user	user_created	{"method": "direct"}	\N	\N	\N	\N	t	2025-09-19 16:24:23.083863	2025-09-19 16:24:23.083863	\N
\.


--
-- Data for Name: user_analytics; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_analytics (id, user_id, event_type, event_data, session_id, created_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: user_bank; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_bank (id, user_location_id, organization_id, bank_id, account_number, account_name, account_type, branch_name, branch_code, is_verified, verification_date, is_primary, note, is_active, created_date, updated_date, deleted_date) FROM stdin;
\.


--
-- Data for Name: user_business_roles; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_business_roles (id, name, description, permissions, created_date, updated_date, is_active, deleted_date) FROM stdin;
1	owner	Business Owner	\N	2025-09-04 09:23:08.3685+00	2025-09-04 09:23:08.3685+00	t	\N
2	manager	Business Manager	\N	2025-09-04 09:23:08.3685+00	2025-09-04 09:23:08.3685+00	t	\N
3	employee	Business Employee	\N	2025-09-04 09:23:08.3685+00	2025-09-04 09:23:08.3685+00	t	\N
4	contractor	External Contractor	\N	2025-09-04 09:23:08.3685+00	2025-09-04 09:23:08.3685+00	t	\N
\.


--
-- Data for Name: user_devices; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_devices (id, user_location_id, device_id, device_name, device_type, platform, browser, browser_version, os_version, app_version, is_trusted, push_token, last_active, first_seen, is_active, created_date, updated_date, deleted_date) FROM stdin;
\.


--
-- Data for Name: user_input_channels; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_input_channels (id, user_id, channel, device_id, last_accessed_at, created_date, updated_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: user_invitations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_invitations (id, email, phone, invited_by_id, organization_id, intended_role, intended_organization_role, intended_platform, status, invitation_token, expires_at, accepted_at, created_user_id, custom_message, invitation_data, is_active, created_date, updated_date, deleted_date) FROM stdin;
\.


--
-- Data for Name: user_locations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_locations (id, is_user, is_location, name_th, name_en, display_name, email, is_email_active, email_notification, phone, username, password, facebook_id, apple_id, google_id_gmail, platform, role_id, organization_role_id, coordinate, address, postal_code, country_id, province_id, district_id, subdistrict_id, business_type, business_industry, business_sub_industry, company_name, company_phone, company_email, tax_id, functions, type, population, material, profile_image_url, national_id, national_card_image, business_registration_certificate, organization_id, parent_location_id, created_by_id, auditor_id, parent_user_id, organization_level, organization_path, sub_users, locale, nationality_id, currency_id, phone_code_id, note, expired_date, footprint, created_date, updated_date, is_active, deleted_date, hub_type, members) FROM stdin;
2053	f	t	\N	Branch 1	Branch 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	branch	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	\N	\N
2054	f	t	\N	Building 1	Building 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	building	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	\N	\N
3	t	f	\N	asd asd	qwe	asd@asd.com	f	\N	123	asd@asd.com	$2b$12$rtLG.Tx8q2xBBUqF1WrjT.oZFqx7fX.fj1tgp07VURbBBtFXY6weS	\N	\N	\N	NA	\N	\N	\N	\N	\N	212	\N	\N	\N	\N			qwe	123	asd@asd.com	\N	\N	\N	\N	\N	\N	\N	\N	\N	3	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-04 09:46:04.919487+00	2025-09-04 09:46:04.919487+00	t	\N	\N	\N
4	t	f	\N	Pakpol Roongsri	Belle	pakpolkiller@gmail.com	f	\N	0967863555	pakpolkiller@gmail.com	$2b$12$8w.zD5McZvmX6x4NKrWcZ.A8cfSxUglYHL8E9xwsFehZSx.u1kUz6	\N	\N	\N	NA	\N	\N	\N	\N	\N	212	\N	\N	\N	\N			Belle	0967863555	pakpolkiller@gmail.com	\N	\N	\N	\N	\N	\N	\N	\N	\N	4	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-16 05:55:27.683091+00	2025-09-16 05:55:27.683091+00	t	\N	\N	\N
5	t	f	\N	asd asd	toptop	top@asd.com	f	\N	123	top@asd.com	$2b$12$8OOd/i1.X8xUT2blsgkCre8cfcg7gwtSAiM2Qd2b9hA1wd/3WdCLG	\N	\N	\N	NA	\N	\N	\N	\N	\N	212	\N	\N	\N	\N			toptop	123	top@asd.com	\N	\N	\N	\N	\N	\N	\N	\N	\N	5	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-16 09:01:29.337448+00	2025-09-16 09:01:29.337448+00	t	\N	\N	\N
6	t	f	\N	top asd	topasd	top2@asd.com	f	\N	123	top2@asd.com	$2b$12$0aFpWcKREJEnfLzSKRESuOrfXr0Lc1MkhV3rxrMI.6pkSf1xW1w2u	\N	\N	\N	NA	\N	\N	\N	\N	\N	212	\N	\N	\N	\N			topasd	123	top2@asd.com	\N	\N	\N	\N	\N	\N	\N	\N	\N	6	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-17 06:43:38.81813+00	2025-09-17 06:43:38.81813+00	t	\N	\N	\N
7	t	f	\N	top asd3	toptop	top3@asd.com	f	\N	123	top3@asd.com	$2b$12$PhRxnqmUgtBkHQi9XHAquuI1PL43GKZskl/yGpTCEMT5SSynZGr/6	\N	\N	\N	NA	\N	\N	\N	\N	\N	212	\N	\N	\N	\N			toptop	123	top3@asd.com	\N	\N	\N	\N	\N	\N	\N	\N	\N	7	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-17 06:59:17.406163+00	2025-09-17 06:59:17.406163+00	t	\N	\N	\N
2055	f	t	\N	Floor 1	Floor 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	\N	\N
26	t	f	\N	top toptop	toptoptop	top3@top.com	f	\N	123	top3@top.com	$2b$12$PBnCzdV0EDSF6fqY09sEa.BOnP4dO/yvuACP9/mtNgZ1qdQ03ZCzC	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N			toptoptop	123	top3@top.com	\N	\N	\N	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-18 05:42:31.977491+00	2025-09-18 05:42:31.977491+00	t	\N	\N	\N
2056	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	\N	\N
2057	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	\N	\N
28	t	f	\N	\N	toot11	toot11@asd.com	f	\N	\N	\N	$2b$12$.77uf1vUeCYOvdE2AOP4o.slk6uWyPBCJsyOxIwj2EHKV6NTU9Hlm	\N	\N	\N	GEPP_BUSINESS_WEB	\N	15	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	8	\N	26	\N	26	0	/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-18 06:17:38.426669+00	2025-09-18 06:17:38.426669+00	t	\N	\N	\N
2058	f	t	\N	Room 3	Room 3	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	\N	\N
29	t	f	\N	\N	toot12	toot12@asd.com	f	\N	\N	\N	$2b$12$83o8qF6j6sZqT74BB0MXSuCmpmLnbDlDV5XRM2wVXg.1tZedbr5ya	\N	\N	\N	GEPP_BUSINESS_WEB	\N	16	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	8	\N	26	\N	26	0	/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-18 06:17:59.268628+00	2025-09-18 06:17:59.268628+00	t	\N	\N	\N
2059	f	t	\N	Hub	Hub	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub-main	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	\N	\N
2060	f	t	\N	Cafe Collection Point	Cafe Collection Point	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	Collectors	\N
2061	f	t	\N	Kitchen Waste Station	Kitchen Waste Station	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	Collectors	\N
27	t	f	\N	\N	toot10	toot10@asd.com	f	\N	\N	\N	$2b$12$BjPFvZHwvVGAsY0wrpJlaOHTquACN5eNkUaTQjhaa2U2iYTYxPjAW	\N	\N	\N	GEPP_BUSINESS_WEB	\N	13	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	8	\N	26	\N	26	0	/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-18 06:09:52.893309+00	2025-09-18 06:34:48.927639+00	t	\N	\N	\N
2062	f	t	\N	Basic Sorting Station	Basic Sorting Station	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	Sorters	\N
2063	f	t	\N	Local Pickup Point	Local Pickup Point	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	Transfer Station	\N
15	t	f	\N	\N	sas	sas@asd.com	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	10	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	/15/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-17 08:54:29.873097+00	2025-09-17 08:54:29.873097+00	t	\N	\N	\N
16	t	f	\N	\N	asddsa	asddsa@asd.com	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	10	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	/16/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-17 08:54:56.224596+00	2025-09-17 08:54:56.224596+00	t	\N	\N	\N
17	t	f	\N	\N	toot	toot@asd.com	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	10	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	/17/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-17 09:11:19.942454+00	2025-09-17 09:11:19.942454+00	t	\N	\N	\N
18	t	f	\N	\N	toot2	toot2@asd.com	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	10	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	/18/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-17 09:12:19.495436+00	2025-09-17 09:12:19.495436+00	t	\N	\N	\N
19	t	f	\N	\N	toot3	toot3@asd.com	f	\N	\N	\N	$2b$12$ZJHUO0TH7OjZx6BY3FF8teFWoXftTn93hBv4uxDjfMW5CATTPsPaS	\N	\N	\N	GEPP_BUSINESS_WEB	\N	10	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	/19/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-18 04:41:13.33469+00	2025-09-18 04:41:13.33469+00	t	\N	\N	\N
20	t	f	\N	\N	toot4	toot4@asd.com	f	\N	\N	\N	$2b$12$wTfQu2jzFXP1Hih8UF0W4ufk9tGVMz5dldqtxBudcM0cpWysSJoui	\N	\N	\N	GEPP_BUSINESS_WEB	\N	11	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	/20/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-18 04:50:15.029074+00	2025-09-18 04:50:15.029074+00	t	\N	\N	\N
21	t	f	\N	\N	toot5	toot5@asd.com	f	\N	\N	\N	$2b$12$7Fd/5GK704cIYXYQVLWhH.6Pj29x.PC1iZC1oQ0zFTCOScehBCKrO	\N	\N	\N	GEPP_BUSINESS_WEB	\N	9	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	/21/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-18 04:50:52.834572+00	2025-09-18 04:50:52.834572+00	t	\N	\N	\N
22	t	f	\N	\N	toot6	toot6@asd.com	f	\N	\N	\N	$2b$12$Thgy8D765inCfjscZwvRkOa/.t7s19x07K42MGGoyKYULkIm7B29C	\N	\N	\N	GEPP_BUSINESS_WEB	\N	9	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	/22/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-18 04:56:23.450985+00	2025-09-18 04:56:23.450985+00	t	\N	\N	\N
23	t	f	\N	\N	toot7	toot7@asd.com	f	\N	\N	\N	$2b$12$fNDeef//f5qbTQ6JQNJldejGAwDpaGX6X1yTv.tEznXyAP5T3vgVm	\N	\N	\N	GEPP_BUSINESS_WEB	\N	12	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	/23/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-18 05:08:02.517359+00	2025-09-18 05:08:02.517359+00	t	\N	\N	\N
24	t	f	\N	\N	toot8	toot8@asd.com	f	\N	\N	\N	$2b$12$1u4Q8P.0sh5fWdBGZLyc7.v8BnrIgtkZwPrdxDTJAIezwu6rmwG0e	\N	\N	\N	GEPP_BUSINESS_WEB	\N	12	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	0	/24/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-18 05:13:39.773781+00	2025-09-18 05:13:39.773781+00	t	\N	\N	\N
25	t	f	\N	\N	toot9	toot9@asd.com	f	\N	\N	\N	$2b$12$TT7JE5WI4yK8WcIJy49Wk.Lw8Mr/saJjlgITkFJze9FXbrk5nHhvG	\N	\N	\N	GEPP_BUSINESS_WEB	\N	12	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	7	\N	7	\N	7	0	/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-18 05:19:29.842749+00	2025-09-18 05:19:29.842749+00	t	\N	\N	\N
2064	f	t	\N	Community Recycling Center	Community Recycling Center	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	MRF	\N
2065	f	t	\N	Cup & Lid Processor	Cup & Lid Processor	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	Recycling Plant	\N
2066	f	t	\N	Paper Cup Mill	Paper Cup Mill	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	Recycling Plant	\N
2067	f	t	\N	Organic Waste Composter	Organic Waste Composter	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	Compost Facility	\N
2068	f	t	\N	Municipal Landfill	Municipal Landfill	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	Landfill	\N
2069	f	t	\N	Local Energy Plant	Local Energy Plant	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:25:04.166252+00	2025-09-19 08:25:04.166252+00	t	\N	Waste-to-Energy	\N
2070	t	f	\N	\N	toot13	toot13@asd.com	f	\N	\N	\N	$2b$12$P1RcpW4g0HXtX1lytUjMLudywDq2TM4Dog86KrF/PNFO0lvK/lyBS	\N	\N	\N	GEPP_BUSINESS_WEB	\N	14	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	8	\N	26	\N	26	0	/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 08:34:00.315837+00	2025-09-19 08:34:00.315837+00	t	\N	\N	\N
2071	f	t	\N	Building 1	Building 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	building	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:07:16.632874+00	2025-09-19 09:07:16.632874+00	t	\N	\N	\N
2072	f	t	\N	Floor 1	Floor 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:08:06.695347+00	2025-09-19 09:08:06.695347+00	t	\N	\N	\N
2073	f	t	\N	Floor 2	Floor 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:08:06.695347+00	2025-09-19 09:08:06.695347+00	t	\N	\N	\N
2074	f	t	\N	Floor 3	Floor 3	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:08:06.695347+00	2025-09-19 09:08:06.695347+00	t	\N	\N	\N
2075	f	t	\N	Floor 4	Floor 4	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:08:06.695347+00	2025-09-19 09:08:06.695347+00	t	\N	\N	\N
2076	f	t	\N	Floor 5	Floor 5	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:08:06.695347+00	2025-09-19 09:08:06.695347+00	t	\N	\N	\N
2077	f	t	\N	Branch 1	Branch 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	branch	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2078	f	t	\N	Building 1	Building 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	building	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2079	f	t	\N	Floor 1	Floor 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2080	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2081	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2082	f	t	\N	Floor 2	Floor 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2083	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2084	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2085	f	t	\N	Building 2	Building 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	building	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2086	f	t	\N	Floor 1	Floor 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2087	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2088	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2089	f	t	\N	Floor 2	Floor 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2090	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2091	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2092	f	t	\N	Branch 2	Branch 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	branch	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2093	f	t	\N	Building 1	Building 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	building	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2094	f	t	\N	Floor 1	Floor 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2095	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2096	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2097	f	t	\N	Floor 2	Floor 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2098	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2099	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2100	f	t	\N	Building 2	Building 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	building	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2101	f	t	\N	Floor 1	Floor 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2102	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2103	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2104	f	t	\N	Floor 2	Floor 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2105	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2106	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2107	f	t	\N	Hub	Hub	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub-main	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	\N	\N
2108	f	t	\N	Cafe Collection Point	Cafe Collection Point	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	Collectors	\N
2109	f	t	\N	Kitchen Waste Station	Kitchen Waste Station	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	Collectors	\N
2110	f	t	\N	Basic Sorting Station	Basic Sorting Station	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	Sorters	\N
2111	f	t	\N	Local Pickup Point	Local Pickup Point	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	Transfer Station	\N
2112	f	t	\N	Community Recycling Center	Community Recycling Center	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	MRF	\N
2113	f	t	\N	Cup & Lid Processor	Cup & Lid Processor	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	Recycling Plant	\N
2114	f	t	\N	Paper Cup Mill	Paper Cup Mill	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	Recycling Plant	\N
2115	f	t	\N	Organic Waste Composter	Organic Waste Composter	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	Compost Facility	\N
2116	f	t	\N	Municipal Landfill	Municipal Landfill	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	Landfill	\N
2117	f	t	\N	Local Energy Plant	Local Energy Plant	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:19:28.806448+00	2025-09-19 09:19:28.806448+00	t	\N	Waste-to-Energy	\N
2118	f	t	\N	Branch 1	Branch 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	branch	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2119	f	t	\N	Building 1	Building 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	building	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2120	f	t	\N	Floor 1	Floor 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2121	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2122	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2123	f	t	\N	Floor 2	Floor 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2124	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2125	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2126	f	t	\N	Building 2	Building 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	building	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2127	f	t	\N	Floor 1	Floor 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2128	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2129	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2130	f	t	\N	Floor 2	Floor 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2131	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2132	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2133	f	t	\N	Branch 2	Branch 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	branch	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2134	f	t	\N	Building 1	Building 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	building	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2135	f	t	\N	Floor 1	Floor 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2136	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2137	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2138	f	t	\N	Floor 2	Floor 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2139	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2140	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2141	f	t	\N	Building 2	Building 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	building	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2142	f	t	\N	Floor 1	Floor 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2143	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2144	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2145	f	t	\N	Floor 2	Floor 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2146	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2147	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2148	f	t	\N	Hub	Hub	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub-main	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	\N	\N
2149	f	t	\N	Chemical Waste Station	Chemical Waste Station	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	Collectors	\N
2150	f	t	\N	Hair Clippings Hub	Hair Clippings Hub	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	Collectors	\N
2151	f	t	\N	Beauty Product Waste	Beauty Product Waste	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	Collectors	\N
2152	f	t	\N	Salon General Waste	Salon General Waste	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	Collectors	\N
2153	f	t	\N	Beauty Chemical Processor	Beauty Chemical Processor	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	Chemical Treatment	\N
2154	f	t	\N	Hair Composter	Hair Composter	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	Compost Facility	\N
2155	f	t	\N	Plastic Container Recycler	Plastic Container Recycler	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	Recycling Plant	\N
2156	f	t	\N	Municipal Landfill	Municipal Landfill	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	Landfill	\N
2157	f	t	\N	Salon Wastewater Plant	Salon Wastewater Plant	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	Water Treatment	\N
2158	f	t	\N	Chemical Disposal Unit	Chemical Disposal Unit	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:20:41.504411+00	2025-09-19 09:20:41.504411+00	t	\N	Hazmat Facility	\N
2159	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:21:57.691833+00	2025-09-19 09:21:57.691833+00	t	\N	\N	\N
2160	f	t	\N	Floor 1	Floor 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:21:57.691833+00	2025-09-19 09:21:57.691833+00	t	\N	\N	\N
2161	f	t	\N	Floor 2	Floor 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:21:57.691833+00	2025-09-19 09:21:57.691833+00	t	\N	\N	\N
2162	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:24:29.165592+00	2025-09-19 09:24:29.165592+00	t	\N	\N	\N
2163	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:24:29.165592+00	2025-09-19 09:24:29.165592+00	t	\N	\N	\N
2164	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:24:29.165592+00	2025-09-19 09:24:29.165592+00	t	\N	\N	\N
2165	f	t	\N	Floor 1	Floor 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:24:29.165592+00	2025-09-19 09:24:29.165592+00	t	\N	\N	\N
2166	f	t	\N	Floor 2	Floor 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 09:24:29.165592+00	2025-09-19 09:24:29.165592+00	t	\N	\N	\N
2167	f	t	\N	Branch 1	Branch 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	branch	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 14:59:39.709313+00	t	\N	\N	[]
2168	f	t	\N	Building 1	Building 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	building	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 14:59:39.709313+00	t	\N	\N	[]
2173	f	t	\N	Hub	Hub	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub-main	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 14:59:39.709313+00	t	\N	\N	[]
2174	f	t	\N	Cafe Collection Point	Cafe Collection Point	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 14:59:39.709313+00	t	\N	Collectors	[]
2175	f	t	\N	Kitchen Waste Station	Kitchen Waste Station	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 14:59:39.709313+00	t	\N	Collectors	[]
2176	f	t	\N	Basic Sorting Station	Basic Sorting Station	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 14:59:39.709313+00	t	\N	Sorters	[]
2177	f	t	\N	Local Pickup Point	Local Pickup Point	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 14:59:39.709313+00	t	\N	Transfer Station	[]
2178	f	t	\N	Community Recycling Center	Community Recycling Center	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 14:59:39.709313+00	t	\N	MRF	[]
2179	f	t	\N	Cup & Lid Processor	Cup & Lid Processor	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 14:59:39.709313+00	t	\N	Recycling Plant	[]
2180	f	t	\N	Paper Cup Mill	Paper Cup Mill	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 14:59:39.709313+00	t	\N	Recycling Plant	[]
2181	f	t	\N	Organic Waste Composter	Organic Waste Composter	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 14:59:39.709313+00	t	\N	Compost Facility	[]
2182	f	t	\N	Municipal Landfill	Municipal Landfill	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 14:59:39.709313+00	t	\N	Landfill	[]
2183	f	t	\N	Local Energy Plant	Local Energy Plant	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	hub	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 14:59:39.709313+00	t	\N	Waste-to-Energy	[]
2170	f	t	\N	Room 1	Room 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 15:47:20.641267+00	t	\N	\N	[{"role": "admin", "user_id": 27}, {"role": "dataInput", "user_id": 2070}, {"role": "auditor", "user_id": 28}]
2184	t	f	\N	\N	toot14	toot14@asd.com	f	\N	\N	\N	$2b$12$h.J7cCCpOgf/pIoqfaFTcuK9Ar148Digu5AGLCB/pqHTgKsTHgX6.	\N	\N	\N	GEPP_BUSINESS_WEB	\N	13	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	8	\N	26	\N	26	0	/	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 16:24:23.083863+00	2025-09-19 16:24:23.083863+00	t	\N	\N	\N
2171	f	t	\N	Room 2	Room 2	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 16:25:17.137033+00	t	\N	\N	[{"role": "admin", "user_id": 2184}, {"role": "admin", "user_id": 27}, {"role": "dataInput", "user_id": 2070}, {"role": "auditor", "user_id": 28}]
2169	f	t	\N	Floor 1	Floor 1	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	floor	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 16:32:31.627273+00	t	\N	\N	[{"role": "admin", "user_id": 27}]
2172	f	t	\N	Room 3	Room 3	\N	f	\N	\N	\N	\N	\N	\N	\N	GEPP_BUSINESS_WEB	\N	\N	\N	\N	\N	212	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	room	\N	\N	\N	\N	\N	\N	8	\N	\N	\N	\N	0	\N	\N	TH	\N	12	\N	\N	\N	\N	2025-09-19 14:59:39.709313+00	2025-09-19 16:25:33.620275+00	t	\N	\N	[{"role": "admin", "user_id": 2184}, {"role": "dataInput", "user_id": 2070}]
\.


--
-- Data for Name: user_organization_role_mapping; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_organization_role_mapping (user_location_id, organization_id, role_id) FROM stdin;
\.


--
-- Data for Name: user_organization_roles; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_organization_roles (user_location_id, organization_id, role_id) FROM stdin;
\.


--
-- Data for Name: user_point_balances; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_point_balances (id, user_id, points_type, current_balance, lifetime_earned, lifetime_redeemed, pending_points, expired_points, last_activity_date, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: user_preferences; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_preferences (id, user_location_id, email_notifications, push_notifications, sms_notifications, language, timezone, theme, currency, show_tutorials, compact_view, auto_save, profile_visibility, share_analytics, custom_settings, is_active, created_date, updated_date, deleted_date) FROM stdin;
1	15	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-17 08:54:29.873097	2025-09-17 08:54:29.873097	\N
2	16	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-17 08:54:56.224596	2025-09-17 08:54:56.224596	\N
3	17	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-17 09:11:19.942454	2025-09-17 09:11:19.942454	\N
4	18	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-17 09:12:19.495436	2025-09-17 09:12:19.495436	\N
5	19	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-18 04:41:13.33469	2025-09-18 04:41:13.33469	\N
6	20	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-18 04:50:15.029074	2025-09-18 04:50:15.029074	\N
7	21	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-18 04:50:52.834572	2025-09-18 04:50:52.834572	\N
8	22	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-18 04:56:23.450985	2025-09-18 04:56:23.450985	\N
9	23	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-18 05:08:02.517359	2025-09-18 05:08:02.517359	\N
10	24	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-18 05:13:39.773781	2025-09-18 05:13:39.773781	\N
11	25	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-18 05:19:29.842749	2025-09-18 05:19:29.842749	\N
12	27	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-18 06:09:52.893309	2025-09-18 06:09:52.893309	\N
13	28	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-18 06:17:38.426669	2025-09-18 06:17:38.426669	\N
14	29	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-18 06:17:59.268628	2025-09-18 06:17:59.268628	\N
15	2070	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-19 08:34:00.315837	2025-09-19 08:34:00.315837	\N
16	2184	t	t	f	th	Asia/Bangkok	light	THB	t	f	t	organization	t	\N	t	2025-09-19 16:24:23.083863	2025-09-19 16:24:23.083863	\N
\.


--
-- Data for Name: user_roles; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_roles (id, name, description, permissions, created_date, updated_date, is_active, deleted_date, organization_id) FROM stdin;
1	admin	System Administrator	\N	2025-09-04 09:23:08.334026+00	2025-09-04 09:23:08.334026+00	t	\N	\N
2	user	Regular User	\N	2025-09-04 09:23:08.334026+00	2025-09-04 09:23:08.334026+00	t	\N	\N
3	operator	System Operator	\N	2025-09-04 09:23:08.334026+00	2025-09-04 09:23:08.334026+00	t	\N	\N
4	viewer	Read-only User	\N	2025-09-04 09:23:08.334026+00	2025-09-04 09:23:08.334026+00	t	\N	\N
\.


--
-- Data for Name: user_sessions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_sessions (id, user_id, session_token, device_info, ip_address, expires_at, created_date, updated_date, is_active, deleted_date) FROM stdin;
\.


--
-- Data for Name: user_subscriptions; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_subscriptions (id, user_location_id, organization_id, subscription_package_id, start_date, end_date, status, billing_cycle, next_billing_date, auto_renew, usage_data, is_active, created_date, updated_date, deleted_date) FROM stdin;
\.


--
-- Data for Name: user_subusers; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.user_subusers (parent_user_id, subuser_id, created_date, is_active) FROM stdin;
\.


--
-- Data for Name: waste_collections; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.waste_collections (id, transaction_id, collection_date, collection_address, collection_coordinate, collector_id, collection_team, vehicle_type, vehicle_plate, vehicle_capacity, collection_method, container_types, weather_conditions, traffic_conditions, start_time, end_time, notes, images, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Data for Name: waste_processing; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.waste_processing (id, transaction_id, processing_date, processing_facility_id, input_weight, output_weight, waste_reduction_percent, processing_method, processing_equipment, processing_duration, quality_grade, contamination_removed, byproducts, residue_amount, residue_disposal_method, energy_consumed, water_used, operator_id, supervisor_id, notes, processing_report_url, created_date, updated_date, is_active) FROM stdin;
\.


--
-- Name: audit_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.audit_logs_id_seq', 1, false);


--
-- Name: banks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.banks_id_seq', 1, false);


--
-- Name: base_materials_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.base_materials_id_seq', 1, false);


--
-- Name: chat_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.chat_history_id_seq', 1, false);


--
-- Name: chats_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.chats_id_seq', 1, false);


--
-- Name: currencies_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.currencies_id_seq', 100, true);


--
-- Name: epr_audits_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.epr_audits_id_seq', 1, false);


--
-- Name: epr_data_submissions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.epr_data_submissions_id_seq', 1, false);


--
-- Name: epr_notifications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.epr_notifications_id_seq', 1, false);


--
-- Name: epr_payments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.epr_payments_id_seq', 1, false);


--
-- Name: epr_programs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.epr_programs_id_seq', 1, false);


--
-- Name: epr_registrations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.epr_registrations_id_seq', 1, false);


--
-- Name: epr_reports_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.epr_reports_id_seq', 1, false);


--
-- Name: epr_targets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.epr_targets_id_seq', 1, false);


--
-- Name: experts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.experts_id_seq', 1, false);


--
-- Name: gri_indicators_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.gri_indicators_id_seq', 1, false);


--
-- Name: gri_report_data_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.gri_report_data_id_seq', 1, false);


--
-- Name: gri_reports_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.gri_reports_id_seq', 1, false);


--
-- Name: gri_standards_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.gri_standards_id_seq', 5, true);


--
-- Name: km_chunks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.km_chunks_id_seq', 1, false);


--
-- Name: km_files_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.km_files_id_seq', 1, false);


--
-- Name: locales_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.locales_id_seq', 1, false);


--
-- Name: location_countries_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.location_countries_id_seq', 250, true);


--
-- Name: location_districts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.location_districts_id_seq', 1, false);


--
-- Name: location_provinces_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.location_provinces_id_seq', 1, false);


--
-- Name: location_regions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.location_regions_id_seq', 1, false);


--
-- Name: location_subdistricts_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.location_subdistricts_id_seq', 1, false);


--
-- Name: main_materials_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.main_materials_id_seq', 20, true);


--
-- Name: material_categories_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.material_categories_id_seq', 7, true);


--
-- Name: material_tag_groups_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.material_tag_groups_id_seq', 1, false);


--
-- Name: material_tags_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.material_tags_id_seq', 1, false);


--
-- Name: materials_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.materials_id_seq', 261, true);


--
-- Name: meeting_participants_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.meeting_participants_id_seq', 1, false);


--
-- Name: meetings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.meetings_id_seq', 1, false);


--
-- Name: nationalities_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.nationalities_id_seq', 1, false);


--
-- Name: organization_info_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.organization_info_id_seq', 8, true);


--
-- Name: organization_permissions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.organization_permissions_id_seq', 28, true);


--
-- Name: organization_roles_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.organization_roles_id_seq', 16, true);


--
-- Name: organization_setup_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.organization_setup_id_seq', 108, true);


--
-- Name: organizations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.organizations_id_seq', 8, true);


--
-- Name: phone_number_country_codes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.phone_number_country_codes_id_seq', 1, false);


--
-- Name: platform_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.platform_logs_id_seq', 1, false);


--
-- Name: point_transactions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.point_transactions_id_seq', 1, false);


--
-- Name: reward_redemptions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.reward_redemptions_id_seq', 1, false);


--
-- Name: rewards_catalog_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.rewards_catalog_id_seq', 1, false);


--
-- Name: schema_migrations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.schema_migrations_id_seq', 37, true);


--
-- Name: subscription_plans_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.subscription_plans_id_seq', 1, true);


--
-- Name: subscriptions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.subscriptions_id_seq', 6, true);


--
-- Name: system_events_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.system_events_id_seq', 1, false);


--
-- Name: system_permissions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.system_permissions_id_seq', 10, true);


--
-- Name: system_roles_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.system_roles_id_seq', 4, true);


--
-- Name: transaction_analytics_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.transaction_analytics_id_seq', 1, false);


--
-- Name: transaction_documents_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.transaction_documents_id_seq', 1, false);


--
-- Name: transaction_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.transaction_items_id_seq', 1, false);


--
-- Name: transaction_payments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.transaction_payments_id_seq', 1, false);


--
-- Name: transaction_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.transaction_records_id_seq', 1, false);


--
-- Name: transaction_status_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.transaction_status_history_id_seq', 1, false);


--
-- Name: transactions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.transactions_id_seq', 1, false);


--
-- Name: user_activities_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_activities_id_seq', 6, true);


--
-- Name: user_analytics_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_analytics_id_seq', 1, false);


--
-- Name: user_bank_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_bank_id_seq', 1, false);


--
-- Name: user_business_roles_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_business_roles_id_seq', 4, true);


--
-- Name: user_devices_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_devices_id_seq', 1, false);


--
-- Name: user_input_channels_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_input_channels_id_seq', 1, false);


--
-- Name: user_invitations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_invitations_id_seq', 1, false);


--
-- Name: user_locations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_locations_id_seq', 2184, true);


--
-- Name: user_point_balances_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_point_balances_id_seq', 1, false);


--
-- Name: user_preferences_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_preferences_id_seq', 16, true);


--
-- Name: user_roles_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_roles_id_seq', 4, true);


--
-- Name: user_sessions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_sessions_id_seq', 1, false);


--
-- Name: user_subscriptions_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.user_subscriptions_id_seq', 1, false);


--
-- Name: waste_collections_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.waste_collections_id_seq', 1, false);


--
-- Name: waste_processing_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.waste_processing_id_seq', 1, false);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);


--
-- Name: banks banks_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.banks
    ADD CONSTRAINT banks_code_key UNIQUE (code);


--
-- Name: banks banks_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.banks
    ADD CONSTRAINT banks_pkey PRIMARY KEY (id);


--
-- Name: base_materials base_materials_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.base_materials
    ADD CONSTRAINT base_materials_pkey PRIMARY KEY (id);


--
-- Name: chat_history chat_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chat_history
    ADD CONSTRAINT chat_history_pkey PRIMARY KEY (id);


--
-- Name: chats chats_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chats
    ADD CONSTRAINT chats_pkey PRIMARY KEY (id);


--
-- Name: currencies currencies_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.currencies
    ADD CONSTRAINT currencies_code_key UNIQUE (code);


--
-- Name: currencies currencies_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.currencies
    ADD CONSTRAINT currencies_pkey PRIMARY KEY (id);


--
-- Name: epr_audits epr_audits_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_audits
    ADD CONSTRAINT epr_audits_pkey PRIMARY KEY (id);


--
-- Name: epr_data_submissions epr_data_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_data_submissions
    ADD CONSTRAINT epr_data_submissions_pkey PRIMARY KEY (id);


--
-- Name: epr_notifications epr_notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_notifications
    ADD CONSTRAINT epr_notifications_pkey PRIMARY KEY (id);


--
-- Name: epr_payments epr_payments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_payments
    ADD CONSTRAINT epr_payments_pkey PRIMARY KEY (id);


--
-- Name: epr_programs epr_programs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_programs
    ADD CONSTRAINT epr_programs_pkey PRIMARY KEY (id);


--
-- Name: epr_registrations epr_registrations_organization_id_program_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_registrations
    ADD CONSTRAINT epr_registrations_organization_id_program_id_key UNIQUE (organization_id, program_id);


--
-- Name: epr_registrations epr_registrations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_registrations
    ADD CONSTRAINT epr_registrations_pkey PRIMARY KEY (id);


--
-- Name: epr_reports epr_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_reports
    ADD CONSTRAINT epr_reports_pkey PRIMARY KEY (id);


--
-- Name: epr_targets epr_targets_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_targets
    ADD CONSTRAINT epr_targets_pkey PRIMARY KEY (id);


--
-- Name: experts experts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.experts
    ADD CONSTRAINT experts_pkey PRIMARY KEY (id);


--
-- Name: gri_indicators gri_indicators_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_indicators
    ADD CONSTRAINT gri_indicators_pkey PRIMARY KEY (id);


--
-- Name: gri_indicators gri_indicators_standard_id_indicator_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_indicators
    ADD CONSTRAINT gri_indicators_standard_id_indicator_code_key UNIQUE (standard_id, indicator_code);


--
-- Name: gri_report_data gri_report_data_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_report_data
    ADD CONSTRAINT gri_report_data_pkey PRIMARY KEY (id);


--
-- Name: gri_reports gri_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_reports
    ADD CONSTRAINT gri_reports_pkey PRIMARY KEY (id);


--
-- Name: gri_standards gri_standards_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_standards
    ADD CONSTRAINT gri_standards_pkey PRIMARY KEY (id);


--
-- Name: gri_standards gri_standards_standard_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_standards
    ADD CONSTRAINT gri_standards_standard_code_key UNIQUE (standard_code);


--
-- Name: km_chunks km_chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.km_chunks
    ADD CONSTRAINT km_chunks_pkey PRIMARY KEY (id);


--
-- Name: km_files km_files_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.km_files
    ADD CONSTRAINT km_files_pkey PRIMARY KEY (id);


--
-- Name: locales locales_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.locales
    ADD CONSTRAINT locales_code_key UNIQUE (code);


--
-- Name: locales locales_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.locales
    ADD CONSTRAINT locales_pkey PRIMARY KEY (id);


--
-- Name: location_countries location_countries_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_countries
    ADD CONSTRAINT location_countries_code_key UNIQUE (code);


--
-- Name: location_countries location_countries_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_countries
    ADD CONSTRAINT location_countries_pkey PRIMARY KEY (id);


--
-- Name: location_districts location_districts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_districts
    ADD CONSTRAINT location_districts_pkey PRIMARY KEY (id);


--
-- Name: location_provinces location_provinces_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_provinces
    ADD CONSTRAINT location_provinces_pkey PRIMARY KEY (id);


--
-- Name: location_regions location_regions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_regions
    ADD CONSTRAINT location_regions_pkey PRIMARY KEY (id);


--
-- Name: location_subdistricts location_subdistricts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_subdistricts
    ADD CONSTRAINT location_subdistricts_pkey PRIMARY KEY (id);


--
-- Name: main_materials main_materials_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.main_materials
    ADD CONSTRAINT main_materials_pkey PRIMARY KEY (id);


--
-- Name: material_categories material_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.material_categories
    ADD CONSTRAINT material_categories_pkey PRIMARY KEY (id);


--
-- Name: material_tag_groups material_tag_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.material_tag_groups
    ADD CONSTRAINT material_tag_groups_pkey PRIMARY KEY (id);


--
-- Name: material_tags material_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.material_tags
    ADD CONSTRAINT material_tags_pkey PRIMARY KEY (id);


--
-- Name: materials materials_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.materials
    ADD CONSTRAINT materials_pkey PRIMARY KEY (id);


--
-- Name: meeting_participants meeting_participants_meeting_id_user_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.meeting_participants
    ADD CONSTRAINT meeting_participants_meeting_id_user_id_key UNIQUE (meeting_id, user_id);


--
-- Name: meeting_participants meeting_participants_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.meeting_participants
    ADD CONSTRAINT meeting_participants_pkey PRIMARY KEY (id);


--
-- Name: meetings meetings_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.meetings
    ADD CONSTRAINT meetings_pkey PRIMARY KEY (id);


--
-- Name: nationalities nationalities_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.nationalities
    ADD CONSTRAINT nationalities_code_key UNIQUE (code);


--
-- Name: nationalities nationalities_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.nationalities
    ADD CONSTRAINT nationalities_pkey PRIMARY KEY (id);


--
-- Name: organization_info organization_info_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_info
    ADD CONSTRAINT organization_info_pkey PRIMARY KEY (id);


--
-- Name: organization_permissions organization_permissions_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_permissions
    ADD CONSTRAINT organization_permissions_code_key UNIQUE (code);


--
-- Name: organization_permissions organization_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_permissions
    ADD CONSTRAINT organization_permissions_pkey PRIMARY KEY (id);


--
-- Name: organization_role_permissions organization_role_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_role_permissions
    ADD CONSTRAINT organization_role_permissions_pkey PRIMARY KEY (role_id, permission_id);


--
-- Name: organization_roles organization_roles_organization_id_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_roles
    ADD CONSTRAINT organization_roles_organization_id_name_key UNIQUE (organization_id, name);


--
-- Name: organization_roles organization_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_roles
    ADD CONSTRAINT organization_roles_pkey PRIMARY KEY (id);


--
-- Name: organization_setup organization_setup_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_setup
    ADD CONSTRAINT organization_setup_pkey PRIMARY KEY (id);


--
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);


--
-- Name: phone_number_country_codes phone_number_country_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.phone_number_country_codes
    ADD CONSTRAINT phone_number_country_codes_pkey PRIMARY KEY (id);


--
-- Name: platform_logs platform_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.platform_logs
    ADD CONSTRAINT platform_logs_pkey PRIMARY KEY (id);


--
-- Name: point_transactions point_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.point_transactions
    ADD CONSTRAINT point_transactions_pkey PRIMARY KEY (id);


--
-- Name: reward_redemptions reward_redemptions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reward_redemptions
    ADD CONSTRAINT reward_redemptions_pkey PRIMARY KEY (id);


--
-- Name: reward_redemptions reward_redemptions_redemption_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reward_redemptions
    ADD CONSTRAINT reward_redemptions_redemption_code_key UNIQUE (redemption_code);


--
-- Name: rewards_catalog rewards_catalog_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rewards_catalog
    ADD CONSTRAINT rewards_catalog_pkey PRIMARY KEY (id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (id);


--
-- Name: schema_migrations schema_migrations_version_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_version_key UNIQUE (version);


--
-- Name: subscription_permissions subscription_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscription_permissions
    ADD CONSTRAINT subscription_permissions_pkey PRIMARY KEY (subscription_id, permission_id);


--
-- Name: subscription_plans subscription_plans_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscription_plans
    ADD CONSTRAINT subscription_plans_name_key UNIQUE (name);


--
-- Name: subscription_plans subscription_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscription_plans
    ADD CONSTRAINT subscription_plans_pkey PRIMARY KEY (id);


--
-- Name: subscriptions subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_pkey PRIMARY KEY (id);


--
-- Name: system_events system_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.system_events
    ADD CONSTRAINT system_events_pkey PRIMARY KEY (id);


--
-- Name: system_permissions system_permissions_code_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.system_permissions
    ADD CONSTRAINT system_permissions_code_key UNIQUE (code);


--
-- Name: system_permissions system_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.system_permissions
    ADD CONSTRAINT system_permissions_pkey PRIMARY KEY (id);


--
-- Name: system_roles system_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.system_roles
    ADD CONSTRAINT system_roles_pkey PRIMARY KEY (id);


--
-- Name: transaction_analytics transaction_analytics_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_analytics
    ADD CONSTRAINT transaction_analytics_pkey PRIMARY KEY (id);


--
-- Name: transaction_documents transaction_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_documents
    ADD CONSTRAINT transaction_documents_pkey PRIMARY KEY (id);


--
-- Name: transaction_items transaction_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_items
    ADD CONSTRAINT transaction_items_pkey PRIMARY KEY (id);


--
-- Name: transaction_payments transaction_payments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_payments
    ADD CONSTRAINT transaction_payments_pkey PRIMARY KEY (id);


--
-- Name: transaction_records transaction_records_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_records
    ADD CONSTRAINT transaction_records_pkey PRIMARY KEY (id);


--
-- Name: transaction_status_history transaction_status_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_status_history
    ADD CONSTRAINT transaction_status_history_pkey PRIMARY KEY (id);


--
-- Name: transactions transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transactions
    ADD CONSTRAINT transactions_pkey PRIMARY KEY (id);


--
-- Name: user_activities user_activities_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_activities
    ADD CONSTRAINT user_activities_pkey PRIMARY KEY (id);


--
-- Name: user_analytics user_analytics_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_analytics
    ADD CONSTRAINT user_analytics_pkey PRIMARY KEY (id);


--
-- Name: user_bank user_bank_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_bank
    ADD CONSTRAINT user_bank_pkey PRIMARY KEY (id);


--
-- Name: user_business_roles user_business_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_business_roles
    ADD CONSTRAINT user_business_roles_pkey PRIMARY KEY (id);


--
-- Name: user_devices user_devices_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_devices
    ADD CONSTRAINT user_devices_pkey PRIMARY KEY (id);


--
-- Name: user_devices user_devices_user_device_unique; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_devices
    ADD CONSTRAINT user_devices_user_device_unique UNIQUE (user_location_id, device_id);


--
-- Name: user_input_channels user_input_channels_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_input_channels
    ADD CONSTRAINT user_input_channels_pkey PRIMARY KEY (id);


--
-- Name: user_invitations user_invitations_invitation_token_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_invitations
    ADD CONSTRAINT user_invitations_invitation_token_key UNIQUE (invitation_token);


--
-- Name: user_invitations user_invitations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_invitations
    ADD CONSTRAINT user_invitations_pkey PRIMARY KEY (id);


--
-- Name: user_locations user_locations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations
    ADD CONSTRAINT user_locations_pkey PRIMARY KEY (id);


--
-- Name: user_organization_role_mapping user_organization_role_mapping_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_organization_role_mapping
    ADD CONSTRAINT user_organization_role_mapping_pkey PRIMARY KEY (user_location_id, organization_id);


--
-- Name: user_organization_roles user_organization_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_organization_roles
    ADD CONSTRAINT user_organization_roles_pkey PRIMARY KEY (user_location_id, organization_id, role_id);


--
-- Name: user_point_balances user_point_balances_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_point_balances
    ADD CONSTRAINT user_point_balances_pkey PRIMARY KEY (id);


--
-- Name: user_point_balances user_point_balances_user_id_points_type_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_point_balances
    ADD CONSTRAINT user_point_balances_user_id_points_type_key UNIQUE (user_id, points_type);


--
-- Name: user_preferences user_preferences_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT user_preferences_pkey PRIMARY KEY (id);


--
-- Name: user_roles user_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_pkey PRIMARY KEY (id);


--
-- Name: user_sessions user_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_pkey PRIMARY KEY (id);


--
-- Name: user_subscriptions user_subscriptions_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_subscriptions
    ADD CONSTRAINT user_subscriptions_pkey PRIMARY KEY (id);


--
-- Name: user_subusers user_subusers_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_subusers
    ADD CONSTRAINT user_subusers_pkey PRIMARY KEY (parent_user_id, subuser_id);


--
-- Name: waste_collections waste_collections_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.waste_collections
    ADD CONSTRAINT waste_collections_pkey PRIMARY KEY (id);


--
-- Name: waste_processing waste_processing_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.waste_processing
    ADD CONSTRAINT waste_processing_pkey PRIMARY KEY (id);


--
-- Name: idx_audit_logs_action; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_audit_logs_action ON public.audit_logs USING btree (action);


--
-- Name: idx_audit_logs_compliance; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_audit_logs_compliance ON public.audit_logs USING btree (compliance_category);


--
-- Name: idx_audit_logs_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_audit_logs_created ON public.audit_logs USING btree (created_date);


--
-- Name: idx_audit_logs_deleted_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_audit_logs_deleted_date ON public.audit_logs USING btree (deleted_date);


--
-- Name: idx_audit_logs_organization; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_audit_logs_organization ON public.audit_logs USING btree (organization_id);


--
-- Name: idx_audit_logs_resource; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_audit_logs_resource ON public.audit_logs USING btree (resource_type, resource_id);


--
-- Name: idx_audit_logs_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_audit_logs_user ON public.audit_logs USING btree (user_id);


--
-- Name: idx_banks_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_banks_code ON public.banks USING btree (code);


--
-- Name: idx_base_materials_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_base_materials_category ON public.base_materials USING btree (category_id);


--
-- Name: idx_base_materials_is_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_base_materials_is_active ON public.base_materials USING btree (is_active);


--
-- Name: idx_base_materials_main_material; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_base_materials_main_material ON public.base_materials USING btree (main_material_id);


--
-- Name: idx_base_materials_name_en; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_base_materials_name_en ON public.base_materials USING btree (name_en);


--
-- Name: idx_base_materials_name_th; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_base_materials_name_th ON public.base_materials USING btree (name_th);


--
-- Name: idx_base_materials_tag_groups; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_base_materials_tag_groups ON public.base_materials USING gin (tag_groups);


--
-- Name: idx_chat_history_chat; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_chat_history_chat ON public.chat_history USING btree (chat_id);


--
-- Name: idx_chat_history_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_chat_history_created ON public.chat_history USING btree (created_date);


--
-- Name: idx_chat_history_sender; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_chat_history_sender ON public.chat_history USING btree (sender_id);


--
-- Name: idx_chats_expert; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_chats_expert ON public.chats USING btree (expert_id);


--
-- Name: idx_chats_started_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_chats_started_at ON public.chats USING btree (started_at);


--
-- Name: idx_chats_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_chats_status ON public.chats USING btree (status);


--
-- Name: idx_chats_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_chats_type ON public.chats USING btree (chat_type);


--
-- Name: idx_chats_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_chats_user ON public.chats USING btree (user_id);


--
-- Name: idx_currencies_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_currencies_code ON public.currencies USING btree (code);


--
-- Name: idx_epr_audits_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_audits_date ON public.epr_audits USING btree (audit_date_start);


--
-- Name: idx_epr_audits_registration; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_audits_registration ON public.epr_audits USING btree (registration_id);


--
-- Name: idx_epr_data_submissions_period; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_data_submissions_period ON public.epr_data_submissions USING btree (reporting_year, reporting_period);


--
-- Name: idx_epr_data_submissions_registration; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_data_submissions_registration ON public.epr_data_submissions USING btree (registration_id);


--
-- Name: idx_epr_data_submissions_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_data_submissions_status ON public.epr_data_submissions USING btree (submission_status);


--
-- Name: idx_epr_notifications_organization; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_notifications_organization ON public.epr_notifications USING btree (organization_id);


--
-- Name: idx_epr_notifications_registration; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_notifications_registration ON public.epr_notifications USING btree (registration_id);


--
-- Name: idx_epr_notifications_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_notifications_type ON public.epr_notifications USING btree (notification_type);


--
-- Name: idx_epr_payments_due_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_payments_due_date ON public.epr_payments USING btree (due_date);


--
-- Name: idx_epr_payments_registration; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_payments_registration ON public.epr_payments USING btree (registration_id);


--
-- Name: idx_epr_payments_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_payments_status ON public.epr_payments USING btree (status);


--
-- Name: idx_epr_programs_country; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_programs_country ON public.epr_programs USING btree (country_id);


--
-- Name: idx_epr_programs_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_programs_type ON public.epr_programs USING btree (program_type);


--
-- Name: idx_epr_registrations_organization; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_registrations_organization ON public.epr_registrations USING btree (organization_id);


--
-- Name: idx_epr_registrations_program; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_registrations_program ON public.epr_registrations USING btree (program_id);


--
-- Name: idx_epr_registrations_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_registrations_status ON public.epr_registrations USING btree (registration_status);


--
-- Name: idx_epr_reports_period; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_reports_period ON public.epr_reports USING btree (report_year, report_period);


--
-- Name: idx_epr_reports_registration; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_reports_registration ON public.epr_reports USING btree (registration_id);


--
-- Name: idx_epr_reports_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_reports_type ON public.epr_reports USING btree (report_type);


--
-- Name: idx_epr_targets_registration; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_targets_registration ON public.epr_targets USING btree (registration_id);


--
-- Name: idx_epr_targets_year; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_epr_targets_year ON public.epr_targets USING btree (target_year);


--
-- Name: idx_experts_deleted_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_experts_deleted_date ON public.experts USING btree (deleted_date);


--
-- Name: idx_experts_expertise; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_experts_expertise ON public.experts USING gin (expertise_areas);


--
-- Name: idx_experts_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_experts_status ON public.experts USING btree (availability_status);


--
-- Name: idx_gri_indicators_standard; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_gri_indicators_standard ON public.gri_indicators USING btree (standard_id);


--
-- Name: idx_gri_report_data_indicator; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_gri_report_data_indicator ON public.gri_report_data USING btree (indicator_id);


--
-- Name: idx_gri_report_data_report; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_gri_report_data_report ON public.gri_report_data USING btree (report_id);


--
-- Name: idx_gri_reports_organization; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_gri_reports_organization ON public.gri_reports USING btree (organization_id);


--
-- Name: idx_gri_reports_year; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_gri_reports_year ON public.gri_reports USING btree (reporting_year);


--
-- Name: idx_km_chunks_file; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_km_chunks_file ON public.km_chunks USING btree (file_id);


--
-- Name: idx_km_files_access_level; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_km_files_access_level ON public.km_files USING btree (access_level);


--
-- Name: idx_km_files_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_km_files_category ON public.km_files USING btree (category);


--
-- Name: idx_km_files_latest; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_km_files_latest ON public.km_files USING btree (is_latest_version);


--
-- Name: idx_km_files_organization; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_km_files_organization ON public.km_files USING btree (organization_id);


--
-- Name: idx_location_countries_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_location_countries_active ON public.location_countries USING btree (is_active);


--
-- Name: idx_location_countries_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_location_countries_code ON public.location_countries USING btree (code);


--
-- Name: idx_location_districts_province; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_location_districts_province ON public.location_districts USING btree (province_id);


--
-- Name: idx_location_provinces_country; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_location_provinces_country ON public.location_provinces USING btree (country_id);


--
-- Name: idx_location_provinces_region; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_location_provinces_region ON public.location_provinces USING btree (region_id);


--
-- Name: idx_location_regions_country; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_location_regions_country ON public.location_regions USING btree (country_id);


--
-- Name: idx_location_subdistricts_district; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_location_subdistricts_district ON public.location_subdistricts USING btree (district_id);


--
-- Name: idx_main_materials_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_main_materials_code ON public.main_materials USING btree (code);


--
-- Name: idx_main_materials_is_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_main_materials_is_active ON public.main_materials USING btree (is_active);


--
-- Name: idx_main_materials_tag_groups; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_main_materials_tag_groups ON public.main_materials USING gin (material_tag_groups);


--
-- Name: idx_material_categories_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_material_categories_code ON public.material_categories USING btree (code);


--
-- Name: idx_material_categories_is_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_material_categories_is_active ON public.material_categories USING btree (is_active);


--
-- Name: idx_material_tag_groups_is_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_material_tag_groups_is_active ON public.material_tag_groups USING btree (is_active);


--
-- Name: idx_material_tag_groups_is_global; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_material_tag_groups_is_global ON public.material_tag_groups USING btree (is_global);


--
-- Name: idx_material_tag_groups_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_material_tag_groups_name ON public.material_tag_groups USING btree (name);


--
-- Name: idx_material_tag_groups_organization; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_material_tag_groups_organization ON public.material_tag_groups USING btree (organization_id);


--
-- Name: idx_material_tag_groups_tags; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_material_tag_groups_tags ON public.material_tag_groups USING gin (tags);


--
-- Name: idx_material_tags_is_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_material_tags_is_active ON public.material_tags USING btree (is_active);


--
-- Name: idx_material_tags_is_global; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_material_tags_is_global ON public.material_tags USING btree (is_global);


--
-- Name: idx_material_tags_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_material_tags_name ON public.material_tags USING btree (name);


--
-- Name: idx_material_tags_organization; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_material_tags_organization ON public.material_tags USING btree (organization_id);


--
-- Name: idx_materials_category_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_materials_category_id ON public.materials USING btree (category_id);


--
-- Name: idx_materials_fixed_tags; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_materials_fixed_tags ON public.materials USING gin (fixed_tags);


--
-- Name: idx_materials_is_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_materials_is_active ON public.materials USING btree (is_active);


--
-- Name: idx_materials_main_material_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_materials_main_material_id ON public.materials USING btree (main_material_id);


--
-- Name: idx_materials_migration_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX idx_materials_migration_id ON public.materials USING btree (migration_id) WHERE (migration_id IS NOT NULL);


--
-- Name: idx_materials_tags; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_materials_tags ON public.materials USING gin (tags);


--
-- Name: idx_meeting_participants_meeting; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_meeting_participants_meeting ON public.meeting_participants USING btree (meeting_id);


--
-- Name: idx_meeting_participants_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_meeting_participants_user ON public.meeting_participants USING btree (user_id);


--
-- Name: idx_meetings_expert; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_meetings_expert ON public.meetings USING btree (expert_id);


--
-- Name: idx_meetings_organizer; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_meetings_organizer ON public.meetings USING btree (organizer_id);


--
-- Name: idx_meetings_scheduled_start; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_meetings_scheduled_start ON public.meetings USING btree (scheduled_start);


--
-- Name: idx_meetings_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_meetings_status ON public.meetings USING btree (status);


--
-- Name: idx_nationalities_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_nationalities_code ON public.nationalities USING btree (code);


--
-- Name: idx_organization_permissions_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_organization_permissions_category ON public.organization_permissions USING btree (category);


--
-- Name: idx_organization_permissions_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_organization_permissions_code ON public.organization_permissions USING btree (code);


--
-- Name: idx_organization_roles_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_organization_roles_name ON public.organization_roles USING btree (organization_id, name);


--
-- Name: idx_organization_roles_org_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX idx_organization_roles_org_key ON public.organization_roles USING btree (organization_id, key);


--
-- Name: idx_organization_roles_organization; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_organization_roles_organization ON public.organization_roles USING btree (organization_id);


--
-- Name: idx_organization_roles_organization_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_organization_roles_organization_id ON public.organization_roles USING btree (organization_id);


--
-- Name: idx_organization_setup_created_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_organization_setup_created_date ON public.organization_setup USING btree (created_date);


--
-- Name: idx_organization_setup_is_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_organization_setup_is_active ON public.organization_setup USING btree (is_active);


--
-- Name: idx_organization_setup_organization_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_organization_setup_organization_id ON public.organization_setup USING btree (organization_id);


--
-- Name: idx_organization_setup_version; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_organization_setup_version ON public.organization_setup USING btree (organization_id, version);


--
-- Name: idx_organizations_deleted_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_organizations_deleted_date ON public.organizations USING btree (deleted_date);


--
-- Name: idx_organizations_info; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_organizations_info ON public.organizations USING btree (organization_info_id);


--
-- Name: idx_organizations_owner; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_organizations_owner ON public.organizations USING btree (owner_id);


--
-- Name: idx_organizations_subscription; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_organizations_subscription ON public.organizations USING btree (subscription_id);


--
-- Name: idx_organizations_system_role_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_organizations_system_role_id ON public.organizations USING btree (system_role_id);


--
-- Name: idx_platform_logs_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_platform_logs_category ON public.platform_logs USING btree (category);


--
-- Name: idx_platform_logs_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_platform_logs_created ON public.platform_logs USING btree (created_date);


--
-- Name: idx_platform_logs_level; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_platform_logs_level ON public.platform_logs USING btree (log_level);


--
-- Name: idx_platform_logs_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_platform_logs_user ON public.platform_logs USING btree (user_id);


--
-- Name: idx_point_transactions_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_point_transactions_type ON public.point_transactions USING btree (transaction_type);


--
-- Name: idx_point_transactions_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_point_transactions_user ON public.point_transactions USING btree (user_id);


--
-- Name: idx_reward_redemptions_reward; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_reward_redemptions_reward ON public.reward_redemptions USING btree (reward_id);


--
-- Name: idx_reward_redemptions_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_reward_redemptions_status ON public.reward_redemptions USING btree (status);


--
-- Name: idx_reward_redemptions_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_reward_redemptions_user ON public.reward_redemptions USING btree (user_id);


--
-- Name: idx_rewards_catalog_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_rewards_catalog_active ON public.rewards_catalog USING btree (is_active);


--
-- Name: idx_rewards_catalog_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_rewards_catalog_category ON public.rewards_catalog USING btree (category);


--
-- Name: idx_rewards_catalog_points; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_rewards_catalog_points ON public.rewards_catalog USING btree (points_required);


--
-- Name: idx_schema_migrations_batch_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_schema_migrations_batch_id ON public.schema_migrations USING btree (batch_id);


--
-- Name: idx_schema_migrations_executed_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_schema_migrations_executed_at ON public.schema_migrations USING btree (executed_at);


--
-- Name: idx_schema_migrations_version; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_schema_migrations_version ON public.schema_migrations USING btree (version);


--
-- Name: idx_subscriptions_organization; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_subscriptions_organization ON public.subscriptions USING btree (organization_id);


--
-- Name: idx_subscriptions_plan; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_subscriptions_plan ON public.subscriptions USING btree (plan_id);


--
-- Name: idx_subscriptions_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_subscriptions_status ON public.subscriptions USING btree (status);


--
-- Name: idx_system_events_correlation; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_system_events_correlation ON public.system_events USING btree (correlation_id);


--
-- Name: idx_system_events_scheduled; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_system_events_scheduled ON public.system_events USING btree (scheduled_for);


--
-- Name: idx_system_events_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_system_events_status ON public.system_events USING btree (processing_status);


--
-- Name: idx_system_events_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_system_events_type ON public.system_events USING btree (event_type);


--
-- Name: idx_system_permissions_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_system_permissions_category ON public.system_permissions USING btree (category);


--
-- Name: idx_system_permissions_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_system_permissions_code ON public.system_permissions USING btree (code);


--
-- Name: idx_system_roles_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_system_roles_name ON public.system_roles USING btree (name);


--
-- Name: idx_transaction_items_deleted_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_items_deleted_date ON public.transaction_items USING btree (deleted_date);


--
-- Name: idx_transaction_items_material; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_items_material ON public.transaction_items USING btree (material_id);


--
-- Name: idx_transaction_items_transaction; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_items_transaction ON public.transaction_items USING btree (transaction_id);


--
-- Name: idx_transaction_payments_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_payments_date ON public.transaction_payments USING btree (payment_date);


--
-- Name: idx_transaction_payments_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_payments_status ON public.transaction_payments USING btree (payment_status);


--
-- Name: idx_transaction_payments_transaction; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_payments_transaction ON public.transaction_payments USING btree (transaction_id);


--
-- Name: idx_transaction_records_approved_by; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_approved_by ON public.transaction_records USING btree (approved_by_id);


--
-- Name: idx_transaction_records_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_category ON public.transaction_records USING btree (category_id);


--
-- Name: idx_transaction_records_created_by; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_created_by ON public.transaction_records USING btree (created_by_id);


--
-- Name: idx_transaction_records_created_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_created_date ON public.transaction_records USING btree (created_date);


--
-- Name: idx_transaction_records_created_transaction; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_created_transaction ON public.transaction_records USING btree (created_transaction_id);


--
-- Name: idx_transaction_records_currency; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_currency ON public.transaction_records USING btree (currency_id);


--
-- Name: idx_transaction_records_dest_coords; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_dest_coords ON public.transaction_records USING gin (destination_coordinates);


--
-- Name: idx_transaction_records_images; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_images ON public.transaction_records USING gin (images);


--
-- Name: idx_transaction_records_is_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_is_active ON public.transaction_records USING btree (is_active);


--
-- Name: idx_transaction_records_main_material; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_main_material ON public.transaction_records USING btree (main_material_id);


--
-- Name: idx_transaction_records_material; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_material ON public.transaction_records USING btree (material_id);


--
-- Name: idx_transaction_records_origin_coords; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_origin_coords ON public.transaction_records USING gin (origin_coordinates);


--
-- Name: idx_transaction_records_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_status ON public.transaction_records USING btree (status);


--
-- Name: idx_transaction_records_tags; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_tags ON public.transaction_records USING gin (tags);


--
-- Name: idx_transaction_records_traceability; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_traceability ON public.transaction_records USING gin (traceability);


--
-- Name: idx_transaction_records_transaction_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_records_transaction_type ON public.transaction_records USING btree (transaction_type);


--
-- Name: idx_transaction_status_history_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_status_history_date ON public.transaction_status_history USING btree (changed_at);


--
-- Name: idx_transaction_status_history_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_status_history_status ON public.transaction_status_history USING btree (status);


--
-- Name: idx_transaction_status_history_transaction; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transaction_status_history_transaction ON public.transaction_status_history USING btree (transaction_id);


--
-- Name: idx_transactions_amount; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_amount ON public.transactions USING btree (total_amount);


--
-- Name: idx_transactions_approved_by; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_approved_by ON public.transactions USING btree (approved_by_id);


--
-- Name: idx_transactions_arrival_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_arrival_date ON public.transactions USING btree (arrival_date);


--
-- Name: idx_transactions_created_by; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_created_by ON public.transactions USING btree (created_by_id);


--
-- Name: idx_transactions_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_date ON public.transactions USING btree (transaction_date);


--
-- Name: idx_transactions_deleted_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_deleted_date ON public.transactions USING btree (deleted_date);


--
-- Name: idx_transactions_dest_coords; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_dest_coords ON public.transactions USING gin (destination_coordinates);


--
-- Name: idx_transactions_destination; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_destination ON public.transactions USING btree (destination_id);


--
-- Name: idx_transactions_driver_info; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_driver_info ON public.transactions USING gin (driver_info);


--
-- Name: idx_transactions_hazardous_level; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_hazardous_level ON public.transactions USING btree (hazardous_level);


--
-- Name: idx_transactions_images; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_images ON public.transactions USING gin (images);


--
-- Name: idx_transactions_is_active; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_is_active ON public.transactions USING btree (is_active);


--
-- Name: idx_transactions_method; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_method ON public.transactions USING btree (transaction_method);


--
-- Name: idx_transactions_organization; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_organization ON public.transactions USING btree (organization_id);


--
-- Name: idx_transactions_origin; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_origin ON public.transactions USING btree (origin_id);


--
-- Name: idx_transactions_origin_coords; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_origin_coords ON public.transactions USING gin (origin_coordinates);


--
-- Name: idx_transactions_records; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_records ON public.transactions USING gin (transaction_records);


--
-- Name: idx_transactions_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_status ON public.transactions USING btree (status);


--
-- Name: idx_transactions_transaction_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_transaction_date ON public.transactions USING btree (transaction_date);


--
-- Name: idx_transactions_transaction_method; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_transaction_method ON public.transactions USING btree (transaction_method);


--
-- Name: idx_transactions_updated_by; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_updated_by ON public.transactions USING btree (updated_by_id);


--
-- Name: idx_transactions_vehicle_info; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_vehicle_info ON public.transactions USING gin (vehicle_info);


--
-- Name: idx_transactions_weight; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_transactions_weight ON public.transactions USING btree (weight_kg);


--
-- Name: idx_user_activities_user_location_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_activities_user_location_id ON public.user_activities USING btree (user_location_id);


--
-- Name: idx_user_analytics_created; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_analytics_created ON public.user_analytics USING btree (created_date);


--
-- Name: idx_user_analytics_event_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_analytics_event_type ON public.user_analytics USING btree (event_type);


--
-- Name: idx_user_analytics_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_analytics_user ON public.user_analytics USING btree (user_id);


--
-- Name: idx_user_bank_user_location_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_bank_user_location_id ON public.user_bank USING btree (user_location_id);


--
-- Name: idx_user_business_roles_deleted_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_business_roles_deleted_date ON public.user_business_roles USING btree (deleted_date);


--
-- Name: idx_user_devices_device_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_devices_device_id ON public.user_devices USING btree (device_id);


--
-- Name: idx_user_devices_user_location_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_devices_user_location_id ON public.user_devices USING btree (user_location_id);


--
-- Name: idx_user_invitations_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_invitations_email ON public.user_invitations USING btree (email);


--
-- Name: idx_user_invitations_organization_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_invitations_organization_id ON public.user_invitations USING btree (organization_id);


--
-- Name: idx_user_invitations_token; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_invitations_token ON public.user_invitations USING btree (invitation_token);


--
-- Name: idx_user_locations_active_users; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_locations_active_users ON public.user_locations USING btree (is_user, is_active);


--
-- Name: idx_user_locations_country; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_locations_country ON public.user_locations USING btree (country_id);


--
-- Name: idx_user_locations_deleted_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_locations_deleted_date ON public.user_locations USING btree (deleted_date);


--
-- Name: idx_user_locations_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_locations_email ON public.user_locations USING btree (email);


--
-- Name: idx_user_locations_hub_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_locations_hub_type ON public.user_locations USING btree (hub_type) WHERE (hub_type IS NOT NULL);


--
-- Name: INDEX idx_user_locations_hub_type; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON INDEX public.idx_user_locations_hub_type IS 'Index for efficient queries on hub_type field';


--
-- Name: idx_user_locations_members; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_locations_members ON public.user_locations USING gin (members jsonb_path_ops) WHERE (members IS NOT NULL);


--
-- Name: INDEX idx_user_locations_members; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON INDEX public.idx_user_locations_members IS 'GIN index for efficient JSON queries on members field';


--
-- Name: idx_user_locations_organization; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_locations_organization ON public.user_locations USING btree (organization_id);


--
-- Name: idx_user_locations_organization_role; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_locations_organization_role ON public.user_locations USING btree (organization_role_id);


--
-- Name: idx_user_locations_parent_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_locations_parent_user ON public.user_locations USING btree (parent_user_id);


--
-- Name: idx_user_locations_province; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_locations_province ON public.user_locations USING btree (province_id);


--
-- Name: idx_user_locations_role; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_locations_role ON public.user_locations USING btree (role_id);


--
-- Name: idx_user_locations_username; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_locations_username ON public.user_locations USING btree (username);


--
-- Name: idx_user_organization_role_mapping_org; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_organization_role_mapping_org ON public.user_organization_role_mapping USING btree (organization_id);


--
-- Name: idx_user_organization_role_mapping_role; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_organization_role_mapping_role ON public.user_organization_role_mapping USING btree (role_id);


--
-- Name: idx_user_organization_role_mapping_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_organization_role_mapping_user ON public.user_organization_role_mapping USING btree (user_location_id);


--
-- Name: idx_user_organization_roles_org; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_organization_roles_org ON public.user_organization_roles USING btree (organization_id);


--
-- Name: idx_user_organization_roles_role; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_organization_roles_role ON public.user_organization_roles USING btree (role_id);


--
-- Name: idx_user_organization_roles_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_organization_roles_user ON public.user_organization_roles USING btree (user_location_id);


--
-- Name: idx_user_point_balances_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_point_balances_user ON public.user_point_balances USING btree (user_id);


--
-- Name: idx_user_preferences_user_location_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_preferences_user_location_id ON public.user_preferences USING btree (user_location_id);


--
-- Name: idx_user_roles_deleted_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_roles_deleted_date ON public.user_roles USING btree (deleted_date);


--
-- Name: idx_user_roles_organization_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_roles_organization_id ON public.user_roles USING btree (organization_id);


--
-- Name: idx_user_sessions_expires; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_sessions_expires ON public.user_sessions USING btree (expires_at);


--
-- Name: idx_user_sessions_token; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_sessions_token ON public.user_sessions USING btree (session_token);


--
-- Name: idx_user_sessions_user; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_sessions_user ON public.user_sessions USING btree (user_id);


--
-- Name: idx_user_subscriptions_user_location_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_subscriptions_user_location_id ON public.user_subscriptions USING btree (user_location_id);


--
-- Name: idx_waste_collections_collector; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_waste_collections_collector ON public.waste_collections USING btree (collector_id);


--
-- Name: idx_waste_collections_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_waste_collections_date ON public.waste_collections USING btree (collection_date);


--
-- Name: idx_waste_collections_transaction; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_waste_collections_transaction ON public.waste_collections USING btree (transaction_id);


--
-- Name: idx_waste_processing_date; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_waste_processing_date ON public.waste_processing USING btree (processing_date);


--
-- Name: idx_waste_processing_facility; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_waste_processing_facility ON public.waste_processing USING btree (processing_facility_id);


--
-- Name: idx_waste_processing_transaction; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_waste_processing_transaction ON public.waste_processing USING btree (transaction_id);


--
-- Name: uq_organization_setup_active_version; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX uq_organization_setup_active_version ON public.organization_setup USING btree (organization_id) WHERE (is_active = true);


--
-- Name: INDEX uq_organization_setup_active_version; Type: COMMENT; Schema: public; Owner: postgres
--

COMMENT ON INDEX public.uq_organization_setup_active_version IS 'Ensures only one active version per organization while allowing multiple inactive versions';


--
-- Name: organization_setup trigger_ensure_single_active_organization_setup; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trigger_ensure_single_active_organization_setup BEFORE INSERT OR UPDATE ON public.organization_setup FOR EACH ROW WHEN ((new.is_active = true)) EXECUTE FUNCTION public.ensure_single_active_organization_setup();


--
-- Name: organization_setup trigger_organization_setup_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trigger_organization_setup_updated_date BEFORE UPDATE ON public.organization_setup FOR EACH ROW EXECUTE FUNCTION public.update_organization_setup_updated_date();


--
-- Name: system_roles trigger_update_system_roles_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER trigger_update_system_roles_updated_date BEFORE UPDATE ON public.system_roles FOR EACH ROW EXECUTE FUNCTION public.update_system_roles_updated_date();


--
-- Name: banks update_banks_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_banks_updated_date BEFORE UPDATE ON public.banks FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: base_materials update_base_materials_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_base_materials_updated_date BEFORE UPDATE ON public.base_materials FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: chats update_chats_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_chats_updated_date BEFORE UPDATE ON public.chats FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: currencies update_currencies_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_currencies_updated_date BEFORE UPDATE ON public.currencies FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: epr_audits update_epr_audits_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_epr_audits_updated_date BEFORE UPDATE ON public.epr_audits FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: epr_data_submissions update_epr_data_submissions_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_epr_data_submissions_updated_date BEFORE UPDATE ON public.epr_data_submissions FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: epr_notifications update_epr_notifications_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_epr_notifications_updated_date BEFORE UPDATE ON public.epr_notifications FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: epr_payments update_epr_payments_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_epr_payments_updated_date BEFORE UPDATE ON public.epr_payments FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: epr_programs update_epr_programs_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_epr_programs_updated_date BEFORE UPDATE ON public.epr_programs FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: epr_registrations update_epr_registrations_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_epr_registrations_updated_date BEFORE UPDATE ON public.epr_registrations FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: epr_reports update_epr_reports_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_epr_reports_updated_date BEFORE UPDATE ON public.epr_reports FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: epr_targets update_epr_targets_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_epr_targets_updated_date BEFORE UPDATE ON public.epr_targets FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: experts update_experts_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_experts_updated_date BEFORE UPDATE ON public.experts FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: gri_indicators update_gri_indicators_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_gri_indicators_updated_date BEFORE UPDATE ON public.gri_indicators FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: gri_report_data update_gri_report_data_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_gri_report_data_updated_date BEFORE UPDATE ON public.gri_report_data FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: gri_reports update_gri_reports_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_gri_reports_updated_date BEFORE UPDATE ON public.gri_reports FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: gri_standards update_gri_standards_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_gri_standards_updated_date BEFORE UPDATE ON public.gri_standards FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: km_files update_km_files_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_km_files_updated_date BEFORE UPDATE ON public.km_files FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: location_countries update_location_countries_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_location_countries_updated_date BEFORE UPDATE ON public.location_countries FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: location_districts update_location_districts_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_location_districts_updated_date BEFORE UPDATE ON public.location_districts FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: location_provinces update_location_provinces_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_location_provinces_updated_date BEFORE UPDATE ON public.location_provinces FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: location_regions update_location_regions_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_location_regions_updated_date BEFORE UPDATE ON public.location_regions FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: location_subdistricts update_location_subdistricts_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_location_subdistricts_updated_date BEFORE UPDATE ON public.location_subdistricts FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: main_materials update_main_materials_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_main_materials_updated_date BEFORE UPDATE ON public.main_materials FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: material_categories update_material_categories_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_material_categories_updated_date BEFORE UPDATE ON public.material_categories FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: material_tag_groups update_material_tag_groups_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_material_tag_groups_updated_date BEFORE UPDATE ON public.material_tag_groups FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: material_tags update_material_tags_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_material_tags_updated_date BEFORE UPDATE ON public.material_tags FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: materials update_materials_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_materials_updated_date BEFORE UPDATE ON public.materials FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: meeting_participants update_meeting_participants_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_meeting_participants_updated_date BEFORE UPDATE ON public.meeting_participants FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: meetings update_meetings_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_meetings_updated_date BEFORE UPDATE ON public.meetings FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: nationalities update_nationalities_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_nationalities_updated_date BEFORE UPDATE ON public.nationalities FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: organization_info update_organization_info_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_organization_info_updated_date BEFORE UPDATE ON public.organization_info FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: organization_permissions update_organization_permissions_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_organization_permissions_updated_date BEFORE UPDATE ON public.organization_permissions FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: organization_roles update_organization_roles_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_organization_roles_updated_date BEFORE UPDATE ON public.organization_roles FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: organizations update_organizations_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_organizations_updated_date BEFORE UPDATE ON public.organizations FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: reward_redemptions update_reward_redemptions_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_reward_redemptions_updated_date BEFORE UPDATE ON public.reward_redemptions FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: rewards_catalog update_rewards_catalog_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_rewards_catalog_updated_date BEFORE UPDATE ON public.rewards_catalog FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: subscription_plans update_subscription_plans_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_subscription_plans_updated_date BEFORE UPDATE ON public.subscription_plans FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: subscriptions update_subscriptions_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_subscriptions_updated_date BEFORE UPDATE ON public.subscriptions FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: system_events update_system_events_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_system_events_updated_date BEFORE UPDATE ON public.system_events FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: system_permissions update_system_permissions_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_system_permissions_updated_date BEFORE UPDATE ON public.system_permissions FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: transaction_documents update_transaction_documents_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_transaction_documents_updated_date BEFORE UPDATE ON public.transaction_documents FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: transaction_items update_transaction_items_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_transaction_items_updated_date BEFORE UPDATE ON public.transaction_items FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: transaction_payments update_transaction_payments_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_transaction_payments_updated_date BEFORE UPDATE ON public.transaction_payments FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: transaction_records update_transaction_records_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_transaction_records_updated_date BEFORE UPDATE ON public.transaction_records FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: transactions update_transactions_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_transactions_updated_date BEFORE UPDATE ON public.transactions FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: user_business_roles update_user_business_roles_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_user_business_roles_updated_date BEFORE UPDATE ON public.user_business_roles FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: user_input_channels update_user_input_channels_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_user_input_channels_updated_date BEFORE UPDATE ON public.user_input_channels FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: user_locations update_user_locations_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_user_locations_updated_date BEFORE UPDATE ON public.user_locations FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: user_point_balances update_user_point_balances_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_user_point_balances_updated_date BEFORE UPDATE ON public.user_point_balances FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: user_roles update_user_roles_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_user_roles_updated_date BEFORE UPDATE ON public.user_roles FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: user_sessions update_user_sessions_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_user_sessions_updated_date BEFORE UPDATE ON public.user_sessions FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: waste_collections update_waste_collections_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_waste_collections_updated_date BEFORE UPDATE ON public.waste_collections FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: waste_processing update_waste_processing_updated_date; Type: TRIGGER; Schema: public; Owner: postgres
--

CREATE TRIGGER update_waste_processing_updated_date BEFORE UPDATE ON public.waste_processing FOR EACH ROW EXECUTE FUNCTION public.update_updated_date_column();


--
-- Name: audit_logs audit_logs_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: audit_logs audit_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_locations(id);


--
-- Name: banks banks_country_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.banks
    ADD CONSTRAINT banks_country_id_fkey FOREIGN KEY (country_id) REFERENCES public.location_countries(id);


--
-- Name: base_materials base_materials_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.base_materials
    ADD CONSTRAINT base_materials_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.material_categories(id) ON DELETE SET NULL;


--
-- Name: base_materials base_materials_main_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.base_materials
    ADD CONSTRAINT base_materials_main_material_id_fkey FOREIGN KEY (main_material_id) REFERENCES public.main_materials(id) ON DELETE SET NULL;


--
-- Name: chat_history chat_history_chat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chat_history
    ADD CONSTRAINT chat_history_chat_id_fkey FOREIGN KEY (chat_id) REFERENCES public.chats(id) ON DELETE CASCADE;


--
-- Name: chat_history chat_history_sender_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chat_history
    ADD CONSTRAINT chat_history_sender_id_fkey FOREIGN KEY (sender_id) REFERENCES public.user_locations(id);


--
-- Name: chats chats_expert_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chats
    ADD CONSTRAINT chats_expert_id_fkey FOREIGN KEY (expert_id) REFERENCES public.experts(id);


--
-- Name: chats chats_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.chats
    ADD CONSTRAINT chats_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: epr_audits epr_audits_conducted_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_audits
    ADD CONSTRAINT epr_audits_conducted_by_id_fkey FOREIGN KEY (conducted_by_id) REFERENCES public.user_locations(id);


--
-- Name: epr_audits epr_audits_registration_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_audits
    ADD CONSTRAINT epr_audits_registration_id_fkey FOREIGN KEY (registration_id) REFERENCES public.epr_registrations(id) ON DELETE CASCADE;


--
-- Name: epr_data_submissions epr_data_submissions_registration_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_data_submissions
    ADD CONSTRAINT epr_data_submissions_registration_id_fkey FOREIGN KEY (registration_id) REFERENCES public.epr_registrations(id) ON DELETE CASCADE;


--
-- Name: epr_data_submissions epr_data_submissions_submitted_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_data_submissions
    ADD CONSTRAINT epr_data_submissions_submitted_by_id_fkey FOREIGN KEY (submitted_by_id) REFERENCES public.user_locations(id);


--
-- Name: epr_notifications epr_notifications_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_notifications
    ADD CONSTRAINT epr_notifications_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: epr_notifications epr_notifications_registration_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_notifications
    ADD CONSTRAINT epr_notifications_registration_id_fkey FOREIGN KEY (registration_id) REFERENCES public.epr_registrations(id) ON DELETE CASCADE;


--
-- Name: epr_notifications epr_notifications_related_payment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_notifications
    ADD CONSTRAINT epr_notifications_related_payment_id_fkey FOREIGN KEY (related_payment_id) REFERENCES public.epr_payments(id);


--
-- Name: epr_notifications epr_notifications_related_submission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_notifications
    ADD CONSTRAINT epr_notifications_related_submission_id_fkey FOREIGN KEY (related_submission_id) REFERENCES public.epr_data_submissions(id);


--
-- Name: epr_payments epr_payments_currency_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_payments
    ADD CONSTRAINT epr_payments_currency_id_fkey FOREIGN KEY (currency_id) REFERENCES public.currencies(id);


--
-- Name: epr_payments epr_payments_registration_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_payments
    ADD CONSTRAINT epr_payments_registration_id_fkey FOREIGN KEY (registration_id) REFERENCES public.epr_registrations(id) ON DELETE CASCADE;


--
-- Name: epr_programs epr_programs_country_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_programs
    ADD CONSTRAINT epr_programs_country_id_fkey FOREIGN KEY (country_id) REFERENCES public.location_countries(id);


--
-- Name: epr_registrations epr_registrations_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_registrations
    ADD CONSTRAINT epr_registrations_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: epr_registrations epr_registrations_program_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_registrations
    ADD CONSTRAINT epr_registrations_program_id_fkey FOREIGN KEY (program_id) REFERENCES public.epr_programs(id);


--
-- Name: epr_reports epr_reports_generated_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_reports
    ADD CONSTRAINT epr_reports_generated_by_id_fkey FOREIGN KEY (generated_by_id) REFERENCES public.user_locations(id);


--
-- Name: epr_reports epr_reports_registration_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_reports
    ADD CONSTRAINT epr_reports_registration_id_fkey FOREIGN KEY (registration_id) REFERENCES public.epr_registrations(id) ON DELETE CASCADE;


--
-- Name: epr_targets epr_targets_registration_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.epr_targets
    ADD CONSTRAINT epr_targets_registration_id_fkey FOREIGN KEY (registration_id) REFERENCES public.epr_registrations(id) ON DELETE CASCADE;


--
-- Name: experts experts_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.experts
    ADD CONSTRAINT experts_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.user_locations(id);


--
-- Name: experts experts_currency_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.experts
    ADD CONSTRAINT experts_currency_id_fkey FOREIGN KEY (currency_id) REFERENCES public.currencies(id);


--
-- Name: organization_setup fk_organization_setup_organization_id; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_setup
    ADD CONSTRAINT fk_organization_setup_organization_id FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: gri_indicators gri_indicators_standard_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_indicators
    ADD CONSTRAINT gri_indicators_standard_id_fkey FOREIGN KEY (standard_id) REFERENCES public.gri_standards(id);


--
-- Name: gri_report_data gri_report_data_entered_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_report_data
    ADD CONSTRAINT gri_report_data_entered_by_id_fkey FOREIGN KEY (entered_by_id) REFERENCES public.user_locations(id);


--
-- Name: gri_report_data gri_report_data_indicator_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_report_data
    ADD CONSTRAINT gri_report_data_indicator_id_fkey FOREIGN KEY (indicator_id) REFERENCES public.gri_indicators(id);


--
-- Name: gri_report_data gri_report_data_report_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_report_data
    ADD CONSTRAINT gri_report_data_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.gri_reports(id) ON DELETE CASCADE;


--
-- Name: gri_report_data gri_report_data_verified_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_report_data
    ADD CONSTRAINT gri_report_data_verified_by_id_fkey FOREIGN KEY (verified_by_id) REFERENCES public.user_locations(id);


--
-- Name: gri_reports gri_reports_approved_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_reports
    ADD CONSTRAINT gri_reports_approved_by_id_fkey FOREIGN KEY (approved_by_id) REFERENCES public.user_locations(id);


--
-- Name: gri_reports gri_reports_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_reports
    ADD CONSTRAINT gri_reports_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: gri_reports gri_reports_prepared_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.gri_reports
    ADD CONSTRAINT gri_reports_prepared_by_id_fkey FOREIGN KEY (prepared_by_id) REFERENCES public.user_locations(id);


--
-- Name: km_chunks km_chunks_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.km_chunks
    ADD CONSTRAINT km_chunks_file_id_fkey FOREIGN KEY (file_id) REFERENCES public.km_files(id) ON DELETE CASCADE;


--
-- Name: km_files km_files_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.km_files
    ADD CONSTRAINT km_files_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: km_files km_files_parent_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.km_files
    ADD CONSTRAINT km_files_parent_file_id_fkey FOREIGN KEY (parent_file_id) REFERENCES public.km_files(id);


--
-- Name: km_files km_files_uploaded_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.km_files
    ADD CONSTRAINT km_files_uploaded_by_id_fkey FOREIGN KEY (uploaded_by_id) REFERENCES public.user_locations(id);


--
-- Name: location_districts location_districts_province_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_districts
    ADD CONSTRAINT location_districts_province_id_fkey FOREIGN KEY (province_id) REFERENCES public.location_provinces(id);


--
-- Name: location_provinces location_provinces_country_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_provinces
    ADD CONSTRAINT location_provinces_country_id_fkey FOREIGN KEY (country_id) REFERENCES public.location_countries(id);


--
-- Name: location_provinces location_provinces_region_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_provinces
    ADD CONSTRAINT location_provinces_region_id_fkey FOREIGN KEY (region_id) REFERENCES public.location_regions(id);


--
-- Name: location_regions location_regions_country_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_regions
    ADD CONSTRAINT location_regions_country_id_fkey FOREIGN KEY (country_id) REFERENCES public.location_countries(id);


--
-- Name: location_subdistricts location_subdistricts_district_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.location_subdistricts
    ADD CONSTRAINT location_subdistricts_district_id_fkey FOREIGN KEY (district_id) REFERENCES public.location_districts(id);


--
-- Name: material_tag_groups material_tag_groups_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.material_tag_groups
    ADD CONSTRAINT material_tag_groups_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: material_tags material_tags_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.material_tags
    ADD CONSTRAINT material_tags_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: materials materials_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.materials
    ADD CONSTRAINT materials_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.material_categories(id);


--
-- Name: materials materials_main_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.materials
    ADD CONSTRAINT materials_main_material_id_fkey FOREIGN KEY (main_material_id) REFERENCES public.main_materials(id);


--
-- Name: meeting_participants meeting_participants_meeting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.meeting_participants
    ADD CONSTRAINT meeting_participants_meeting_id_fkey FOREIGN KEY (meeting_id) REFERENCES public.meetings(id) ON DELETE CASCADE;


--
-- Name: meeting_participants meeting_participants_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.meeting_participants
    ADD CONSTRAINT meeting_participants_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: meetings meetings_currency_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.meetings
    ADD CONSTRAINT meetings_currency_id_fkey FOREIGN KEY (currency_id) REFERENCES public.currencies(id);


--
-- Name: meetings meetings_expert_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.meetings
    ADD CONSTRAINT meetings_expert_id_fkey FOREIGN KEY (expert_id) REFERENCES public.experts(id);


--
-- Name: meetings meetings_organizer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.meetings
    ADD CONSTRAINT meetings_organizer_id_fkey FOREIGN KEY (organizer_id) REFERENCES public.user_locations(id);


--
-- Name: nationalities nationalities_country_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.nationalities
    ADD CONSTRAINT nationalities_country_id_fkey FOREIGN KEY (country_id) REFERENCES public.location_countries(id);


--
-- Name: organization_info organization_info_country_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_info
    ADD CONSTRAINT organization_info_country_id_fkey FOREIGN KEY (country_id) REFERENCES public.location_countries(id);


--
-- Name: organization_info organization_info_district_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_info
    ADD CONSTRAINT organization_info_district_id_fkey FOREIGN KEY (district_id) REFERENCES public.location_districts(id);


--
-- Name: organization_info organization_info_province_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_info
    ADD CONSTRAINT organization_info_province_id_fkey FOREIGN KEY (province_id) REFERENCES public.location_provinces(id);


--
-- Name: organization_info organization_info_subdistrict_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_info
    ADD CONSTRAINT organization_info_subdistrict_id_fkey FOREIGN KEY (subdistrict_id) REFERENCES public.location_subdistricts(id);


--
-- Name: organization_role_permissions organization_role_permissions_permission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_role_permissions
    ADD CONSTRAINT organization_role_permissions_permission_id_fkey FOREIGN KEY (permission_id) REFERENCES public.organization_permissions(id) ON DELETE CASCADE;


--
-- Name: organization_role_permissions organization_role_permissions_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_role_permissions
    ADD CONSTRAINT organization_role_permissions_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.organization_roles(id) ON DELETE CASCADE;


--
-- Name: organization_roles organization_roles_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organization_roles
    ADD CONSTRAINT organization_roles_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: organizations organizations_organization_info_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_organization_info_id_fkey FOREIGN KEY (organization_info_id) REFERENCES public.organization_info(id);


--
-- Name: organizations organizations_system_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_system_role_id_fkey FOREIGN KEY (system_role_id) REFERENCES public.system_roles(id);


--
-- Name: phone_number_country_codes phone_number_country_codes_country_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.phone_number_country_codes
    ADD CONSTRAINT phone_number_country_codes_country_id_fkey FOREIGN KEY (country_id) REFERENCES public.location_countries(id);


--
-- Name: platform_logs platform_logs_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.platform_logs
    ADD CONSTRAINT platform_logs_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: platform_logs platform_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.platform_logs
    ADD CONSTRAINT platform_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_locations(id);


--
-- Name: point_transactions point_transactions_processed_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.point_transactions
    ADD CONSTRAINT point_transactions_processed_by_id_fkey FOREIGN KEY (processed_by_id) REFERENCES public.user_locations(id);


--
-- Name: point_transactions point_transactions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.point_transactions
    ADD CONSTRAINT point_transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: reward_redemptions reward_redemptions_processed_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reward_redemptions
    ADD CONSTRAINT reward_redemptions_processed_by_id_fkey FOREIGN KEY (processed_by_id) REFERENCES public.user_locations(id);


--
-- Name: reward_redemptions reward_redemptions_reward_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reward_redemptions
    ADD CONSTRAINT reward_redemptions_reward_id_fkey FOREIGN KEY (reward_id) REFERENCES public.rewards_catalog(id);


--
-- Name: reward_redemptions reward_redemptions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.reward_redemptions
    ADD CONSTRAINT reward_redemptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: rewards_catalog rewards_catalog_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rewards_catalog
    ADD CONSTRAINT rewards_catalog_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.user_locations(id);


--
-- Name: rewards_catalog rewards_catalog_currency_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rewards_catalog
    ADD CONSTRAINT rewards_catalog_currency_id_fkey FOREIGN KEY (currency_id) REFERENCES public.currencies(id);


--
-- Name: rewards_catalog rewards_catalog_provider_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rewards_catalog
    ADD CONSTRAINT rewards_catalog_provider_organization_id_fkey FOREIGN KEY (provider_organization_id) REFERENCES public.organizations(id);


--
-- Name: subscription_permissions subscription_permissions_permission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscription_permissions
    ADD CONSTRAINT subscription_permissions_permission_id_fkey FOREIGN KEY (permission_id) REFERENCES public.system_permissions(id) ON DELETE CASCADE;


--
-- Name: subscription_permissions subscription_permissions_subscription_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscription_permissions
    ADD CONSTRAINT subscription_permissions_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES public.subscriptions(id) ON DELETE CASCADE;


--
-- Name: subscriptions subscriptions_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: subscriptions subscriptions_plan_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_plan_id_fkey FOREIGN KEY (plan_id) REFERENCES public.subscription_plans(id);


--
-- Name: transaction_analytics transaction_analytics_transaction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_analytics
    ADD CONSTRAINT transaction_analytics_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id) ON DELETE CASCADE;


--
-- Name: transaction_documents transaction_documents_transaction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_documents
    ADD CONSTRAINT transaction_documents_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id) ON DELETE CASCADE;


--
-- Name: transaction_documents transaction_documents_uploaded_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_documents
    ADD CONSTRAINT transaction_documents_uploaded_by_id_fkey FOREIGN KEY (uploaded_by_id) REFERENCES public.user_locations(id);


--
-- Name: transaction_documents transaction_documents_verified_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_documents
    ADD CONSTRAINT transaction_documents_verified_by_id_fkey FOREIGN KEY (verified_by_id) REFERENCES public.user_locations(id);


--
-- Name: transaction_items transaction_items_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_items
    ADD CONSTRAINT transaction_items_material_id_fkey FOREIGN KEY (material_id) REFERENCES public.materials(id);


--
-- Name: transaction_items transaction_items_transaction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_items
    ADD CONSTRAINT transaction_items_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id) ON DELETE CASCADE;


--
-- Name: transaction_payments transaction_payments_currency_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_payments
    ADD CONSTRAINT transaction_payments_currency_id_fkey FOREIGN KEY (currency_id) REFERENCES public.currencies(id);


--
-- Name: transaction_payments transaction_payments_payee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_payments
    ADD CONSTRAINT transaction_payments_payee_id_fkey FOREIGN KEY (payee_id) REFERENCES public.user_locations(id);


--
-- Name: transaction_payments transaction_payments_payer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_payments
    ADD CONSTRAINT transaction_payments_payer_id_fkey FOREIGN KEY (payer_id) REFERENCES public.user_locations(id);


--
-- Name: transaction_payments transaction_payments_transaction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_payments
    ADD CONSTRAINT transaction_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id) ON DELETE CASCADE;


--
-- Name: transaction_records transaction_records_approved_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_records
    ADD CONSTRAINT transaction_records_approved_by_id_fkey FOREIGN KEY (approved_by_id) REFERENCES public.user_locations(id) ON DELETE SET NULL;


--
-- Name: transaction_records transaction_records_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_records
    ADD CONSTRAINT transaction_records_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.material_categories(id) ON DELETE CASCADE;


--
-- Name: transaction_records transaction_records_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_records
    ADD CONSTRAINT transaction_records_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: transaction_records transaction_records_created_transaction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_records
    ADD CONSTRAINT transaction_records_created_transaction_id_fkey FOREIGN KEY (created_transaction_id) REFERENCES public.transactions(id) ON DELETE CASCADE;


--
-- Name: transaction_records transaction_records_currency_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_records
    ADD CONSTRAINT transaction_records_currency_id_fkey FOREIGN KEY (currency_id) REFERENCES public.currencies(id) ON DELETE SET NULL;


--
-- Name: transaction_records transaction_records_main_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_records
    ADD CONSTRAINT transaction_records_main_material_id_fkey FOREIGN KEY (main_material_id) REFERENCES public.main_materials(id) ON DELETE CASCADE;


--
-- Name: transaction_records transaction_records_material_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_records
    ADD CONSTRAINT transaction_records_material_id_fkey FOREIGN KEY (material_id) REFERENCES public.materials(id) ON DELETE SET NULL;


--
-- Name: transaction_status_history transaction_status_history_changed_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_status_history
    ADD CONSTRAINT transaction_status_history_changed_by_id_fkey FOREIGN KEY (changed_by_id) REFERENCES public.user_locations(id);


--
-- Name: transaction_status_history transaction_status_history_transaction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transaction_status_history
    ADD CONSTRAINT transaction_status_history_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id) ON DELETE CASCADE;


--
-- Name: transactions transactions_approved_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transactions
    ADD CONSTRAINT transactions_approved_by_id_fkey FOREIGN KEY (approved_by_id) REFERENCES public.user_locations(id);


--
-- Name: transactions transactions_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transactions
    ADD CONSTRAINT transactions_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.user_locations(id);


--
-- Name: transactions transactions_destination_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transactions
    ADD CONSTRAINT transactions_destination_id_fkey FOREIGN KEY (destination_id) REFERENCES public.user_locations(id) ON DELETE SET NULL;


--
-- Name: transactions transactions_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transactions
    ADD CONSTRAINT transactions_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE SET NULL;


--
-- Name: transactions transactions_origin_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transactions
    ADD CONSTRAINT transactions_origin_id_fkey FOREIGN KEY (origin_id) REFERENCES public.user_locations(id) ON DELETE SET NULL;


--
-- Name: transactions transactions_updated_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.transactions
    ADD CONSTRAINT transactions_updated_by_id_fkey FOREIGN KEY (updated_by_id) REFERENCES public.user_locations(id);


--
-- Name: user_activities user_activities_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_activities
    ADD CONSTRAINT user_activities_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.user_locations(id);


--
-- Name: user_activities user_activities_user_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_activities
    ADD CONSTRAINT user_activities_user_location_id_fkey FOREIGN KEY (user_location_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: user_analytics user_analytics_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_analytics
    ADD CONSTRAINT user_analytics_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.user_sessions(id);


--
-- Name: user_analytics user_analytics_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_analytics
    ADD CONSTRAINT user_analytics_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: user_bank user_bank_bank_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_bank
    ADD CONSTRAINT user_bank_bank_id_fkey FOREIGN KEY (bank_id) REFERENCES public.banks(id);


--
-- Name: user_bank user_bank_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_bank
    ADD CONSTRAINT user_bank_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: user_bank user_bank_user_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_bank
    ADD CONSTRAINT user_bank_user_location_id_fkey FOREIGN KEY (user_location_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: user_devices user_devices_user_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_devices
    ADD CONSTRAINT user_devices_user_location_id_fkey FOREIGN KEY (user_location_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: user_input_channels user_input_channels_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_input_channels
    ADD CONSTRAINT user_input_channels_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: user_invitations user_invitations_created_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_invitations
    ADD CONSTRAINT user_invitations_created_user_id_fkey FOREIGN KEY (created_user_id) REFERENCES public.user_locations(id);


--
-- Name: user_invitations user_invitations_intended_organization_role_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_invitations
    ADD CONSTRAINT user_invitations_intended_organization_role_fkey FOREIGN KEY (intended_organization_role) REFERENCES public.organization_roles(id);


--
-- Name: user_invitations user_invitations_invited_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_invitations
    ADD CONSTRAINT user_invitations_invited_by_id_fkey FOREIGN KEY (invited_by_id) REFERENCES public.user_locations(id);


--
-- Name: user_invitations user_invitations_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_invitations
    ADD CONSTRAINT user_invitations_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: user_locations user_locations_auditor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations
    ADD CONSTRAINT user_locations_auditor_id_fkey FOREIGN KEY (auditor_id) REFERENCES public.user_locations(id);


--
-- Name: user_locations user_locations_country_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations
    ADD CONSTRAINT user_locations_country_id_fkey FOREIGN KEY (country_id) REFERENCES public.location_countries(id);


--
-- Name: user_locations user_locations_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations
    ADD CONSTRAINT user_locations_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.user_locations(id);


--
-- Name: user_locations user_locations_currency_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations
    ADD CONSTRAINT user_locations_currency_id_fkey FOREIGN KEY (currency_id) REFERENCES public.currencies(id);


--
-- Name: user_locations user_locations_district_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations
    ADD CONSTRAINT user_locations_district_id_fkey FOREIGN KEY (district_id) REFERENCES public.location_districts(id);


--
-- Name: user_locations user_locations_nationality_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations
    ADD CONSTRAINT user_locations_nationality_id_fkey FOREIGN KEY (nationality_id) REFERENCES public.nationalities(id);


--
-- Name: user_locations user_locations_organization_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations
    ADD CONSTRAINT user_locations_organization_role_id_fkey FOREIGN KEY (organization_role_id) REFERENCES public.organization_roles(id);


--
-- Name: user_locations user_locations_parent_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations
    ADD CONSTRAINT user_locations_parent_location_id_fkey FOREIGN KEY (parent_location_id) REFERENCES public.user_locations(id);


--
-- Name: user_locations user_locations_parent_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations
    ADD CONSTRAINT user_locations_parent_user_id_fkey FOREIGN KEY (parent_user_id) REFERENCES public.user_locations(id);


--
-- Name: user_locations user_locations_phone_code_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations
    ADD CONSTRAINT user_locations_phone_code_id_fkey FOREIGN KEY (phone_code_id) REFERENCES public.phone_number_country_codes(id);


--
-- Name: user_locations user_locations_province_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations
    ADD CONSTRAINT user_locations_province_id_fkey FOREIGN KEY (province_id) REFERENCES public.location_provinces(id);


--
-- Name: user_locations user_locations_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations
    ADD CONSTRAINT user_locations_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.user_roles(id);


--
-- Name: user_locations user_locations_subdistrict_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_locations
    ADD CONSTRAINT user_locations_subdistrict_id_fkey FOREIGN KEY (subdistrict_id) REFERENCES public.location_subdistricts(id);


--
-- Name: user_organization_role_mapping user_organization_role_mapping_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_organization_role_mapping
    ADD CONSTRAINT user_organization_role_mapping_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: user_organization_role_mapping user_organization_role_mapping_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_organization_role_mapping
    ADD CONSTRAINT user_organization_role_mapping_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.organization_roles(id) ON DELETE CASCADE;


--
-- Name: user_organization_roles user_organization_roles_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_organization_roles
    ADD CONSTRAINT user_organization_roles_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--
-- Name: user_organization_roles user_organization_roles_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_organization_roles
    ADD CONSTRAINT user_organization_roles_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.organization_roles(id) ON DELETE CASCADE;


--
-- Name: user_point_balances user_point_balances_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_point_balances
    ADD CONSTRAINT user_point_balances_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: user_preferences user_preferences_user_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT user_preferences_user_location_id_fkey FOREIGN KEY (user_location_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: user_roles user_roles_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_roles
    ADD CONSTRAINT user_roles_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: user_sessions user_sessions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_sessions
    ADD CONSTRAINT user_sessions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: user_subscriptions user_subscriptions_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_subscriptions
    ADD CONSTRAINT user_subscriptions_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);


--
-- Name: user_subscriptions user_subscriptions_user_location_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_subscriptions
    ADD CONSTRAINT user_subscriptions_user_location_id_fkey FOREIGN KEY (user_location_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: user_subusers user_subusers_parent_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_subusers
    ADD CONSTRAINT user_subusers_parent_user_id_fkey FOREIGN KEY (parent_user_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: user_subusers user_subusers_subuser_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_subusers
    ADD CONSTRAINT user_subusers_subuser_id_fkey FOREIGN KEY (subuser_id) REFERENCES public.user_locations(id) ON DELETE CASCADE;


--
-- Name: waste_collections waste_collections_collector_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.waste_collections
    ADD CONSTRAINT waste_collections_collector_id_fkey FOREIGN KEY (collector_id) REFERENCES public.user_locations(id);


--
-- Name: waste_collections waste_collections_transaction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.waste_collections
    ADD CONSTRAINT waste_collections_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);


--
-- Name: waste_processing waste_processing_operator_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.waste_processing
    ADD CONSTRAINT waste_processing_operator_id_fkey FOREIGN KEY (operator_id) REFERENCES public.user_locations(id);


--
-- Name: waste_processing waste_processing_processing_facility_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.waste_processing
    ADD CONSTRAINT waste_processing_processing_facility_id_fkey FOREIGN KEY (processing_facility_id) REFERENCES public.user_locations(id);


--
-- Name: waste_processing waste_processing_supervisor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.waste_processing
    ADD CONSTRAINT waste_processing_supervisor_id_fkey FOREIGN KEY (supervisor_id) REFERENCES public.user_locations(id);


--
-- Name: waste_processing waste_processing_transaction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.waste_processing
    ADD CONSTRAINT waste_processing_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);


--
-- PostgreSQL database dump complete
--

\unrestrict b7MWdqZfZHADxR4nmJhSbOaxismBf1hU2fwR7NoEyb6bCffvzENglk6KP3szeDO

