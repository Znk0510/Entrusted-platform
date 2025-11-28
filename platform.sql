--
-- PostgreSQL database dump
--

\restrict PthLa7lJ8bySqOffo8G2eGSxgJGo9mmekE3crLbaxOz1T4brBkdC7BUuZ1w6nHP

-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.6

-- Started on 2025-11-29 00:03:05

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
-- TOC entry 856 (class 1247 OID 24584)
-- Name: project_status; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.project_status AS ENUM (
    'open',
    'in_progress',
    'pending_approval',
    'completed',
    'rejected'
);


ALTER TYPE public.project_status OWNER TO postgres;

--
-- TOC entry 853 (class 1247 OID 24578)
-- Name: user_role; Type: TYPE; Schema: public; Owner: postgres
--

CREATE TYPE public.user_role AS ENUM (
    'client',
    'contractor'
);


ALTER TYPE public.user_role OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 224 (class 1259 OID 24653)
-- Name: project_files; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.project_files (
    id integer NOT NULL,
    filename character varying(255) NOT NULL,
    filepath character varying(1024) NOT NULL,
    uploaded_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    project_id integer NOT NULL,
    uploader_id integer NOT NULL
);


ALTER TABLE public.project_files OWNER TO postgres;

--
-- TOC entry 223 (class 1259 OID 24652)
-- Name: project_files_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.project_files_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.project_files_id_seq OWNER TO postgres;

--
-- TOC entry 4954 (class 0 OID 0)
-- Dependencies: 223
-- Name: project_files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.project_files_id_seq OWNED BY public.project_files.id;


--
-- TOC entry 220 (class 1259 OID 24610)
-- Name: projects; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.projects (
    id integer NOT NULL,
    title character varying(255) NOT NULL,
    description text NOT NULL,
    status public.project_status DEFAULT 'open'::public.project_status NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    client_id integer NOT NULL,
    contractor_id integer
);


ALTER TABLE public.projects OWNER TO postgres;

--
-- TOC entry 219 (class 1259 OID 24609)
-- Name: projects_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.projects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.projects_id_seq OWNER TO postgres;

--
-- TOC entry 4955 (class 0 OID 0)
-- Dependencies: 219
-- Name: projects_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.projects_id_seq OWNED BY public.projects.id;


--
-- TOC entry 222 (class 1259 OID 24631)
-- Name: proposals; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.proposals (
    id integer NOT NULL,
    quote numeric(10,2) NOT NULL,
    message text,
    submitted_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    contractor_id integer NOT NULL,
    project_id integer NOT NULL
);


ALTER TABLE public.proposals OWNER TO postgres;

--
-- TOC entry 221 (class 1259 OID 24630)
-- Name: proposals_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.proposals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.proposals_id_seq OWNER TO postgres;

--
-- TOC entry 4956 (class 0 OID 0)
-- Dependencies: 221
-- Name: proposals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.proposals_id_seq OWNED BY public.proposals.id;


--
-- TOC entry 218 (class 1259 OID 24596)
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(100) NOT NULL,
    email character varying(255) NOT NULL,
    hashed_password character varying(255) NOT NULL,
    role public.user_role NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.users OWNER TO postgres;

--
-- TOC entry 217 (class 1259 OID 24595)
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO postgres;

--
-- TOC entry 4957 (class 0 OID 0)
-- Dependencies: 217
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- TOC entry 4770 (class 2604 OID 24656)
-- Name: project_files id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.project_files ALTER COLUMN id SET DEFAULT nextval('public.project_files_id_seq'::regclass);


--
-- TOC entry 4765 (class 2604 OID 24613)
-- Name: projects id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.projects ALTER COLUMN id SET DEFAULT nextval('public.projects_id_seq'::regclass);


--
-- TOC entry 4768 (class 2604 OID 24634)
-- Name: proposals id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.proposals ALTER COLUMN id SET DEFAULT nextval('public.proposals_id_seq'::regclass);


--
-- TOC entry 4763 (class 2604 OID 24599)
-- Name: users id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- TOC entry 4948 (class 0 OID 24653)
-- Dependencies: 224
-- Data for Name: project_files; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.project_files (id, filename, filepath, uploaded_at, project_id, uploader_id) FROM stdin;
1	SAD-第八大組.doc	uploads\\1_4_SAD-第八大組.doc	2025-11-02 17:06:49.480079	1	4
2	ch03_TraditionalSymmetric-KeyCiphers_HungYufurtherreduce.pdf	uploads\\4_2_ch03_TraditionalSymmetric-KeyCiphers_HungYufurtherreduce.pdf	2025-11-07 20:07:59.746348	4	2
3	ch02_04_09_Mathematics of Cryptography_furtherreduced_HungYu-4-104-2-101.pdf	uploads\\4_2_ch02_04_09_Mathematics of Cryptography_furtherreduced_HungYu-4-104-2-101.pdf	2025-11-07 20:08:50.993589	4	2
\.


