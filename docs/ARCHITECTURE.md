# Architecture Diagram (Mermaid)

> Phase 1 scope (solid lines) and future phases (dashed lines).

```mermaid
flowchart TB
    subgraph Client["Frontend (Phase 5 — React PWA)"]
        UI[React + Tailwind + shadcn/ui]
    end

    subgraph API["FastAPI Backend"]
        MAIN[main.py<br/>CORS + lifespan + /health]
        INGEST[/api/ingest<br/>POST]
        QUERY[/api/query<br/>stub: Phase 2/]
        PID[/api/pid<br/>stub: Phase 3/]
        VOICE[/api/voice<br/>stub/]
        MAINT[/api/maintenance<br/>stub/]
        COMP[/api/compliance<br/>stub/]
        AUTH[/api/auth<br/>stub/]
    end

    subgraph Core["Core Engine"]
        PARSER[document_parser.py<br/>pdfplumber + OCR fallback]
        EXTRACTOR[entity_extractor.py<br/>Claude tool-use NER]
        GRAPH[knowledge_graph.py<br/>Neo4j MERGE]
        VECTOR[vector_store.py<br/>ChromaDB chunk + embed]
    end

    subgraph Stores["Data Stores"]
        NEO4J[(Neo4j AuraDB<br/>Knowledge Graph)]
        CHROMA[(ChromaDB<br/>Vector store)]
        PG[(PostgreSQL + pgvector<br/>Supabase — later)]
    end

    subgraph External["External Services"]
        CLAUDE[Anthropic Claude API]
        TESS[Tesseract + Poppler<br/>optional OCR]
    end

    UI -.->|HTTPS| INGEST
    UI -.->|HTTPS| QUERY

    MAIN --> INGEST
    MAIN --> QUERY
    MAIN --> PID
    MAIN --> VOICE
    MAIN --> MAINT
    MAIN --> COMP
    MAIN --> AUTH

    INGEST --> PARSER
    PARSER -->|text sparse?| TESS
    PARSER --> EXTRACTOR
    EXTRACTOR -->|tool-use forced call| CLAUDE
    EXTRACTOR --> GRAPH
    EXTRACTOR --> VECTOR

    GRAPH -->|MERGE idempotent| NEO4J
    VECTOR -->|chunk + embed| CHROMA
    PARSER -.->|metadata| PG

    classDef done fill:#d1fae5,stroke:#059669,color:#064e3b;
    classDef future fill:#fef3c7,stroke:#d97706,color:#78350f;
    class INGEST,PARSER,EXTRACTOR,GRAPH,VECTOR,MAIN,NEO4J,CHROMA,CLAUDE done;
    class UI,QUERY,PID,VOICE,MAINT,COMP,AUTH,PG,TESS future;
```

## Phase 1 data flow

```
POST /api/ingest (PDF)
   └─ DocumentParser.parse()        pdfplumber → OCR fallback (graceful)
       └─ EntityExtractor.extract() Claude tool-use → ExtractedEntities
            ├─ KnowledgeGraph.link_entities()   Neo4j  (MERGE, idempotent)
            └─ VectorStore.add_document()       ChromaDB (chunk + embed)
   → IngestionResponse (structured JSON)
```