--
-- TOC entry 4944 (class 0 OID 24610)
-- Dependencies: 220
-- Data for Name: projects; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.projects (id, title, description, status, created_at, client_id, contractor_id) FROM stdin;
2	test03	test03的內容	open	2025-11-02 16:52:57.362917	3	\N
1	測試01	測試01的內容	completed	2025-11-02 16:43:27.294417	1	4
3	123	123	open	2025-11-02 20:24:59.866783	1	\N
4	888	888	completed	2025-11-07 20:03:17.701423	1	2
\.


--
-- TOC entry 4946 (class 0 OID 24631)
-- Dependencies: 222
-- Data for Name: proposals; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.proposals (id, quote, message, submitted_at, contractor_id, project_id) FROM stdin;
1	1000.00		2025-11-02 16:51:22.097461	2	1
2	2000.00		2025-11-02 16:52:17.357983	4	1
3	5000.00		2025-11-07 20:06:33.667968	2	4
\.


--
-- TOC entry 4942 (class 0 OID 24596)
-- Dependencies: 218
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (id, username, email, hashed_password, role, created_at) FROM stdin;
1	test01	test01@example.com	test01	client	2025-11-02 16:39:28.590516
2	test02	test02@example.com	test02	contractor	2025-11-02 16:43:56.2109
3	test03	test03@example.com	test03	client	2025-11-02 16:51:47.011076
4	test04	test04@example.com	test04	contractor	2025-11-02 16:52:01.397959
5	test05	test05@example.com	test05	client	2025-11-07 20:02:05.611534
\.


--
-- TOC entry 4958 (class 0 OID 0)
-- Dependencies: 223
-- Name: project_files_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.project_files_id_seq', 3, true);


--
-- TOC entry 4959 (class 0 OID 0)
-- Dependencies: 219
-- Name: projects_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.projects_id_seq', 4, true);


--
-- TOC entry 4960 (class 0 OID 0)
-- Dependencies: 221
-- Name: proposals_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.proposals_id_seq', 3, true);


--
-- TOC entry 4961 (class 0 OID 0)
-- Dependencies: 217
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.users_id_seq', 5, true);


--
-- TOC entry 4789 (class 2606 OID 24661)
-- Name: project_files project_files_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.project_files
    ADD CONSTRAINT project_files_pkey PRIMARY KEY (id);


--
-- TOC entry 4782 (class 2606 OID 24619)
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- TOC entry 4785 (class 2606 OID 24641)
-- Name: proposals proposals_contractor_id_project_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.proposals
    ADD CONSTRAINT proposals_contractor_id_project_id_key UNIQUE (contractor_id, project_id);


--
-- TOC entry 4787 (class 2606 OID 24639)
-- Name: proposals proposals_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.proposals
    ADD CONSTRAINT proposals_pkey PRIMARY KEY (id);


--
-- TOC entry 4773 (class 2606 OID 24608)
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- TOC entry 4775 (class 2606 OID 24604)
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- TOC entry 4777 (class 2606 OID 24606)
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- TOC entry 4778 (class 1259 OID 24672)
-- Name: idx_projects_client_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_projects_client_id ON public.projects USING btree (client_id);


--
-- TOC entry 4779 (class 1259 OID 24673)
-- Name: idx_projects_contractor_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_projects_contractor_id ON public.projects USING btree (contractor_id);


--
-- TOC entry 4780 (class 1259 OID 24674)
-- Name: idx_projects_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_projects_status ON public.projects USING btree (status);


--
-- TOC entry 4783 (class 1259 OID 24675)
-- Name: idx_proposals_project_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_proposals_project_id ON public.proposals USING btree (project_id);


--
-- TOC entry 4794 (class 2606 OID 24662)
-- Name: project_files project_files_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.project_files
    ADD CONSTRAINT project_files_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


--
-- TOC entry 4795 (class 2606 OID 24667)
-- Name: project_files project_files_uploader_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.project_files
    ADD CONSTRAINT project_files_uploader_id_fkey FOREIGN KEY (uploader_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 4790 (class 2606 OID 24620)
-- Name: projects projects_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 4791 (class 2606 OID 24625)
-- Name: projects projects_contractor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_contractor_id_fkey FOREIGN KEY (contractor_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- TOC entry 4792 (class 2606 OID 24642)
-- Name: proposals proposals_contractor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.proposals
    ADD CONSTRAINT proposals_contractor_id_fkey FOREIGN KEY (contractor_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- TOC entry 4793 (class 2606 OID 24647)
-- Name: proposals proposals_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.proposals
    ADD CONSTRAINT proposals_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id) ON DELETE CASCADE;


-- Completed on 2025-11-29 00:03:05

--
-- PostgreSQL database dump complete
--

\unrestrict PthLa7lJ8bySqOffo8G2eGSxgJGo9mmekE3crLbaxOz1T4brBkdC7BUuZ1w6nHP

